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

ensure_qqbot_plugin() {
  if openclaw plugins list 2>/tmp/qqbot-plugin-list.err | grep -qi 'stock:qqbot/index.js\|qqbot.*enabled'; then
    return 0
  fi

  version="$(node -p 'require("/app/package.json").version' 2>/dev/null || true)"
  if [ -z "$version" ]; then
    log "qqbot plugin install skipped: unable to resolve OpenClaw version"
    cat /tmp/qqbot-plugin-list.err 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
    return 0
  fi

  spec="@openclaw/qqbot@$version"
  log "qqbot plugin unavailable; installing $spec"
  if openclaw plugins install "$spec" --force >/tmp/qqbot-plugin-install.out 2>/tmp/qqbot-plugin-install.err; then
    cat /tmp/qqbot-plugin-install.out 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  else
    log "qqbot plugin install failed"
    cat /tmp/qqbot-plugin-install.err 2>/dev/null | while IFS= read -r line; do log "$line"; done || true
  fi
}

patch_qqbot_reply_prefix() {
  python3 - <<'PY'
import re
import subprocess
from pathlib import Path

RUNTIME_MARKER = "OPENCLAW_QQBOT_REPLY_PREFIX_CONTEXT_PATCH_RUNTIME"
SOURCE_MARKER = "OPENCLAW_QQBOT_REPLY_PREFIX_CONTEXT_PATCH"
RUNTIME_ROOT = Path("/home/node/.openclaw/npm/node_modules/@openclaw/qqbot/dist")
SOURCE_TARGET = Path("/app/extensions/qqbot/src/engine/gateway/outbound-dispatch.ts")


def write_backup(target: Path, original: str, suffix: str) -> None:
    backup = target.with_suffix(target.suffix + suffix)
    if not backup.exists():
        backup.write_text(original, encoding="utf-8")


def patch_runtime(target: Path) -> bool:
    text = target.read_text(encoding="utf-8")
    if RUNTIME_MARKER in text:
        return False

    original = text
    import_anchor = 'import { implicitMentionKindWhen, resolveInboundMentionDecision } from "openclaw/plugin-sdk/channel-mention-gating";'
    if "openclaw/plugin-sdk/channel-reply-pipeline" not in text:
        if import_anchor not in text:
            raise SystemExit(f"qqbot reply prefix patch failed: runtime import anchor not found in {target}")
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
            f'\tconst {RUNTIME_MARKER} = "2026-05-05.2";\n'
            f"\tvoid {RUNTIME_MARKER};"
        ),
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"qqbot reply prefix patch failed: runtime dispatch block not found in {target}")

    text, count = re.subn(
        r"(dispatcherOptions:\s*\{\s*responsePrefix: messagesConfig\.responsePrefix,\s*)deliver:",
        r"\1responsePrefixContextProvider: replyPrefixContext.responsePrefixContextProvider,\n\t\t\t\t\t\t\tdeliver:",
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"qqbot reply prefix patch failed: runtime dispatcher prefix block not found in {target}")

    text, count = re.subn(
        r"(replyOptions:\s*\{\s*)disableBlockStreaming:",
        r"\1onModelSelected: replyPrefixContext.onModelSelected,\n\t\t\t\t\t\t\tdisableBlockStreaming:",
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"qqbot reply prefix patch failed: runtime replyOptions block not found in {target}")

    write_backup(target, original, ".bak-openclaw-prefix-runtime")
    target.write_text(text, encoding="utf-8")
    check = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True)
    if check.returncode != 0:
        target.write_text(original, encoding="utf-8")
        raise SystemExit(check.stderr or check.stdout or f"qqbot reply prefix patch failed: node --check failed for {target}")
    print(f"patched runtime {target}")
    return True


def patch_source(target: Path) -> bool:
    if not target.exists():
        return False
    text = target.read_text(encoding="utf-8")
    if SOURCE_MARKER in text:
        return False

    original = text
    import_line = 'import type { FinalizedMsgContext } from "openclaw/plugin-sdk/reply-runtime";\n'
    replacement_import = (
        'import { createReplyPrefixContext } from "openclaw/plugin-sdk/channel-reply-pipeline";\n'
        + import_line
    )
    if import_line not in text:
        raise SystemExit("qqbot reply prefix patch failed: source reply-runtime import not found")
    text = text.replace(import_line, replacement_import, 1)

    dispatch_block = """  // ---- Dispatch ----
  const messagesConfig = runtime.channel.reply.resolveEffectiveMessagesConfig(
    cfg,
    inbound.route.agentId,
  );
"""
    replacement_dispatch_block = f"""  // ---- Dispatch ----
  const replyPrefixContext = createReplyPrefixContext({{
    cfg,
    channel: "qqbot",
    accountId: inbound.route.accountId,
    agentId: inbound.route.agentId,
  }});
  const messagesConfig = {{ responsePrefix: replyPrefixContext.responsePrefix }};
  const {SOURCE_MARKER} = "2026-05-05.1";
  void {SOURCE_MARKER};
"""
    if dispatch_block not in text:
        raise SystemExit("qqbot reply prefix patch failed: source dispatch config block not found")
    text = text.replace(dispatch_block, replacement_dispatch_block, 1)

    dispatcher_prefix = """              responsePrefix: messagesConfig.responsePrefix,
              deliver: async (payload: ReplyDeliverPayload, info: { kind: string }) => {
"""
    replacement_dispatcher_prefix = """              responsePrefix: messagesConfig.responsePrefix,
              responsePrefixContextProvider: replyPrefixContext.responsePrefixContextProvider,
              deliver: async (payload: ReplyDeliverPayload, info: { kind: string }) => {
"""
    if dispatcher_prefix not in text:
        raise SystemExit("qqbot reply prefix patch failed: source dispatcher prefix block not found")
    text = text.replace(dispatcher_prefix, replacement_dispatcher_prefix, 1)

    reply_options = "            replyOptions: {\n"
    if reply_options not in text:
        raise SystemExit("qqbot reply prefix patch failed: source replyOptions block not found")
    text = text.replace(
        reply_options,
        reply_options + "              onModelSelected: replyPrefixContext.onModelSelected,\n",
        1,
    )

    write_backup(target, original, ".bak-openclaw-prefix")
    target.write_text(text, encoding="utf-8")
    print(f"patched source {target}")
    return True


patched_any = False
runtime_targets = sorted(RUNTIME_ROOT.glob("gateway-*.js")) if RUNTIME_ROOT.exists() else []
for target in runtime_targets:
    patched_any = patch_runtime(target) or patched_any
patched_any = patch_source(SOURCE_TARGET) or patched_any

if not runtime_targets and not SOURCE_TARGET.exists():
    raise SystemExit("qqbot reply prefix patch skipped: no QQBot runtime or source target found")
if not patched_any:
    print("qqbot reply prefix patch already present")
PY
  status=$?
  if [ "$status" -eq 0 ]; then
    log "qqbot reply prefix patch ensured"
  else
    log "qqbot reply prefix patch failed"
    return "$status"
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
ensure_qqbot_plugin
patch_qqbot_reply_prefix
ensure_browser_config

if [ "$#" -eq 0 ]; then
  set -- node openclaw.mjs gateway --allow-unconfigured
fi

exec docker-entrypoint.sh "$@"
