#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if [[ ! -f "processed/lexical_index.json" ]]; then
  echo "Index not found: processed/lexical_index.json"
  echo "Run build first: ./build.sh"
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  echo "Virtual environment not found: .venv"
  echo "Run build first: ./build.sh"
  exit 1
fi

BASE_PORT="${WEB_SERVER_PORT:-7860}"
if [[ ! "$BASE_PORT" =~ ^[0-9]+$ ]]; then
  BASE_PORT="7860"
fi

SELECTED_PORT="$(python3 - "$BASE_PORT" <<'PY'
import socket
import sys

start = int(sys.argv[1])
end = start + 50
host = "127.0.0.1"

for port in range(start, end + 1):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind((host, port))
    except OSError:
        pass
    else:
        print(port)
        sock.close()
        raise SystemExit(0)
    finally:
        sock.close()

raise SystemExit(1)
PY
)"

if [[ -z "${SELECTED_PORT:-}" ]]; then
  echo "Cannot find free port in range ${BASE_PORT}-$((BASE_PORT + 50))"
  echo "Set WEB_SERVER_PORT manually and retry"
  exit 1
fi

if [[ "$SELECTED_PORT" != "$BASE_PORT" ]]; then
  echo "Port $BASE_PORT is busy, using $SELECTED_PORT"
fi
echo "Starting app on http://127.0.0.1:${SELECTED_PORT}"

export WEB_SERVER_PORT="$SELECTED_PORT"
exec ".venv/bin/python" app.py
