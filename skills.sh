#!/usr/bin/env bash
# Bash entry point for scripts/install.py; installation is optional and never runs with the skill.
set -euo pipefail
command -v python3 >/dev/null 2>&1 || {
  printf '%s\n' 'error: optional installer requires Python 3.10+ (python3)' >&2
  exit 127
}
exec python3 -B -c '
import runpy
import sys
from pathlib import Path
if sys.version_info < (3, 10):
    raise SystemExit("error: optional installer requires Python 3.10+")
script = Path(sys.argv.pop(1)).resolve().parent / "scripts" / "install.py"
sys.path.insert(0, str(script.parent))
sys.argv[0] = str(script)
runpy.run_path(str(script), run_name="__main__")
' "${BASH_SOURCE[0]}" "$@"
