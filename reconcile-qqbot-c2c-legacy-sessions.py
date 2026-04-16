#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from datetime import datetime
import json
import os
import re
import sys

DEFAULT_SESSIONS_DIR = Path("/home/node/.openclaw/agents/main/sessions")
LEGACY_KEY_RE = re.compile(r"^agent:(?P<agent>[^:]+):qqbot:group:c2c:(?P<peer>.+)$", re.I)


def log(message: str) -> None:
    print(f"[qqbot-c2c-reconcile] {message}")


def resolve_sessions_dir() -> Path:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return Path(sys.argv[1].strip())
    override = os.environ.get("OPENCLAW_SESSIONS_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_SESSIONS_DIR


def merge_unique_jsonl_lines(source: Path, target: Path) -> int:
    if not source.exists() or not target.exists():
        return 0
    source_lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    if len(source_lines) <= 1:
        return 0
    target_lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    known_lines = set(target_lines)
    new_lines = []
    for line in source_lines[1:]:
        if not line or line in known_lines:
            continue
        known_lines.add(line)
        new_lines.append(line)
    if not new_lines:
        return 0
    with target.open("a", encoding="utf-8", newline="\n") as fh:
        for line in new_lines:
            fh.write(line + "\n")
    return len(new_lines)


def ensure_backup(sessions_path: Path) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    backup = sessions_path.with_name(f"{sessions_path.name}.backup-{timestamp}-qqbot-c2c-reconcile")
    backup.write_text(sessions_path.read_text(encoding="utf-8"), encoding="utf-8")
    log(f"backup created: {backup.name}")


def build_direct_key(agent_id: str, peer_id: str) -> str:
    return f"agent:{agent_id}:qqbot:direct:{peer_id.lower()}"


def main() -> int:
    sessions_dir = resolve_sessions_dir()
    sessions_path = sessions_dir / "sessions.json"
    if not sessions_path.exists():
        log(f"sessions store missing: {sessions_path}")
        return 0
    store = json.loads(sessions_path.read_text(encoding="utf-8"))
    changed = False
    merged_pairs = 0
    merged_lines_total = 0
    for legacy_key in list(store.keys()):
        match = LEGACY_KEY_RE.match(legacy_key)
        if not match:
            continue
        legacy_entry = store.get(legacy_key) or {}
        direct_key = build_direct_key(match.group("agent"), match.group("peer"))
        direct_entry = store.get(direct_key)
        if not isinstance(direct_entry, dict):
            continue
        legacy_file = Path(legacy_entry.get("sessionFile", ""))
        direct_file = Path(direct_entry.get("sessionFile", ""))
        merged_lines = merge_unique_jsonl_lines(legacy_file, direct_file) if legacy_file and direct_file else 0
        if merged_lines > 0:
            merged_lines_total += merged_lines
            log(f"merged {merged_lines} transcript line(s): {legacy_file.name} -> {direct_file.name}")
        legacy_updated_at = legacy_entry.get("updatedAt")
        direct_updated_at = direct_entry.get("updatedAt")
        if isinstance(legacy_updated_at, (int, float)) and (
            not isinstance(direct_updated_at, (int, float)) or legacy_updated_at > direct_updated_at
        ):
            direct_entry["updatedAt"] = int(legacy_updated_at)
        store[direct_key] = direct_entry
        del store[legacy_key]
        merged_pairs += 1
        changed = True
        log(f"removed legacy key {legacy_key} -> preserved {direct_key}")
    if not changed:
        log("no legacy qqbot c2c session keys found")
        return 0
    ensure_backup(sessions_path)
    sessions_path.write_text(json.dumps(store, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"reconciled {merged_pairs} legacy key(s), merged {merged_lines_total} transcript line(s)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"failed: {exc}")
        raise
