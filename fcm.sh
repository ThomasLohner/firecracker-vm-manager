#!/bin/bash

# fcm - Firecracker VM Manager Wrapper Script
# This script manages the Python virtual environment and dependencies
# for the Firecracker VM Manager

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"
VM_MANAGER_SCRIPT="$SCRIPT_DIR/firecracker_vm_manager.py"

# Check if virtual environment exists, create if not
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Check if required modules are installed
# Note: Package names vs import names differ for some packages
REQUIRED_PACKAGES=("requests" "requests-unixsocket")
IMPORT_NAMES=("requests" "requests_unixsocket")
MISSING_MODULES=()

for i in "${!IMPORT_NAMES[@]}"; do
    if ! python -c "import ${IMPORT_NAMES[$i]}" &> /dev/null; then
        MISSING_MODULES+=("${REQUIRED_PACKAGES[$i]}")
    fi
done

# Install missing modules
if [ ${#MISSING_MODULES[@]} -gt 0 ]; then
    echo "Installing missing Python modules: ${MISSING_MODULES[*]}"
    pip install "${MISSING_MODULES[@]}"
fi

# Check if firecracker_vm_manager.py exists
if [ ! -f "$VM_MANAGER_SCRIPT" ]; then
    echo "Error: firecracker_vm_manager.py not found in $SCRIPT_DIR"
    exit 1
fi

# Execute the VM manager with all arguments
exec python "$VM_MANAGER_SCRIPT" "$@"