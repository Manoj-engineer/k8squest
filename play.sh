#!/bin/bash
# Quick launcher for K8sQuest

cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "❌ Virtual environment not found. Please run ./install.sh first"
  exit 1
fi

# Set PYTHONPATH to include the project root
export PYTHONPATH="$(pwd):$PYTHONPATH"

# Use venv Python directly (cross-platform)
if [ -f "venv/bin/python3" ]; then
  venv/bin/python3 engine/engine.py
elif [ -f "venv/Scripts/python.exe" ]; then
  venv/Scripts/python.exe engine/engine.py
else
  echo "❌ Virtual environment Python not found"
  exit 1
fi
