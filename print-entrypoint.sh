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

patch_qqbot_dynamic_response_prefix() {
  python3 - <<'PY'
import re
import subprocess
from pathlib import Path

MARKER = "OPENCLAW_QQBOT_DYNAMIC_RESPONSE_PREFIX_PATCH"
RUNTIME_ROOT = Path("/home/node/.openclaw/npm/node_modules/@openclaw/qqbot/dist")


def patch_runtime(target: Path) -> bool:
    text = target.read_text(encoding="utf-8")
    if MARKER in text:
        return False

    original = text
    import_anchor = 'import { implicitMentionKindWhen, resolveInboundMentionDecision } from "openclaw/plugin-sdk/channel-mention-gating";'
    if "openclaw/plugin-sdk/channel-reply-pipeline" not in text:
        if import_anchor not in text:
            raise RuntimeError(f"dynamic prefix import anchor not found in {target}")
        text = text.replace(
            import_anchor,
            'import { createReplyPrefixContext } from "openclaw/plugin-sdk/channel-reply-pipeline";\n'
            + import_anchor,
            1,
        )

    text, count = re.subn(
        r"const messagesConfig = runtime\.channel\.reply\.resolveEffectiveMessagesConfig\(cfg, inbound\.route\.agentId\);",
        (
            'const replyPrefixContext = createReplyPrefixContext({\n'
            '\t\tcfg,\n'
            '\t\tchannel: "qqbot",\n'
            "\t\taccountId: inbound.route.accountId,\n"
            "\t\tagentId: inbound.route.agentId\n"
            "\t});\n"
            "\tconst messagesConfig = { responsePrefix: replyPrefixContext.responsePrefix };\n"
            f'\tconst {MARKER} = "2026-05-07.1";\n'
            f"\tvoid {MARKER};"
        ),
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"dynamic prefix dispatch block not found in {target}")

    text, count = re.subn(
        r"(dispatcherOptions:\s*\{\s*responsePrefix: messagesConfig\.responsePrefix,\s*)deliver:",
        r"\1responsePrefixContextProvider: replyPrefixContext.responsePrefixContextProvider,\n\t\t\t\t\t\t\tdeliver:",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"dynamic prefix dispatcher options block not found in {target}")

    text, count = re.subn(
        r"(replyOptions:\s*\{\s*)disableBlockStreaming:",
        r"\1onModelSelected: replyPrefixContext.onModelSelected,\n\t\t\t\t\t\t\tdisableBlockStreaming:",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"dynamic prefix replyOptions block not found in {target}")

    target.write_text(text, encoding="utf-8")
    check = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True)
    if check.returncode != 0:
        target.write_text(original, encoding="utf-8")
        raise RuntimeError(check.stderr or check.stdout or f"node --check failed for {target}")
    print(f"patched {target}")
    return True


if not RUNTIME_ROOT.exists():
    print("qqbot dynamic response prefix patch skipped: official qqbot plugin not installed")
    raise SystemExit(0)

targets = sorted(RUNTIME_ROOT.glob("gateway-*.js"))
if not targets:
    print("qqbot dynamic response prefix patch skipped: no gateway runtime found")
    raise SystemExit(0)

patched_any = False
for target in targets:
    patched_any = patch_runtime(target) or patched_any

if not patched_any:
    print("qqbot dynamic response prefix patch already present")
PY
  status=$?
  if [ "$status" -eq 0 ]; then
    log "qqbot dynamic response prefix patch ensured"
  else
    log "qqbot dynamic response prefix patch failed; continuing without dynamic prefix"
  fi
  return 0
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
patch_qqbot_dynamic_response_prefix
ensure_browser_config

if [ "$#" -eq 0 ]; then
  set -- node openclaw.mjs gateway --allow-unconfigured
fi

exec docker-entrypoint.sh "$@"
