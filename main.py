import argparse
import csv
import sys
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
    parser = argparse.ArgumentParser(description="Fetch Garmin Connect data.")
    parser.add_argument("--start-date", type=str, help="Start date in YYYY-MM-DD format.")
    parser.add_argument("--end-date", type=str, help="End date in YYYY-MM-DD format.")
    parser.add_argument("--export-csv", action="store_true", help="Export data to CSV files.")
    args = parser.parse_args()

    api = init_api()
    if not api:
        print("Login failed.")
        sys.exit(1)

    # Setup date range and timestamp
    today = datetime.date.today()
    
    if args.start_date:
        try:
            start_date = datetime.datetime.strptime(args.start_date, "%Y-%m-%d").date()
        except ValueError:
            print("Error: --start-date must be in YYYY-MM-DD format.")
            sys.exit(1)
            
        if args.end_date:
            try:
                end_date = datetime.datetime.strptime(args.end_date, "%Y-%m-%d").date()
            except ValueError:
                print("Error: --end-date must be in YYYY-MM-DD format.")
                sys.exit(1)
        else:
            end_date = today
            
    elif args.end_date:
        print("Error: Cannot provide --end-date without --start-date.")
        sys.exit(1)
    else:
        end_date = today
        start_date = end_date - datetime.timedelta(days=14)

    if start_date > end_date:
        print("Error: --start-date must be before or equal to --end-date.")
        sys.exit(1)

    delta = end_date - start_date
    date_list = [end_date - datetime.timedelta(days=x) for x in range(delta.days + 1)]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Setup export directory
    if args.export_csv:
        export_dir = Path("exports")
        export_dir.mkdir(exist_ok=True)
        
        daily_csv_path = export_dir / f"daily_stats_{timestamp}.csv"
        activity_csv_path = export_dir / f"activities_{timestamp}.csv"
    
    daily_headers = ['Date', 'RHR', 'Steps', 'Body Fat', 'VO2 Max', 'Fitness Age', 'Youth Bonus', 'Vigorous Avg', 'Sleep Score', 'Avg Stress']
    daily_rows = []
    
    # Print Header
    print(f"{'Date':<12} | {'RHR':<5} | {'Steps':<6} | {'Body Fat':<8} | {'VO2 Max':<8} | {'Fitness Age':<11} | {'Youth Bonus':<11} | {'Vigorous Avg':<12} | {'Sleep Score':<11} | {'Avg Stress'}")
    print("-" * 135)

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
            print(f"{date_str:<12} | {rhr:<5} | {steps:<6} | {fat:<8} | {vo2:<8} | {f_age:<11} | {youth_bonus:<11} | {vigorous_avg:<12} | {sleep_score:<11} | {avg_stress}")
            daily_rows.append([date_str, rhr, steps, fat, vo2, f_age, youth_bonus, vigorous_avg, sleep_score, avg_stress])

        except Exception as e:
            # This will only catch actual connection errors, not missing data
            print(f"{date_str:<12} | CRITICAL ERROR: {e}")

    # Write daily CSV
    if args.export_csv:
        with open(daily_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(daily_headers)
            writer.writerows(daily_rows)
        print(f"\n✅ Exported daily stats to {daily_csv_path}")

    print("\n\n")
    print("👟 Recent Activities")
    print(f"{'Datum/Time':<20} | {'Activity':<20} | {'Dur(m)':<6} | {'Cal':<5} | {'AvgHR':<5} | {'MaxHR':<5} | {'ModMin':<6} | {'VigMin':<6} | {'Z1':<8} | {'Z2':<8} | {'Z3':<8} | {'Z4':<8} | {'Z5':<8}")
    print("-" * 145)

    activity_headers = ['Datum/Time', 'Activity', 'Dur(m)', 'Cal', 'AvgHR', 'MaxHR', 'ModMin', 'VigMin', 'Z1', 'Z2', 'Z3', 'Z4', 'Z5']
    activity_rows = []

    start_date_str = date_list[-1].isoformat()
    end_date_str = date_list[0].isoformat()

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
            
            print(f"{start_time:<20} | {name:<20} | {duration_m:<6} | {cal:<5} | {avg_hr:<5} | {max_hr:<5} | {mod_min:<6} | {vig_min:<6} | {z1:<8} | {z2:<8} | {z3:<8} | {z4:<8} | {z5:<8}")
            activity_rows.append([start_time, name, duration_m, cal, avg_hr, max_hr, mod_min, vig_min, z1, z2, z3, z4, z5])

    except Exception as e:
         print(f"Error fetching activities: {e}")

    # Write activity CSV
    if args.export_csv and activity_rows:
        with open(activity_csv_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(activity_headers)
            writer.writerows(activity_rows)
        print(f"✅ Exported activities to {activity_csv_path}")

if __name__ == "__main__":
    main()