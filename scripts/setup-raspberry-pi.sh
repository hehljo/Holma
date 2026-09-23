#!/bin/bash
# Holma - Raspberry Pi Setup Script
# Automated setup for Raspberry Pi

set -e

echo "============================================"
echo "Holma - Raspberry Pi Setup"
echo "============================================"
echo ""

# Check if running on Raspberry Pi
if ! grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
    echo "WARNING: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "Updating system..."
sudo apt update && sudo apt upgrade -y

# Install Docker
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
else
    echo "Docker already installed"
fi

# Install Docker Compose
if ! docker compose version &> /dev/null; then
    echo "Installing Docker Compose..."
    sudo apt install docker-compose-plugin -y
else
    echo "Docker Compose already installed"
fi

# Install required tools
echo "Installing required tools..."
sudo apt install -y \
    git \
    curl \
    rsync \
    rclone \
    git-lfs \
    openssh-client \
    cifs-utils \
    nfs-common

# Create backup mount point
echo "Creating backup mount point..."
sudo mkdir -p /mnt/backup
sudo chown $USER:$USER /mnt/backup

# Clone repository (if not already in it)
if [ ! -f "docker-compose.yml" ]; then
    echo "Cloning Holma repository..."
    read -p "Enter repository URL: " REPO_URL
    git clone "$REPO_URL" Holma
    cd Holma
fi

# Create necessary directories
echo "Creating directories..."
mkdir -p config data logs

# Copy example configuration files
echo "Setting up configuration files..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "Created .env file - please edit it with your settings"
fi

if [ ! -f "config/sources.json" ]; then
    cp config/sources-example.json config/sources.json
    echo "Created config/sources.json - please edit it with your backup sources"
fi

if [ ! -f "config/rclone.conf" ]; then
    cp config/rclone-example.conf config/rclone.conf
    echo "Created config/rclone.conf - configure your cloud remotes"
fi

# Set permissions
chmod +x scripts/*.sh

echo ""
echo "============================================"
echo "Setup Complete!"
echo "============================================"
echo ""
echo "Next steps:"
echo ""
echo "1. Edit configuration files:"
echo "   nano .env"
echo "   nano config/sources.json"
echo ""
echo "2. Start Holma:"
echo "   docker compose up -d"
echo ""
echo "3. Check logs:"
echo "   docker compose logs -f"
echo ""
echo "4. Access web interface:"
echo "   http://$(hostname -I | awk '{print $1}'):3000"
echo ""
echo "5. Install systemd service (optional):"
echo "   sudo ./scripts/install-systemd.sh"
echo ""
echo "6. Get initial admin password:"
echo "   docker compose logs backend | grep 'Initial password'"
echo ""
echo ""
echo "NOTE: You may need to logout and login again for Docker group membership to take effect"
echo ""
