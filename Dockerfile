FROM budtmo/docker-android:emulator_13.0

# Install Python 3 and pip for batch prompt processing
USER root
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy scripts and config
COPY scripts/ /app/scripts/
COPY prompts/ /app/prompts/
COPY requirements.txt /app/requirements.txt

# Make scripts executable
RUN chmod +x /app/scripts/*.sh

# Install Python dependencies
RUN pip3 install --no-cache-dir -r /app/requirements.txt

# Default environment variables
ENV EMULATOR_DEVICE="Samsung Galaxy S10"
ENV WEB_VNC=true
ENV APPIUM=false
ENV OPENCLAW_APK=/app/openclaw.apk
ENV PROMPTS_FILE=/app/prompts/prompts.txt
ENV OUTPUT_FILE=/app/output/results.json
ENV PROMPT_DELAY=3

ENTRYPOINT ["/app/scripts/run.sh"]
