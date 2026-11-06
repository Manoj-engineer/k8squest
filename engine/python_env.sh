python_dependencies_ready() {
  "$1" -c 'import yaml; import rich' >/dev/null 2>&1
}

install_python_dependencies() {
  local python="$1"

  echo "📦 Installing Python dependencies for $python..."
  if "$python" -m pip --version >/dev/null 2>&1; then
    "$python" -m pip install -r requirements.txt || return 1
  elif "$python" -c 'import ensurepip' >/dev/null 2>&1; then
    "$python" -m ensurepip --upgrade || return 1
    "$python" -m pip install -r requirements.txt || return 1
  elif command -v uv >/dev/null 2>&1; then
    uv pip install --python "$python" -r requirements.txt || return 1
  else
    echo "❌ This Python environment has neither pip nor ensurepip."
    echo "   On Debian/Ubuntu, install the matching python3-venv package."
    printf '   Then run: %q -m ensurepip --upgrade\n' "$python"
    echo "   Alternatively, install uv and run ./play.sh again."
    return 1
  fi

  if ! python_dependencies_ready "$python"; then
    echo "❌ PyYAML and rich still cannot be imported by $python."
    return 1
  fi
}
