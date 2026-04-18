#!/bin/sh
set -eu

log() {
  printf '%s\n' "[print-init] $*"
}

start_cups() {
  mkdir -p /run/cups/certs /var/spool/cups/tmp /var/cache/cups
  pkill cupsd >/dev/null 2>&1 || true
  /usr/sbin/cupsd -f >/tmp/cupsd.out 2>/tmp/cupsd.err &
  i=0
  while [ "$i" -lt 10 ]; do
    if lpstat -r >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
    i=$((i+1))
  done
  log "cups scheduler unavailable after startup"
  cat /tmp/cupsd.err 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  return 0
}

configure_printer() {
  PRINTER_NAME="${PRINTER_NAME:-}"
  PRINTER_URI="${PRINTER_URI:-}"
  PRINTER_PPD="${PRINTER_PPD:-}"

  if [ -z "$PRINTER_NAME" ] || [ -z "$PRINTER_URI" ]; then
    log "PRINTER_NAME or PRINTER_URI not set; skipping printer setup"
    return 0
  fi

  if ! lpstat -r >/dev/null 2>&1; then
    log "cups scheduler unavailable; skipping printer setup"
    return 0
  fi

  if ! lpstat -p "$PRINTER_NAME" >/dev/null 2>&1; then
    log "creating printer queue $PRINTER_NAME -> $PRINTER_URI"
    if [ -n "$PRINTER_PPD" ] && [ -f "$PRINTER_PPD" ]; then
      lpadmin -p "$PRINTER_NAME" -E -v "$PRINTER_URI" -P "$PRINTER_PPD" >/dev/null 2>&1 || log "ESC/P-R queue setup failed"
    else
      if ! lpadmin -p "$PRINTER_NAME" -E -v "$PRINTER_URI" -m everywhere >/dev/null 2>&1; then
        log "driverless setup failed; retrying raw queue"
        lpadmin -p "$PRINTER_NAME" -E -v "$PRINTER_URI" -m raw >/dev/null 2>&1 || log "raw queue setup failed"
      fi
    fi
  fi

  lpadmin -p "$PRINTER_NAME" -o PageSize=A4 -o MediaType=PLAIN_HIGH >/dev/null 2>&1 || true
  lpadmin -d "$PRINTER_NAME" >/dev/null 2>&1 || true
  lpstat -d 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
}

apply_qqbot_model_label_patch() {
  if [ ! -f /usr/local/bin/patch-qqbot-model-label.py ]; then
    log "qqbot model label patch script not found; skipping"
    return 0
  fi

  if python3 /usr/local/bin/patch-qqbot-model-label.py >/tmp/qqbot-model-label-patch.out 2>/tmp/qqbot-model-label-patch.err; then
    cat /tmp/qqbot-model-label-patch.out 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  else
    log "qqbot model label patch failed"
    cat /tmp/qqbot-model-label-patch.err 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  fi
}

ensure_browser_config() {
  config_path="/home/node/.openclaw/openclaw.json"

  mkdir -p /home/node/.openclaw

  python3 - "$config_path" <<'PY'
import json
import os
import sys
from pathlib import Path

config_path = Path(sys.argv[1])

if config_path.exists():
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        raise SystemExit("invalid openclaw.json; refusing to rewrite browser config")
else:
    config = {}

browser = config.setdefault("browser", {})
browser.setdefault("enabled", True)
browser.setdefault("defaultProfile", "openclaw")
browser.setdefault("headless", True)
browser.setdefault("noSandbox", True)

if os.path.exists("/usr/bin/chromium"):
    browser.setdefault("executablePath", "/usr/bin/chromium")

config_path.write_text(
    json.dumps(config, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

  log "browser defaults ensured for headless Chromium"
}

start_cups
configure_printer
apply_qqbot_model_label_patch
ensure_browser_config

if [ "$#" -eq 0 ]; then
  set -- node openclaw.mjs gateway --allow-unconfigured
fi

exec docker-entrypoint.sh "$@"
