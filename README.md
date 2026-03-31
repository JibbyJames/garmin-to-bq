# Garmin to BigQuery (garmin-to-bq)

This script is designed to extract health and activity data from Garmin Connect and export it. It supports viewing the data in the console, exporting it to CSVs, or uploading it directly to Google BigQuery.

## What is Collected?

### 1. Daily Stats
Extracts summary health metrics for each day:
- **Date**
- **Resting Heart Rate (RHR)**
- **Total Steps**
- **Weight (kg)**, **Body Fat %**, & **Muscle Mass (kg)**
- **VO2 Max** (Precise Value)
- **Fitness Age** & **Youth Bonus**
- **Vigorous Minutes** (Average from the last 6 weeks)
- **Sleep Score** & **Average Stress**

### 2. Recent Activities
Extracts individual logged activities (e.g. Strength, Cycling, Running):
- **Start Time** & **Activity Name** (Activity type is also collected)
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
- `--export-bq {overwrite,append}`: Exports data to BigQuery. Requires `BQ_PROJECT` and `BQ_DATASET` constants to be set in `main.py`. **Note**: If `append` is used, any existing records within the chosen date range will be deleted before new records are inserted to prevent duplicates.
- `--skip {daily,activities}`: Skips either daily stats or activities api call
- `--quiet`: Suppresses printing the formatted tables to the console (useful for automated runs).

**Examples:**
```bash
# Fetch data from March 1st to March 5th and print to console
python main.py --start-date 2026-02-01 --end-date 2026-03-25

# Fetch data from March 5th up to today and export it to CSV
python main.py --start-date 2026-03-05 --export-csv

# Overwrite BigQuery tables with data from March 1st
python main.py --start-date 2026-03-01 --export-bq overwrite
```

## Running as a GCP Cloud Function

This script is also configured to run automatically as a Google Cloud Function. When the script detects it is running in a Cloud Function environment (via the `K_SERVICE` or `FUNCTION_TARGET` environment variables), it bypasses all interactive shell prompts and automatically:

1. Retrieves your Garmin credentials from Google Secret Manager (`garmin-email` and `garmin-password`).
2. Retrieves and subsequently saves authentication session tokens to Secret Manager (`garmin-tokens`) to prevent needing a full login and MFA on every execution.
3. Automatically runs yesterday's and today's dates, writing in BigQuery `--append` mode via the `cloud_function_entry` entry point.

Make sure the GCP Service Account executing the function has **Secret Manager Secret Accessor** (to read credentials) and **Secret Manager Secret Version Adder** (to save new tokens) roles.

### Deployment Guide

You can deploy the Cloud Function, Service Account, and Cloud Scheduler Job using the `gcloud` CLI. Ensure you are in the project root containing `main.py` and `requirements.txt`.

```bash
# Set your project ID
export PROJECT_ID="james-gcp-project"
gcloud config set project $PROJECT_ID

# Get the Project Number (required for the Google-managed service agents)
PROJECT_NUMBER=$(gcloud projects describe ${PROJECT_ID} --format="value(projectNumber)")

# 1. Create a dedicated Service Account for Garmin Sync
gcloud iam service-accounts create garmin \
  --display-name="Garmin Sync Service Account"

# 2. Grant Secret Manager access 
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretVersionAdder"

# 3. Grant BigQuery access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# This grants the Google-managed Scheduler service agent permission to create OIDC tokens
gcloud iam service-accounts add-iam-policy-binding \
  "garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --member="serviceAccount:service-${PROJECT_NUMBER}@gcp-sa-cloudscheduler.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountTokenCreator"

# 4. Deploy the 2nd Gen Cloud Function
gcloud functions deploy garmin-to-bq \
  --gen2 \
  --runtime=python313 \
  --region=europe-west1 \
  --source=. \
  --entry-point=cloud_function_entry \
  --trigger-http \
  --no-allow-unauthenticated \
  --service-account="garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --timeout=540s \
  --memory=1024MB

# 5. Grant Invoker permission (Unified Function-level binding)
gcloud functions add-invoker-policy-binding garmin-to-bq \
  --region=europe-west1 \
  --member="serviceAccount:garmin@${PROJECT_ID}.iam.gserviceaccount.com"

# 6. Create (or Update) the Cloud Scheduler Job
FUNCTION_URL=$(gcloud functions describe garmin-to-bq --gen2 --region=europe-west1 --format="value(serviceConfig.uri)")

# Use 'update' if job exists, or 'create' for first time. 
# "0 6 * * *" is once daily at 6AM.
gcloud scheduler jobs update http garmin-to-bq \
  --location=europe-west1 \
  --schedule="0 6 * * *" \
  --time-zone="Europe/London" \
  --uri=$FUNCTION_URL \
  --http-method=POST \
  --oidc-service-account-email="garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --oidc-token-audience=$FUNCTION_URL
```

## Inspiration & References

The extraction logic uses the [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) library. 

Many of the precise metric extractions (like VO2 Max, Sleep Score, HR Zones, and Body Composition) were modeled directly from the library's primary [demo.py file](https://github.com/cyberjunky/python-garminconnect/blob/master/demo.py).
