import argparse
import csv
import sys
import datetime
import logging
import os
import json
import time
import random
import garth
import pandas as pd
import pandas_gbq
import requests

from getpass import getpass
from pathlib import Path
from garminconnect import Garmin
from google.cloud import bigquery
from google.cloud import secretmanager
from google.cloud import firestore
from google.cloud.exceptions import NotFound

# --- BigQuery Configuration ---
BQ_PROJECT = "james-gcp-project"
BQ_DATASET = "garmin"
BQ_DAILY_TABLE = "daily_stats"
BQ_ACTIVITY_TABLE = "activities"

# Check if running as a cloud function
IS_CLOUD_FUNCTION = os.environ.get('K_SERVICE') is not None or os.environ.get('FUNCTION_TARGET') is not None
LOCAL_LOGGING = os.environ.get('FUNCTION_LOCAL_LOGGING') is not None and os.environ.get('FUNCTION_LOCAL_LOGGING') == 'true'

# Define Schemas (used for console grouping, CSV headers, and BQ schema)
DAILY_SCHEMA = [
    bigquery.SchemaField("Date", "DATE", description="The date of the stats"),
    bigquery.SchemaField("RestingHeartRate", "INTEGER", description="Resting heart rate in beats per minute"),
    bigquery.SchemaField("Steps", "INTEGER", description="Total number of steps taken in the day"),
    bigquery.SchemaField("WeightKg", "FLOAT", description="Weight in kilograms"),
    bigquery.SchemaField("BodyFat", "FLOAT", description="Body fat percentage"),
    bigquery.SchemaField("MuscleMassKg", "FLOAT", description="Skeletal muscle mass in kilograms"),
    bigquery.SchemaField("VO2Max", "FLOAT", description="VO2 max estimate"),
    bigquery.SchemaField("FitnessAge", "FLOAT", description="Estimated fitness age"),
    bigquery.SchemaField("YouthBonus", "FLOAT", description="Youth bonus derived from fitness age"),
    bigquery.SchemaField("VigorousMinutesAvg", "FLOAT", description="Average vigorous intensity minutes from last six weeks"),
    bigquery.SchemaField("SleepScore", "INTEGER", description="Garmin sleep score"),
    bigquery.SchemaField("AverageStress", "INTEGER", description="Average daily stress level"),
]

ACTIVITY_SCHEMA = [
    bigquery.SchemaField("StartTime", "DATETIME", description="Start time of the activity"),
    bigquery.SchemaField("ActivityName", "STRING", description="Name of the activity"),
    bigquery.SchemaField("ActivityType", "STRING", description="Type of activity"),
    bigquery.SchemaField("DurationMin", "FLOAT", description="Duration of the activity in minutes"),
    bigquery.SchemaField("Calories", "INTEGER", description="Calories burned during the activity"),
    bigquery.SchemaField("AverageHR", "INTEGER", description="Average heart rate during the activity"),
    bigquery.SchemaField("MaxHR", "INTEGER", description="Maximum heart rate during the activity"),
    bigquery.SchemaField("ModerateIntensityMinutes", "INTEGER", description="Minutes of moderate intensity"),
    bigquery.SchemaField("VigorousIntensityMinutes", "INTEGER", description="Minutes of vigorous intensity"),
    bigquery.SchemaField("Zone1", "TIME", description="Time spent in Warm Up HR Zone (Z1)"),
    bigquery.SchemaField("Zone2", "TIME", description="Time spent in Easy HR Zone (Z2)"),
    bigquery.SchemaField("Zone3", "TIME", description="Time spent in Aerobic HR Zone (Z3)"),
    bigquery.SchemaField("Zone4", "TIME", description="Time spent in Threshold HR Zone (Z4)"),
    bigquery.SchemaField("Zone5", "TIME", description="Time spent in Maximum HR Zone (Z5)"),
]





if IS_CLOUD_FUNCTION and not LOCAL_LOGGING:
    import google.cloud.logging
    client = google.cloud.logging.Client()
    client.setup_logging()
else:
    logging.basicConfig(level=logging.INFO)

logger = logging.getLogger(__name__)

# --- Secret Manager Helpers ---
def get_secret(secret_id, project_id=BQ_PROJECT):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    try:
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as e:
        logger.warning(f"Failed to access secret {secret_id}: {e}")
        return None

def update_secret(secret_id, payload, project_id=BQ_PROJECT):
    client = secretmanager.SecretManagerServiceClient()
    parent = f"projects/{project_id}/secrets/{secret_id}"
    try:
        response = client.add_secret_version(
            request={"parent": parent, "payload": {"data": payload.encode("UTF-8")}}
        )
        logger.info(f"Updated secret {secret_id} to version {response.name}")
    except Exception as e:
        logger.error(f"Failed to update secret {secret_id}: {e}")

# --- Firestore Helpers ---
def get_session_firestore(project_id=BQ_PROJECT):
    try:
        db = firestore.Client(project=project_id)
        doc_ref = db.collection("garmin").document("session")
        doc = doc_ref.get()
        if doc.exists:
            return doc.to_dict()
        return None
    except Exception as e:
        logger.warning(f"Failed to access Firestore session: {e}")
        return None

def save_session_firestore(tokens, project_id=BQ_PROJECT):
    try:
        db = firestore.Client(project=project_id)
        doc_ref = db.collection("garmin").document("session")
        doc_ref.set(tokens)
        logger.info("Updated Firestore session with new tokens")
    except Exception as e:
        logger.error(f"Failed to update Firestore session: {e}")

def init_api():

    """Initialize Garmin API with hydration strategy (Firestore/GCS)."""
    
    garth.configure(domain="garmin.com")
    garth.client.sess.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    })
    
    tokenstore_path = Path("/tmp/.garminconnect" if IS_CLOUD_FUNCTION else "~/.garminconnect").expanduser()
    
    # 1. Check if a session file exists in Firestore (Hydration)
    logger.info("Hydrating session from Firestore...")
    session_data = get_session_firestore()
    
    # 2. Download: If it exists, download it to the /tmp directory
    if session_data:
        tokenstore_path.mkdir(parents=True, exist_ok=True)
        try:
            for filename, content in session_data.items():
                (tokenstore_path / filename).write_text(content)
            logger.info(f"Session hydrated to {tokenstore_path}")
        except Exception as e:
            logger.error(f"Failed to write session files to /tmp: {e}")
            session_data = None # Reset so we don't try to load invalid files

    garmin = None
    if tokenstore_path.exists() and session_data:
        # 3. Initialize: Point the Garmin client to that /tmp file
        logger.info("Initializing Garmin client with hydrated session...")
        try:
            garmin = Garmin()
            garmin.login(str(tokenstore_path))
            
            # 4. Validate: Attempt a light call (e.g., get_full_name())
            logger.info("Validating session with light call (get_full_name)...")
            full_name = garmin.get_full_name()
            logger.info(f"Session valid. User: {full_name}")
            
            # 5. Re-upload: If library updates the session, upload the new version back to Firestore
            # Garth refreshes tokens automatically if expired but still refreshable.
            # We'll re-dump and compare.
            garmin.garth.dump(str(tokenstore_path))
            
            current_tokens = {}
            for filepath in tokenstore_path.iterdir():
                if filepath.is_file():
                    current_tokens[filepath.name] = filepath.read_text()
            
            if current_tokens != session_data:
                logger.info("Tokens updated during initialization/validation. Updating Firestore...")
                save_session_firestore(current_tokens)
            
            return garmin
        except Exception as e:
            logger.warning(f"⚠️ Hydrated session invalid or expired: {e}. Falling back to credentials.")

    # Fallback: Login with credentials from Secrets
    email = get_secret("garmin-email")
    password = get_secret("garmin-password")

    if not IS_CLOUD_FUNCTION:
        if not email:
            email = input("Login email: ")
        if not password:
            password = getpass("Enter password: ")
    
    if not email or not password:
         logger.error("Missing email or password.")
         return None

    try:
        logger.info(f"Attempting manual login for: {email}")
        garmin = Garmin(email, password, is_cn=False, return_on_mfa=True)
        garmin.garth.sess.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"})
        result = garmin.login()

        # Handle MFA
        if result[0] == "needs_mfa":
            if IS_CLOUD_FUNCTION:
                 logger.error("MFA required but running as Cloud Function.")
                 return None
            logger.info("🔐 MFA Required! Check your email/SMS.")
            mfa_code = input("Enter MFA Code: ")
            garmin.resume_login(result[1], mfa_code)
        
        # Save tokens for next time
        tokenstore_path.mkdir(parents=True, exist_ok=True)
        garmin.garth.dump(str(tokenstore_path))
        logger.info(f"Login successful. Tokens saved to {tokenstore_path}")
        
        # Upload new session to Firestore
        current_tokens = {}
        for filepath in tokenstore_path.iterdir():
            if filepath.is_file():
                current_tokens[filepath.name] = filepath.read_text()
        
        save_session_firestore(current_tokens)
            
        return garmin

    except Exception as e:
        logger.error(f"LOGIN FAILED: {e}")
        return None


def main(cmd_args=None):
    parser = argparse.ArgumentParser(description="Fetch Garmin Connect data.")
    parser.add_argument("--start-date", type=str, help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", type=str, help="End date in YYYY-MM-DD format.")
    parser.add_argument("--export-csv", action="store_true", help="Export data to CSV files.")
    parser.add_argument("--export-bq", choices=['overwrite', 'append'], help="Export data to BigQuery")
    parser.add_argument("--skip", choices=['daily', 'activities'], help="Skip either daily stats or activities api")
    parser.add_argument("--quiet", action="store_true", help="Do not print formatted tables to console")
    args = parser.parse_args(cmd_args)

    api = init_api()
    if not api:
        logger.error("Login failed.")
        raise RuntimeError("Login failed.")

    # Setup date range and timestamp
    today = datetime.date.today()
    
    if args.start_date:
        try:
            start_date = datetime.datetime.strptime(args.start_date, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Error: --start-date must be in YYYY-MM-DD format.")
            raise ValueError("Invalid start-date format")
            
        if args.end_date:
            try:
                end_date = datetime.datetime.strptime(args.end_date, "%Y-%m-%d").date()
            except ValueError:
                logger.error("Error: --end-date must be in YYYY-MM-DD format.")
                raise ValueError("Invalid end-date format")
        else:
            end_date = today
            
    elif args.end_date:
        logger.error("Error: Cannot provide --end-date without --start-date.")
        raise ValueError("Cannot provide --end-date without --start-date")
    else:
        end_date = today
        start_date = end_date - datetime.timedelta(days=14)

    if start_date > end_date:
        logger.error("Error: --start-date must be before or equal to --end-date.")
        raise ValueError("--start-date must be before or equal to --end-date")

    delta = end_date - start_date
    date_list = [end_date - datetime.timedelta(days=x) for x in range(delta.days + 1)]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Setup export directory
    if args.export_csv:
        export_dir = Path("exports")
        export_dir.mkdir(exist_ok=True)
        
        daily_csv_path = export_dir / f"daily_stats_{timestamp}.csv"
        activity_csv_path = export_dir / f"activities_{timestamp}.csv"
    
    daily_headers = [field.name for field in DAILY_SCHEMA]
    daily_rows = []
    
    if args.skip != 'daily':
        logger.info(f"Fetching daily stats from {start_date} to {end_date}...")
        
        # Print Header
        if not args.quiet:
            print("--- Daily Stats ---")
            print(f"{'Date':<12} | {'RestingHeartRate':<16} | {'Steps':<6} | {'WeightKg':<8} | {'BodyFat':<8} | {'MuscleMassKg':<12} | {'VO2Max':<8} | {'FitnessAge':<11} | {'YouthBonus':<11} | {'VigorousMinutesAvg':<18} | {'SleepScore':<11} | {'AverageStress':<13}")
            print("-" * 167)

        for check_date in reversed(date_list):
            date_str = check_date.isoformat()
            
            try:
                # Multi-call: Fetch data for the day
                stats = api.get_stats(date_str)
                body = api.get_body_composition(date_str)
                metrics = api.get_max_metrics(date_str)
                fage_data = api.get_fitnessage_data(date_str)
                sleep_data = api.get_sleep_data(date_str)

                # Resting Heart Rate
                rhr = (stats or {}).get('restingHeartRate', '-')
                
                # Body Comp (Fat, Weight, Muscle Mass in grams)
                fat = '-'
                weight = '-'
                muscle = '-'
                if body and isinstance(body, dict):
                    avg = body.get('totalAverage', {})
                    if avg:
                        if avg.get('bodyFat') is not None:
                            fat = avg.get('bodyFat')
                        if avg.get('weight') is not None:
                            weight = round(avg.get('weight') / 1000, 2)
                        if avg.get('muscleMass') is not None:
                            muscle = round(avg.get('muscleMass') / 1000, 2)

                # VO2 Max
                vo2 = '-'
                if metrics and isinstance(metrics, list) and len(metrics) > 0:
                    generic = metrics[0].get('generic', {})
                    if generic and generic.get('vo2MaxPreciseValue') is not None:
                        vo2 = generic.get('vo2MaxPreciseValue')

                # Fitness Age & Chronological Age
                f_age = '-'
                youth_bonus = '-'
                vigorous_avg = '-'
                if fage_data and isinstance(fage_data, dict):
                    c_age_val = fage_data.get('chronologicalAge')
                    f_age_val = fage_data.get('fitnessAge')
                    
                    if f_age_val is not None:
                        f_age = round(f_age_val, 2)
                        
                        # Calculate Youth Bonus (Actual Age - Fitness Age)
                        if c_age_val is not None:
                            youth_bonus = round(c_age_val - f_age_val, 2)

                    # Extract Vigorous Minutes Average
                    components = fage_data.get('components', {})
                    vig_mins = components.get('vigorousMinutesAvg', {}).get('value')
                    if vig_mins is not None:
                        vigorous_avg = vig_mins

                # Sleep Score
                sleep_score = '-'
                if sleep_data and isinstance(sleep_data, dict):
                    daily_sleep = sleep_data.get('dailySleepDTO', {})
                    if daily_sleep and isinstance(daily_sleep, dict):
                        scores = daily_sleep.get('sleepScores', {})
                        if scores and isinstance(scores, dict):
                            overall = scores.get('overall', {})
                            if overall and overall.get('value') is not None:
                                sleep_score = overall.get('value')

                # All-Day Stress
                # stress_data returns a list of dictionaries if present, or dict directly
                avg_stress = '-'
                steps = '-'
                # We can also get average stress directly from the stats summary we already fetched
                if stats and isinstance(stats, dict):
                    if stats.get('averageStressLevel') is not None:
                        avg_stress = stats.get('averageStressLevel')
                    if stats.get('totalSteps') is not None:
                        steps = stats.get('totalSteps')

                # Print the row
                if not args.quiet:
                    print(f"{date_str:<12} | {rhr:<16} | {steps:<6} | {weight:<8} | {fat:<8} | {muscle:<12} | {vo2:<8} | {f_age:<11} | {youth_bonus:<11} | {vigorous_avg:<18} | {sleep_score:<11} | {avg_stress:<13}")
                daily_rows.append([date_str, rhr, steps, weight, fat, muscle, vo2, f_age, youth_bonus, vigorous_avg, sleep_score, avg_stress])

            except Exception as e:
                # This will only catch actual connection errors, not missing data
                if not args.quiet:
                    print(f"{date_str:<12} | CRITICAL ERROR: {e}")
                else:
                    logger.error(f"{date_str:<12} | CRITICAL ERROR: {e}")
                    
        logger.info(f"Fetched {len(daily_rows)} daily stats records.")

        # Write daily CSV
        if args.export_csv:
            with open(daily_csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(daily_headers)
                writer.writerows(daily_rows)
            logger.info(f"Exported daily stats to {daily_csv_path}")

        # Write daily BigQuery
        if args.export_bq and daily_rows:
            try:
                client = bigquery.Client(project=BQ_PROJECT)
                # Create a DataFrame from the rows, mapping to schema names
                df_daily = pd.DataFrame(daily_rows, columns=[field.name for field in DAILY_SCHEMA])
                
                # Convert types to handle '-' gracefully
                df_daily = df_daily.replace('-', pd.NA)
                
                # Convert 'Date' column to standard date objects
                df_daily['Date'] = pd.to_datetime(df_daily['Date']).dt.date
                
                daily_table_id = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_DAILY_TABLE}"
                
                if args.export_bq == 'append':
                    delete_query = f"""
                        DELETE FROM `{daily_table_id}`
                        WHERE Date >= '{date_list[-1].isoformat()}' AND Date <= '{date_list[0].isoformat()}'
                    """
                    try:
                        logger.info(f"Deleting existing records between {date_list[-1].isoformat()} and {date_list[0].isoformat()} before appending...")
                        delete_job = client.query(delete_query)
                        delete_job.result()
                    except NotFound:
                         logger.info("Table does not exist yet. Skipping delete.")
                
                job_config = bigquery.LoadJobConfig(
                    schema=DAILY_SCHEMA,
                    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE if args.export_bq == 'overwrite' else bigquery.WriteDisposition.WRITE_APPEND
                )
                
                logger.info(f"Uploading Daily Stats to BigQuery ({args.export_bq})...")
                job = client.load_table_from_dataframe(df_daily, daily_table_id, job_config=job_config)
                job.result()  # Wait for the job to complete.
                
                # Update table description
                table = client.get_table(daily_table_id)
                table.description = "Daily health and fitness statistics from Garmin Connect"
                client.update_table(table, ["description"])
                
                logger.info(f"Exported daily stats to BigQuery table {daily_table_id}")
            except Exception as e:
                logger.error(f"Failed to export daily stats to BigQuery: {e}")

    if args.skip != 'activities':
        start_date_str = date_list[-1].isoformat()
        end_date_str = date_list[0].isoformat()
        logger.info(f"Fetching activities from {start_date_str} to {end_date_str}...")
        
        if not args.quiet:
            print("\n\n")
            print("--- Recent Activities ---")
            print(f"{'StartTime':<16} | {'ActivityName':<20} | {'ActivityType':<20} | {'DurationMin':<11} | {'Calories':<8} | {'AverageHR':<9} | {'MaxHR':<5} | {'ModerateIntensityMinutes':<24} | {'VigorousIntensityMinutes':<24} | {'Zone1':<8} | {'Zone2':<8} | {'Zone3':<8} | {'Zone4':<8} | {'Zone5':<8}")
            print("-" * 193)

        activity_headers = [field.name for field in ACTIVITY_SCHEMA]
        activity_rows = []

        def format_duration(seconds):
            if not seconds:
                return '-'
            s = int(seconds)
            return f"{s // 3600:02d}:{(s % 3600) // 60:02d}:{s % 60:02d}"

        try:
            activities = api.get_activities_by_date(start_date_str, end_date_str)
            # Garmin returns activities ordered by start time descending usually, but we can reverse just in case
            for activity in reversed(activities):
                start_time = activity.get('startTimeLocal', '')[:16]
                name = activity.get('activityName', '')[:20]
                activity_type = activity.get('activityType', '').get('typeKey', '')[:20]
                
                duration_s = activity.get('duration', 0)
                duration_m = round(duration_s / 60, 1) if duration_s else '-'
                
                cal = round(activity.get('calories', 0)) if activity.get('calories') else '-'
                avg_hr = activity.get('averageHR', '-')
                max_hr = activity.get('maxHR', '-')
                mod_min = activity.get('moderateIntensityMinutes', '-')
                vig_min = activity.get('vigorousIntensityMinutes', '-')
                
                # Garmin provides HR zones in seconds
                z1 = format_duration(activity.get('hrTimeInZone_1'))
                z2 = format_duration(activity.get('hrTimeInZone_2'))
                z3 = format_duration(activity.get('hrTimeInZone_3'))
                z4 = format_duration(activity.get('hrTimeInZone_4'))
                z5 = format_duration(activity.get('hrTimeInZone_5'))
                
                if not args.quiet:
                    print(f"{start_time:<16} | {name:<20} | {activity_type:<20} | {duration_m:<11} | {cal:<8} | {avg_hr:<9} | {max_hr:<5} | {mod_min:<24} | {vig_min:<24} | {z1:<8} | {z2:<8} | {z3:<8} | {z4:<8} | {z5:<8}")
                activity_rows.append([start_time, name, activity_type, duration_m, cal, avg_hr, max_hr, mod_min, vig_min, z1, z2, z3, z4, z5])

        except Exception as e:
             if not args.quiet:
                 print(f"Error fetching activities: {e}")
             else:
                 logger.error(f"Error fetching activities: {e}")
                 
        logger.info(f"Fetched {len(activity_rows)} activities records.")

        # Write activity CSV
        if args.export_csv and activity_rows:
            with open(activity_csv_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(activity_headers)
                writer.writerows(activity_rows)
            logger.info(f"Exported activities to {activity_csv_path}")

        # Write activity BigQuery
        if args.export_bq and activity_rows:
            try:
                client = bigquery.Client(project=BQ_PROJECT)
                df_activity = pd.DataFrame(activity_rows, columns=[field.name for field in ACTIVITY_SCHEMA])
                
                # Convert types to handle '-' gracefully
                df_activity = df_activity.replace('-', pd.NA)
                
                # Activities datetime parsing (Format '2026-03-08 15:59')
                df_activity['StartTime'] = pd.to_datetime(df_activity['StartTime'])
                
                # Handle TIME duration formats (HH:MM:SS) for Zones
                for col in ['Zone1', 'Zone2', 'Zone3', 'Zone4', 'Zone5']:
                     df_activity[col] = pd.to_datetime(df_activity[col], format='%H:%M:%S', errors='coerce').dt.time
                
                activity_table_id = f"{BQ_PROJECT}.{BQ_DATASET}.{BQ_ACTIVITY_TABLE}"
                
                if args.export_bq == 'append':
                    delete_query = f"""
                        DELETE FROM `{activity_table_id}`
                        WHERE DATE(StartTime) >= '{start_date_str}' AND DATE(StartTime) <= '{end_date_str}'
                    """
                    try:
                        logger.info(f"Deleting existing records between {start_date_str} and {end_date_str} before appending...")
                        delete_job = client.query(delete_query)
                        delete_job.result()
                    except NotFound:
                        logger.info("Table does not exist yet. Skipping delete.")
                
                job_config = bigquery.LoadJobConfig(
                    schema=ACTIVITY_SCHEMA,
                    write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE if args.export_bq == 'overwrite' else bigquery.WriteDisposition.WRITE_APPEND
                )
                
                logger.info(f"Uploading Activities to BigQuery ({args.export_bq})...")
                job = client.load_table_from_dataframe(df_activity, activity_table_id, job_config=job_config)
                job.result()
                
                # Update table description
                table = client.get_table(activity_table_id)
                table.description = "Detailed activity records from Garmin Connect"
                client.update_table(table, ["description"])
                
                logger.info(f"Exported activities to BigQuery table {activity_table_id}")
            except Exception as e:
                logger.error(f"Failed to export activities to BigQuery: {e}")

if __name__ == "__main__":
    main()