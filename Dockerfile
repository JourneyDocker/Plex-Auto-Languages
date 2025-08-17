FROM python:3.13.7-alpine

# Set environment variables
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    CONTAINERIZED=True \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install dependencies and clean up in a single layer to reduce image size
RUN apk --no-cache add curl tini tzdata

# Set up working directory and install Python dependencies
WORKDIR /app

COPY ./requirements.txt /app/requirements.txt

RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . /app/

# Define a mount point for configuration
VOLUME /config

# Healthcheck: First check readiness, then check health
# This way, Docker can detect when the service is ready to start receiving traffic and whether it remains healthy over time.
HEALTHCHECK --interval=30s --timeout=10s --start-period=2m --retries=3 \
  CMD curl --silent --fail http://localhost:9880/ready || exit 1 && \
      curl --silent --fail http://localhost:9880/health || exit 1

# Use tini as the init system to handle zombie processes and signal forwarding
ENTRYPOINT ["/sbin/tini", "--"]

# Define the default command
CMD ["python3", "main.py", "-c", "/config/config.yaml"]
