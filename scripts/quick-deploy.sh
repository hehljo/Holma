#!/bin/bash
################################################################################
# Holma Quick Deploy v1.5 - Multi-Architecture Support
# One-Command Installation für schnelles Deployment
################################################################################

set -e

VERSION="1.5"
REPO_URL="${REPO_URL:-https://github.com/hehljo/Holma.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/Holma}"
BRANCH="${BRANCH:-main}"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RED='\033[0;31m'
NC='\033[0m'

# Error handler
error_exit() {
    echo -e "\n${RED}✗ Installation failed at step: $1${NC}"
    echo -e "${YELLOW}Please check the error message above for details.${NC}"
    exit 1
}

trap 'error_exit "Unknown step"' ERR

echo "Starting Quick Deploy..."
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Holma Quick Deploy v${VERSION}         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════╝${NC}\n"

# 1. System Update
echo -e "${YELLOW}[1/6]${NC} System aktualisieren..."
sudo apt update -qq || error_exit "System update (apt update)"
echo -e "${GREEN}  ✓${NC} System update abgeschlossen"

# 2. Docker installieren
echo -e "${YELLOW}[2/6]${NC} Docker installieren..."
if ! command -v docker &> /dev/null; then
    echo -e "  ${YELLOW}→${NC} Docker wird installiert (kann einige Minuten dauern)..."
    curl -fsSL https://get.docker.com | sudo sh > /dev/null || error_exit "Docker installation"
    sudo usermod -aG docker ${SUDO_USER:-$USER}
    echo -e "${GREEN}  ✓${NC} Docker installiert"
else
    echo -e "${GREEN}  ✓${NC} Docker bereits installiert"
fi

if ! docker compose version &> /dev/null; then
    echo -e "  ${YELLOW}→${NC} Docker Compose Plugin wird installiert..."
    sudo apt install -y docker-compose-plugin > /dev/null || error_exit "Docker Compose plugin installation"
    echo -e "${GREEN}  ✓${NC} Docker Compose Plugin installiert"
else
    echo -e "${GREEN}  ✓${NC} Docker Compose bereits installiert"
fi

# 3. Dependencies
echo -e "${YELLOW}[3/6]${NC} Abhängigkeiten installieren..."
echo -e "  ${YELLOW}→${NC} Installiere: git, curl, rsync, cifs-utils, nfs-common, unzip..."
sudo apt install -y git curl rsync cifs-utils nfs-common unzip > /dev/null || error_exit "Package installation (apt install)"
echo -e "${GREEN}  ✓${NC} Basis-Pakete installiert"

# Install rclone
if ! command -v rclone &> /dev/null; then
    echo -e "  ${YELLOW}→${NC} rclone wird installiert..."
    curl -s https://rclone.org/install.sh | sudo bash || error_exit "rclone installation"
    echo -e "${GREEN}  ✓${NC} rclone installiert"
else
    echo -e "${GREEN}  ✓${NC} rclone bereits installiert"
fi

# 4. Repository klonen
echo -e "${YELLOW}[4/6]${NC} Repository klonen..."
if [ -d "$INSTALL_DIR" ]; then
    echo -e "  ${YELLOW}→${NC} Repository existiert bereits, aktualisiere..."
    cd "$INSTALL_DIR"
    git pull origin $BRANCH > /dev/null 2>&1 || true
    echo -e "${GREEN}  ✓${NC} Repository aktualisiert"
else
    echo -e "  ${YELLOW}→${NC} Klone Repository nach $INSTALL_DIR..."
    sudo mkdir -p "$INSTALL_DIR"
    sudo chown ${SUDO_USER:-$USER}:${SUDO_USER:-$USER} "$INSTALL_DIR"
    git clone -b $BRANCH "$REPO_URL" "$INSTALL_DIR" > /dev/null 2>&1
    cd "$INSTALL_DIR"
    echo -e "${GREEN}  ✓${NC} Repository geklont"
fi

# 5. Konfiguration
echo -e "${YELLOW}[5/6]${NC} Konfiguration vorbereiten..."
echo -e "  ${YELLOW}→${NC} Erstelle Verzeichnisse und Konfigurationsdateien..."
mkdir -p config data logs
sudo mkdir -p /mnt/backup
sudo chown ${SUDO_USER:-$USER}:${SUDO_USER:-$USER} /mnt/backup

# .env
if [ ! -f ".env" ]; then
    echo -e "  ${YELLOW}→${NC} Erstelle .env mit zufälligem SECRET_KEY..."
    cp .env.example .env
    SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))' 2>/dev/null || openssl rand -base64 32)
    sed -i "s|SECRET_KEY=.*|SECRET_KEY=$SECRET_KEY|" .env
    echo -e "${GREEN}  ✓${NC} .env Datei erstellt"
else
    echo -e "${GREEN}  ✓${NC} .env bereits vorhanden"
fi

# sources.json
if [ ! -f "config/sources.json" ]; then
    if [ -f "config/sources-example.json" ]; then
        cp config/sources-example.json config/sources.json
    else
        echo '{"backup_sources":[]}' > config/sources.json
    fi
    echo -e "${GREEN}  ✓${NC} sources.json erstellt"
else
    echo -e "${GREEN}  ✓${NC} sources.json bereits vorhanden"
fi

# rclone.conf
if [ ! -f "config/rclone.conf" ]; then
    touch config/rclone.conf
    echo -e "${GREEN}  ✓${NC} rclone.conf erstellt"
else
    echo -e "${GREEN}  ✓${NC} rclone.conf bereits vorhanden"
fi

chmod +x scripts/*.sh 2>/dev/null || true
echo -e "${GREEN}  ✓${NC} Konfiguration abgeschlossen"

# 6. Docker Build & Start
echo -e "${YELLOW}[6/6]${NC} Docker Container starten (dies kann 10-20 Minuten dauern)..."
echo -e "  ${YELLOW}→${NC} Building und Starting Docker Container..."
docker compose up -d --build || error_exit "Docker container build/start"
echo -e "${GREEN}  ✓${NC} Container erfolgreich gestartet"

echo -e "\n${GREEN}╔════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║   Deployment abgeschlossen!                ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════╝${NC}\n"

# Get IP and wait for containers
IP=$(hostname -I | awk '{print $1}')
echo -e "${YELLOW}→${NC} Warte auf Container-Start..."
sleep 5

# Get admin password
ADMIN_PASS=$(docker compose logs backend 2>/dev/null | grep -i "initial.*password" | tail -1 | awk '{print $NF}' || echo "siehe 'docker compose logs backend'")

echo -e "${BLUE}Web-Interface:${NC} http://$IP:3000"
echo -e "${BLUE}Benutzername:${NC}  admin"
echo -e "${BLUE}Passwort:${NC}      $ADMIN_PASS"
echo ""
echo -e "Container Status: ${GREEN}$(docker compose ps --services | wc -l)${NC} Services aktiv"
echo ""
echo -e "${YELLOW}Nächste Schritte:${NC}"
echo "1. Web-Interface öffnen und einloggen"
echo "2. Passwort ändern in Einstellungen"
echo "3. Backup-Quellen konfigurieren: nano $INSTALL_DIR/config/sources.json"
echo "4. Container neu starten: docker compose restart"
echo ""
echo "Logs anzeigen: docker compose logs -f"
echo "Container stoppen: docker compose stop"
echo ""
