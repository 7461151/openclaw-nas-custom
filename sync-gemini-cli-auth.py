#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


HOME_DIR = Path(os.environ.get("HOME") or "/home/node")
OPENCLAW_DIR = HOME_DIR / ".openclaw"
AUTH_PROFILES_PATH = OPENCLAW_DIR / "agents" / "main" / "agent" / "auth-profiles.json"
GEMINI_DIR = HOME_DIR / ".gemini"
GEMINI_SETTINGS_PATH = GEMINI_DIR / "settings.json"
GEMINI_OAUTH_CREDS_PATH = GEMINI_DIR / "oauth_creds.json"
GEMINI_GOOGLE_ACCOUNTS_PATH = GEMINI_DIR / "google_accounts.json"
GEMINI_PROVIDER = "google-gemini-cli"
GOOGLE_OAUTH_SCOPE = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile"
)
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
OAUTH_CLIENT_ID_ENV_VARS = (
    "OPENCLAW_GEMINI_OAUTH_CLIENT_ID",
    "GEMINI_CLI_OAUTH_CLIENT_ID",
)
OAUTH_CLIENT_SECRET_ENV_VARS = (
    "OPENCLAW_GEMINI_OAUTH_CLIENT_SECRET",
    "GEMINI_CLI_OAUTH_CLIENT_SECRET",
)
GEMINI_CLI_BUNDLE_DIR = Path("/usr/local/lib/node_modules/@google/gemini-cli/bundle")
OAUTH_CLIENT_ID_PATTERN = re.compile(r'(?:const|var)\s+OAUTH_CLIENT_ID\s*=\s*"([^"]+)";')
OAUTH_CLIENT_SECRET_PATTERN = re.compile(r'(?:const|var)\s+OAUTH_CLIENT_SECRET\s*=\s*"([^"]+)";')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Sync Gemini CLI OAuth files from OpenClaw auth profiles.")
    parser.add_argument("--quiet", action="store_true", help="Suppress success logs.")
    return parser.parse_args()


def log(message: str, quiet: bool = False) -> None:
    if quiet:
        return
    print(f"[gemini-auth-sync] {message}")


def read_json(path: Path, default):
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return default


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    try:
        path.chmod(0o600)
    except Exception:
        pass


def read_env(names: tuple[str, ...], fallback: str = "") -> str:
    for name in names:
        value = (os.environ.get(name) or "").strip()
        if value:
            return value
    return fallback


def read_bundle_oauth_value(pattern: re.Pattern[str]) -> str:
    try:
        bundle_files = sorted(GEMINI_CLI_BUNDLE_DIR.glob("chunk-*.js"))
    except Exception:
        bundle_files = []
    for bundle_file in bundle_files:
        try:
            match = pattern.search(bundle_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        if match and match.group(1).strip():
            return match.group(1).strip()
    return ""


def resolve_oauth_client_id() -> str:
    return read_env(OAUTH_CLIENT_ID_ENV_VARS) or read_bundle_oauth_value(OAUTH_CLIENT_ID_PATTERN)


def resolve_oauth_client_secret() -> str:
    return read_env(OAUTH_CLIENT_SECRET_ENV_VARS) or read_bundle_oauth_value(OAUTH_CLIENT_SECRET_PATTERN)


def find_best_profile(profiles: dict) -> tuple[str, dict] | tuple[None, None]:
    candidates: list[tuple[int, str, dict]] = []
    for profile_id, profile in (profiles or {}).items():
        if not isinstance(profile, dict):
            continue
        if profile.get("provider") != GEMINI_PROVIDER:
            continue
        if not profile.get("refresh"):
            continue
        expires = profile.get("expires")
        try:
            expires_value = int(expires) if expires is not None else 0
        except Exception:
            expires_value = 0
        candidates.append((expires_value, profile_id, profile))
    if not candidates:
        return None, None
    candidates.sort(key=lambda item: item[0], reverse=True)
    _, profile_id, profile = candidates[0]
    return profile_id, profile


def ensure_settings() -> None:
    settings = read_json(GEMINI_SETTINGS_PATH, {})
    if not isinstance(settings, dict):
        settings = {}
    security = settings.get("security")
    if not isinstance(security, dict):
        security = {}
    auth = security.get("auth")
    if not isinstance(auth, dict):
        auth = {}
    auth["selectedType"] = "oauth-personal"
    security["auth"] = auth
    settings["security"] = security
    settings["selectedAuthType"] = "oauth-personal"
    write_json(GEMINI_SETTINGS_PATH, settings)


def refresh_access_token(profile: dict, quiet: bool) -> tuple[dict, dict]:
    refresh_token = (profile.get("refresh") or "").strip() if isinstance(profile.get("refresh"), str) else ""
    if not refresh_token:
        return dict(profile), {}

    client_id = resolve_oauth_client_id()
    client_secret = resolve_oauth_client_secret()
    if not client_id or not client_secret:
        log("refresh skipped: Gemini CLI OAuth client metadata unavailable", quiet=quiet)
        return dict(profile), {}

    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode("utf-8")
    request = urllib.request.Request(
        TOKEN_ENDPOINT,
        data=payload,
        headers={
            "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
            "Accept": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace").strip()
        log(f"refresh failed with HTTP {exc.code}: {detail or exc.reason}", quiet=quiet)
        return dict(profile), {}
    except Exception as exc:
        log(f"refresh failed: {exc}", quiet=quiet)
        return dict(profile), {}

    access_token = data.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        log("refresh failed: missing access token in refresh response", quiet=quiet)
        return dict(profile), {}

    try:
        expires_in = int(data.get("expires_in") or 3600)
    except Exception:
        expires_in = 3600
    expires_ms = int(time.time() * 1000) + max(expires_in, 300) * 1000 - 300000

    refreshed = dict(profile)
    refreshed["access"] = access_token
    refreshed["expires"] = expires_ms
    if isinstance(data.get("refresh_token"), str) and data["refresh_token"].strip():
        refreshed["refresh"] = data["refresh_token"].strip()

    extra = {
        "token_type": data.get("token_type") if isinstance(data.get("token_type"), str) else "Bearer",
        "scope": data.get("scope") if isinstance(data.get("scope"), str) else GOOGLE_OAUTH_SCOPE,
        "expiry_date": expires_ms,
    }
    if isinstance(data.get("id_token"), str) and data["id_token"].strip():
        extra["id_token"] = data["id_token"].strip()
    if isinstance(data.get("refresh_token"), str) and data["refresh_token"].strip():
        extra["refresh_token"] = data["refresh_token"].strip()
    return refreshed, extra


def sync_oauth_creds(profile: dict, refreshed_meta: dict) -> None:
    existing = read_json(GEMINI_OAUTH_CREDS_PATH, {})
    if not isinstance(existing, dict):
        existing = {}
    existing["access_token"] = profile.get("access")
    existing["refresh_token"] = refreshed_meta.get("refresh_token") or profile.get("refresh")
    existing["expiry_date"] = refreshed_meta.get("expiry_date") or profile.get("expires")
    existing["token_type"] = refreshed_meta.get("token_type") or existing.get("token_type") or "Bearer"
    existing["scope"] = refreshed_meta.get("scope") or existing.get("scope") or GOOGLE_OAUTH_SCOPE
    if refreshed_meta.get("id_token"):
        existing["id_token"] = refreshed_meta["id_token"]
    write_json(GEMINI_OAUTH_CREDS_PATH, existing)


def sync_google_accounts(profile: dict) -> None:
    email = profile.get("email")
    if not isinstance(email, str) or not email.strip():
        return
    payload = {"active": email.strip(), "old": []}
    write_json(GEMINI_GOOGLE_ACCOUNTS_PATH, payload)


def format_expiry(expires) -> str:
    try:
        dt = datetime.fromtimestamp(int(expires) / 1000, tz=timezone.utc)
    except Exception:
        return "unknown"
    return dt.astimezone().isoformat(timespec="seconds")


def main() -> int:
    args = parse_args()
    auth_profiles = read_json(AUTH_PROFILES_PATH, {})
    if not isinstance(auth_profiles, dict):
        log(f"invalid auth profile payload at {AUTH_PROFILES_PATH}", quiet=args.quiet)
        return 0
    profile_id, profile = find_best_profile(auth_profiles.get("profiles") or {})
    if not profile:
        log("no google-gemini-cli OAuth profile found; skipping sync", quiet=args.quiet)
        return 0

    synced_profile, refreshed_meta = refresh_access_token(profile, quiet=args.quiet)
    ensure_settings()
    sync_oauth_creds(synced_profile, refreshed_meta)
    sync_google_accounts(synced_profile)

    refresh_note = " refreshed" if refreshed_meta else " synced"
    log(
        f"{refresh_note.strip()} profile "
        f"{profile_id} "
        f"(email={synced_profile.get('email') or 'unknown'}, expires={format_expiry(synced_profile.get('expires'))})",
        quiet=args.quiet,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
