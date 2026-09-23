#!/bin/bash
################################################################################
# Holma - Interaktiver Setup-Wizard für Raspberry Pi
# Einfache, geführte Installation mit Schritt-für-Schritt Anleitung
################################################################################

set -e

# Farben für bessere Lesbarkeit
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# Variablen
INSTALL_DIR="/opt/Holma"
BACKUP_MOUNT="/mnt/backup"
CURRENT_USER="${SUDO_USER:-$USER}"

################################################################################
# Hilfsfunktionen
################################################################################

print_header() {
    echo -e "${CYAN}${BOLD}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                                                                ║"
    echo "║            Holma - Interaktiver Setup-Wizard            ║"
    echo "║                  Raspberry Pi Deployment                       ║"
    echo "║                                                                ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "\n${BLUE}${BOLD}━━━ $1 ━━━${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${CYAN}ℹ $1${NC}"
}

ask_yes_no() {
    local prompt="$1"
    local default="${2:-n}"

    if [ "$default" = "y" ]; then
        prompt="$prompt [Y/n]: "
    else
        prompt="$prompt [y/N]: "
    fi

    read -p "$(echo -e ${YELLOW}${prompt}${NC})" -r response
    response=${response:-$default}

    [[ "$response" =~ ^[Yy]$ ]]
}

ask_input() {
    local prompt="$1"
    local default="$2"

    if [ -n "$default" ]; then
        prompt="$prompt [$default]: "
    else
        prompt="$prompt: "
    fi

    read -p "$(echo -e ${YELLOW}${prompt}${NC})" -r response
    echo "${response:-$default}"
}

check_command() {
    command -v "$1" &> /dev/null
}

################################################################################
# System-Prüfungen
################################################################################

check_system() {
    print_step "Schritt 1/7: System-Prüfung"

    # Check if running on Raspberry Pi
    if grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
        local pi_model=$(grep "Model" /proc/cpuinfo | cut -d: -f2 | xargs)
        print_success "Raspberry Pi erkannt: $pi_model"
    else
        print_warning "Dies scheint kein Raspberry Pi zu sein"
        if ! ask_yes_no "Trotzdem fortfahren?"; then
            exit 1
        fi
    fi

    # Check memory
    local total_mem=$(free -m | awk '/^Mem:/{print $2}')
    print_info "Verfügbarer RAM: ${total_mem}MB"

    if [ "$total_mem" -lt 1500 ]; then
        print_warning "Weniger als 2GB RAM verfügbar. Performance könnte beeinträchtigt sein."
    fi

    # Check disk space
    local available_space=$(df -BG / | awk 'NR==2 {print $4}' | sed 's/G//')
    print_info "Verfügbarer Speicherplatz: ${available_space}GB"

    if [ "$available_space" -lt 5 ]; then
        print_error "Weniger als 5GB Speicherplatz verfügbar!"
        exit 1
    fi

    # Check architecture
    local arch=$(uname -m)
    print_info "Architektur: $arch"

    if [[ ! "$arch" =~ ^(armv7l|aarch64|x86_64)$ ]]; then
        print_warning "Ungetestete Architektur: $arch"
    fi
}

################################################################################
# Abhängigkeiten installieren
################################################################################

install_dependencies() {
    print_step "Schritt 2/7: Abhängigkeiten installieren"

    # Update system
    print_info "System wird aktualisiert..."
    sudo apt update -qq

    if ask_yes_no "System-Upgrade durchführen? (empfohlen, kann einige Minuten dauern)" "y"; then
        sudo apt upgrade -y
        print_success "System-Upgrade abgeschlossen"
    fi

    # Docker
    if check_command docker; then
        local docker_version=$(docker --version | cut -d' ' -f3 | sed 's/,//')
        print_success "Docker bereits installiert: v${docker_version}"
    else
        print_info "Docker wird installiert..."
        curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
        sudo sh /tmp/get-docker.sh
        sudo usermod -aG docker "$CURRENT_USER"
        rm /tmp/get-docker.sh
        print_success "Docker installiert"

        # Set Docker to use less memory on Raspberry Pi
        sudo mkdir -p /etc/docker
        sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  },
  "storage-driver": "overlay2"
}
EOF
        sudo systemctl restart docker || true
    fi

    # Docker Compose
    if docker compose version &> /dev/null; then
        local compose_version=$(docker compose version --short)
        print_success "Docker Compose bereits installiert: v${compose_version}"
    else
        print_info "Docker Compose wird installiert..."
        sudo apt install -y docker-compose-plugin
        print_success "Docker Compose installiert"
    fi

    # Required tools
    print_info "Zusätzliche Tools werden installiert..."
    sudo apt install -y \
        git \
        curl \
        rsync \
        git-lfs \
        openssh-client \
        cifs-utils \
        nfs-common \
        python3-pip \
        > /dev/null 2>&1

    # Install rclone if not present
    if ! check_command rclone; then
        print_info "Rclone wird installiert..."
        curl -s https://rclone.org/install.sh | sudo bash > /dev/null 2>&1
        print_success "Rclone installiert"
    else
        print_success "Rclone bereits installiert"
    fi

    print_success "Alle Abhängigkeiten installiert"
}

################################################################################
# Repository klonen/vorbereiten
################################################################################

setup_repository() {
    print_step "Schritt 3/7: Holma installieren"

    # Check if already in Holma directory
    if [ -f "docker-compose.yml" ] && [ -d "backend" ] && [ -d "frontend" ]; then
        print_info "Holma-Repository bereits vorhanden"
        INSTALL_DIR=$(pwd)
        return
    fi

    # Ask for installation location
    local install_location=$(ask_input "Installationsverzeichnis" "$INSTALL_DIR")
    INSTALL_DIR="$install_location"

    if [ -d "$INSTALL_DIR" ]; then
        if [ "$(ls -A $INSTALL_DIR)" ]; then
            print_warning "Verzeichnis $INSTALL_DIR existiert bereits und ist nicht leer"
            if ask_yes_no "Vorhandenes Verzeichnis verwenden?"; then
                cd "$INSTALL_DIR"
                return
            else
                print_error "Abbruch"
                exit 1
            fi
        fi
    fi

    # Clone or copy repository
    if [ ! -d "$INSTALL_DIR" ]; then
        sudo mkdir -p "$INSTALL_DIR"
        sudo chown "$CURRENT_USER:$CURRENT_USER" "$INSTALL_DIR"
    fi

    # If running from cloned repo, just copy
    if [ -f "$(dirname $0)/../docker-compose.yml" ]; then
        print_info "Kopiere Dateien nach $INSTALL_DIR..."
        cp -r "$(dirname $0)/.." "$INSTALL_DIR/"
        cd "$INSTALL_DIR"
    else
        print_info "Repository wird geklont..."
        local repo_url=$(ask_input "Git Repository URL" "https://github.com/hehljo/Holma.git")
        git clone "$repo_url" "$INSTALL_DIR"
        cd "$INSTALL_DIR"
    fi

    print_success "Holma installiert in: $INSTALL_DIR"
}

################################################################################
# Konfiguration
################################################################################

configure_holma() {
    print_step "Schritt 4/7: Konfiguration"

    # Create directories
    print_info "Erstelle Verzeichnisse..."
    mkdir -p config data logs
    sudo mkdir -p "$BACKUP_MOUNT"
    sudo chown "$CURRENT_USER:$CURRENT_USER" "$BACKUP_MOUNT"

    # .env file
    if [ ! -f ".env" ]; then
        print_info "Erstelle .env Konfigurationsdatei..."
        cp .env.example .env

        # Generate secret key
        local secret_key=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
        sed -i "s|SECRET_KEY=.*|SECRET_KEY=$secret_key|" .env

        # Ask for custom backup path
        local custom_backup_path=$(ask_input "Backup-Mount-Verzeichnis" "$BACKUP_MOUNT")
        if [ "$custom_backup_path" != "$BACKUP_MOUNT" ]; then
            BACKUP_MOUNT="$custom_backup_path"
            sudo mkdir -p "$BACKUP_MOUNT"
            sudo chown "$CURRENT_USER:$CURRENT_USER" "$BACKUP_MOUNT"
            sed -i "s|BACKUP_BASE_PATH=.*|BACKUP_BASE_PATH=$BACKUP_MOUNT|" .env
        fi

        # Ask for max parallel tasks
        local max_tasks=$(ask_input "Maximale parallele Backup-Tasks (1-4)" "2")
        sed -i "s|MAX_PARALLEL_TASKS=.*|MAX_PARALLEL_TASKS=$max_tasks|" .env

        print_success ".env Datei erstellt"
    else
        print_info ".env Datei existiert bereits"
    fi

    # Sources configuration
    if [ ! -f "config/sources.json" ]; then
        print_info "Erstelle Standard-Backup-Quellen-Konfiguration..."
        if [ -f "config/sources-example.json" ]; then
            cp config/sources-example.json config/sources.json
        else
            # Create minimal config
            cat > config/sources.json <<'EOF'
{
  "backup_sources": []
}
EOF
        fi
        print_success "config/sources.json erstellt"
        print_warning "Bitte später Backup-Quellen in config/sources.json konfigurieren"
    fi

    # Rclone configuration
    if [ ! -f "config/rclone.conf" ]; then
        print_info "Erstelle rclone Konfigurationsdatei..."
        if [ -f "config/rclone-example.conf" ]; then
            cp config/rclone-example.conf config/rclone.conf
        else
            touch config/rclone.conf
        fi
        print_success "config/rclone.conf erstellt"
    fi

    # Make scripts executable
    chmod +x scripts/*.sh 2>/dev/null || true

    print_success "Konfiguration abgeschlossen"
}

################################################################################
# Docker Build & Start
################################################################################

build_and_start() {
    print_step "Schritt 5/7: Docker Container bauen und starten"

    print_info "Docker Images werden gebaut (dies kann 10-20 Minuten dauern)..."
    print_warning "Bitte warten Sie, während die Container kompiliert werden..."

    # Build with progress
    if docker compose build --progress=plain 2>&1 | grep -E '(Step|#|FROM|RUN|COPY|WORKDIR)'; then
        print_success "Docker Images erfolgreich gebaut"
    else
        print_error "Fehler beim Bauen der Docker Images"
        exit 1
    fi

    print_info "Container werden gestartet..."
    docker compose up -d

    # Wait for containers to be healthy
    print_info "Warte auf Container-Start..."
    sleep 10

    # Check container status
    if docker compose ps | grep -q "Up"; then
        print_success "Container erfolgreich gestartet"

        # Display container status
        echo -e "\n${BOLD}Container Status:${NC}"
        docker compose ps
    else
        print_error "Container konnten nicht gestartet werden"
        echo -e "\n${BOLD}Logs:${NC}"
        docker compose logs --tail=50
        exit 1
    fi
}

################################################################################
# Systemd Service (Optional)
################################################################################

install_systemd_service() {
    print_step "Schritt 6/7: Automatisches Backup bei USB-Anschluss (Optional)"

    if ! ask_yes_no "Soll Holma automatisch starten wenn eine USB-Festplatte angeschlossen wird?"; then
        print_info "Systemd-Service übersprungen"
        return
    fi

    print_info "Installiere systemd Service und udev Regeln..."

    if [ -f "$INSTALL_DIR/scripts/install-systemd.sh" ]; then
        sudo "$INSTALL_DIR/scripts/install-systemd.sh"
        print_success "Systemd Service installiert"
    else
        print_warning "install-systemd.sh Script nicht gefunden"
    fi
}

################################################################################
# Finalisierung
################################################################################

finalize_setup() {
    print_step "Schritt 7/7: Setup abgeschlossen!"

    # Get IP address
    local ip_address=$(hostname -I | awk '{print $1}')

    # Get admin password from logs
    print_info "Hole Admin-Passwort aus Logs..."
    sleep 2
    local admin_password=$(docker compose logs backend 2>/dev/null | grep -i "initial.*password" | tail -1 | awk '{print $NF}' || echo "Siehe Docker Logs")

    echo -e "\n${GREEN}${BOLD}╔════════════════════════════════════════════════════════════════╗"
    echo "║                   Setup erfolgreich!                           ║"
    echo "╚════════════════════════════════════════════════════════════════╝${NC}"

    echo -e "\n${CYAN}${BOLD}📋 Zugangsdaten:${NC}"
    echo -e "${BOLD}Web-Interface:${NC}  http://$ip_address:3000"
    echo -e "${BOLD}Benutzername:${NC}   admin"
    echo -e "${BOLD}Passwort:${NC}       $admin_password"

    echo -e "\n${CYAN}${BOLD}📁 Wichtige Verzeichnisse:${NC}"
    echo -e "${BOLD}Installation:${NC}   $INSTALL_DIR"
    echo -e "${BOLD}Backup-Mount:${NC}   $BACKUP_MOUNT"
    echo -e "${BOLD}Konfiguration:${NC}  $INSTALL_DIR/config/"
    echo -e "${BOLD}Logs:${NC}           $INSTALL_DIR/logs/"

    echo -e "\n${CYAN}${BOLD}🔧 Nützliche Befehle:${NC}"
    echo -e "${BOLD}Container Status:${NC}      docker compose ps"
    echo -e "${BOLD}Logs ansehen:${NC}          docker compose logs -f"
    echo -e "${BOLD}Container stoppen:${NC}     docker compose stop"
    echo -e "${BOLD}Container starten:${NC}     docker compose start"
    echo -e "${BOLD}Container neu starten:${NC} docker compose restart"

    echo -e "\n${CYAN}${BOLD}📝 Nächste Schritte:${NC}"
    echo -e "1. Öffnen Sie ${BOLD}http://$ip_address:3000${NC} im Browser"
    echo -e "2. Melden Sie sich mit den obigen Zugangsdaten an"
    echo -e "3. Ändern Sie das Admin-Passwort in den Einstellungen"
    echo -e "4. Konfigurieren Sie Ihre Backup-Quellen:"
    echo -e "   ${BOLD}nano $INSTALL_DIR/config/sources.json${NC}"
    echo -e "5. Für Cloud-Storage (Google Drive, Dropbox, etc.):"
    echo -e "   ${BOLD}docker exec -it holma-backend rclone config${NC}"

    echo -e "\n${CYAN}${BOLD}📚 Dokumentation:${NC}"
    echo -e "Vollständige Dokumentation: $INSTALL_DIR/Readme.md"
    echo -e "Backup-Quellen Guide:       $INSTALL_DIR/docs/BACKUP_SOURCES.md"
    echo -e "i18n Dokumentation:         $INSTALL_DIR/docs/i18n.md"

    if [ "$CURRENT_USER" != "$USER" ]; then
        echo -e "\n${YELLOW}${BOLD}⚠ WICHTIG:${NC}"
        echo -e "Bitte loggen Sie sich aus und wieder ein, damit die Docker-Gruppenmitgliedschaft aktiv wird:"
        echo -e "${BOLD}logout${NC}"
    fi

    echo -e "\n${GREEN}Viel Erfolg mit Holma! 🚀${NC}\n"
}

################################################################################
# Main
################################################################################

main() {
    # Check if running as root (we need sudo for some operations)
    if [ "$EUID" -eq 0 ] && [ -z "$SUDO_USER" ]; then
        print_error "Bitte führen Sie dieses Script nicht als root aus."
        print_info "Verwenden Sie: ./setup-wizard.sh"
        print_info "Das Script wird bei Bedarf nach sudo-Passwort fragen."
        exit 1
    fi

    clear
    print_header

    echo -e "${BOLD}Dieser Wizard führt Sie durch die Installation von Holma.${NC}"
    echo -e "Der Prozess dauert ca. 15-25 Minuten (abhängig von Internet-Geschwindigkeit).\n"

    if ! ask_yes_no "Möchten Sie mit der Installation beginnen?" "y"; then
        print_info "Installation abgebrochen"
        exit 0
    fi

    # Execute setup steps
    check_system
    install_dependencies
    setup_repository
    configure_holma
    build_and_start
    install_systemd_service
    finalize_setup
}

# Run main function
main "$@"
