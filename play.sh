#!/bin/bash
# Quick launcher for K8sQuest

cd "$(dirname "$0")" || exit 1
source engine/python_env.sh || exit 1

# Resolve the Python interpreter to use, in priority order:
_find_python() {
  if [ -n "$CONDA_PREFIX" ]; then
    if   [ -f "$CONDA_PREFIX/bin/python3" ]; then echo "$CONDA_PREFIX/bin/python3"; return
    elif [ -f "$CONDA_PREFIX/bin/python"  ]; then echo "$CONDA_PREFIX/bin/python";  return
    fi
  fi
  if [ -n "$VIRTUAL_ENV" ]; then
    if   [ -f "$VIRTUAL_ENV/bin/python3"       ]; then echo "$VIRTUAL_ENV/bin/python3";       return
    elif [ -f "$VIRTUAL_ENV/Scripts/python.exe" ]; then echo "$VIRTUAL_ENV/Scripts/python.exe"; return
    fi
  fi
  if   [ -f "venv/bin/python3"       ]; then echo "venv/bin/python3";       return
  elif [ -f "venv/Scripts/python.exe" ]; then echo "venv/Scripts/python.exe"; return
  fi
}

# Function to check if a cluster is already running
_check_existing_clusters() {
  local has_kind=false
  local has_k3s=false

  # Check for kind clusters
  if command -v kind &> /dev/null; then
    if kind get clusters 2>/dev/null | grep -q .; then
      has_kind=true
    fi
  fi

  # Check for k3s
  if systemctl is-active --quiet k3s 2>/dev/null; then
    has_k3s=true
  elif [ -f /etc/rancher/k3s/k3s.yaml ] && kubectl --kubeconfig=/etc/rancher/k3s/k3s.yaml get nodes &> /dev/null; then
    has_k3s=true
  fi

  if $has_kind && $has_k3s; then
    echo "both"
  elif $has_kind; then
    echo "kind"
  elif $has_k3s; then
    echo "k3s"
  else
    echo "none"
  fi
}

# Function to set up k3s kubeconfig
_setup_k3s_kubeconfig() {
  local default_kubeconfig="/etc/rancher/k3s/k3s.yaml"
  
  # Check if k3s is running
  if ! systemctl is-active --quiet k3s 2>/dev/null; then
    echo "ℹ️  k3s is installed but not running. Starting..."
    sudo systemctl start k3s
    echo "⏳ Waiting for k3s to start..."
    local k3s_attempt=0
    until timeout 10 k3s kubectl get nodes &> /dev/null; do
      k3s_attempt=$((k3s_attempt + 1))
      if [ $k3s_attempt -ge 90 ]; then
        echo "❌ k3s failed to start within 3 minutes"
        return 1
      fi
      sleep 2
    done
  fi
  
  # Ask for custom kubeconfig path
  echo ""
  echo "Default k3s kubeconfig location: $default_kubeconfig"
  echo "Note: This file requires root permissions to read."
  read -p "Enter custom path for kubeconfig (or press Enter for default: $HOME/.kube/k3s-config): " CUSTOM_KUBECONFIG
  
  if [ -z "$CUSTOM_KUBECONFIG" ]; then
    CUSTOM_KUBECONFIG="$HOME/.kube/k3s-config"
  fi
  
  # If custom path is not the default, copy it
  if [ "$CUSTOM_KUBECONFIG" != "$default_kubeconfig" ]; then
    echo "ℹ️  Using custom kubeconfig path: $CUSTOM_KUBECONFIG"
    echo "📦 Copying k3s kubeconfig to $CUSTOM_KUBECONFIG..."
    mkdir -p "$(dirname "$CUSTOM_KUBECONFIG")"
    sudo cp "$default_kubeconfig" "$CUSTOM_KUBECONFIG"
    sudo chown "$USER:$USER" "$CUSTOM_KUBECONFIG"
    export KUBECONFIG="$CUSTOM_KUBECONFIG"
  else
    # Copy to user-accessible location anyway
    echo "📦 Copying k3s kubeconfig to $HOME/.kube/k3s-config..."
    mkdir -p "$HOME/.kube"
    sudo cp "$default_kubeconfig" "$HOME/.kube/k3s-config"
    sudo chown "$USER:$USER" "$HOME/.kube/k3s-config"
    export KUBECONFIG="$HOME/.kube/k3s-config"
  fi
  
  _rename_k3s_context "$KUBECONFIG"

  # Symlink default kubeconfig so new terminals auto-use this config
  if [ -f "$HOME/.kube/config" ] && [ ! -L "$HOME/.kube/config" ]; then
    cp "$HOME/.kube/config" "$HOME/.kube/config.k8squest.bak"
    echo "ℹ️  Backed up ~/.kube/config → ~/.kube/config.k8squest.bak (your existing config is preserved there)"
  fi
  ln -snf "$KUBECONFIG" "$HOME/.kube/config"

  echo "✅ k3s cluster is ready (kubeconfig: $KUBECONFIG)"
}

# Rename k3s context from 'default' to 'k3s-k8squest'
_rename_k3s_context() {
  local kubeconfig="$1"
  local new_ctx="k3s-k8squest"
  local tmp_dir="/tmp/k8squest-k3s-$$"

  [ ! -f "$kubeconfig" ] && return

  local cur_ctx
  cur_ctx=$(kubectl --kubeconfig="$kubeconfig" config view -o jsonpath='{.current-context}' 2>/dev/null)
  [ "$cur_ctx" = "$new_ctx" ] && return

  echo "🔄 Renaming k3s context from '$cur_ctx' to '$new_ctx'..."

  local json
  json=$(kubectl --kubeconfig="$kubeconfig" config view --raw -o json 2>/dev/null)

  local server ca_data cert_data key_data
  server=$(echo "$json" | jq -r --arg ctx "$cur_ctx" '.clusters[] | select(.name==$ctx) | .cluster.server')
  ca_data=$(echo "$json" | jq -r --arg ctx "$cur_ctx" '.clusters[] | select(.name==$ctx) | .cluster["certificate-authority-data"] // empty')
  cert_data=$(echo "$json" | jq -r --arg ctx "$cur_ctx" '.users[] | select(.name==$ctx) | .user["client-certificate-data"] // empty')
  key_data=$(echo "$json" | jq -r --arg ctx "$cur_ctx" '.users[] | select(.name==$ctx) | .user["client-key-data"] // empty')

  if [ -z "$server" ]; then
    echo "❌ Failed to extract cluster '$cur_ctx' from kubeconfig"
    return 1
  fi

  # Write cert data to temp files (old kubectl doesn't have --*-data flags)
  mkdir -p "$tmp_dir"
  echo "$ca_data" | tr -d '\n' | base64 -d > "$tmp_dir/ca.crt" 2>/dev/null
  echo "$cert_data" | tr -d '\n' | base64 -d > "$tmp_dir/client.crt" 2>/dev/null
  echo "$key_data" | tr -d '\n' | base64 -d > "$tmp_dir/client.key" 2>/dev/null

  kubectl --kubeconfig="$kubeconfig" config set-cluster "$new_ctx" \
    --server="$server" --certificate-authority="$tmp_dir/ca.crt" --embed-certs

  kubectl --kubeconfig="$kubeconfig" config set-credentials "$new_ctx" \
    --client-certificate="$tmp_dir/client.crt" --client-key="$tmp_dir/client.key" --embed-certs

  kubectl --kubeconfig="$kubeconfig" config set-context "$new_ctx" \
    --cluster="$new_ctx" --user="$new_ctx" --namespace="k8squest"

  kubectl --kubeconfig="$kubeconfig" config use-context "$new_ctx"

  rm -rf "$tmp_dir"
}

# Function to install k3s
_install_k3s() {
  echo "🔧 Setting up k3s cluster..."
  if ! command -v k3s &> /dev/null; then
    # Remove any dangling kubectl symlink from a previous uninstall
    if [ -L /usr/local/bin/kubectl ] && [ ! -e /usr/local/bin/kubectl ]; then
      echo "🧹 Removing stale kubectl symlink..."
      sudo rm -f /usr/local/bin/kubectl
    fi
    echo "📦 Installing k3s..."
    curl -sfL https://get.k3s.io | sh -s - server \
      --cluster-init \
      --disable traefik \
      --write-kubeconfig-mode 644
    if [ $? -ne 0 ]; then
      echo "❌ Failed to install k3s"
      exit 1
    fi
    hash -r
    echo "⏳ Waiting for k3s to start..."
    local k3s_attempt=0
    until timeout 10 k3s kubectl get nodes &> /dev/null; do
      k3s_attempt=$((k3s_attempt + 1))
      if [ $k3s_attempt -ge 90 ]; then
        echo "❌ k3s failed to start within 3 minutes"
        exit 1
      fi
      sleep 2
    done
  else
    echo "ℹ️  k3s is already installed. Starting service if not running..."
    sudo systemctl start k3s || true
  fi
  _setup_k3s_kubeconfig
  
  # Run k3s compatibility setup
  if [ -f "$(dirname "$0")/k3s-setup.sh" ]; then
    echo "🔧 Running k3s compatibility setup for K8sQuest..."
    bash "$(dirname "$0")/k3s-setup.sh"
  fi
}

PYTHON=$(_find_python)
if [ -z "$PYTHON" ]; then
  echo "❌ No Python environment found. Please run ./install.sh first"
  echo "   Supported: conda env, virtualenv, or project venv (created by install.sh)"
  exit 1
fi

if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'; then
  echo "❌ K8sQuest requires Python 3.9+ in the selected environment: $PYTHON"
  exit 1
fi

if ! python_dependencies_ready "$PYTHON"; then
  if ! install_python_dependencies "$PYTHON"; then
    echo "❌ Python dependency setup failed. Fix the error above and run ./play.sh again."
    exit 1
  fi
fi

# Check and install jq if needed (required for some level validations)
if ! command -v jq &> /dev/null; then
    echo "📦 jq not found. Installing jq (required for Level 33 and other validations)..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install jq || { echo "❌ Failed to install jq. Please install manually: brew install jq"; exit 1; }
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        sudo apt-get update && sudo apt-get install -y jq || { echo "❌ Failed to install jq. Please install manually: sudo apt-get install jq"; exit 1; }
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        echo "💡 For Windows, please install jq manually:"
        echo "   Option 1 (Chocolatey): choco install jq"
        echo "   Option 2 (Scoop): scoop install jq"
        echo "   Option 3: Download from https://stedolan.github.io/jq/download/"
        exit 1
    else
        echo "❌ Unsupported OS. Please install jq manually."
        echo "💡 Download from: https://stedolan.github.io/jq/download/"
        exit 1
    fi
    echo "✅ jq installed successfully"
fi

# Set PYTHONPATH to include the project root
export PYTHONPATH="$(pwd):$PYTHONPATH"

# Check for existing clusters
EXISTING_CLUSTER=$(_check_existing_clusters)

if [ "$EXISTING_CLUSTER" != "none" ] && [ -z "$K8S_CLUSTER_TYPE" ]; then
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  ⚠️  Detected existing $EXISTING_CLUSTER cluster(s) running!  ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""
  if [ "$EXISTING_CLUSTER" = "both" ]; then
    echo "📊 Both 🐳 kind and 🚀 k3s clusters are detected."
    echo ""
    echo "  Options:"
    echo "    1) 🐳 Use existing kind cluster"
    echo "    2) 🚀 Use existing k3s cluster"
    echo "    3) 🔄 Reinstall/restart k3s (will not affect kind)"
    echo "    4) ⏭️  Continue without changes (use current kubectl context)"
    echo ""
    read -p "  Select option [1-4] (default: 1): " CLUSTER_CHOICE
    case $CLUSTER_CHOICE in
      2)
        echo "  ✅ Using existing k3s cluster"
        export K8S_CLUSTER_TYPE=k3s
        _setup_k3s_kubeconfig
        ;;
      3)
        export K8S_CLUSTER_TYPE=k3s
        _install_k3s
        ;;
      4)
        echo "  ✅ Using current kubectl context"
        ;;
      *)
        echo "  ✅ Using existing kind cluster"
        export K8S_CLUSTER_TYPE=kind
        ;;
    esac
  else
    echo "  📊 An existing 🐳 $EXISTING_CLUSTER cluster is detected."
    echo ""
    read -p "  Do you want to use the existing $EXISTING_CLUSTER cluster? [Y/n]: " USE_EXISTING
    case $USE_EXISTING in
      [Nn]*)
        if [ "$EXISTING_CLUSTER" = "k3s" ]; then
          export K8S_CLUSTER_TYPE=k3s
          _install_k3s
        else
          echo "  ✅ Using kind cluster"
          export K8S_CLUSTER_TYPE=kind
        fi
        ;;
      *)
        echo "  ✅ Using existing $EXISTING_CLUSTER cluster"
        if [ "$EXISTING_CLUSTER" = "k3s" ]; then
          export K8S_CLUSTER_TYPE=k3s
          _setup_k3s_kubeconfig
        else
          export K8S_CLUSTER_TYPE=kind
        fi
        ;;
    esac
  fi
else
  # Cluster selection prompt (only if no existing cluster detected or K8S_CLUSTER_TYPE is set)
  if [ -z "$K8S_CLUSTER_TYPE" ]; then
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════╗"
    echo "║          🎮 SELECT YOUR KUBERNETES CLUSTER TYPE 🎮             ║"
    echo "╚══════════════════════════════════════════════════════════════════╝"
    echo ""
    echo "  1) 🐳 kind  - Multi-node clusters in Docker containers"
    echo "     └─ Perfect for: Learning, development, CI/CD pipelines"
    echo "     └─ Pros: Easy setup, runs anywhere Docker runs, fast reset"
    echo "     └─ Cons: Requires Docker, not production-like networking"
    echo ""
    echo "  2) 🚀 k3s  - Lightweight production-ready Kubernetes"
    echo "     └─ Perfect for: Edge, IoT, local production-like testing"
    echo "     └─ Pros: Real cluster, no Docker needed, closer to production"
    echo "     └─ Cons: Uses system resources, single-node by default"
    echo ""
    read -p "Select cluster type [1/2] (default: kind): " CLUSTER_CHOICE
    case $CLUSTER_CHOICE in
      2|k3s|K3s)
        export K8S_CLUSTER_TYPE=k3s
        _install_k3s
        ;;
      *)
        echo "✅ Using kind cluster"
        export K8S_CLUSTER_TYPE=kind
        ;;
    esac
  fi
fi

# When using kind, remove k3s symlink to restore default kubeconfig
_remove_k3s_symlink() {
  local default_kube="$HOME/.kube/config"
  if [ -L "$default_kube" ]; then
    local target
    target="$(readlink "$default_kube")"
    if [ "$target" = "k3s-config" ] || [ "$target" = "$HOME/.kube/k3s-config" ]; then
      rm "$default_kube"
      if [ -f "$HOME/.kube/config.k8squest.bak" ]; then
        mv "$HOME/.kube/config.k8squest.bak" "$default_kube"
        echo "ℹ️  Restored ~/.kube/config from backup (~/.kube/config.k8squest.bak)"
      fi
    fi
  fi
}

if [ "${K8S_CLUSTER_TYPE:-}" = "kind" ]; then
  _remove_k3s_symlink
fi

# Ensure KUBECONFIG is set for the engine
if [ "$K8S_CLUSTER_TYPE" = "k3s" ] && [ -z "${KUBECONFIG:-}" ] && [ -f "$HOME/.kube/k3s-config" ]; then
  export KUBECONFIG="$HOME/.kube/k3s-config"
  echo "ℹ️  Using kubeconfig: $KUBECONFIG"
fi

"$PYTHON" engine/engine.py
