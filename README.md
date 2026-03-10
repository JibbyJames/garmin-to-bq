# Garmin to BigQuery (garmin-to-bq)

This script is designed to extract health and activity data from Garmin Connect and export it. It supports viewing the data in the console, exporting it to CSVs, or uploading it directly to Google BigQuery.

## What is Collected?

### 1. Daily Stats
Extracts summary health metrics for each day:
- **Date**
- **Resting Heart Rate (RHR)**
- **Total Steps**
- **Body Fat %**
- **VO2 Max** (Precise Value)
- **Fitness Age** & **Youth Bonus**
- **Vigorous Minutes** (Average from the last 6 weeks)
- **Sleep Score** & **Average Stress**

### 2. Recent Activities
Extracts individual logged activities (e.g. Strength, Cycling, Running):
- **Start Time** & **Activity Name**
- **Duration (Min)** & **Calories**
- **Average HR** & **Max HR**
- **Moderate / Vigorous Intensity Minutes**
- **HR Zones (1-5)** (Time spent in each zone)

## Prerequisites
- `pip install garminconnect` (required to use the Garmin API)
- `pip install google-cloud-bigquery pandas pyarrow` (required if exporting to BigQuery)

## Usage

You can run the script via the command line to specify custom date ranges and export options. By default, running `python main.py` checks the past 14 days and prints to the console.

**Command Line Arguments:**
- `--start-date YYYY-MM-DD`: The date to start fetching data from.
- `--end-date YYYY-MM-DD`: The date to stop fetching data. (If `--start-date` is provided but this isn't, it defaults to today).
- `--export-csv`: A flag that, if present, enables exporting the console tables into an `exports/` folder with timestamped filenames.
- `--export-bq {overwrite,append}`: Exports data to BigQuery. Requires `BQ_PROJECT` and `BQ_DATASET` environment variables to be set, or updated as constants inside `main.py`.

**Examples:**
```bash
# Fetch data from March 1st to March 5th and print to console
python main.py --start-date 2026-03-01 --end-date 2026-03-05

# Fetch data from March 5th up to today and export it to CSV
python main.py --start-date 2026-03-05 --export-csv

# Overwrite BigQuery tables with data from March 1st
python main.py --start-date 2026-03-01 --export-bq overwrite
```

## Inspiration & References

The extraction logic uses the excellent [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) library. 

Many of the precise metric extractions (like VO2 Max, Sleep Score, HR Zones, and Body Composition) were modeled directly from the library's primary [demo.py file](https://github.com/cyberjunky/python-garminconnect/blob/master/demo.py).
