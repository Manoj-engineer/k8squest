#!/usr/bin/env bash

# ============================================================
# K8sQuest Launcher
#
# Supported Kubernetes environments:
#   - Kind
#   - k3s
#   - Bare / kubeadm / existing Kubernetes cluster
# ============================================================

set -Eeuo pipefail

# ============================================================
# Configuration
# ============================================================

NAMESPACE="k8squest"

# ============================================================
# Helper functions
# ============================================================

info() {
    echo "ℹ️  $1"
}

success() {
    echo "✅ $1"
}

warning() {
    echo "⚠️  $1"
}

error() {
    echo "❌ $1"
    exit 1
}

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# ============================================================
# Error handler
# ============================================================

trap 'echo ""; error "Launcher failed at line $LINENO while executing: $BASH_COMMAND"' ERR

# ============================================================
# Move to project directory
# ============================================================

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

cd "$SCRIPT_DIR"

echo ""
echo "🎮 K8sQuest"
echo "==========="
echo ""

# ============================================================
# Find Python
# ============================================================

_find_python() {

    # --------------------------------------------------------
    # Conda
    # --------------------------------------------------------

    if [ -n "${CONDA_PREFIX:-}" ]; then

        if [ -f "$CONDA_PREFIX/bin/python3" ]; then
            echo "$CONDA_PREFIX/bin/python3"
            return 0

        elif [ -f "$CONDA_PREFIX/bin/python" ]; then
            echo "$CONDA_PREFIX/bin/python"
            return 0
        fi

    fi

    # --------------------------------------------------------
    # Virtual environment
    # --------------------------------------------------------

    if [ -n "${VIRTUAL_ENV:-}" ]; then

        if [ -f "$VIRTUAL_ENV/bin/python3" ]; then
            echo "$VIRTUAL_ENV/bin/python3"
            return 0

        elif [ -f "$VIRTUAL_ENV/bin/python" ]; then
            echo "$VIRTUAL_ENV/bin/python"
            return 0
        fi

    fi

    # --------------------------------------------------------
    # Project venv
    # --------------------------------------------------------

    if [ -x "$SCRIPT_DIR/venv/bin/python3" ]; then
        echo "$SCRIPT_DIR/venv/bin/python3"
        return 0

    elif [ -x "$SCRIPT_DIR/venv/bin/python" ]; then
        echo "$SCRIPT_DIR/venv/bin/python"
        return 0
    fi

    return 1
}

PYTHON="$(_find_python || true)"

if [ -z "$PYTHON" ]; then

    error "No Python environment found.

Please run:

    ./install.sh

first."

fi

success "Python: $PYTHON"

# ============================================================
# Check kubectl
# ============================================================

if ! command_exists kubectl; then
    error "kubectl is not installed."
fi

success "kubectl detected"

# ============================================================
# Check jq
# ============================================================

if ! command_exists jq; then

    warning "jq is not installed."

    if command_exists apt-get; then

        echo ""
        read -r -p "Install jq using apt? [Y/n]: " INSTALL_JQ

        case "${INSTALL_JQ:-Y}" in

            [Yy]*)
                if [ "$(id -u)" -eq 0 ]; then
                    apt-get update
                    apt-get install -y jq
                elif command_exists sudo; then
                    sudo apt-get update
                    sudo apt-get install -y jq
                else
                    error "sudo is not available. Install jq manually."
                fi
                ;;

            *)
                error "jq is required by K8sQuest."
                ;;
        esac

    else

        error "jq is required by K8sQuest.

Please install jq manually."

    fi

fi

success "jq detected"

# ============================================================
# Set PYTHONPATH
# ============================================================

export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"

# ============================================================
# Kubernetes validation
# ============================================================

_validate_kubernetes() {

    echo ""
    echo "☸️  Validating Kubernetes cluster..."
    echo ""

    # --------------------------------------------------------
    # Check current context
    # --------------------------------------------------------

    local context

    context="$(kubectl config current-context 2>/dev/null || true)"

    if [ -z "$context" ]; then

        error "No Kubernetes context is configured.

Run:

    kubectl config get-contexts"

    fi

    echo "📡 Current context:"
    echo "   $context"
    echo ""

    # --------------------------------------------------------
    # Check API server
    # --------------------------------------------------------

    if ! kubectl cluster-info >/dev/null 2>&1; then

        error "Cannot connect to Kubernetes API server.

Check:

    kubectl cluster-info
    kubectl get nodes"

    fi

    success "Kubernetes API server is reachable"

    # --------------------------------------------------------
    # Check nodes
    # --------------------------------------------------------

    echo ""
    echo "🖥️  Kubernetes nodes:"
    echo ""

    kubectl get nodes -o wide

    echo ""

    local node_count

    node_count="$(
        kubectl get nodes --no-headers 2>/dev/null |
        wc -l |
        tr -d ' '
    )"

    if [ "$node_count" -eq 0 ]; then
        error "No Kubernetes nodes found."
    fi

    # --------------------------------------------------------
    # Check Ready status
    # --------------------------------------------------------

    local not_ready

    not_ready="$(
        kubectl get nodes --no-headers 2>/dev/null |
        awk '$2 != "Ready" {print $1}'
    )"

    if [ -n "$not_ready" ]; then

        warning "The following nodes are not Ready:"
        echo "$not_ready"
        echo ""

        error "K8sQuest requires all Kubernetes nodes to be Ready."

    fi

    success "All Kubernetes nodes are Ready"

    # --------------------------------------------------------
    # Check namespace
    # --------------------------------------------------------

    if kubectl get namespace "$NAMESPACE" >/dev/null 2>&1; then

        success "Namespace '$NAMESPACE' exists"

    else

        info "Creating namespace '$NAMESPACE'..."

        kubectl create namespace "$NAMESPACE"

        success "Namespace '$NAMESPACE' created"

    fi

    # --------------------------------------------------------
    # Set namespace in current context
    # --------------------------------------------------------

    kubectl config set-context \
        --current \
        --namespace="$NAMESPACE" >/dev/null 2>&1 || true

    success "K8sQuest namespace configured"

    echo ""
}

# ============================================================
# Detect existing clusters
# ============================================================

_check_existing_clusters() {

    local has_kind=false
    local has_k3s=false
    local has_current_k8s=false

    # --------------------------------------------------------
    # Kind
    # --------------------------------------------------------

    if command_exists kind; then

        if kind get clusters 2>/dev/null | grep -q .; then
            has_kind=true
        fi

    fi

    # --------------------------------------------------------
    # k3s
    # --------------------------------------------------------

    if command_exists systemctl &&
       systemctl is-active --quiet k3s 2>/dev/null; then

        has_k3s=true

    elif [ -f /etc/rancher/k3s/k3s.yaml ] &&
         kubectl \
            --kubeconfig=/etc/rancher/k3s/k3s.yaml \
            get nodes >/dev/null 2>&1; then

        has_k3s=true

    fi

    # --------------------------------------------------------
    # Existing / bare Kubernetes
    #
    # This includes:
    #   kubeadm
    #   bare metal
    #   VM-based cluster
    #   cloud Kubernetes
    #   any cluster accessible through kubectl
    # --------------------------------------------------------

    if kubectl cluster-info >/dev/null 2>&1; then
        has_current_k8s=true
    fi

    # --------------------------------------------------------
    # Return detected types
    # --------------------------------------------------------

    local result=""

    $has_kind && result="${result}kind "
    $has_k3s && result="${result}k3s "
    $has_current_k8s && result="${result}bare "

    echo "$result" | xargs
}

# ============================================================
# Setup k3s kubeconfig
# ============================================================

_setup_k3s_kubeconfig() {

    local default_kubeconfig="/etc/rancher/k3s/k3s.yaml"

    # --------------------------------------------------------
    # Check k3s
    # --------------------------------------------------------

    if ! systemctl is-active --quiet k3s 2>/dev/null; then

        info "k3s is installed but not running. Starting..."

        sudo systemctl start k3s

        info "Waiting for k3s..."

        local attempt=0

        until timeout 10 k3s kubectl get nodes >/dev/null 2>&1; do

            attempt=$((attempt + 1))

            if [ "$attempt" -ge 90 ]; then
                error "k3s failed to start within 3 minutes."
            fi

            sleep 2

        done

    fi

    # --------------------------------------------------------
    # Configure kubeconfig
    # --------------------------------------------------------

    local kubeconfig="$HOME/.kube/k3s-config"

    echo ""
    echo "Default k3s kubeconfig:"
    echo "  $default_kubeconfig"
    echo ""

    read -r -p \
        "Enter custom kubeconfig path (Enter for $kubeconfig): " \
        custom

    if [ -n "$custom" ]; then
        kubeconfig="$custom"
    fi

    mkdir -p "$(dirname "$kubeconfig")"

    info "Copying k3s kubeconfig..."

    sudo cp "$default_kubeconfig" "$kubeconfig"
    sudo chown "$(id -u):$(id -g)" "$kubeconfig"

    export KUBECONFIG="$kubeconfig"

    success "k3s kubeconfig configured: $KUBECONFIG"

    _validate_kubernetes
}

# ============================================================
# Install k3s
# ============================================================

_install_k3s() {

    echo ""
    echo "🔧 Setting up k3s..."
    echo ""

    if ! command_exists k3s; then

        info "Installing k3s..."

        if ! command_exists curl; then
            error "curl is required to install k3s."
        fi

        curl -sfL https://get.k3s.io |
            sh -s - server \
            --cluster-init \
            --disable traefik \
            --write-kubeconfig-mode 644

        hash -r

    else

        info "k3s is already installed."

        sudo systemctl start k3s || true

    fi

    _setup_k3s_kubeconfig

    # --------------------------------------------------------
    # k3s compatibility setup
    # --------------------------------------------------------

    if [ -f "$SCRIPT_DIR/k3s-setup.sh" ]; then

        info "Running k3s compatibility setup..."

        bash "$SCRIPT_DIR/k3s-setup.sh"

    fi
}

# ============================================================
# Use existing / bare Kubernetes cluster
# ============================================================

_use_bare_kubernetes() {

    echo ""
    echo "============================================================"
    echo "☸️  Existing Kubernetes Cluster"
    echo "============================================================"
    echo ""

    info "K8sQuest will use your existing Kubernetes cluster."
    echo ""
    echo "This mode does NOT:"
    echo "  • install Kubernetes"
    echo "  • install k3s"
    echo "  • create a Kind cluster"
    echo "  • modify worker nodes"
    echo "  • change your CNI"
    echo ""

    _validate_kubernetes

    export K8S_CLUSTER_TYPE="bare"

    local context

    context="$(kubectl config current-context)"

    export K8S_CLUSTER_CONTEXT="$context"

    success "Using existing Kubernetes cluster"
    success "Cluster type: bare"
    success "Context: $context"
}

# ============================================================
# Kind cluster
# ============================================================

_use_kind() {

    if ! command_exists kind; then

        error "Kind is not installed.

Install Kind or select another cluster type."

    fi

    if ! command_exists docker; then

        error "Docker is required for Kind."

    fi

    local clusters

    clusters="$(kind get clusters 2>/dev/null || true)"

    if [ -z "$clusters" ]; then

        info "No Kind cluster detected."

        error "Create a Kind cluster first or choose another cluster type."

    fi

    echo ""
    echo "🐳 Available Kind clusters:"
    echo ""

    echo "$clusters"

    echo ""

    local kind_cluster

    kind_cluster="$(echo "$clusters" | head -1)"

    info "Using Kind cluster: $kind_cluster"

    kubectl config use-context "kind-$kind_cluster"

    export K8S_CLUSTER_TYPE="kind"

    _validate_kubernetes

    success "Kind cluster ready"
}

# ============================================================
# Remove old k3s kubeconfig symlink
# ============================================================

_remove_k3s_symlink() {

    local default_kube="$HOME/.kube/config"

    if [ ! -L "$default_kube" ]; then
        return
    fi

    local target

    target="$(readlink "$default_kube" 2>/dev/null || true)"

    if [[ "$target" == *"k3s-config"* ]]; then

        rm -f "$default_kube"

        if [ -f "$HOME/.kube/config.k8squest.bak" ]; then

            mv \
                "$HOME/.kube/config.k8squest.bak" \
                "$default_kube"

            info "Restored previous ~/.kube/config"

        fi

    fi
}

# ============================================================
# Cluster selection
# ============================================================

EXISTING_CLUSTERS="$(_check_existing_clusters)"

echo ""
echo "🔍 Cluster detection"
echo "--------------------"

if [ -n "$EXISTING_CLUSTERS" ]; then
    echo "Detected: $EXISTING_CLUSTERS"
else
    echo "No existing cluster detected."
fi

echo ""

# ============================================================
# Explicit K8S_CLUSTER_TYPE
# ============================================================

if [ -n "${K8S_CLUSTER_TYPE:-}" ]; then

    case "$K8S_CLUSTER_TYPE" in

        kind)
            _use_kind
            ;;

        k3s)
            _setup_k3s_kubeconfig
            export K8S_CLUSTER_TYPE="k3s"
            ;;

        bare|kubernetes|k8s|existing)
            _use_bare_kubernetes
            ;;

        *)
            error "Unknown K8S_CLUSTER_TYPE: $K8S_CLUSTER_TYPE

Supported:

    kind
    k3s
    bare"

            ;;
    esac

else

    # ========================================================
    # If an existing kubectl cluster is available, offer it
    # ========================================================

    CURRENT_CONTEXT="$(kubectl config current-context 2>/dev/null || true)"

    if [ -n "$CURRENT_CONTEXT" ] &&
       kubectl cluster-info >/dev/null 2>&1; then

        echo "╔══════════════════════════════════════════════════════════════╗"
        echo "║           ☸️  KUBERNETES CLUSTER DETECTED                  ║"
        echo "╚══════════════════════════════════════════════════════════════╝"
        echo ""
        echo "Current kubectl context:"
        echo "  $CURRENT_CONTEXT"
        echo ""
        echo "Choose how K8sQuest should run:"
        echo ""
        echo "  1) ☸️  Use existing Kubernetes cluster"
        echo "  2) 🐳 Use Kind"
        echo "  3) 🚀 Use k3s"
        echo ""
        read -r -p "Select option [1-3] (default: 1): " CLUSTER_CHOICE

        case "${CLUSTER_CHOICE:-1}" in

            1)
                _use_bare_kubernetes
                ;;

            2)
                export K8S_CLUSTER_TYPE="kind"
                _use_kind
                ;;

            3)
                export K8S_CLUSTER_TYPE="k3s"
                _install_k3s
                ;;

            *)
                error "Invalid option."
                ;;
        esac

    else

        # ====================================================
        # No current Kubernetes cluster
        # ====================================================

        echo "╔══════════════════════════════════════════════════════════════╗"
        echo "║          🎮 SELECT KUBERNETES CLUSTER TYPE 🎮              ║"
        echo "╚══════════════════════════════════════════════════════════════╝"
        echo ""

        echo "  1) 🐳 Kind"
        echo "     Development / learning / CI"
        echo ""
        echo "  2) 🚀 k3s"
        echo "     Lightweight Kubernetes"
        echo ""
        echo "  3) ☸️  Existing Kubernetes"
        echo "     kubeadm / bare metal / VM / cloud"
        echo ""

        read -r -p "Select cluster type [1-3] (default: 1): " CLUSTER_CHOICE

        case "${CLUSTER_CHOICE:-1}" in

            1)
                export K8S_CLUSTER_TYPE="kind"
                _use_kind
                ;;

            2)
                export K8S_CLUSTER_TYPE="k3s"
                _install_k3s
                ;;

            3)
                export K8S_CLUSTER_TYPE="bare"
                _use_bare_kubernetes
                ;;

            *)
                error "Invalid option."
                ;;
        esac

    fi

fi

# ============================================================
# Display final cluster information
# ============================================================

echo ""
echo "============================================================"
echo "☸️  Kubernetes Environment"
echo "============================================================"
echo ""

echo "Cluster type:"
echo "  ${K8S_CLUSTER_TYPE:-unknown}"

echo ""

echo "Context:"
kubectl config current-context

echo ""

echo "Server:"
kubectl cluster-info | head -1 || true

echo ""

echo "Nodes:"
kubectl get nodes

echo ""

echo "Namespace:"
kubectl get namespace "$NAMESPACE"

# ============================================================
# Run K8sQuest engine
# ============================================================

echo ""
echo "============================================================"
echo "🎮 Starting K8sQuest"
echo "============================================================"
echo ""

export K8S_CLUSTER_TYPE="${K8S_CLUSTER_TYPE:-bare}"

"$PYTHON" "$SCRIPT_DIR/engine/engine.py"
