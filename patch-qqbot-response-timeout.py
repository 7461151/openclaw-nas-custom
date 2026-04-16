#!/usr/bin/env python3
from pathlib import Path
import os
import re

DIST_DIR = Path("/app/dist")
PATCH_VERSION = "2026-04-16.1"
PATCH_MARKER = 'const QQBOT_RESPONSE_TIMEOUT_PATCH = "'
DEFAULT_RESPONSE_TIMEOUT_MS = 240_000
MIN_RESPONSE_TIMEOUT_MS = 30_000


def read_response_timeout_ms() -> int:
    raw = os.environ.get("QQBOT_RESPONSE_TIMEOUT_MS", "").strip()
    if not raw:
        return DEFAULT_RESPONSE_TIMEOUT_MS
    try:
        value = int(raw)
    except ValueError:
        print(
            f"invalid QQBOT_RESPONSE_TIMEOUT_MS={raw!r}; "
            f"using default {DEFAULT_RESPONSE_TIMEOUT_MS}ms"
        )
        return DEFAULT_RESPONSE_TIMEOUT_MS
    if value < MIN_RESPONSE_TIMEOUT_MS:
        print(
            f"QQBOT_RESPONSE_TIMEOUT_MS={value}ms is too small; "
            f"using minimum {MIN_RESPONSE_TIMEOUT_MS}ms"
        )
        return MIN_RESPONSE_TIMEOUT_MS
    return value


def locate_gateway_file() -> Path:
    candidates = sorted(DIST_DIR.glob("gateway-*.js"))
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "No response within timeout" in text and "dispatchReplyWithBufferedBlockDispatcher" in text:
            return path
    raise RuntimeError("Could not locate compiled qqbot gateway chunk under /app/dist")


def extract_indent(text: str) -> str:
    match = re.search(r"\n([ \t]*)$", text)
    return match.group(1) if match else ""


def patch_gateway_js(path: Path, response_timeout_ms: int) -> None:
    text = path.read_text(encoding="utf-8")

    if PATCH_MARKER in text:
        pattern = re.compile(
            r'(const QQBOT_RESPONSE_TIMEOUT_PATCH = ")([^"]+)(";[ \t\r\n]*const responseTimeout = )([^;]+)(;)',
            re.MULTILINE,
        )

        def replace_existing(match: re.Match[str]) -> str:
            return (
                f'{match.group(1)}{PATCH_VERSION}'
                f'{match.group(3)}{response_timeout_ms}'
                f'{match.group(5)}'
            )

        updated_text, count = pattern.subn(replace_existing, text, count=1)
        if count != 1:
            raise RuntimeError(f"{path}: existing QQ timeout patch marker found but replacement failed")
        if updated_text == text:
            print(f"{path}: already patched (response timeout: {response_timeout_ms}ms)")
            return
        path.write_text(updated_text, encoding="utf-8")
        print(f"{path}: updated QQ response timeout patch to {response_timeout_ms}ms")
        return

    pattern = re.compile(
        r"(let toolFallbackSent = false;[ \t\r\n]*)(const responseTimeout = )([^;]+)(;[ \t\r\n]*const toolOnlyTimeout = 6e4;)",
        re.MULTILINE,
    )

    def inject_patch(match: re.Match[str]) -> str:
        leading = match.group(1)
        indent = extract_indent(leading)
        return (
            f'{leading}const QQBOT_RESPONSE_TIMEOUT_PATCH = "{PATCH_VERSION}";\n'
            f"{indent}const responseTimeout = {response_timeout_ms}"
            f"{match.group(4)}"
        )

    updated_text, count = pattern.subn(inject_patch, text, count=1)
    if count != 1:
        raise RuntimeError(f"{path}: missing expected QQ response-timeout snippet")

    path.write_text(updated_text, encoding="utf-8")
    print(f"{path}: patched successfully (response timeout: {response_timeout_ms}ms)")


if __name__ == "__main__":
    patch_gateway_js(locate_gateway_file(), read_response_timeout_ms())
