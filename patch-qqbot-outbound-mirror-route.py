#!/usr/bin/env python3
from pathlib import Path
import os
import re
import sys

MARKER = "QQBOT_OUTBOUND_MIRROR_ROUTE_PATCH"
PATCH_VERSION = "2026-04-16.1"
DEFAULT_DIST_DIR = Path("/app/dist")

HELPER_BLOCK = f'''const {MARKER} = "{PATCH_VERSION}";
function normalizeQQBotOutboundMirrorSessionKey(raw) {{
\tconst trimmed = typeof raw === "string" ? raw.trim() : "";
\tif (!trimmed) return "";
\tif (/^agent:[^:]+:qqbot:direct:[^:]+$/i.test(trimmed)) return trimmed;
\tconst legacyMatch = /^agent:([^:]+):qqbot:group:c2c:(.+)$/i.exec(trimmed);
\tif (!legacyMatch) return "";
\tconst agentId = typeof legacyMatch[1] === "string" && legacyMatch[1].trim() ? legacyMatch[1].trim() : "main";
\tconst peerId = typeof legacyMatch[2] === "string" && legacyMatch[2].trim() ? legacyMatch[2].trim().toLowerCase() : "unknown";
\treturn `agent:${{agentId}}:qqbot:direct:${{peerId}}`;
}}
function preferCurrentQQBotMirrorRoute(route, params) {{
\tconst channel = typeof params?.channel === "string" ? params.channel.trim().toLowerCase() : "";
\tif (channel !== "qqbot") return route;
\tconst preferredSessionKey = normalizeQQBotOutboundMirrorSessionKey(params?.currentSessionKey);
\tif (!preferredSessionKey) return route;
\tif (!route || typeof route !== "object") return route;
\tconst resolvedKind = typeof params?.resolvedTarget?.kind === "string" ? params.resolvedTarget.kind.trim().toLowerCase() : "";
\tconst routeChatType = typeof route.chatType === "string" ? route.chatType.trim().toLowerCase() : "";
\tif (resolvedKind && resolvedKind !== "user") return route;
\tif (routeChatType && routeChatType !== "direct") return route;
\tif (typeof route.sessionKey === "string" && route.sessionKey.trim() === preferredSessionKey) return route;
\treturn {{
\t\t...route,
\t\tsessionKey: preferredSessionKey,
\t\t...typeof route.baseSessionKey === "string" ? {{ baseSessionKey: preferredSessionKey }} : {{}}
\t}};
}}
'''

ROUTE_DECL = """\tconst outboundRoute = params.agentId && !params.dryRun ? await params.resolveOutboundSessionRoute({
\t\tcfg: params.cfg,
\t\tchannel: params.channel,
\t\tagentId: params.agentId,
\t\taccountId: params.accountId,
\t\ttarget: params.to,
\t\tcurrentSessionKey: params.currentSessionKey,
\t\tresolvedTarget: params.resolvedTarget,
\t\treplyToId,
\t\tthreadId: resolvedThreadId
\t}) : null;"""

OUTBOUND_ROUTE_PATCH_LINE = "\tconst effectiveOutboundRoute = preferCurrentQQBotMirrorRoute(outboundRoute, params);"
ENSURE_OLD = """\tif (outboundRoute && params.agentId && !params.dryRun) await params.ensureOutboundSessionEntry({
\t\tcfg: params.cfg,
\t\tchannel: params.channel,
\t\taccountId: params.accountId,
\t\troute: outboundRoute
\t});"""
ENSURE_NEW = """\tif (effectiveOutboundRoute && params.agentId && !params.dryRun) await params.ensureOutboundSessionEntry({
\t\tcfg: params.cfg,
\t\tchannel: params.channel,
\t\taccountId: params.accountId,
\t\troute: effectiveOutboundRoute
\t});"""
SESSIONKEY_OLD = "\tif (outboundRoute && !params.dryRun) params.actionParams.__sessionKey = outboundRoute.sessionKey;"
SESSIONKEY_NEW = "\tif (effectiveOutboundRoute && !params.dryRun) params.actionParams.__sessionKey = effectiveOutboundRoute.sessionKey;"
RETURN_OLD = """\treturn {
\t\tresolvedThreadId,
\t\toutboundRoute
\t};"""
RETURN_NEW = """\treturn {
\t\tresolvedThreadId,
\t\toutboundRoute: effectiveOutboundRoute
\t};"""


def log(message: str) -> None:
    print(f"[qqbot-outbound-mirror-route] {message}")


def resolve_dist_dir() -> Path:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return Path(sys.argv[1].strip())
    override = os.environ.get("OPENCLAW_DIST_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_DIST_DIR


def find_target_files(dist_dir: Path) -> list[Path]:
    anchor = "async function prepareOutboundMirrorRoute(params) {"
    candidates: list[Path] = []
    for path in sorted(dist_dir.glob("message-action-runner-*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if anchor not in text:
            continue
        if MARKER in text or ROUTE_DECL in text:
            candidates.append(path)
    if not candidates:
        raise RuntimeError("message-action-runner target not found")
    return candidates


def ensure_helper_block(text: str) -> str:
    anchor = "async function prepareOutboundMirrorRoute(params) {"
    if MARKER in text:
        pattern = re.compile(
            rf'const {MARKER} = ".*?";\nfunction normalizeQQBotOutboundMirrorSessionKey\(raw\) \{{.*?\n\}}\nfunction preferCurrentQQBotMirrorRoute\(route, params\) \{{.*?\n\}}\n',
            re.S,
        )
        if not pattern.search(text):
            raise RuntimeError("existing outbound mirror helper block marker found but shape changed")
        return pattern.sub(HELPER_BLOCK, text, count=1)
    if anchor not in text:
        raise RuntimeError("prepareOutboundMirrorRoute anchor missing")
    return text.replace(anchor, HELPER_BLOCK + anchor, 1)


def replace_once_if_needed(text: str, old: str, new: str, marker: str, name: str) -> str:
    if marker in text:
        return text
    if old not in text:
        raise RuntimeError(f"{name} anchor missing")
    return text.replace(old, new, 1)


def patch_text(text: str) -> str:
    text = ensure_helper_block(text)
    text = replace_once_if_needed(
        text,
        ROUTE_DECL,
        ROUTE_DECL + "\n" + OUTBOUND_ROUTE_PATCH_LINE,
        OUTBOUND_ROUTE_PATCH_LINE,
        "effective outbound route insertion",
    )
    text = replace_once_if_needed(
        text,
        ENSURE_OLD,
        ENSURE_NEW,
        ENSURE_NEW,
        "effective outbound route ensure",
    )
    text = replace_once_if_needed(
        text,
        SESSIONKEY_OLD,
        SESSIONKEY_NEW,
        SESSIONKEY_NEW,
        "effective outbound route session key propagation",
    )
    text = replace_once_if_needed(
        text,
        RETURN_OLD,
        RETURN_NEW,
        RETURN_NEW,
        "effective outbound route return",
    )
    return text


def main() -> int:
    dist_dir = resolve_dist_dir()
    targets = find_target_files(dist_dir)
    changed = False
    for target in targets:
        original = target.read_text(encoding="utf-8")
        patched = patch_text(original)
        if patched == original:
            log(f"patch already present for {target.name} ({PATCH_VERSION})")
            continue
        target.write_text(patched, encoding="utf-8")
        changed = True
        log(f"patched {target.name} -> {PATCH_VERSION}")
    if not changed:
        log(f"patch already present for {len(targets)} file(s) ({PATCH_VERSION})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"failed: {exc}")
        raise
