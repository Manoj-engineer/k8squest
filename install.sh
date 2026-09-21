#!/usr/bin/env bash

# ============================================================
# K8sQuest Installer
# Bare Kubernetes / kubeadm compatible
# ============================================================

set -Eeuo pipefail

# ============================================================
# Configuration
# ============================================================

NAMESPACE="k8squest"
VENV_DIR="venv"
REQUIREMENTS_FILE="requirements.txt"
RBAC_FILE="rbac/k8squest-rbac.yaml"

# ============================================================
# Colors
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ============================================================
# Helper functions
# ============================================================

log() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

success() {
    echo -e "${GREEN}✅ $1${NC}"
}

warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

error() {
    echo -e "${RED}❌ $1${NC}" >&2
    exit 1
}

step() {
    echo ""
    echo "============================================================"
    echo "▶ $1"
    echo "============================================================"
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# ============================================================
# Error handler
# ============================================================

trap 'echo ""; error "Installer failed at line $LINENO while executing: $BASH_COMMAND"' ERR

# ============================================================
# Determine project directory
# ============================================================

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

echo ""
echo "🎮 K8sQuest Installation"
echo "========================"
echo ""

log "Project directory: $SCRIPT_DIR"

sleep 2
# ============================================================
# 1. Operating System
# ============================================================

step "Checking operating system"

if [ -f /etc/os-release ]; then

    # shellcheck disable=SC1091
    source /etc/os-release

    log "Operating system: ${PRETTY_NAME:-Unknown}"

else

    warning "Unable to determine Linux distribution."

fi

sleep 2
# ============================================================
# 2. Project Files
# ============================================================

step "Checking project files"

if [ ! -f "$REQUIREMENTS_FILE" ]; then

    error "requirements.txt not found.

Make sure you run this installer from the K8sQuest project."

fi

success "requirements.txt found"

if [ -f "$RBAC_FILE" ]; then

    success "RBAC configuration found"

else

    warning "RBAC configuration not found."
    warning "RBAC setup will be skipped."

fi

sleep 2
# ============================================================
# 3. kubectl
# ============================================================

step "Checking kubectl"

if ! command_exists kubectl; then

    error "kubectl is not installed.

Install kubectl and run this installer again."

fi

success "kubectl detected"

sleep 2
# ============================================================
# 4. Python
# ============================================================

step "Checking Python"

if ! command_exists python3; then

    error "python3 is not installed.

Install Python 3.9 or newer."

fi

PYTHON_VERSION="$(
    python3 -c \
    'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")'
)"

PYTHON_MAJOR="$(
    python3 -c \
    'import sys; print(sys.version_info.major)'
)"

PYTHON_MINOR="$(
    python3 -c \
    'import sys; print(sys.version_info.minor)'
)"

if [ "$PYTHON_MAJOR" -lt 3 ] ||
   { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 9 ]; }; then

    error "Python 3.9 or newer is required.

Detected: Python $PYTHON_VERSION"

fi

success "Python $PYTHON_VERSION detected"

sleep 2
# ============================================================
# 5. Verify Python venv support
# ============================================================

step "Checking Python virtual environment support"

log "Testing whether Python can create a virtual environment..."

TEST_DIR="$(mktemp -d)"

VENV_TEST_FAILED=0
if ! python3 -m venv "$TEST_DIR/test-venv" >/dev/null 2>&1; then
    VENV_TEST_FAILED=1
fi

rm -rf "$TEST_DIR"

# ------------------------------------------------------------
# Install missing venv package
# ------------------------------------------------------------

if [ "$VENV_TEST_FAILED" -eq 1 ]; then

    warning "Python virtual environment support is unavailable."

    if command_exists apt-get; then

        VENV_PACKAGE="python${PYTHON_MAJOR}.${PYTHON_MINOR}-venv"

        log "Detected Debian/Ubuntu package manager."

        echo ""
        echo "Required package:"
        echo "    $VENV_PACKAGE"
        echo ""

        if [ "$(id -u)" -eq 0 ]; then

            log "Running as root."

            apt-get update
            apt-get install -y "$VENV_PACKAGE"

        elif command_exists sudo; then

            log "Using sudo to install Python venv support."

            sudo apt-get update
            sudo apt-get install -y "$VENV_PACKAGE"

        else

            error "Python venv support is missing.

Install manually:

    apt-get update
    apt-get install -y $VENV_PACKAGE

Then run:

    ./install.sh"

        fi

        success "$VENV_PACKAGE installed"

    else

        error "Python venv support is missing.

Install the appropriate Python venv package
for your Linux distribution and run this installer again."

    fi
fi

sleep 2
# ------------------------------------------------------------
# Verify venv works after installation
# ------------------------------------------------------------

TEST_DIR="$(mktemp -d)"

if ! python3 -m venv "$TEST_DIR/test-venv" >/dev/null 2>&1; then

    rm -rf "$TEST_DIR"

    error "Python virtual environment support is still unavailable.

For Python $PYTHON_VERSION, install:

    python${PYTHON_MAJOR}.${PYTHON_MINOR}-venv"

fi

rm -rf "$TEST_DIR"

success "Python virtual environment support is ready"

sleep 2
# ============================================================
# 6. Kubernetes Context
# ============================================================

step "Checking Kubernetes configuration"

CURRENT_CONTEXT="$(kubectl config current-context 2>/dev/null || true)"

if [ -z "$CURRENT_CONTEXT" ]; then

    error "No Kubernetes context is configured.

Check:

    kubectl config get-contexts

Configure kubectl and run the installer again."

fi

success "Kubernetes context: $CURRENT_CONTEXT"

sleep 2
# ============================================================
# 7. Kubernetes API
# ============================================================

step "Checking Kubernetes API server"

if ! kubectl cluster-info >/dev/null 2>&1; then

    error "Unable to connect to the Kubernetes API server.

Check:

    kubectl cluster-info
    kubectl get nodes"

fi

success "Kubernetes API server is reachable"

sleep 2
# ============================================================
# 8. Kubernetes Nodes
# ============================================================

step "Checking Kubernetes nodes"

kubectl get nodes -o wide

echo ""

NODE_COUNT="$(
    kubectl get nodes --no-headers 2>/dev/null \
    | wc -l \
    | tr -d ' '
)"

if [ "$NODE_COUNT" -eq 0 ]; then

    error "No Kubernetes nodes were found."

fi

NOT_READY_NODES="$(
    kubectl get nodes --no-headers 2>/dev/null \
    | awk '$2 != "Ready" {print $1}'
)"

if [ -n "$NOT_READY_NODES" ]; then

    warning "The following nodes are not Ready:"
    echo "$NOT_READY_NODES"
    echo ""

    error "All Kubernetes nodes must be Ready."

fi

success "All Kubernetes nodes are Ready"

sleep 2
# ============================================================
# 9. Prepare Python Virtual Environment
# ============================================================

step "Preparing Python virtual environment"

VENV_ACTIVATE="$VENV_DIR/bin/activate"
VENV_PYTHON="$VENV_DIR/bin/python"

# ------------------------------------------------------------
# Check existing environment
# ------------------------------------------------------------

if [ -f "$VENV_ACTIVATE" ] &&
   [ -x "$VENV_PYTHON" ]; then

    success "Existing Python virtual environment is valid"

else

    if [ -e "$VENV_DIR" ]; then

        warning "Existing '$VENV_DIR' is incomplete or broken."

        log "Removing broken virtual environment..."

        rm -rf "$VENV_DIR"

        success "Broken virtual environment removed"

    fi

    # --------------------------------------------------------
    # Create new environment
    # --------------------------------------------------------

    log "Creating Python virtual environment..."

    python3 -m venv "$VENV_DIR"

    if [ ! -f "$VENV_ACTIVATE" ] ||
       [ ! -x "$VENV_PYTHON" ]; then

        error "Python virtual environment was not created correctly."

    fi

    success "Python virtual environment created"

fi

sleep 2
# ============================================================
# 10. Activate Python Environment
# ============================================================

step "Activating Python environment"

# shellcheck disable=SC1091
source "$VENV_ACTIVATE"

success "Python virtual environment activated"

# ============================================================
# 11. Upgrade pip
# ============================================================

step "Preparing pip"

python -m pip install --upgrade pip

success "pip is ready"

sleep 2
# ============================================================
# 12. Install Dependencies
# ============================================================

step "Installing Python dependencies"

python -m pip install -r "$REQUIREMENTS_FILE"

success "Python dependencies installed"

# ============================================================
# 13. Kubernetes Namespace
# ============================================================

step "Preparing Kubernetes namespace"

if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then

    success "Namespace '$NAMESPACE' already exists"

else

    kubectl create namespace "$NAMESPACE"

    success "Namespace '$NAMESPACE' created"

fi

sleep 2
# ============================================================
# 14. RBAC
# ============================================================

step "Configuring Kubernetes RBAC"

if [ -f "$RBAC_FILE" ]; then

    kubectl apply -f "$RBAC_FILE"

    success "RBAC configuration applied"

else

    warning "RBAC file not found."
    warning "Skipping RBAC."

fi

sleep 2
# ============================================================
# 15. Verify Namespace
# ============================================================

step "Verifying Kubernetes configuration"

kubectl get namespace "$NAMESPACE"

success "Namespace '$NAMESPACE' is ready"

sleep 2
# ============================================================
# 16. Final Verification
# ============================================================

step "Running final verification"

echo ""
echo "☸️  Kubernetes context:"
kubectl config current-context

echo ""
echo "🖥️  Kubernetes nodes:"
kubectl get nodes

echo ""
echo "📦 K8sQuest namespace:"
kubectl get namespace "$NAMESPACE"

echo ""
echo "🐍 Python:"
"$VENV_PYTHON" --version

echo ""
echo "📦 pip:"
"$VENV_PYTHON" -m pip --version

# ============================================================
# Complete
# ============================================================

echo ""
echo "============================================================"
echo "🚀 K8sQuest Installation Complete!"
echo "============================================================"
echo ""

echo "☸️  Kubernetes"
echo "   Context  : $CURRENT_CONTEXT"
echo "   Namespace: $NAMESPACE"

echo ""
echo "🐍 Python"
echo "   Version  : $PYTHON_VERSION"
echo "   venv     : $SCRIPT_DIR/$VENV_DIR"

echo ""
echo "🎮 Start K8sQuest:"
echo ""
echo "   ./play.sh"
echo ""

sleep 2
echo "🔍 Useful commands:"
echo ""
echo "   kubectl get nodes"
echo "   kubectl get pods -n $NAMESPACE"
echo "   kubectl get all -n $NAMESPACE"
echo ""

echo "🎉 Have fun learning Kubernetes!"
echo ""
