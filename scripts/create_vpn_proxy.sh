#!/bin/bash

PROJECT_ID="james-gcp-project"
REGION="europe-west1"
ZONE="${REGION}-b"
INSTANCE_NAME="garmin-auth-proxy"
NETWORK="james-network"
SUBNET="james-subnet"

function clean_up {
    echo ""
    echo "Cleaning up: Deleting temporary instance..."
    gcloud compute instances delete $INSTANCE_NAME --zone=$ZONE --quiet || true
    echo "Cleanup complete."
}

# Ensure the instance is always deleted when the script exits or is interrupted
trap clean_up EXIT

echo "Setting active project to $PROJECT_ID..."
gcloud config set project $PROJECT_ID

echo "1. Checking for temporary Compute Engine instance in $NETWORK..."
# We create this instance WITHOUT an external IP so that its outbound traffic 
# is forced through the Cloud NAT gateway (and your james-static-ip)

if gcloud compute instances describe $INSTANCE_NAME --zone=$ZONE > /dev/null 2>&1; then
    echo "Instance $INSTANCE_NAME already exists. Ensuring it is running..."
    gcloud compute instances start $INSTANCE_NAME --zone=$ZONE --quiet || true
else
    echo "Creating instance $INSTANCE_NAME..."
    gcloud compute instances create $INSTANCE_NAME \
        --zone=$ZONE \
        --machine-type=e2-micro \
        --network=$NETWORK \
        --subnet=$SUBNET \
        --no-address \
        --image-family=debian-11 \
        --image-project=debian-cloud
fi

echo "Waiting for instance to fully boot and SSH keys to propagate (may take up to 30 seconds)..."
sleep 30

echo "2. Opening SOCKS5 Proxy..."
echo "========================================================"
echo "Keep this terminal open! A SOCKS5 proxy will wrap on localhost:1080."
echo "Press Ctrl+C to terminate the proxy and automatically clean up the instance."
echo ""
echo "INSTRUCTIONS:"
echo "1. Configure your local web browser or system proxy to use SOCKS5 on 127.0.0.1:1080"
echo "   (If using Chrome, you can launch it with: chrome.exe --proxy-server="socks5://localhost:1080" --user-data-dir="%temp%\proxy_chrome")"
echo "2. Verify your IP: go to https://ifconfig.me in that browser and verify it matches your GCP James Static IP."
echo "3. Run your initial garmin-givemydata python login script."
echo "4. After successful login (CAPTCHA solved) and extraction finishes, upload your local /browser_profile and /garmin.db to GCS."
echo "========================================================"

# Launch the SSH tunnel with Dynamic Port Forwarding (-D 1080)
# We remove the `-N` flag so that an interactive shell opens, allowing the tunnel to stay alive on Windows PuTTY.
echo "Attempting to create SSH tunnel..."
gcloud compute ssh $INSTANCE_NAME --zone=$ZONE --tunnel-through-iap -- -D 1080 || true

echo ""
echo "========================================================"
echo "If a separate SSH/PuTTY window opened, keep it open until you are finished."
echo "If you saw an error, you may need to wait another minute for GCP SSH keys to sync and run this script again."
echo "========================================================"
read -p "When the sync is complete, press [ENTER] here to close the proxy and delete the instance..."
