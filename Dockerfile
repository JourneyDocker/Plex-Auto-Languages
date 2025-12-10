# Build stage
FROM python:3.14.2-alpine as builder

# Install Python dependencies
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Runtime stage
FROM python:3.14.2-alpine

# Set environment variables
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    CONTAINERIZED=True \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install runtime dependencies
RUN apk update && apk --no-cache --no-scripts add curl tini tzdata

# Set up working directory
WORKDIR /app

# Copy installed Python packages from builder stage
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages

# Copy the application code
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
