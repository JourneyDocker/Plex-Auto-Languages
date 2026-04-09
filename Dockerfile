# Stage 0: Base
FROM python:3.14.4-alpine AS base

# Set the working directory
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

# Create a Python virtual environment
RUN python -m venv /opt/venv

# Upgrade pip and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Stage 2: Final
FROM base AS final

# Install runtime system dependencies
RUN apk add --no-cache curl tini tzdata

# Copy the virtual environment and application code from the build stage
COPY --from=build /opt/venv /opt/venv
COPY --from=build /app .

# Define mount points
VOLUME /config

# Set the entrypoint and default command
ENTRYPOINT ["/sbin/tini", "--"]
CMD ["python", "main.py", "-c", "/config/config.yaml"]

# Configure the health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=2m --retries=3 \
  CMD curl --silent --fail http://localhost:9880/ready || exit 1 && \
      curl --silent --fail http://localhost:9880/health || exit 1
