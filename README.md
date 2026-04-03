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

## Running as a Cloud Run Web Application

This project has been refactored to run as a full Flask web application hosted on Google Cloud Run. It features a retro GameBoy UI, mobile PWA capabilities, restricted access via Google OAuth, and manual execution triggers directly from the UI.

### 1. Configure Google OAuth credentials

Before deploying, you must create OAuth credentials for the application to authenticate users:

1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Navigate to **APIs & Services** > **Credentials**.
3. Click **Create Credentials** > **OAuth client ID**.
4. Set Application Type to **Web application**.
5. Add an Authorized Redirect URI. E.g. `https://your-cloud-run-url.a.run.app/authorize`.
6. Copy the **Client ID** and **Client Secret**. Provide these as environment variables during deployment (or save them into Google Secret Manager natively).

### 2. Testing Locally

To test the application locally:
1. Make sure you have created the `-dev` suffixed secrets in Secret Manager (`garmin-google-oauth-client-id-dev` and `garmin-google-oauth-client-secret-dev`).
2. Add `http://127.0.0.1:5000/authorize` to your Google OAuth Authorized Redirect URIs.
3. Authenticate your local terminal with GCP via `gcloud auth application-default login`.
4. Allow local HTTP OAuth testing by exporting the insecure transport flag: `export OAUTHLIB_INSECURE_TRANSPORT="1"`.
5. Run the server using `flask run --host=127.0.0.1 --port=5000`.

### 3. Deployment Guide

You can deploy the Cloud Run Web App and the associated Service Account using the `gcloud` CLI. Ensure you are in the project root containing `Dockerfile`.

```bash
# Set your project ID
export PROJECT_ID="james-gcp-project"
gcloud config set project $PROJECT_ID

# 1. Create a dedicated Service Account for Garmin Sync
gcloud iam service-accounts create garmin \
  --display-name="Garmin Sync Service Account"

# 2. Enable Firestore and create database (required for session hydration)
# This creates the '(default)' database used by the application
gcloud services enable firestore.googleapis.com
gcloud firestore databases create --location=europe-west1

# 3. Grant required permissions to the Service Account
# roles/datastore.user provides access to the '(default)' Firestore database
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/datastore.user"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretVersionAdder"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.dataEditor"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/bigquery.jobUser"

# Make sure you have created the following secrets in Google Secret Manager beforehand:
# 1. garmin-google-oauth-client-id (from OAuth setup)
# 2. garmin-google-oauth-secret (from OAuth setup)
# 3. garmin-email (Your Garmin Connect email)
# 4. garmin-password (Your Garmin Connect password)

gcloud run deploy garmin-os \
  --source . \
  --region europe-west1 \
  --service-account "garmin@${PROJECT_ID}.iam.gserviceaccount.com" \
  --allow-unauthenticated

# 5. Make sure you update the Authorized redirect URIs in the Google Cloud Console with the newly generated Cloud Run URL!
```

## Inspiration & References

The extraction logic uses the [python-garminconnect](https://github.com/cyberjunky/python-garminconnect) library. 

Many of the precise metric extractions (like VO2 Max, Sleep Score, HR Zones, and Body Composition) were modeled directly from the library's primary [demo.py file](https://github.com/cyberjunky/python-garminconnect/blob/master/demo.py).
