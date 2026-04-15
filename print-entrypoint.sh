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

apply_qqbot_c2c_direct_session_patch() {
  if [ ! -f /usr/local/bin/patch-qqbot-c2c-direct-session.py ]; then
    log "qqbot c2c direct session patch script not found; skipping"
    return 0
  fi

  if python3 /usr/local/bin/patch-qqbot-c2c-direct-session.py >/tmp/qqbot-c2c-direct-session-patch.out 2>/tmp/qqbot-c2c-direct-session-patch.err; then
    cat /tmp/qqbot-c2c-direct-session-patch.out 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  else
    log "qqbot c2c direct session patch failed"
    cat /tmp/qqbot-c2c-direct-session-patch.err 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  fi
}

apply_control_ui_delivery_model_patch() {
  if [ ! -f /usr/local/bin/patch-control-ui-delivery-model.py ]; then
    log "control-ui delivery model patch script not found; skipping"
    return 0
  fi

  if python3 /usr/local/bin/patch-control-ui-delivery-model.py >/tmp/control-ui-delivery-model-patch.out 2>/tmp/control-ui-delivery-model-patch.err; then
    cat /tmp/control-ui-delivery-model-patch.out 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  else
    log "control-ui delivery model patch failed"
    cat /tmp/control-ui-delivery-model-patch.err 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  fi
}

apply_gemini_cli_provider_refresh_patch() {
  if [ ! -f /usr/local/bin/patch-gemini-cli-provider-refresh.py ]; then
    log "gemini provider refresh patch script not found; skipping"
    return 0
  fi

  if python3 /usr/local/bin/patch-gemini-cli-provider-refresh.py >/tmp/gemini-provider-refresh-patch.out 2>/tmp/gemini-provider-refresh-patch.err; then
    cat /tmp/gemini-provider-refresh-patch.out 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  else
    log "gemini provider refresh patch failed"
    cat /tmp/gemini-provider-refresh-patch.err 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  fi
}

sync_gemini_cli_auth() {
  if [ ! -f /usr/local/bin/sync-gemini-cli-auth.py ]; then
    log "gemini auth sync script not found; skipping"
    return 0
  fi

  if python3 /usr/local/bin/sync-gemini-cli-auth.py >/tmp/gemini-auth-sync.out 2>/tmp/gemini-auth-sync.err; then
    cat /tmp/gemini-auth-sync.out 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  else
    log "gemini auth sync failed"
    cat /tmp/gemini-auth-sync.err 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  fi
}

start_gemini_auth_sync_loop() {
  if [ ! -f /usr/local/bin/sync-gemini-cli-auth.py ]; then
    return 0
  fi

  interval="${GEMINI_AUTH_SYNC_INTERVAL:-15}"
  case "$interval" in
    ''|*[!0-9]*)
      interval=15
      ;;
  esac

  if [ "$interval" -le 0 ] 2>/dev/null; then
    log "gemini auth sync loop disabled"
    return 0
  fi

  (
    while true; do
      python3 /usr/local/bin/sync-gemini-cli-auth.py --quiet >/dev/null 2>&1 || true
      sleep "$interval"
    done
  ) &
  log "gemini auth sync loop started (interval: ${interval}s)"
}

start_cups
configure_printer
apply_qqbot_model_label_patch
apply_qqbot_c2c_direct_session_patch
apply_control_ui_delivery_model_patch
apply_gemini_cli_provider_refresh_patch
sync_gemini_cli_auth
start_gemini_auth_sync_loop

if [ "$#" -eq 0 ]; then
  set -- node openclaw.mjs gateway --allow-unconfigured
fi

exec docker-entrypoint.sh "$@"
