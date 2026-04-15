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

This project includes a fully static progressive web application (PWA) with a retro GameBoy UI that gets deployed to **Firebase Hosting**. The dashboard achieves near-instant load times by fetching aggregated daily statistics directly from a **Cloud Firestore** document cache populated efficiently during the BigQuery sync stage.

### 1. Configure Firebase & Firestore
Before deploying the web application, you must initialize Firebase within your GCP Project:
1. Navigate to the [Firebase Console](https://console.firebase.google.com/) and add your existing GCP project (`james-gcp-project`).
2. Go to **Build > Firestore Database** and click **Create Database** (Select your preferred region).
3. Go to **Build > Authentication**, click **Get Started**, and enable the **Google** sign-in provider.

### 2. Deploy Front-End
From the root directory, ensure you have the `firebase-tools` CLI installed (`npm install -g firebase-tools`), and then deploy the static HTML and Firestore security rules:
```bash
firebase login
firebase use --add james-gcp-project
firebase deploy
```

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
    - Optimise the sync process by uploading only the tables used in the GBQ views currently.

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
