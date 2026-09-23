# Backend Dockerfile for Holma
FROM python:3.13-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    default-mysql-client \
    git \
    git-lfs \
    gzip \
    lftp \
    openssh-client \
    postgresql-client \
    redis-tools \
    rsync \
    smbclient \
    sshpass \
    tar \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install only Docker's authenticated CLI package. The daemon remains on the
# host and is reached through the explicitly mounted socket.
RUN install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        -o /etc/apt/keyrings/docker.asc \
    && chmod a+r /etc/apt/keyrings/docker.asc \
    && . /etc/os-release \
    && printf 'Types: deb\nURIs: https://download.docker.com/linux/debian\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' \
        "$VERSION_CODENAME" "$(dpkg --print-architecture)" \
        > /etc/apt/sources.list.d/docker.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends docker-ce-cli \
    && rm -rf /var/lib/apt/lists/*

# Install rclone with version pinning and automatic architecture detection
# Using official binary distribution for better security
ARG RCLONE_VERSION=v1.75.0
ARG TARGETARCH
RUN set -x && \
    # Map Docker TARGETARCH to rclone architecture naming
    case "${TARGETARCH}" in \
        amd64) RCLONE_ARCH="amd64" ;; \
        arm64) RCLONE_ARCH="arm64" ;; \
        arm) RCLONE_ARCH="arm" ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}"; exit 1 ;; \
    esac && \
    echo "Installing rclone for architecture: ${RCLONE_ARCH} (Docker: ${TARGETARCH})" && \
    curl -fsSL https://downloads.rclone.org/${RCLONE_VERSION}/rclone-${RCLONE_VERSION}-linux-${RCLONE_ARCH}.zip -o rclone.zip && \
    unzip -q rclone.zip && \
    cp rclone-${RCLONE_VERSION}-linux-${RCLONE_ARCH}/rclone /usr/local/bin/ && \
    chmod +x /usr/local/bin/rclone && \
    rm -rf rclone* && \
    # Unset RCLONE_VERSION to avoid conflict with rclone's environment variables
    unset RCLONE_VERSION && \
    rclone version

# Set working directory
WORKDIR /app

# Copy requirements first (better layer caching)
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ .

# Copy hardware detection script
COPY scripts/detect-hardware.sh /app/scripts/detect-hardware.sh

# Create necessary directories and set permissions
RUN mkdir -p /data /var/log/backupgenie /app/config /app/scripts \
    && chmod +x /app/entrypoint.sh /app/scripts/detect-hardware.sh

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1

# Entrypoint handles hardware detection and starts gunicorn
ENTRYPOINT ["/app/entrypoint.sh"]
