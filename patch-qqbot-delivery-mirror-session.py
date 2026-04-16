#!/usr/bin/env python3
from pathlib import Path
import os
import re
import sys

MARKER = "QQBOT_DELIVERY_MIRROR_SESSION_PATCH"
PATCH_VERSION = "2026-04-16.1"
DEFAULT_DIST_DIR = Path("/app/dist")
BASE_SNIPPETS = [
    "async function appendAssistantMessageToSessionTranscript(params) {",
    "async function appendExactAssistantMessageToSessionTranscript(params) {",
]

HELPER_BLOCK = f'''const {MARKER} = "{PATCH_VERSION}";
function normalizeQQBotMirrorSessionKey(raw) {{
\tconst trimmed = typeof raw === "string" ? raw.trim() : "";
\tif (!trimmed) return "";
\tconst match = /^agent:([^:]+):qqbot:group:c2c:(.+)$/i.exec(trimmed);
\tif (!match) return trimmed;
\tconst agentId = typeof match[1] === "string" && match[1].trim() ? match[1].trim() : "main";
\tconst peerId = typeof match[2] === "string" && match[2].trim() ? match[2].trim().toLowerCase() : "unknown";
\treturn `agent:${{agentId}}:qqbot:direct:${{peerId}}`;
}}
'''


def log(message: str) -> None:
    print(f"[qqbot-delivery-mirror-session] {message}")


def resolve_dist_dir() -> Path:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return Path(sys.argv[1].strip())
    override = os.environ.get("OPENCLAW_DIST_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_DIST_DIR


def find_target_file(dist_dir: Path) -> Path:
    patched_candidates = []
    fresh_candidates = []
    for path in sorted(dist_dir.glob("transcript-*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if MARKER in text and all(snippet in text for snippet in BASE_SNIPPETS):
            patched_candidates.append(path)
            continue
        if all(snippet in text for snippet in BASE_SNIPPETS) and "const sessionKey = params.sessionKey.trim();" in text:
            fresh_candidates.append(path)
    if patched_candidates:
        return patched_candidates[0]
    if fresh_candidates:
        return fresh_candidates[0]
    raise RuntimeError("transcript target not found")


def ensure_helper_block(text: str) -> str:
    anchor = "async function appendAssistantMessageToSessionTranscript(params) {"
    if MARKER in text:
        pattern = re.compile(
            rf'const {MARKER} = ".*?";\nfunction normalizeQQBotMirrorSessionKey\(raw\) \{{.*?\n\}}\n',
            re.S,
        )
        if not pattern.search(text):
            raise RuntimeError("existing mirror helper block marker found but shape changed")
        return pattern.sub(HELPER_BLOCK, text, count=1)
    if anchor not in text:
        raise RuntimeError("appendAssistantMessageToSessionTranscript anchor missing")
    return text.replace(anchor, HELPER_BLOCK + anchor, 1)


def replace_once_if_needed(text: str, old: str, new: str, marker: str, name: str) -> str:
    if marker in text:
        return text
    if old not in text:
        raise RuntimeError(f"{name} anchor missing")
    return text.replace(old, new, 1)


def patch_text(text: str) -> str:
    text = ensure_helper_block(text)
    normalized_line = "const sessionKey = normalizeQQBotMirrorSessionKey(params.sessionKey);"
    text = replace_once_if_needed(
        text,
        "const sessionKey = params.sessionKey.trim();",
        normalized_line,
        normalized_line,
        "appendAssistant session key normalization",
    )
    text = replace_once_if_needed(
        text,
        "const sessionKey = params.sessionKey.trim();",
        normalized_line,
        normalized_line,
        "appendExactAssistant session key normalization",
    )
    return text


def main() -> int:
    dist_dir = resolve_dist_dir()
    target = find_target_file(dist_dir)
    original = target.read_text(encoding="utf-8")
    patched = patch_text(original)
    if patched == original:
        log(f"patch already present for {target.name} ({PATCH_VERSION})")
        return 0
    target.write_text(patched, encoding="utf-8")
    log(f"patched {target.name} -> {PATCH_VERSION}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"failed: {exc}")
        raise
