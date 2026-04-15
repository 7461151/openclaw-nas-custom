#!/usr/bin/env python3
from pathlib import Path
import re


DIST_DIR = Path("/app/dist")
MARKER = "GEMINI_CLI_PROVIDER_REFRESH_PATCH"
PATCH_VERSION = "2026-04-15.1"
IMPORT_BLOCK = 'import { readdirSync, readFileSync } from "node:fs";\nimport { join } from "node:path";\n'
BASE_SNIPPETS = [
    'const PROVIDER_ID = "google-gemini-cli";',
    'const PROVIDER_LABEL = "Gemini CLI OAuth";',
    'const DEFAULT_MODEL = "google-gemini-cli/gemini-3.1-pro-preview";',
    'formatApiKey: (cred) => formatGoogleOauthApiKey(cred),',
    'fetchUsageSnapshot: async (ctx) => await fetchGeminiCliUsage(ctx)'
]

HELPER_BLOCK = """const GEMINI_CLI_PROVIDER_REFRESH_PATCH = "2026-04-15.1";
const GEMINI_CLI_BUNDLE_DIR = "/usr/local/lib/node_modules/@google/gemini-cli/bundle";
function readGeminiCliBundleOauthValue(name) {
\ttry {
\t\tconst pattern = new RegExp(`(?:const|var)\\\\s+${name}\\\\s*=\\\\s+"([^"]+)"`);
\t\tfor (const entry of readdirSync(GEMINI_CLI_BUNDLE_DIR)) {
\t\t\tif (!entry.startsWith("chunk-") || !entry.endsWith(".js")) continue;
\t\t\tconst match = readFileSync(join(GEMINI_CLI_BUNDLE_DIR, entry), "utf8").match(pattern);
\t\t\tif (match?.[1]) return match[1];
\t\t}
\t} catch {}
\treturn "";
}
function resolveGeminiOAuthClientId() {
\tfor (const name of ENV_VARS) {
\t\tif (!name.includes("CLIENT_ID")) continue;
\t\tconst value = process.env[name]?.trim();
\t\tif (value) return value;
\t}
\treturn readGeminiCliBundleOauthValue("OAUTH_CLIENT_ID");
}
function resolveGeminiOAuthClientSecret() {
\tfor (const name of ENV_VARS) {
\t\tif (!name.includes("CLIENT_SECRET")) continue;
\t\tconst value = process.env[name]?.trim();
\t\tif (value) return value;
\t}
\treturn readGeminiCliBundleOauthValue("OAUTH_CLIENT_SECRET");
}
async function refreshGeminiCliOAuthCredential(ctx) {
\tconst refreshToken = typeof ctx?.refresh === "string" ? ctx.refresh.trim() : "";
\tif (!refreshToken) return null;
\tconst clientId = resolveGeminiOAuthClientId();
\tconst clientSecret = resolveGeminiOAuthClientSecret();
\tif (!clientId || !clientSecret) throw new Error(`Failed to refresh OAuth token for ${PROVIDER_ID}: Gemini CLI OAuth client metadata unavailable`);
\tconst payload = new URLSearchParams({
\t\tclient_id: clientId,
\t\trefresh_token: refreshToken,
\t\tgrant_type: "refresh_token"
\t});
\tpayload.set("client_secret", clientSecret);
\tconst response = await fetch("https://oauth2.googleapis.com/token", {
\t\tmethod: "POST",
\t\theaders: {
\t\t\t"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
\t\t\tAccept: "application/json"
\t\t},
\t\tbody: payload.toString()
\t});
\tif (!response.ok) {
\t\tlet detail = "";
\t\ttry {
\t\t\tdetail = (await response.text())?.trim() ?? "";
\t\t} catch {}
\t\tthrow new Error(`Failed to refresh OAuth token for ${PROVIDER_ID}${detail ? `: ${detail}` : ""}`);
\t}
\tconst data = await response.json();
\tif (typeof data?.access_token !== "string" || data.access_token.length === 0) throw new Error(`Failed to refresh OAuth token for ${PROVIDER_ID}: missing access token`);
\tconst expiresInSeconds = Number(data?.expires_in || 0);
\treturn {
\t\taccess: data.access_token,
\t\trefresh: typeof data?.refresh_token === "string" && data.refresh_token.length > 0 ? data.refresh_token : refreshToken,
\t\texpires: Date.now() + expiresInSeconds * 1000 - 300000
\t};
}"""


def log(msg: str) -> None:
    print(f"[gemini-provider-refresh] {msg}")


def find_target() -> Path:
    patched = []
    fresh = []
    for path in sorted(DIST_DIR.glob("gemini-cli-provider-*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if MARKER in text:
            patched.append(path)
            continue
        if all(snippet in text for snippet in BASE_SNIPPETS):
            fresh.append(path)
    if patched:
        return patched[0]
    if fresh:
        return fresh[0]
    raise RuntimeError("gemini-cli-provider target not found")


def ensure_helper_block(text: str) -> str:
    anchor = "async function fetchGeminiCliUsage(ctx) {"
    if MARKER in text:
        pattern = re.compile(r'const GEMINI_CLI_PROVIDER_REFRESH_PATCH = ".*?";\n.*?(?=async function fetchGeminiCliUsage\(ctx\) \{)', re.S)
        if not pattern.search(text):
            raise RuntimeError("patched helper block anchor missing")
        return pattern.sub(lambda m: HELPER_BLOCK + "\n", text, count=1)
    if anchor not in text:
        raise RuntimeError("fetchGeminiCliUsage anchor missing")
    return text.replace(anchor, HELPER_BLOCK + "\n" + anchor, 1)


def ensure_imports(text: str) -> str:
    if IMPORT_BLOCK.strip() in text:
        return text
    anchor = "//#region extensions/google/gemini-cli-provider.ts"
    if anchor not in text:
        raise RuntimeError("provider region anchor missing")
    return text.replace(anchor, IMPORT_BLOCK + anchor, 1)


def replace_once_if_needed(text: str, old: str, new: str, marker: str, name: str) -> str:
    if marker in text:
        return text
    if old not in text:
        raise RuntimeError(f"{name} anchor missing")
    return text.replace(old, new, 1)


def patch_once(text: str) -> str:
    text = ensure_imports(text)
    text = ensure_helper_block(text)
    text = replace_once_if_needed(
        text,
        '\t\tformatApiKey: (cred) => formatGoogleOauthApiKey(cred),\n\t\tresolveUsageAuth: async (ctx) => {',
        '\t\tformatApiKey: (cred) => formatGoogleOauthApiKey(cred),\n\t\trefreshOAuth: async (ctx) => await refreshGeminiCliOAuthCredential(ctx),\n\t\tresolveUsageAuth: async (ctx) => {',
        'refreshOAuth: async (ctx) => await refreshGeminiCliOAuthCredential(ctx),',
        'refreshOAuth property'
    )
    return text


def main() -> int:
    target = find_target()
    original = target.read_text(encoding="utf-8")
    patched = patch_once(original)
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
