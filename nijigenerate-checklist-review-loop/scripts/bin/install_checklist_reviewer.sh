#!/usr/bin/env bash
set -euo pipefail

if (( $# > 1 )) || [[ ${1-x} == "" ]]; then
  echo 'Usage: install_checklist_reviewer.sh [new-directory]' >&2
  exit 2
fi
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$script_dir/install_checklist_reviewer.py" "${1:-./checklist-reviewer}"
