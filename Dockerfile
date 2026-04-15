# Use the official Python image
FROM python:3.11-slim-bullseye

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Install OS dependencies for Chrome and Xvfb
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    xvfb \
    x11-utils \
    libnss3 \
    libgconf-2-4 \
    fontconfig \
    unzip \
    git \
    apt-transport-https \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Google Chrome
RUN wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/googlechrome-linux-keyring.gpg && \
    sh -c 'echo "deb [arch=amd64 signed-by=/usr/share/keyrings/googlechrome-linux-keyring.gpg] http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list' && \
    apt-get update && apt-get install -y google-chrome-stable && rm -rf /var/lib/apt/lists/*

# Install Google Cloud CLI (for gsutil)
RUN wget -qO - https://packages.cloud.google.com/apt/doc/apt-key.gpg | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" | tee -a /etc/apt/sources.list.d/google-cloud-sdk.list && \
    apt-get update && apt-get install -y google-cloud-cli && rm -rf /var/lib/apt/lists/*

# Create a new user
RUN useradd --create-home appuser
WORKDIR /home/appuser/app

# Set up a virtual environment so downloaded drivers can be saved to a mutable, user-owned directory
ENV VIRTUAL_ENV=/home/appuser/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

# Install dependencies (First clone garmin-givemydata to ensure we have latest version and its specific requirements)
RUN git clone https://github.com/nrvim/garmin-givemydata.git givemydata_repo
RUN pip install --no-cache-dir -r givemydata_repo/requirements.txt

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Change ownership of the entire home directory (including venv and app) to appuser
RUN chown -R appuser:appuser /home/appuser

# Switch to the non-root user
USER appuser

# Run the orchestration script on container startup
CMD ["python", "sync_orchestrator.py"]
