#!/usr/bin/env bash
# File managers may require "Allow executing as a program" / "Run in Terminal".
set -u
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)" || exit 1
cd -- "$project_dir" || exit 1
if [[ -x "$project_dir/.venv/bin/python" ]]; then
    python_command="$project_dir/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    python_command="$(command -v python3)"
else
    echo 'Python 3 belum terpasang. Lihat README.md untuk paket distro Anda.' >&2
    exit 1
fi
"$python_command" "$project_dir/scripts/bootstrap.py" --launch
result=$?
if [[ "$result" -ne 0 && -t 0 ]]; then
    read -r -p 'Tekan Enter untuk menutup jendela...' || true
fi
exit "$result"
