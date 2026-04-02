import os

# Disable werkzeug colors for git bash compatibility (MUST be before flask import)
os.environ["WERKZEUG_COLOR"] = "0"

import datetime
import threading
import logging
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, redirect, url_for, session, render_template, request, jsonify
from authlib.integrations.flask_client import OAuth
from google.cloud import bigquery
import main as garmin_sync

app = Flask(__name__)

# Fetch Google OAuth secrets direct from GCP Secret Manager via main.py (or via ENV block for local testing)
FLASK_SECRET = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)

is_prod = os.environ.get("K_SERVICE") is not None
secret_suffix = "" if is_prod else "-dev"

GOOGLE_CLIENT_ID = garmin_sync.get_secret(f"garmin-google-oauth-client-id{secret_suffix}") 
GOOGLE_CLIENT_SECRET = garmin_sync.get_secret(f"garmin-google-oauth-secret{secret_suffix}")

# Secret key needs to be set for sessions
app.secret_key = FLASK_SECRET

oauth = OAuth(app)
google = oauth.register(
    name='google',
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'}
)

ALLOWED_USER = "jjbuckley.91@gmail.com"

# Logging setup for the background thread
class MemoryLogHandler(logging.Handler):
    def __init__(self, maxlen=200):
        super().__init__()
        self.logs = deque(maxlen=maxlen)
    def emit(self, record):
        self.logs.append(self.format(record))
        
sync_log_handler = MemoryLogHandler()
sync_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
garmin_sync.logger.addHandler(sync_log_handler)

sync_status = {
    "is_running": False,
    "last_run": None,
    "error": None
}

def bg_sync_task():
    global sync_status
    sync_status["is_running"] = True
    sync_status["error"] = None
    sync_log_handler.logs.clear()
    
    garmin_sync.logger.info("Starting Garmin Sync task...")
    try:
        # Check bigquery for latest date
        client = bigquery.Client()
        query = "SELECT MAX(Date) as max_date FROM `james-gcp-project.garmin.daily_stats`"
        job = client.query(query)
        result = list(job.result())
        start_date = result[0].max_date if result and result[0].max_date else (datetime.date.today() - datetime.timedelta(days=14))
        
        today = datetime.date.today()
        
        # We run the command similar to the old cloud_function_entry
        cmd_args = [
            "--start-date", start_date.isoformat(),
            "--end-date", today.isoformat(),
            "--export-bq", "append",
            "--quiet"
        ]
        garmin_sync.main(cmd_args)
        garmin_sync.logger.info("Sync task completed successfully.")
        sync_status["last_run"] = datetime.datetime.now().isoformat()
    except Exception as e:
        garmin_sync.logger.error(f"Sync task failed: {e}")
        sync_status["error"] = str(e)
    finally:
        sync_status["is_running"] = False

@app.before_request
def require_oauth():
    allowed_routes = ['login', 'authorize', 'static']
    if request.endpoint not in allowed_routes and 'user' not in session:
        return redirect(url_for('login'))
    if 'user' in session and session['user'].get('email') != ALLOWED_USER and request.endpoint not in allowed_routes:
        return "Unauthorized Access. Only allowed users can access this service.", 403

@app.route('/login')
def login():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    redirect_uri = url_for('authorize', _external=True)
    if 'X-Forwarded-Proto' in request.headers:
        redirect_uri = redirect_uri.replace('http://', 'https://')
    return google.authorize_redirect(redirect_uri)

@app.route('/authorize')
def authorize():
    token = google.authorize_access_token()
    # With OpenID Connect, userinfo is parsed directly from the ID token
    user_info = token.get('userinfo')
    session['user'] = user_info
    return redirect(url_for('dashboard'))

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if 'user' not in session:
         return render_template('login.html')
    return redirect(url_for('dashboard'))

def fetch_bq_data(query):
    client = bigquery.Client()
    job = client.query(query)
    return [dict(row) for row in job.result()]

@app.route('/dashboard')
def dashboard():
    query_kpis = "SELECT * FROM `james-gcp-project.garmin.health_kpis`"
    query_week = "SELECT * FROM `james-gcp-project.garmin.week_progress` ORDER BY goal_name"
    
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_kpis = executor.submit(fetch_bq_data, query_kpis)
        future_week = executor.submit(fetch_bq_data, query_week)
        
        kpis_data = future_kpis.result()
        week_data = future_week.result()

    return render_template('dashboard.html', kpis_data=kpis_data, week_data=week_data)

@app.route('/sync', methods=['POST'])
def run_sync():
    if not sync_status["is_running"]:
        thread = threading.Thread(target=bg_sync_task)
        thread.start()
        return jsonify({"status": "started"})
    return jsonify({"status": "already_running"})

@app.route('/sync/status')
def get_sync_status():
    return jsonify({
        "is_running": sync_status["is_running"],
        "logs": list(sync_log_handler.logs),
        "last_run": sync_status["last_run"],
        "error": sync_status["error"]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)), debug=True)
