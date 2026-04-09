# Garmin to BigQuery (garmin-to-bq)

This repository extracts health and activity data from Garmin Connect and exports it to Google BigQuery. 
To bypass advanced Cloudflare bot-mitigation applied by Garmin, this backend relies upon `garmin-givemydata` which utilizes `seleniumbase` and Xvfb for headless stealth extraction.

## What is Collected?

The project runs an automated daily extraction pulling all historical FIT data and synchronizing it into a local SQLite database, before transforming the data into 47 unique CSV tables spanning all Garmin metrics, which are then natively ingested into Google BigQuery. 

## Prerequisites
- Docker (for local testing of the orchestrated job)
- Google Cloud Platform Account
- Google Secret Manager and Google Cloud Storage (for session state persistence)

## Automated Extraction Architecture

The extraction process operates entirely serverless within Google Cloud Platform using a distributed **Cloud Run Job** (`sync_orchestrator.py`).
It is triggered on a daily cadence via **Google Cloud Scheduler**. State (e.g. SQLite database, `.garmin-givemydata` directory, and Cloudflare cookies) is dynamically preserved across serverless executions within Google Cloud Storage.

## Web Application Dashboard

This project runs a separate Flask web application on Google Cloud Run to provide a visual dashboard. It features a retro GameBoy UI, mobile PWA capabilities, and limits viewing access to specific users via Google OAuth.

### 1. Configure Google OAuth credentials
To secure the dashboard, setup OAuth:
1. Navigate to your Google Cloud Console **APIs & Services** > **Credentials**.
2. Click **Create Credentials** > **OAuth client ID** (Web Application).
3. Add an Authorized Redirect URI (e.g., `https://your-cloud-run-url.a.run.app/authorize`).
4. Save the **Client ID** and **Client Secret** into Google Secret Manager as `garmin-google-oauth-client-id` and `garmin-google-oauth-secret`.

***

## Full Deployment Guide

We separate the deployment into two layers: the Web Dashboard (Service), and the Data Extraction (Job). Make sure you are authenticated with `gcloud`.

```bash
export PROJECT_ID="james-gcp-project"
gcloud config set project $PROJECT_ID

# Run the supplied setup script to automatically provision:
# 1. Static NAT IP networking infrastructure
# 2. Cloud Run Service (Web Dashboard Deployment)
# 3. Cloud Storage State Buckets
# 4. Cloud Run Job and Daily Scheduler
chmod +x scripts/setup_gcp_resources.sh
./scripts/setup_gcp_resources.sh
```

### 3. Initial CAPTCHA Auth Bootstrap

Because `garmin-givemydata` utilizes specialized bot-evasion via a headless browser profile, **you must complete the very first login manually from your local machine**. 
To ensure Cloudflare doesn't immediately invalidate the proxy session when it moves to the cloud, your initial local execution MUST route its traffic through the exact same `james-static-ip` created above.

We provide a script to spawn a temporary Compute Engine proxy tunnel for this exact purpose:
```bash
# 1. Run the proxy script to open a local SOCKS5 tunnel
chmod +x scripts/create_vpn_proxy.sh
./scripts/create_vpn_proxy.sh

# 2. Configure Windows to use the proxy (Settings > Network & internet > Proxy > Setup)
# Route Windows traffic to `localhost` Port `1080`.
# (Verify your IP is the static GCP IP at ifconfig.me)

# 3. Run the python extraction script locally!
python sync_orchestrator.py

# 4. The script will pop open a secure browser. Log into Garmin Connect normally.
# Once finished computing (it may take 10 minutes to pull your entire history), the orchestrator automatically uploads your `.garmin-givemydata/` database and session straight to the Google Cloud Bucket we created earlier!

# 5. Disable your Windows Proxy and press Enter to terminate the VPN instance when done.
```

## Inspiration & References

The extraction logic depends entirely on the [garmin-givemydata](https://github.com/nrvim/garmin-givemydata) repository, executing via SeleniumBase.


## TODO

- Data Sync
    - Export logic is missing many fields I require for the web app, so a custom SQLite querying task should be done instead
    - Use the db_inspection.txt to assist with how to query the database
    - Find out where the "vo2max_trend" data is being populated in the database as there doesn't appear to be the same VO2 Max readings anywhere.

- Misc
    - Remove X on main dashboard
    - See if OAuth session duration can be increased (browser cookies?)
    - Show "Last Updated" time/date somewhere
    - Ask Gen AI for features/ideas/improvements

- KPIs
    - Make latest KPIs compared with current average (update SQL required)
    - Add a title to the KPIs page

- Week
    - Remove colon after week activity titles
    - Show "Total %" in week progress
    - Show week progress (based on time of day)

- Charts
    - Create a new charts tab with the KPI metrics on time series graphs
