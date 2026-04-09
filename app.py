import os

# Disable werkzeug colors for git bash compatibility (MUST be before flask import)
os.environ["WERKZEUG_COLOR"] = "0"

from flask import Flask, redirect, url_for, session, render_template, request, jsonify
from authlib.integrations.flask_client import OAuth
from google.cloud import bigquery
from google.cloud import secretmanager
from google.cloud.exceptions import NotFound
from concurrent.futures import ThreadPoolExecutor

app = Flask(__name__)

BQ_PROJECT = "james-gcp-project"

def get_secret(secret_id, project_id=BQ_PROJECT):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    try:
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        print(f"Failed to access secret {secret_id}: {e}")
        return None

# Fetch Google OAuth secrets direct from GCP Secret Manager via env or API
FLASK_SECRET = os.environ.get("FLASK_SECRET_KEY") or os.urandom(24)
is_prod = os.environ.get("K_SERVICE") is not None
secret_suffix = "" if is_prod else "-dev"

GOOGLE_CLIENT_ID = get_secret(f"garmin-google-oauth-client-id{secret_suffix}") 
GOOGLE_CLIENT_SECRET = get_secret(f"garmin-google-oauth-secret{secret_suffix}")

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
    # Utilizing the new schemas based on garmin-givemydata
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
    # Sync is now handled autonomously via a Cloud Scheduler triggering the Cloud Run Job.
    return jsonify({
        "status": "info",
        "message": "Manual sync via the UI is disabled. The Cloud Run Sync Job executes daily via Cloud Scheduler."
    })

@app.route('/sync/status')
def get_sync_status():
    return jsonify({
        "is_running": False,
        "logs": ["Sync runs asynchronously via Cloud Run Jobs."],
        "last_run": "See GCP Cloud Scheduler",
        "error": None
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)), debug=True)
