#!/usr/bin/env bash
# ============================================================================
# BackupGenie - Universal Cross-Platform Installer
# Supports: macOS, Windows (WSL2/Git Bash), Linux (Debian/Ubuntu/Raspberry Pi)
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/hehljo/BackupGenie/main/install.sh | bash
#   or: ./install.sh
#   or: ./install.sh --webui    (launches browser-based setup wizard)
# ============================================================================

set -euo pipefail

# --- Configuration ---
REPO_URL="${REPO_URL:-https://github.com/hehljo/BackupGenie.git}"
BRANCH="${BRANCH:-main}"
DEFAULT_PORT="${SETUP_PORT:-8888}"

# --- Colors ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Helpers ---
log_info()    { echo -e "${GREEN}[✓]${NC} $*"; }
log_warn()    { echo -e "${YELLOW}[⚠]${NC} $*"; }
log_error()   { echo -e "${RED}[✗]${NC} $*"; }
log_step()    { echo -e "\n${BLUE}${BOLD}━━━ $* ━━━${NC}\n"; }

banner() {
    echo -e "${CYAN}${BOLD}"
    cat << 'EOF'
    ____             __                ______           _
   / __ )____ ______/ /____  ______  / ____/__  ____  (_)__
  / __  / __ `/ ___/ //_/ / / / __ \/ / __/ _ \/ __ \/ / _ \
 / /_/ / /_/ / /__/ ,< / /_/ / /_/ / /_/ /  __/ / / / /  __/
/_____/\__,_/\___/_/|_|\__,_/ .___/\____/\___/_/ /_/_/\___/
                           /_/
    Universal Installer v1.3.0 (Feb 2026)
EOF
    echo -e "${NC}"
}

# --- Platform Detection ---
detect_platform() {
    local os="" arch="" variant=""

    case "$(uname -s)" in
        Darwin*)  os="macos" ;;
        Linux*)
            if grep -q "Microsoft\|WSL" /proc/version 2>/dev/null; then
                os="wsl"
            elif grep -q "Raspberry Pi" /proc/cpuinfo 2>/dev/null; then
                os="raspberrypi"
                variant=$(grep "Model" /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo "unknown")
            else
                os="linux"
            fi
            ;;
        MINGW*|MSYS*|CYGWIN*)
            os="windows-git-bash"
            ;;
        *)
            os="unknown"
            ;;
    esac

    case "$(uname -m)" in
        x86_64|amd64)   arch="amd64" ;;
        aarch64|arm64)  arch="arm64" ;;
        armv7l|armhf)   arch="arm" ;;
        *)              arch="$(uname -m)" ;;
    esac

    echo "$os|$arch|$variant"
}

# --- Dependency Checks ---
check_docker() {
    if command -v docker &>/dev/null; then
        local ver
        ver=$(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
        log_info "Docker found: v$ver"
        return 0
    fi
    return 1
}

check_docker_compose() {
    if docker compose version &>/dev/null 2>&1; then
        log_info "Docker Compose found: $(docker compose version --short 2>/dev/null)"
        return 0
    fi
    return 1
}

check_git() {
    if command -v git &>/dev/null; then
        log_info "Git found: $(git --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
        return 0
    fi
    return 1
}

# --- Platform-Specific Install ---
install_docker_macos() {
    log_step "Installing Docker Desktop for macOS"

    if check_docker; then
        return 0
    fi

    # Check for Homebrew
    if command -v brew &>/dev/null; then
        log_info "Installing Docker Desktop via Homebrew..."
        brew install --cask docker
        log_warn "Please start Docker Desktop from Applications and wait for it to initialize."
        log_warn "Then re-run this installer."
        echo ""
        read -rp "Press Enter once Docker Desktop is running..."
    else
        echo ""
        log_warn "Docker Desktop is required but not installed."
        echo "  Option 1: Install Homebrew first:"
        echo "    /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        echo "    brew install --cask docker"
        echo ""
        echo "  Option 2: Download Docker Desktop manually:"
        echo "    https://www.docker.com/products/docker-desktop/"
        echo ""
        read -rp "Press Enter once Docker is installed and running..."
    fi

    if ! check_docker; then
        log_error "Docker still not available. Please install Docker Desktop first."
        exit 1
    fi
}

install_docker_linux() {
    log_step "Installing Docker for Linux"

    if check_docker; then
        return 0
    fi

    log_info "Installing Docker via official script..."
    curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
    sudo sh /tmp/get-docker.sh
    sudo usermod -aG docker "${SUDO_USER:-$USER}"
    rm -f /tmp/get-docker.sh

    # Configure Docker for low-memory systems
    sudo mkdir -p /etc/docker
    sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" },
  "storage-driver": "overlay2"
}
EOF
    sudo systemctl enable docker
    sudo systemctl restart docker
    log_info "Docker installed successfully"

    # Docker Compose
    if ! check_docker_compose; then
        log_info "Installing Docker Compose plugin..."
        sudo apt-get install -y docker-compose-plugin 2>/dev/null || true
    fi
}

install_docker_wsl() {
    log_step "Docker Setup for WSL2"

    if check_docker; then
        return 0
    fi

    echo ""
    log_warn "Docker Desktop for Windows is required for WSL2."
    echo "  1. Download from: https://www.docker.com/products/docker-desktop/"
    echo "  2. Install Docker Desktop"
    echo "  3. Enable 'Use the WSL 2 based engine' in Docker Desktop settings"
    echo "  4. Enable WSL integration for your distro in Docker Desktop settings"
    echo ""
    read -rp "Press Enter once Docker Desktop is running with WSL2 integration..."

    if ! check_docker; then
        log_error "Docker not available in WSL. Check Docker Desktop WSL2 integration."
        exit 1
    fi
}

install_deps_raspberrypi() {
    log_step "Installing Raspberry Pi Dependencies"

    log_info "Updating package list..."
    sudo apt-get update -qq

    log_info "Installing required system packages..."
    sudo apt-get install -y -qq \
        git curl rsync git-lfs openssh-client \
        cifs-utils nfs-common \
        > /dev/null 2>&1

    install_docker_linux
}

install_deps_linux() {
    log_step "Installing Linux Dependencies"

    if command -v apt-get &>/dev/null; then
        sudo apt-get update -qq
        sudo apt-get install -y -qq git curl rsync > /dev/null 2>&1
    elif command -v dnf &>/dev/null; then
        sudo dnf install -y -q git curl rsync > /dev/null 2>&1
    elif command -v pacman &>/dev/null; then
        sudo pacman -Sy --noconfirm git curl rsync > /dev/null 2>&1
    fi

    install_docker_linux
}

install_deps_macos() {
    log_step "Installing macOS Dependencies"

    if ! check_git; then
        log_info "Installing Xcode Command Line Tools (for git)..."
        xcode-select --install 2>/dev/null || true
        echo "Please complete the Xcode tools installation if prompted."
        read -rp "Press Enter to continue..."
    fi

    install_docker_macos
}

# --- Clone Repository ---
clone_or_update_repo() {
    log_step "Setting Up BackupGenie"

    local install_dir="$1"

    # If we're already in the repo directory
    if [[ -f "docker-compose.yml" && -d "backend" && -d "frontend" ]]; then
        log_info "Already in BackupGenie directory: $(pwd)"
        install_dir="$(pwd)"
        echo "$install_dir"
        return 0
    fi

    if [[ -d "$install_dir" && -f "$install_dir/docker-compose.yml" ]]; then
        log_info "Existing installation found, updating..."
        cd "$install_dir"
        git pull --rebase 2>/dev/null || true
        echo "$install_dir"
        return 0
    fi

    log_info "Cloning BackupGenie..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        mkdir -p "$install_dir"
    else
        sudo mkdir -p "$install_dir"
        sudo chown "${SUDO_USER:-$USER}:${SUDO_USER:-$USER}" "$install_dir"
    fi

    git clone -b "$BRANCH" "$REPO_URL" "$install_dir" 2>/dev/null
    log_info "Cloned to $install_dir"
    echo "$install_dir"
}

# --- Configuration ---
configure_env() {
    log_step "Configuring BackupGenie"

    local install_dir="$1"
    cd "$install_dir"

    # Create directories
    mkdir -p config data logs

    # .env file
    if [[ ! -f ".env" ]]; then
        if [[ -f ".env.example" ]]; then
            cp .env.example .env
        else
            cat > .env << 'ENVEOF'
# BackupGenie Configuration
SECRET_KEY=CHANGE_ME
DEBUG=false
API_PORT=5000
FRONTEND_PORT=3000
BACKUP_BASE_PATH=/mnt/backup
MAX_PARALLEL_TASKS=auto
PLATFORM_PROFILE=auto
LOG_RETENTION_DAYS=30
ENVEOF
        fi

        # Generate secure secret key
        local secret
        secret=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))' 2>/dev/null || openssl rand -base64 32)
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|SECRET_KEY=.*|SECRET_KEY=$secret|" .env
        else
            sed -i "s|SECRET_KEY=.*|SECRET_KEY=$secret|" .env
        fi

        log_info "Generated .env with secure secret key"
    else
        log_info ".env already exists"
    fi

    # Sources config
    if [[ ! -f "config/sources.json" ]]; then
        if [[ -f "config/sources-example.json" ]]; then
            cp config/sources-example.json config/sources.json
        else
            echo '{"backup_sources": []}' > config/sources.json
        fi
        log_info "Created config/sources.json"
    fi

    # rclone config
    if [[ ! -f "config/rclone.conf" ]]; then
        touch config/rclone.conf
        log_info "Created empty config/rclone.conf"
    fi

    # Make scripts executable
    chmod +x scripts/*.sh 2>/dev/null || true
}

# --- Build & Start ---
build_and_start() {
    log_step "Building & Starting BackupGenie"

    local install_dir="$1"
    cd "$install_dir"

    log_info "Building Docker images (this may take 5-20 minutes)..."
    docker compose build --progress=plain 2>&1 | tail -5

    log_info "Starting containers..."
    docker compose up -d

    # Wait for health checks
    log_info "Waiting for services to be ready..."
    local retries=0
    while [[ $retries -lt 30 ]]; do
        if docker compose ps 2>/dev/null | grep -q "healthy"; then
            break
        fi
        sleep 2
        retries=$((retries + 1))
    done

    if docker compose ps 2>/dev/null | grep -q "Up"; then
        log_info "BackupGenie is running!"
        echo ""
        docker compose ps
    else
        log_error "Containers failed to start. Check logs:"
        echo "  docker compose logs --tail=50"
        exit 1
    fi
}

# --- WebUI Setup Wizard ---
launch_webui_wizard() {
    local install_dir="$1"
    local port="${2:-$DEFAULT_PORT}"

    log_step "Launching WebUI Setup Wizard"

    # Create a minimal Python HTTP server that serves a setup wizard
    local wizard_dir
    wizard_dir=$(mktemp -d)

    cat > "$wizard_dir/wizard.py" << 'PYEOF'
#!/usr/bin/env python3
"""BackupGenie WebUI Setup Wizard - Lightweight setup server"""
import http.server
import hmac
import json
import os
import secrets
import subprocess
import sys
import webbrowser
import threading
import urllib.parse

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8888
INSTALL_DIR = os.path.realpath(sys.argv[2] if len(sys.argv) > 2 else os.getcwd())
SETUP_TOKEN = sys.argv[3] if len(sys.argv) > 3 else ''
if len(SETUP_TOKEN) < 32:
    raise SystemExit('A strong one-time setup token is required')

HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BackupGenie Setup Wizard</title>
<style>
:root {
  --bg: #0f172a; --surface: #1e293b; --surface2: #334155;
  --primary: #3b82f6; --primary-hover: #2563eb; --success: #10b981;
  --warning: #f59e0b; --error: #ef4444; --text: #f8fafc; --text-dim: #94a3b8;
  --border: #475569; --radius: 12px;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background: var(--bg); color: var(--text);
  min-height: 100vh; display: flex; justify-content: center; align-items: center;
  padding: 20px;
}
.wizard {
  background: var(--surface); border-radius: 20px;
  max-width: 640px; width: 100%; padding: 40px;
  box-shadow: 0 25px 50px -12px rgba(0,0,0,0.5);
  border: 1px solid var(--border);
}
.logo { text-align: center; margin-bottom: 32px; }
.logo h1 {
  font-size: 28px; font-weight: 700;
  background: linear-gradient(135deg, #3b82f6, #8b5cf6);
  -webkit-background-clip: text; -webkit-text-fill-color: transparent;
}
.logo p { color: var(--text-dim); margin-top: 8px; font-size: 14px; }
.step { display: none; }
.step.active { display: block; animation: fadeIn 0.3s ease; }
@keyframes fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
.step-indicator {
  display: flex; justify-content: center; gap: 8px; margin-bottom: 32px;
}
.step-dot {
  width: 32px; height: 4px; border-radius: 2px; background: var(--surface2);
  transition: all 0.3s;
}
.step-dot.active { background: var(--primary); width: 48px; }
.step-dot.done { background: var(--success); }
.form-group { margin-bottom: 20px; }
.form-group label {
  display: block; font-size: 13px; font-weight: 600;
  color: var(--text-dim); margin-bottom: 6px; text-transform: uppercase;
  letter-spacing: 0.05em;
}
.form-group input, .form-group select {
  width: 100%; padding: 12px 16px; border-radius: var(--radius);
  background: var(--bg); border: 1px solid var(--border); color: var(--text);
  font-size: 15px; transition: border-color 0.2s;
}
.form-group input:focus, .form-group select:focus {
  outline: none; border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
}
.btn-row { display: flex; gap: 12px; margin-top: 28px; }
.btn {
  flex: 1; padding: 14px 24px; border-radius: var(--radius);
  font-size: 15px; font-weight: 600; cursor: pointer;
  border: none; transition: all 0.2s;
}
.btn-primary {
  background: linear-gradient(135deg, #3b82f6, #6366f1);
  color: white;
}
.btn-primary:hover { transform: translateY(-1px); box-shadow: 0 4px 15px rgba(59,130,246,0.4); }
.btn-secondary { background: var(--surface2); color: var(--text); }
.btn-secondary:hover { background: var(--border); }
.btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }
.status-card {
  background: var(--bg); border-radius: var(--radius); padding: 16px;
  border: 1px solid var(--border); margin-bottom: 12px;
}
.status-row { display: flex; justify-content: space-between; align-items: center; padding: 8px 0; }
.status-row .label { color: var(--text-dim); font-size: 14px; }
.badge {
  padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600;
}
.badge-success { background: rgba(16,185,129,0.15); color: var(--success); }
.badge-error { background: rgba(239,68,68,0.15); color: var(--error); }
.badge-warn { background: rgba(245,158,11,0.15); color: var(--warning); }
.progress-bar {
  width: 100%; height: 6px; background: var(--surface2);
  border-radius: 3px; overflow: hidden; margin: 16px 0;
}
.progress-fill {
  height: 100%; background: linear-gradient(90deg, #3b82f6, #8b5cf6);
  border-radius: 3px; transition: width 0.5s ease;
}
.log-output {
  background: #0d1117; border-radius: 8px; padding: 16px;
  font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px;
  color: #8b949e; max-height: 200px; overflow-y: auto;
  border: 1px solid var(--border); line-height: 1.6;
  white-space: pre-wrap; word-break: break-all;
}
h2 { font-size: 20px; margin-bottom: 8px; }
.subtitle { color: var(--text-dim); font-size: 14px; margin-bottom: 24px; }
.platform-info {
  display: flex; align-items: center; gap: 12px;
  padding: 16px; background: var(--bg); border-radius: var(--radius);
  border: 1px solid var(--border); margin-bottom: 20px;
}
.platform-icon { font-size: 32px; }
.platform-name { font-size: 16px; font-weight: 600; }
.platform-arch { font-size: 13px; color: var(--text-dim); }
.success-box {
  text-align: center; padding: 32px 0;
}
.success-icon { font-size: 64px; margin-bottom: 16px; }
.success-url {
  display: inline-block; padding: 12px 24px; background: var(--bg);
  border-radius: var(--radius); border: 1px solid var(--primary);
  color: var(--primary); font-size: 18px; font-weight: 600;
  text-decoration: none; margin: 16px 0;
  transition: all 0.2s;
}
.success-url:hover { background: rgba(59,130,246,0.1); }
.cred-box {
  background: var(--bg); border-radius: var(--radius); padding: 20px;
  border: 1px solid var(--border); margin: 16px 0;
}
.cred-row { display: flex; justify-content: space-between; padding: 6px 0; }
.cred-label { color: var(--text-dim); }
.cred-value { font-weight: 600; font-family: monospace; }
</style>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
</head>
<body>
<div class="wizard">
  <div class="logo">
    <h1>🧞 BackupGenie</h1>
    <p>Universal Setup Wizard</p>
  </div>
  <div class="step-indicator" id="stepIndicator"></div>

  <!-- Step 1: System Check -->
  <div class="step active" id="step1">
    <h2>System Check</h2>
    <p class="subtitle">Checking your system requirements...</p>
    <div id="systemChecks"></div>
    <div class="btn-row">
      <button class="btn btn-primary" onclick="goStep(2)" id="btn1next">Continue</button>
    </div>
  </div>

  <!-- Step 2: Configuration -->
  <div class="step" id="step2">
    <h2>Configuration</h2>
    <p class="subtitle">Customize your BackupGenie installation</p>
    <div class="form-group">
      <label>Installation Directory</label>
      <input type="text" id="installDir" value="" disabled>
    </div>
    <div class="form-group">
      <label>Backup Mount Path</label>
      <input type="text" id="backupPath" value="/mnt/backup">
    </div>
    <div class="form-group">
      <label>API Port</label>
      <input type="number" id="apiPort" value="5000">
    </div>
    <div class="form-group">
      <label>Frontend Port</label>
      <input type="number" id="frontendPort" value="3000">
    </div>
    <div class="form-group">
      <label>Max Parallel Backups</label>
      <select id="maxParallel">
        <option value="1">1 (Low resource)</option>
        <option value="2" selected>2 (Recommended)</option>
        <option value="3">3 (Fast systems)</option>
        <option value="4">4 (High performance)</option>
      </select>
    </div>
    <div class="btn-row">
      <button class="btn btn-secondary" onclick="goStep(1)">Back</button>
      <button class="btn btn-primary" onclick="saveConfig()">Install</button>
    </div>
  </div>

  <!-- Step 3: Installation Progress -->
  <div class="step" id="step3">
    <h2>Installing...</h2>
    <p class="subtitle" id="installStatus">Preparing installation...</p>
    <div class="progress-bar"><div class="progress-fill" id="progressFill" style="width:0%"></div></div>
    <div class="log-output" id="installLog">Starting BackupGenie installation...\\n</div>
  </div>

  <!-- Step 4: Complete -->
  <div class="step" id="step4">
    <div class="success-box">
      <div class="success-icon">🎉</div>
      <h2>BackupGenie is Ready!</h2>
      <p class="subtitle">Your backup manager is up and running</p>
      <a class="success-url" id="appUrl" href="#" target="_blank">Open BackupGenie →</a>
    </div>
    <div class="cred-box">
      <h3 style="margin-bottom:12px">Login Credentials</h3>
      <div class="cred-row"><span class="cred-label">Username:</span><span class="cred-value">admin</span></div>
      <div class="cred-row"><span class="cred-label">Password:</span><span class="cred-value" id="adminPw">Check docker logs</span></div>
    </div>
    <div class="btn-row">
      <button class="btn btn-primary" onclick="window.open(document.getElementById('appUrl').href)">Open Web Interface</button>
    </div>
  </div>
</div>

<script>
const SETUP_TOKEN = '__SETUP_TOKEN__';
const apiFetch = (url, options = {}) => fetch(url, {
  ...options,
  headers: {...(options.headers || {}), 'X-Setup-Token': SETUP_TOKEN}
});
const STEPS = 4;
let currentStep = 1;

function updateIndicator() {
  const el = document.getElementById('stepIndicator');
  el.innerHTML = '';
  for (let i = 1; i <= STEPS; i++) {
    const dot = document.createElement('div');
    dot.className = 'step-dot' + (i === currentStep ? ' active' : i < currentStep ? ' done' : '');
    el.appendChild(dot);
  }
}

function goStep(n) {
  document.getElementById('step' + currentStep).classList.remove('active');
  currentStep = n;
  document.getElementById('step' + currentStep).classList.add('active');
  updateIndicator();
}

async function checkSystem() {
  const res = await apiFetch('/api/system-check');
  const data = await res.json();
  const el = document.getElementById('systemChecks');

  // Platform
  el.innerHTML = '<div class="platform-info">' +
    '<div class="platform-icon">' + (data.platform_icon || '💻') + '</div>' +
    '<div><div class="platform-name">' + data.platform + '</div>' +
    '<div class="platform-arch">' + data.arch + '</div></div></div>';

  // Checks
  const checks = data.checks || [];
  const card = document.createElement('div');
  card.className = 'status-card';
  checks.forEach(c => {
    const badge = c.ok ? 'badge-success' : (c.warn ? 'badge-warn' : 'badge-error');
    const label = c.ok ? '✓ Ready' : (c.warn ? '⚠ Warning' : '✗ Missing');
    card.innerHTML += '<div class="status-row"><span class="label">' + c.name +
      '</span><span class="badge ' + badge + '">' + label + '</span></div>';
  });
  el.appendChild(card);

  document.getElementById('installDir').value = data.default_install_dir || '/opt/BackupGenie';
  const allOk = checks.every(c => c.ok || c.warn);
  document.getElementById('btn1next').disabled = !allOk;
}

async function saveConfig() {
  const config = {
    backup_path: document.getElementById('backupPath').value,
    api_port: document.getElementById('apiPort').value,
    frontend_port: document.getElementById('frontendPort').value,
    max_parallel: document.getElementById('maxParallel').value
  };

  goStep(3);
  const logEl = document.getElementById('installLog');
  const progressEl = document.getElementById('progressFill');
  const statusEl = document.getElementById('installStatus');

  function addLog(msg) { logEl.textContent += msg + '\\n'; logEl.scrollTop = logEl.scrollHeight; }
  function setProgress(pct, status) { progressEl.style.width = pct + '%'; statusEl.textContent = status; }

  try {
    setProgress(10, 'Saving configuration...');
    addLog('Saving configuration...');

    const res1 = await apiFetch('/api/configure', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(config)
    });
    const r1 = await res1.json();
    addLog(r1.message || 'Configuration saved');

    setProgress(30, 'Building Docker images...');
    addLog('Building Docker images (this may take several minutes)...');

    const res2 = await apiFetch('/api/build', { method: 'POST' });
    const r2 = await res2.json();
    addLog(r2.message || 'Build complete');

    setProgress(70, 'Starting containers...');
    addLog('Starting BackupGenie containers...');

    const res3 = await apiFetch('/api/start', { method: 'POST' });
    const r3 = await res3.json();
    addLog(r3.message || 'Containers started');

    setProgress(90, 'Verifying...');
    addLog('Checking service health...');

    await new Promise(r => setTimeout(r, 5000));
    const res4 = await apiFetch('/api/status');
    const r4 = await res4.json();
    addLog(r4.message || 'Services running');

    setProgress(100, 'Installation complete!');

    // Set up success page
    const url = 'http://' + window.location.hostname + ':' + config.frontend_port;
    document.getElementById('appUrl').href = url;
    document.getElementById('appUrl').textContent = url + ' →';
    if (r4.admin_password) document.getElementById('adminPw').textContent = r4.admin_password;

    setTimeout(() => goStep(4), 1000);

  } catch (err) {
    addLog('ERROR: ' + err.message);
    setProgress(0, 'Installation failed');
  }
}

updateIndicator();
checkSystem();
</script>
</body>
</html>"""


class WizardHandler(http.server.BaseHTTPRequestHandler):
    install_dir = INSTALL_DIR
    stage = 'ready'

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path.startswith('/api/') and not self._authorized():
            self._json_response({'ok': False, 'message': 'Forbidden'}, 403)
            return
        if parsed.path in ('/', '/index.html'):
            query = urllib.parse.parse_qs(parsed.query)
            supplied = query.get('token', [''])[0]
            if not hmac.compare_digest(supplied, SETUP_TOKEN):
                self.send_error(403)
                return
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(HTML.replace('__SETUP_TOKEN__', SETUP_TOKEN).encode())
        elif parsed.path == '/api/system-check':
            self._system_check()
        elif parsed.path == '/api/status':
            self._check_status()
        else:
            self.send_error(404)

    def do_POST(self):
        if not self._authorized():
            self._json_response({'ok': False, 'message': 'Forbidden'}, 403)
            return
        if self.path == '/api/configure':
            length = int(self.headers.get('Content-Length', 0))
            if length > 16384:
                self._json_response({'ok': False, 'message': 'Request too large'}, 413)
                return
            data = json.loads(self.rfile.read(length)) if length else {}
            self._configure(data)
        elif self.path == '/api/build':
            self._build()
        elif self.path == '/api/start':
            self._start()
        else:
            self.send_error(404)

    def _json_response(self, data, code=200):
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _authorized(self):
        supplied = self.headers.get('X-Setup-Token', '')
        return hmac.compare_digest(supplied, SETUP_TOKEN)

    def _require_stage(self, expected):
        if WizardHandler.stage != expected:
            self._json_response({
                'ok': False,
                'message': f'Invalid setup stage: {WizardHandler.stage}'
            }, 409)
            return False
        return True

    def _system_check(self):
        import platform
        checks = []
        os_name = platform.system()

        # Docker
        try:
            r = subprocess.run(['docker', '--version'], capture_output=True, text=True, timeout=5)
            checks.append({'name': 'Docker', 'ok': r.returncode == 0})
        except Exception:
            checks.append({'name': 'Docker', 'ok': False})

        # Docker Compose
        try:
            r = subprocess.run(['docker', 'compose', 'version'], capture_output=True, text=True, timeout=5)
            checks.append({'name': 'Docker Compose', 'ok': r.returncode == 0})
        except Exception:
            checks.append({'name': 'Docker Compose', 'ok': False})

        # Git
        try:
            r = subprocess.run(['git', '--version'], capture_output=True, text=True, timeout=5)
            checks.append({'name': 'Git', 'ok': r.returncode == 0})
        except Exception:
            checks.append({'name': 'Git', 'ok': False})

        # Disk space
        import shutil
        total, used, free = shutil.disk_usage('/')
        free_gb = free // (1024**3)
        checks.append({
            'name': f'Disk Space ({free_gb}GB free)',
            'ok': free_gb >= 5, 'warn': 2 <= free_gb < 5
        })

        # Platform icon
        icons = {'Darwin': '🍎', 'Linux': '🐧', 'Windows': '🪟'}
        platform_name = os_name
        if os_name == 'Linux':
            try:
                with open('/proc/cpuinfo') as f:
                    if 'Raspberry Pi' in f.read():
                        platform_name = 'Raspberry Pi'
                        icons['Linux'] = '🍓'
            except Exception:
                pass

        self._json_response({
            'platform': platform_name,
            'arch': platform.machine(),
            'platform_icon': icons.get(os_name, '💻'),
            'checks': checks,
            'default_install_dir': INSTALL_DIR
        })

    def _configure(self, data):
        if not self._require_stage('ready'):
            return
        self.install_dir = INSTALL_DIR

        try:
            if not os.path.isfile(os.path.join(self.install_dir, 'docker-compose.yml')):
                raise ValueError('Fixed installation directory is not a BackupGenie checkout')
            os.makedirs(os.path.join(self.install_dir, 'config'), exist_ok=True)
            os.makedirs(os.path.join(self.install_dir, 'data'), exist_ok=True)
            os.makedirs(os.path.join(self.install_dir, 'logs'), exist_ok=True)

            env_path = os.path.join(self.install_dir, '.env')
            if not os.path.exists(env_path):
                api_port = int(data.get('api_port', 5000))
                frontend_port = int(data.get('frontend_port', 3000))
                max_parallel = int(data.get('max_parallel', 2))
                backup_path = str(data.get('backup_path', '/mnt/backup')).strip()
                if not (1 <= api_port <= 65535 and 1 <= frontend_port <= 65535):
                    raise ValueError('Ports must be between 1 and 65535')
                if not (1 <= max_parallel <= 10):
                    raise ValueError('Parallel backups must be between 1 and 10')
                if not os.path.isabs(backup_path) or any(c in backup_path for c in '\r\n\0'):
                    raise ValueError('Backup path must be an absolute path')
                env_content = f"""SECRET_KEY={secrets.token_urlsafe(32)}
DEBUG=false
API_PORT={api_port}
FRONTEND_PORT={frontend_port}
BACKUP_BASE_PATH={backup_path}
MAX_PARALLEL_TASKS={max_parallel}
LOG_RETENTION_DAYS=30
"""
                with open(env_path, 'x', encoding='utf-8') as env_file:
                    env_file.write(env_content)
                os.chmod(env_path, 0o600)
                message = 'Configuration saved'
            else:
                message = 'Existing .env preserved'

            sources_path = os.path.join(self.install_dir, 'config', 'sources.json')
            if not os.path.exists(sources_path):
                with open(sources_path, 'x', encoding='utf-8') as sources_file:
                    json.dump({'backup_sources': []}, sources_file)
                os.chmod(sources_path, 0o600)
            rclone_path = os.path.join(self.install_dir, 'config', 'rclone.conf')
            if not os.path.exists(rclone_path):
                with open(rclone_path, 'x', encoding='utf-8'):
                    pass
                os.chmod(rclone_path, 0o600)

            WizardHandler.stage = 'configured'
            self._json_response({'ok': True, 'message': message})
        except Exception as e:
            self._json_response({'ok': False, 'message': str(e)}, 500)

    def _build(self):
        if not self._require_stage('configured'):
            return
        try:
            r = subprocess.run(
                ['docker', 'compose', 'build'],
                capture_output=True, text=True, timeout=1200,
                cwd=self.install_dir
            )
            ok = r.returncode == 0
            msg = 'Build successful' if ok else f'Build failed: {r.stderr[-300:]}'
            if ok:
                WizardHandler.stage = 'built'
            self._json_response({'ok': ok, 'message': msg})
        except Exception as e:
            self._json_response({'ok': False, 'message': str(e)}, 500)

    def _start(self):
        if not self._require_stage('built'):
            return
        try:
            r = subprocess.run(
                ['docker', 'compose', 'up', '-d'],
                capture_output=True, text=True, timeout=120,
                cwd=self.install_dir
            )
            ok = r.returncode == 0
            if ok:
                WizardHandler.stage = 'started'
                threading.Timer(120, self.server.shutdown).start()
            self._json_response({'ok': ok, 'message': 'Containers started' if ok else r.stderr[-200:]})
        except Exception as e:
            self._json_response({'ok': False, 'message': str(e)}, 500)

    def _check_status(self):
        try:
            r = subprocess.run(
                ['docker', 'compose', 'ps', '--format', 'json'],
                capture_output=True, text=True, timeout=10,
                cwd=self.install_dir
            )
            # Try to get admin password
            pw_result = subprocess.run(
                ['docker', 'compose', 'logs', 'backend'],
                capture_output=True, text=True, timeout=10,
                cwd=self.install_dir
            )
            admin_pw = ''
            for line in pw_result.stdout.split('\n'):
                if 'password' in line.lower() and 'initial' in line.lower():
                    admin_pw = line.split()[-1] if line.split() else ''

            self._json_response({
                'ok': r.returncode == 0,
                'message': 'Services running',
                'admin_password': admin_pw
            })
        except Exception as e:
            self._json_response({'ok': False, 'message': str(e)}, 500)


def run_wizard(port):
    server = http.server.HTTPServer(('127.0.0.1', port), WizardHandler)
    url = f'http://127.0.0.1:{port}/?token={urllib.parse.quote(SETUP_TOKEN)}'
    print(f'\n  🧞 BackupGenie Setup Wizard running at:')
    print(f'     {url}')
    print('     Localhost only; the wizard closes automatically after installation.')
    print(f'\n  Press Ctrl+C to stop\n')
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nWizard stopped.')
        server.server_close()


if __name__ == '__main__':
    run_wizard(PORT)
PYEOF

    log_info "Starting setup wizard on port $port..."
    echo ""
    local wizard_token
    wizard_token=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    python3 "$wizard_dir/wizard.py" "$port" "$install_dir" "$wizard_token"
}

# --- Print Summary ---
print_summary() {
    local install_dir="$1"
    local platform="$2"

    # Get IP
    local ip
    if [[ "$platform" == "macos" ]]; then
        ip=$(ipconfig getifaddr en0 2>/dev/null || echo "localhost")
    else
        ip=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
    fi

    # Try to get admin password
    local admin_pw
    admin_pw=$(cd "$install_dir" && docker compose logs backend 2>/dev/null | grep -i "initial.*password" | tail -1 | awk '{print $NF}' || echo "see docker logs")

    echo ""
    echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════╗"
    echo "║        BackupGenie Setup Complete! 🎉        ║"
    echo -e "╚══════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "  ${BOLD}Web Interface:${NC}  http://$ip:3000"
    echo -e "  ${BOLD}Username:${NC}       admin"
    echo -e "  ${BOLD}Password:${NC}       $admin_pw"
    echo ""
    echo -e "  ${BOLD}Installation:${NC}   $install_dir"
    echo -e "  ${BOLD}Configuration:${NC}  $install_dir/config/"
    echo -e "  ${BOLD}Logs:${NC}           $install_dir/logs/"
    echo ""
    echo -e "  ${BOLD}Commands:${NC}"
    echo "    cd $install_dir"
    echo "    docker compose ps          # Status"
    echo "    docker compose logs -f     # Logs"
    echo "    docker compose restart     # Restart"
    echo ""
}

# --- Main ---
main() {
    banner

    # Parse arguments
    local use_webui=false
    local skip_build=false
    for arg in "$@"; do
        case "$arg" in
            --webui|--web)   use_webui=true ;;
            --skip-build)    skip_build=true ;;
            --help|-h)
                echo "Usage: $0 [options]"
                echo ""
                echo "Options:"
                echo "  --webui      Launch browser-based setup wizard"
                echo "  --skip-build Skip Docker build (if images are pre-built)"
                echo "  --help       Show this help"
                echo ""
                echo "Environment Variables:"
                echo "  REPO_URL     Git repository URL (default: hehljo/BackupGenie)"
                echo "  BRANCH       Git branch (default: main)"
                echo "  INSTALL_DIR  Installation directory (default: /opt/BackupGenie)"
                echo ""
                exit 0
                ;;
        esac
    done

    # Detect platform
    local platform_info
    platform_info=$(detect_platform)
    IFS='|' read -r platform arch variant <<< "$platform_info"

    echo -e "  ${BOLD}Platform:${NC}     $platform"
    echo -e "  ${BOLD}Architecture:${NC} $arch"
    [[ -n "$variant" ]] && echo -e "  ${BOLD}Model:${NC}        $variant"
    echo ""

    # Default install directory
    local install_dir="${INSTALL_DIR:-/opt/BackupGenie}"
    if [[ "$platform" == "macos" ]]; then
        install_dir="${INSTALL_DIR:-$HOME/BackupGenie}"
    fi

    # Install dependencies based on platform
    case "$platform" in
        macos)
            install_deps_macos
            ;;
        raspberrypi)
            install_deps_raspberrypi
            ;;
        linux)
            install_deps_linux
            ;;
        wsl)
            install_docker_wsl
            if ! check_git; then
                sudo apt-get install -y git curl > /dev/null 2>&1
            fi
            ;;
        windows-git-bash)
            echo ""
            log_warn "Native Windows detected (Git Bash/MSYS2)"
            echo "  BackupGenie requires Docker, which works best via WSL2 on Windows."
            echo ""
            echo "  Recommended setup:"
            echo "    1. Enable WSL2:  wsl --install"
            echo "    2. Install Docker Desktop with WSL2 backend"
            echo "    3. Run this installer inside WSL2"
            echo ""
            exit 1
            ;;
        *)
            log_error "Unsupported platform: $platform"
            echo "  Supported: macOS, Linux (Debian/Ubuntu/Raspberry Pi), WSL2"
            exit 1
            ;;
    esac

    # WebUI mode
    if [[ "$use_webui" == "true" ]]; then
        install_dir=$(clone_or_update_repo "$install_dir")
        launch_webui_wizard "$install_dir" "$DEFAULT_PORT"
        exit 0
    fi

    # CLI mode
    log_step "Installation Mode"
    echo "  1) Quick Install (automated, recommended)"
    echo "  2) WebUI Wizard (browser-based setup)"
    echo "  3) Manual (clone only, configure yourself)"
    echo ""

    if [[ -t 0 ]]; then
        read -rp "  Choose [1-3] (default: 1): " choice
        choice=${choice:-1}
    else
        echo "  Non-interactive mode: using Quick Install..."
        choice=1
    fi

    case "$choice" in
        1)
            install_dir=$(clone_or_update_repo "$install_dir")
            configure_env "$install_dir"
            if [[ "$skip_build" != "true" ]]; then
                build_and_start "$install_dir"
            fi
            print_summary "$install_dir" "$platform"
            ;;
        2)
            install_dir=$(clone_or_update_repo "$install_dir")
            launch_webui_wizard "$install_dir" "$DEFAULT_PORT"
            ;;
        3)
            install_dir=$(clone_or_update_repo "$install_dir")
            configure_env "$install_dir"
            echo ""
            log_info "Repository ready at: $install_dir"
            echo ""
            echo "  Next steps:"
            echo "    cd $install_dir"
            echo "    nano .env"
            echo "    docker compose build"
            echo "    docker compose up -d"
            echo ""
            ;;
    esac
}

main "$@"
