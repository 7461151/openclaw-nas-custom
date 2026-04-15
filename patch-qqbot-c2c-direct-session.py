#!/usr/bin/env python3
from pathlib import Path
import os
import re

MARKER = 'const routedSessionKey = event.type === "c2c" ? `agent:${typeof route.agentId'
PATCH_VERSION = "2026-04-16.3"
DEFAULT_DIST_DIR = Path("/app/dist")
LEGACY_ROUTE_MARKER = 'const routedSessionKey = event.type === "c2c" ? buildQQBotDirectSessionKey(route.agentId, event.senderId) : route.sessionKey;'
BASE_SNIPPETS = [
    'const route = pluginRuntime.channel.routing.resolveAgentRoute({',
    'SessionKey: route.sessionKey,',
    'sessionKey: route.sessionKey,',
]


def log(msg):
    print(f"[qqbot-c2c-direct-session] {msg}")


def resolve_dist_dir() -> Path:
    if len(__import__("sys").argv) > 1 and __import__("sys").argv[1].strip():
        return Path(__import__("sys").argv[1].strip())
    override = os.environ.get("OPENCLAW_DIST_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_DIST_DIR


def find_gateway_file(dist_dir: Path):
    patched_candidates = []
    legacy_candidates = []
    fresh_candidates = []
    for path in sorted(dist_dir.glob("gateway-*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if MARKER in text and "SessionKey: routedSessionKey," in text:
            patched_candidates.append(path)
            continue
        if LEGACY_ROUTE_MARKER in text and "SessionKey: routedSessionKey," in text:
            legacy_candidates.append(path)
            continue
        if all(snippet in text for snippet in BASE_SNIPPETS):
            fresh_candidates.append(path)
    if patched_candidates:
        return patched_candidates[0]
    if legacy_candidates:
        return legacy_candidates[0]
    if fresh_candidates:
        return fresh_candidates[0]
    raise RuntimeError("gateway target not found")


def replace_once_if_needed(text: str, old: str, new: str, marker: str, name: str) -> str:
    if marker in text:
        return text
    if old not in text:
        raise RuntimeError(f"{name} anchor missing")
    return text.replace(old, new, 1)


def patch_once(text: str) -> str:
    # Cleanup legacy helper block from the first draft of this patch.
    text = re.sub(
        r'const QQBOT_C2C_DIRECT_SESSION_PATCH = ".*?";\nfunction normalizeQQBotDirectSessionPeerId\(raw\) \{.*?\nfunction buildQQBotDirectSessionKey\(agentId, senderId\) \{.*?\n\}\n',
        "",
        text,
        count=1,
        flags=re.S,
    )
    inline_route_marker = 'const routedSessionKey = event.type === "c2c" ? `agent:${typeof route.agentId === "string" && route.agentId.trim() ? route.agentId.trim() : "main"}:qqbot:direct:${typeof event.senderId === "string" && event.senderId.trim() ? event.senderId.trim().toLowerCase() : "unknown"}` : route.sessionKey;'
    if LEGACY_ROUTE_MARKER in text:
        text = text.replace(LEGACY_ROUTE_MARKER, inline_route_marker, 1)

    text = replace_once_if_needed(
        text,
        'const route = pluginRuntime.channel.routing.resolveAgentRoute({\n\t\t\t\t\tcfg,\n\t\t\t\t\tchannel: "qqbot",\n\t\t\t\t\taccountId: account.accountId,\n\t\t\t\t\tpeer: {\n\t\t\t\t\t\tkind: isGroupChat ? "group" : "direct",\n\t\t\t\t\t\tid: peerId\n\t\t\t\t\t}\n\t\t\t\t});',
        'const route = pluginRuntime.channel.routing.resolveAgentRoute({\n\t\t\t\t\tcfg,\n\t\t\t\t\tchannel: "qqbot",\n\t\t\t\t\taccountId: account.accountId,\n\t\t\t\t\tpeer: {\n\t\t\t\t\t\tkind: isGroupChat ? "group" : "direct",\n\t\t\t\t\t\tid: peerId\n\t\t\t\t\t}\n\t\t\t\t});\n\t\t\t\tconst routedSessionKey = event.type === "c2c" ? `agent:${typeof route.agentId === "string" && route.agentId.trim() ? route.agentId.trim() : "main"}:qqbot:direct:${typeof event.senderId === "string" && event.senderId.trim() ? event.senderId.trim().toLowerCase() : "unknown"}` : route.sessionKey;\n\t\t\t\tif (routedSessionKey !== route.sessionKey) log?.info(`[qqbot:${account.accountId}] Routed c2c session ${route.sessionKey} -> ${routedSessionKey}`);',
        MARKER,
        "route session override",
    )

    text = replace_once_if_needed(
        text,
        "SessionKey: route.sessionKey,",
        "SessionKey: routedSessionKey,",
        "SessionKey: routedSessionKey,",
        "ctx session key",
    )

    text = replace_once_if_needed(
        text,
        "let currentModelLabel = resolveReplyModelLabel(route.sessionKey, cfg, route.agentId);",
        "let currentModelLabel = resolveReplyModelLabel(routedSessionKey, cfg, route.agentId);",
        "let currentModelLabel = resolveReplyModelLabel(routedSessionKey, cfg, route.agentId);",
        "model label session key",
    )

    text = replace_once_if_needed(
        text,
        "sessionKey: route.sessionKey,",
        "sessionKey: routedSessionKey,",
        "sessionKey: routedSessionKey,",
        "deliver session key",
    )

    return text


def main() -> int:
    gateway_file = find_gateway_file(resolve_dist_dir())
    original = gateway_file.read_text(encoding="utf-8")
    patched = patch_once(original)
    if patched == original:
        log(f"patch already present for {gateway_file.name} ({PATCH_VERSION})")
        return 0
    gateway_file.write_text(patched, encoding="utf-8")
    log(f"patched {gateway_file.name} -> {PATCH_VERSION}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"failed: {exc}")
        raise
