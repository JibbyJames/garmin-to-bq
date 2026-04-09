#!/bin/bash
set -e

PROJECT_ID="james-gcp-project"
REGION="europe-west1"
BUCKET_NAME="${PROJECT_ID}-garmin-state"
SERVICE_ACCOUNT="garmin@${PROJECT_ID}.iam.gserviceaccount.com"

echo "Setting active project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

echo ""
echo "=========================================================="
echo "1. Configuring Static Networking Infrastructure"
echo "=========================================================="
echo "To prevent Garmin/Cloudflare from detecting bot-like activity, we must"
echo "ensure that all our serverless outbound traffic routes through a single, static IP."
echo "If we didn't do this, every Cloud Run execution would use a random Google Datacenter IP,"
echo "instantly invalidating our authorized session cookies."

# Create the VPC
if ! gcloud compute networks describe james-network >/dev/null 2>&1; then
    echo "Creating VPC Network (james-network)..."
    gcloud compute networks create james-network --subnet-mode=custom
else
    echo "VPC Network already exists."
fi

# Create Subnet
if ! gcloud compute networks subnets describe james-subnet --region=$REGION >/dev/null 2>&1; then
    echo "Creating Subnet (james-subnet)..."
    gcloud compute networks subnets create james-subnet \
      --network=james-network \
      --range=10.124.0.0/24 \
      --region=$REGION
else
    echo "Subnet already exists."
fi

# Create Router
if ! gcloud compute routers describe james-router --region=$REGION >/dev/null 2>&1; then
    echo "Creating Cloud Router (james-router)..."
    gcloud compute routers create james-router \
      --network=james-network \
      --region=$REGION
else
    echo "Cloud Router already exists."
fi

# Create Static IP
if ! gcloud compute addresses describe james-static-ip --region=$REGION >/dev/null 2>&1; then
    echo "Reserving Static External IP Address..."
    gcloud compute addresses create james-static-ip \
      --region=$REGION
else
    echo "Static External IP already exists."
fi

# Create NAT
if ! gcloud compute routers nats describe james-nat --router=james-router --region=$REGION >/dev/null 2>&1; then
    echo "Configuring Cloud NAT to explicitly route subnet traffic through our Static IP..."
    gcloud compute routers nats create james-nat \
      --router=james-router \
      --region=$REGION \
      --nat-all-subnet-ip-ranges \
      --nat-external-ip-pool=james-static-ip
else
    echo "Cloud NAT already exists."
fi


echo ""
echo "=========================================================="
echo "2. Deploying Web Application Dashboard"
echo "=========================================================="
echo "We are deploying the interactive retro GameBoy UI as a completely independent"
echo "public-facing Cloud Run Service. It reads directly from BigQuery."

gcloud run deploy garmin-os \
  --source . \
  --region $REGION \
  --service-account "$SERVICE_ACCOUNT" \
  --allow-unauthenticated


echo ""
echo "=========================================================="
echo "3. Creating Cloud Storage State Bucket"
echo "=========================================================="
echo "Cloud Run is natively stateless (files disappear when it shuts down)."
echo "This bucket acts as our persistent hard drive, perpetually storing our"
echo "Garmin SQLite database, historical FIT files, and Cloudflare session cookies."

if ! gsutil ls -p $PROJECT_ID | grep -q "gs://$BUCKET_NAME"; then
    gsutil mb -c STANDARD -l $REGION -b on gs://$BUCKET_NAME/
    echo "Bucket created."
else
    echo "Bucket already exists."
fi

echo "Assigning Storage permissions to our Service Account..."
gcloud storage buckets add-iam-policy-binding gs://$BUCKET_NAME \
    --member="serviceAccount:$SERVICE_ACCOUNT" \
    --role="roles/storage.objectAdmin"


echo ""
echo "=========================================================="
echo "4. Deploying Background Sync Job"
echo "=========================================================="
echo "This provisions the actual Data Extraction Cloud Run Job that executes daily."
echo "We link it explicitly to our VPC via 'Direct VPC Egress' so that it completely"
echo "inherits the static NAT IP address we created earlier."

# Deploy from source using Cloud Build (which overrides the Dockerfile gunicorn entrypoint for the sync job)
gcloud run jobs deploy garmin-sync-job \
    --source . \
    --region="$REGION" \
    --command="python" \
    --args="sync_orchestrator.py" \
    --tasks=1 \
    --max-retries=0 \
    --memory=4Gi \
    --cpu=2 \
    --task-timeout=30m \
    --network="james-network" \
    --subnet="james-subnet" \
    --vpc-egress=all-traffic \
    --service-account="$SERVICE_ACCOUNT"


echo ""
echo "=========================================================="
echo "5. Automating the Pipeline with Cloud Scheduler"
echo "=========================================================="
echo "Scheduling the Sync Job to run autonomously while you sleep."

gcloud services enable cloudscheduler.googleapis.com

if ! gcloud scheduler jobs describe garmin-daily-sync --location=$REGION 2>/dev/null; then
    gcloud scheduler jobs create http garmin-daily-sync \
        --location="$REGION" \
        --schedule="0 3 * * *" \
        --time-zone="Europe/London" \
        --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/garmin-sync-job:run" \
        --http-method="POST" \
        --oauth-service-account-email="$SERVICE_ACCOUNT"
else
    echo "Scheduler job garmin-daily-sync already exists."
fi


echo ""
echo "=========================================================="
echo "6. Opening Firewall for Local Bootstrap VPN"
echo "=========================================================="
echo "To seed the initial secure cookies on your local Windows computer, we need"
echo "an entrypoint into our Virtual Private Cloud. We open an Identity-Aware-Proxy (IAP) SSH tunnel port."

if ! gcloud compute firewall-rules describe allow-ssh-ingress-from-iap >/dev/null 2>&1; then
    gcloud compute firewall-rules create allow-ssh-ingress-from-iap \
        --direction=INGRESS \
        --action=allow \
        --rules=tcp:22 \
        --source-ranges=35.235.240.0/20 \
        --network="james-network"
else
    echo "Firewall rule already exists."
fi

echo ""
echo "=========================================================="
echo "Infrastructure Provisioning Complete!"
echo "Your entire GCP stack is online and ready."
echo "If you haven't yet, run ./scripts/create_vpn_proxy.sh to harvest your session cookies."
