import os
import sys
import subprocess
import logging
import argparse
from google.cloud import storage, bigquery
import glob
import pandas as pd

BQ_PROJECT = "james-gcp-project"
BQ_DATASET = "garmin"
BUCKET_NAME = f"{BQ_PROJECT}-garmin-state"
WORKSPACE_DIR = os.path.expanduser("~/.garmin-givemydata")

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def pull_state_from_gcs():
    logger.info(f"Connecting to GCS bucket {BUCKET_NAME} for state pull...")
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    cmd = f'gsutil -m rsync -x ".*Singleton.*" -r gs://{BUCKET_NAME} {WORKSPACE_DIR}'
    
    try:
        subprocess.run(cmd, shell=True, check=True)
        logger.info("State successfully pulled into local workspace.")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to pull state from GCS (Assuming first run): {e}")
        return False

def push_state_to_gcs():
    logger.info(f"Pushing updated state back to GCS bucket {BUCKET_NAME}...")
    
    # Preemptively delete specific chrome lock files which are often broken symlinks
    for f in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
        try:
            os.unlink(os.path.join(WORKSPACE_DIR, "browser_profile", f))
        except Exception:
            pass

    cmd = f'gsutil -m rsync -x ".*Singleton.*" -r -d {WORKSPACE_DIR} gs://{BUCKET_NAME}'
    try:
        subprocess.run(cmd, shell=True, check=True)
        logger.info("State successfully synced back to GCS.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to push state back to GCS: {e}")
        raise

def ingest_to_bigquery(bq_staging_dir):
    logger.info("Starting BigQuery ingestion for generated CSV files...")
    client = bigquery.Client(project=BQ_PROJECT)
    
    csv_files = glob.glob(os.path.join(bq_staging_dir, "*.csv"))
    if not csv_files:
        logger.warning(f"No CSV files found in {bq_staging_dir}")
        return

    for csv_file in csv_files:
        filename = os.path.basename(csv_file)
        table_name = os.path.splitext(filename)[0]
        full_table_id = f"{BQ_PROJECT}.{BQ_DATASET}.{table_name}"
        
        logger.info(f"Ingesting {filename} into {full_table_id}...")
        
        df = pd.read_csv(csv_file)
        
        job_config = bigquery.LoadJobConfig(
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
            autodetect=True,
            skip_leading_rows=1
        )
        job_config.column_name_character_map = "V2"
        
        with open(csv_file, "rb") as source_file:
            job = client.load_table_from_file(source_file, full_table_id, job_config=job_config)
            
        try:
            job.result()
            logger.info(f"Successfully truncated and loaded {job.output_rows} rows into {full_table_id}")
        except Exception as e:
            logger.error(f"Error loading {csv_file}: {e}")
            raise

def main():
    parser = argparse.ArgumentParser(description="Garmin Background Sync Orchestrator")
    parser.add_argument("--skip-pull", action="store_true", help="Disable the initial pull of state from GCS")
    args = parser.parse_args()

    logger.info("=== Starting Garmin Background Sync Orchestrator ===")
    os.makedirs(WORKSPACE_DIR, exist_ok=True)
    
    # 1. Pull current state (browser profile, existing SQLite db, .env)
    if not args.skip_pull:
        pull_state_from_gcs()
    else:
        logger.info("Skipping initial state pull from GCS due to --skip-pull argument.")

    # Determine paths based on where givemydata repo is evaluated
    givemydata_entry = os.path.abspath("./garmin_givemydata_repo/garmin_givemydata.py")
    if not os.path.exists(givemydata_entry):
        logger.warning(f"Cannot find extraction handler at {givemydata_entry}. Attempting to clone repository...")
        try:
            # -b dev tells git to clone and switch to the 'dev' branch
            # The URL now points to your personal fork
            subprocess.run("git clone -b dev https://github.com/JibbyJames/garmin-givemydata.git garmin_givemydata_repo", shell=True, check=True)
            
            # Givemydata has specific dependencies we should probably ensure exist locally
            subprocess.run("pip install -r garmin_givemydata_repo/requirements.txt", shell=True, check=True)
        except Exception as e:
            logger.error(f"Failed to clone repository or install dependencies: {e}")
            return

    # 2. Extract Data using virtual framebuffer for selenium bypassing (only on Linux server)
    if os.name == 'nt':
        logger.info("Running on Windows. Omitting xvfb-run (Native GUI will open for CAPTCHA solving).")
        extract_cmd = ["python", givemydata_entry]
    else:
        logger.info("Invoking xvfb-run for secure headless garmin-givemydata extraction...")
        extract_cmd = ["xvfb-run", "--auto-servernum", "python", givemydata_entry]
    
    try:
        # Run extraction
        subprocess.run(extract_cmd, check=True, cwd=WORKSPACE_DIR)
        
        # 3. Export data to CSV
        bq_staging_dir = os.path.join(WORKSPACE_DIR, "bq_staging")
        os.makedirs(bq_staging_dir, exist_ok=True)
        
        logger.info("Invoking data transformation to BQ staging (CSV exclusively)...")
        from pathlib import Path
        repo_path = os.path.abspath("./garmin_givemydata_repo")
        if repo_path not in sys.path:
            sys.path.insert(0, repo_path)
            
        from garmin_mcp.export import export_csv
        export_csv(Path(bq_staging_dir))
               
        # 4. Ingest to BigQuery
        ingest_to_bigquery(bq_staging_dir)
        
        # 5. Push Updated state back to GCS ONLY if BigQuery load was fully successful
        push_state_to_gcs()
        
        logger.info("=== Sync Completed Successfully ===")
        
    except Exception as e:
        logger.error(f"Sync process encountered a fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
