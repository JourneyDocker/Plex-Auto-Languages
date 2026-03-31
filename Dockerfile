# Stage 0: Base
FROM python:3.14.3-alpine AS base

# Set working directory
WORKDIR /app

# Set environment variables
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    CONTAINERIZED=True \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

# Stage 1: Build
FROM base AS build

# Create a virtual environment
RUN python -m venv /opt/venv

# Install Python dependencies
COPY ./requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r /tmp/requirements.txt

# Copy the application code
COPY . .

# Stage 2: Final
FROM base AS final

# Install runtime dependencies
RUN apk add --no-cache curl tini tzdata

# Copy the virtual environment and the application code from the build stage
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app .

# Define a mount point for configuration
VOLUME /config

# Use tini as the init system to handle zombie processes and signal forwarding
ENTRYPOINT ["/sbin/tini", "--"]

# Define the default command
CMD ["python", "main.py", "-c", "/config/config.yaml"]

# Healthcheck: First check readiness, then check health
# This way, Docker can detect when the service is ready to start receiving traffic and whether it remains healthy over time.
HEALTHCHECK --interval=30s --timeout=10s --start-period=2m --retries=3 \
  CMD curl --silent --fail http://localhost:9880/ready || exit 1 && \
      curl --silent --fail http://localhost:9880/health || exit 1
