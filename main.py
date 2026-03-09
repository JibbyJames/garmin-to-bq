import datetime
import logging
import os

from getpass import getpass
from pathlib import Path
from garminconnect import Garmin



logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_api():
    """Initialize Garmin API with verbose feedback."""
    tokenstore = os.getenv("GARMINTOKENS", "~/.garminconnect")
    tokenstore_path = Path(tokenstore).expanduser()
    
    email = os.getenv("EMAIL")
    password = os.getenv("PASSWORD") # If using a raw string, do: r"your_pass"

    # Try token-based login first
    if tokenstore_path.exists():
        logger.info(f"Checking for tokens in {tokenstore_path}...")
        try:
            garmin = Garmin()
            garmin.login(str(tokenstore_path))
            logger.info("✅ Login successful using stored tokens.")
            return garmin
        except Exception as e:
            logger.warning(f"⚠️ Token login failed: {e}. Falling back to credentials.")

    # Credential-based login
    if not email:
        email = input("Login email: ")
    if not password:
        password = getpass("Enter password: ")

    try:
        logger.info(f"Attempting manual login for: {email}")
        # Note: 'is_cn=False' is for non-China accounts
        garmin = Garmin(email, password, is_cn=False, return_on_mfa=True)
        result = garmin.login()

        # Handle MFA
        if result[0] == "needs_mfa":
            logger.info("🔐 MFA Required! Check your email/SMS.")
            mfa_code = input("Enter MFA Code: ")
            garmin.resume_login(result[1], mfa_code)
        
        # Save tokens for next time
        garmin.garth.dump(str(tokenstore_path))
        logger.info(f"✅ Login successful. Tokens saved to {tokenstore_path}")
        return garmin

    except Exception as e:
        logger.error(f"❌ LOGIN FAILED: {e}")
        return None

def main():
    api = init_api()
    if not api:
        print("Login failed.")
        return

    # Setup date range
    today = datetime.date.today()
    date_list = [today - datetime.timedelta(days=x) for x in range(14)]
    
    # Print Header
    print(f"{'Date':<12} | {'RHR':<5} | {'Body Fat':<8} | {'VO2 Max':<8} | {'Fitness Age':<11} | {'Youth Bonus':<11} | {'Sleep Score':<11} | {'Avg Stress'}")
    print("-" * 110)

    for check_date in reversed(date_list):
        date_str = check_date.isoformat()
        
        try:
            # Multi-call: Fetch data for the day
            stats = api.get_stats(date_str)
            body = api.get_body_composition(date_str)
            metrics = api.get_max_metrics(date_str)
            fage_data = api.get_fitnessage_data(date_str)
            sleep_data = api.get_sleep_data(date_str)

            # --- ROBUST PARSING ---
            rhr = (stats or {}).get('restingHeartRate', '-')
            
            # Body fat
            fat = '-'
            if body and isinstance(body, dict):
                avg = body.get('totalAverage', {})
                if avg and avg.get('bodyFat') is not None:
                    fat = avg.get('bodyFat')

            # VO2 Max
            vo2 = '-'
            if metrics and isinstance(metrics, list) and len(metrics) > 0:
                generic = metrics[0].get('generic', {})
                if generic and generic.get('vo2MaxPreciseValue') is not None:
                    vo2 = generic.get('vo2MaxPreciseValue')

            # Fitness Age & Chronological Age
            f_age = '-'
            youth_bonus = '-'
            if fage_data and isinstance(fage_data, dict):
                c_age_val = fage_data.get('chronologicalAge')
                f_age_val = fage_data.get('fitnessAge')
                
                if f_age_val is not None:
                    f_age = round(f_age_val, 2)
                    
                    # Calculate Youth Bonus (Actual Age - Fitness Age)
                    if c_age_val is not None:
                        youth_bonus = round(c_age_val - f_age_val, 2)

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
            # We can also get average stress directly from the stats summary we already fetched
            if stats and isinstance(stats, dict):
                if stats.get('averageStressLevel') is not None:
                    avg_stress = stats.get('averageStressLevel')

            # Print the row
            print(f"{date_str:<12} | {rhr:<5} | {fat:<8} | {vo2:<8} | {f_age:<11} | {youth_bonus:<11} | {sleep_score:<11} | {avg_stress}")

        except Exception as e:
            # This will only catch actual connection errors, not missing data
            print(f"{date_str:<12} | CRITICAL ERROR: {e}")

if __name__ == "__main__":
    main()