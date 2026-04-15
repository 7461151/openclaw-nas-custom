#!/bin/sh
set -eu

if [ -f /usr/local/bin/sync-gemini-cli-auth.py ]; then
  python3 /usr/local/bin/sync-gemini-cli-auth.py --quiet >/dev/null 2>&1 || true
fi

exec node /usr/local/lib/node_modules/@google/gemini-cli/bundle/gemini.js "$@"
