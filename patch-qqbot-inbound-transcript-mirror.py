#!/usr/bin/env python3
from pathlib import Path
import os
import re
import sys

MARKER = "QQBOT_INBOUND_TRANSCRIPT_MIRROR_PATCH"
PATCH_VERSION = "2026-04-16.1"
DEFAULT_DIST_DIR = Path("/app/dist")

TRANSCRIPT_HELPER_BLOCK = f'''const {MARKER} = "{PATCH_VERSION}";
function normalizeQQBotInboundTranscriptSessionKey(raw) {{
\tconst trimmed = typeof raw === "string" ? raw.trim() : "";
\tif (!trimmed) return "";
\tif (/^agent:[^:]+:qqbot:direct:[^:]+$/i.test(trimmed)) return trimmed;
\tconst legacyMatch = /^agent:([^:]+):qqbot:group:c2c:(.+)$/i.exec(trimmed);
\tif (!legacyMatch) return trimmed;
\tconst agentId = typeof legacyMatch[1] === "string" && legacyMatch[1].trim() ? legacyMatch[1].trim() : "main";
\tconst peerId = typeof legacyMatch[2] === "string" && legacyMatch[2].trim() ? legacyMatch[2].trim().toLowerCase() : "unknown";
\treturn `agent:${{agentId}}:qqbot:direct:${{peerId}}`;
}}
'''

TRANSCRIPT_USER_BLOCK = '''async function appendUserMessageToSessionTranscript(params) {
\tconst sessionKey = normalizeQQBotInboundTranscriptSessionKey(params.sessionKey);
\tif (!sessionKey) return {
\t\tok: false,
\t\treason: "missing sessionKey"
\t};
\tconst mirrorText = typeof params.text === "string" ? params.text.trim() : "";
\tif (!mirrorText) return {
\t\tok: false,
\t\treason: "empty text"
\t};
\treturn appendExactUserMessageToSessionTranscript({
\t\tagentId: params.agentId,
\t\tsessionKey,
\t\tstorePath: params.storePath,
\t\tidempotencyKey: params.idempotencyKey,
\t\tupdateMode: params.updateMode,
\t\tmessage: {
\t\t\trole: "user",
\t\t\tcontent: [{
\t\t\t\ttype: "text",
\t\t\t\ttext: mirrorText
\t\t\t}],
\t\t\ttimestamp: typeof params.timestamp === "number" && Number.isFinite(params.timestamp) ? params.timestamp : Date.now()
\t\t}
\t});
}
async function appendExactUserMessageToSessionTranscript(params) {
\tconst sessionKey = normalizeQQBotInboundTranscriptSessionKey(params.sessionKey);
\tif (!sessionKey) return {
\t\tok: false,
\t\treason: "missing sessionKey"
\t};
\tif (params.message.role !== "user") return {
\t\tok: false,
\t\treason: "message role must be user"
\t};
\tconst storePath = params.storePath ?? resolveDefaultSessionStorePath(params.agentId);
\tconst store = loadSessionStore(storePath, { skipCache: true });
\tconst entry = store[normalizeStoreSessionKey(sessionKey)] ?? store[sessionKey];
\tif (!entry?.sessionId) return {
\t\tok: false,
\t\treason: `unknown sessionKey: ${sessionKey}`
\t};
\tlet sessionFile;
\ttry {
\t\tsessionFile = (await resolveAndPersistSessionFile({
\t\t\tsessionId: entry.sessionId,
\t\t\tsessionKey,
\t\t\tsessionStore: store,
\t\t\tstorePath,
\t\t\tsessionEntry: entry,
\t\t\tagentId: params.agentId,
\t\t\tsessionsDir: path.dirname(storePath)
\t\t})).sessionFile;
\t} catch (err) {
\t\treturn {
\t\t\tok: false,
\t\t\treason: formatErrorMessage(err)
\t\t};
\t}
\tawait ensureSessionHeader({
\t\tsessionFile,
\t\tsessionId: entry.sessionId
\t});
\tconst explicitIdempotencyKey = params.idempotencyKey ?? params.message.idempotencyKey;
\tconst dedupeText = params.dedupeText ?? resolveUserTranscriptDedupeText(params.message);
\tconst existingMessageId = explicitIdempotencyKey ? await transcriptHasIdempotencyKey(sessionFile, explicitIdempotencyKey) : dedupeText ? await transcriptHasExactUserText(sessionFile, dedupeText) : void 0;
\tif (existingMessageId) return {
\t\tok: true,
\t\tsessionFile,
\t\tmessageId: existingMessageId
\t};
\tconst message = {
\t\t...params.message,
\t\t...explicitIdempotencyKey ? { idempotencyKey: explicitIdempotencyKey } : {}
\t};
\tconst messageId = SessionManager.open(sessionFile).appendMessage(message);
\tswitch (params.updateMode ?? "inline") {
\t\tcase "inline":
\t\t\temitSessionTranscriptUpdate({
\t\t\t\tsessionFile,
\t\t\t\tsessionKey,
\t\t\t\tmessage,
\t\t\t\tmessageId
\t\t\t});
\t\t\tbreak;
\t\tcase "file-only":
\t\t\temitSessionTranscriptUpdate(sessionFile);
\t\t\tbreak;
\t\tcase "none": break;
\t}
\treturn {
\t\tok: true,
\t\tsessionFile,
\t\tmessageId
\t};
}
function resolveUserTranscriptDedupeText(message) {
\tif (!message || !Array.isArray(message.content)) return null;
\tconst parts = [];
\tfor (const item of message.content) if (item && item.type === "text" && typeof item.text === "string" && item.text) parts.push(item.text);
\tconst joined = parts.join("");
\treturn joined ? joined : null;
}
async function transcriptHasExactUserText(transcriptPath, exactText) {
\tif (!(typeof exactText === "string" && exactText)) return;
\ttry {
\t\tconst raw = await fs.promises.readFile(transcriptPath, "utf-8");
\t\tfor (const line of raw.split(/\\\\r?\\\\n/)) {
\t\t\tif (!line.trim()) continue;
\t\t\ttry {
\t\t\t\tconst parsed = JSON.parse(line);
\t\t\t\tconst message = parsed?.message;
\t\t\t\tif (message?.role !== "user" || !Array.isArray(message.content)) continue;
\t\t\t\tconst joined = message.content.filter((part) => part && part.type === "text" && typeof part.text === "string").map((part) => part.text).join("");
\t\t\t\tif (joined === exactText && typeof parsed.id === "string" && parsed.id) return parsed.id;
\t\t\t} catch {
\t\t\t\tcontinue;
\t\t\t}
\t\t}
\t} catch {
\t\treturn;
\t}
}
'''


def log(message: str) -> None:
    print(f"[qqbot-inbound-transcript-mirror] {message}")


def resolve_dist_dir() -> Path:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return Path(sys.argv[1].strip())
    override = os.environ.get("OPENCLAW_DIST_DIR", "").strip()
    if override:
        return Path(override)
    return DEFAULT_DIST_DIR


def replace_once_if_needed(text: str, old: str, new: str, marker: str, name: str) -> str:
    if marker in text:
        return text
    if old not in text:
        raise RuntimeError(f"{name} anchor missing")
    return text.replace(old, new, 1)


def find_transcript_file(dist_dir: Path) -> Path:
    patched_candidates = []
    fresh_candidates = []
    for path in sorted(dist_dir.glob("transcript-*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if MARKER in text and "async function appendExactUserMessageToSessionTranscript(params) {" in text:
            patched_candidates.append(path)
            continue
        if "async function appendAssistantMessageToSessionTranscript(params) {" in text and "async function appendExactAssistantMessageToSessionTranscript(params) {" in text and "async function transcriptHasIdempotencyKey(transcriptPath, idempotencyKey) {" in text:
            fresh_candidates.append(path)
    if patched_candidates:
        return patched_candidates[0]
    if fresh_candidates:
        return fresh_candidates[0]
    raise RuntimeError("transcript target not found")


def find_transcript_runtime_file(dist_dir: Path, transcript_file: Path) -> Path:
    patched_candidates = []
    fresh_candidates = []
    for path in sorted(dist_dir.glob("transcript.runtime-*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if MARKER in text and "appendExactUserMessageToSessionTranscript" in text:
            patched_candidates.append(path)
            continue
        if transcript_file.name in text and "appendAssistantMessageToSessionTranscript" in text and "appendExactAssistantMessageToSessionTranscript" in text:
            fresh_candidates.append(path)
    if patched_candidates:
        return patched_candidates[0]
    if fresh_candidates:
        return fresh_candidates[0]
    raise RuntimeError("transcript runtime target not found")


def find_gateway_file(dist_dir: Path) -> Path:
    patched_candidates = []
    fresh_candidates = []
    for path in sorted(dist_dir.glob("gateway-*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if MARKER in text and "await mirrorQQBotInboundMessageToTranscript({" in text:
            patched_candidates.append(path)
            continue
        if 'const ctxPayload = pluginRuntime.channel.reply.finalizeInboundContext({' in text and 'const replyCtx = {' in text and 'import { t as getQQBotRuntime } from "./runtime-' in text:
            fresh_candidates.append(path)
    if patched_candidates:
        return patched_candidates[0]
    if fresh_candidates:
        return fresh_candidates[0]
    raise RuntimeError("gateway target not found")


def ensure_transcript_helper_block(text: str) -> str:
    anchor = 'async function appendAssistantMessageToSessionTranscript(params) {'
    if MARKER in text:
        pattern = re.compile(
            rf'const {MARKER} = ".*?";\nfunction normalizeQQBotInboundTranscriptSessionKey\(raw\) \{{.*?\n\}}\n',
            re.S,
        )
        if not pattern.search(text):
            raise RuntimeError("existing transcript helper block marker found but shape changed")
        return pattern.sub(TRANSCRIPT_HELPER_BLOCK, text, count=1)
    if anchor not in text:
        raise RuntimeError("transcript helper anchor missing")
    return text.replace(anchor, TRANSCRIPT_HELPER_BLOCK + anchor, 1)


def ensure_transcript_user_block(text: str) -> str:
    anchor = 'async function transcriptHasIdempotencyKey(transcriptPath, idempotencyKey) {'
    if "async function appendExactUserMessageToSessionTranscript(params) {" in text:
        pattern = re.compile(
            r'async function appendUserMessageToSessionTranscript\(params\) \{.*?\n\}\nasync function appendExactUserMessageToSessionTranscript\(params\) \{.*?\n\}\nfunction resolveUserTranscriptDedupeText\(message\) \{.*?\n\}\nasync function transcriptHasExactUserText\(transcriptPath, exactText\) \{.*?\n\}\n',
            re.S,
        )
        if not pattern.search(text):
            raise RuntimeError("existing transcript user block found but shape changed")
        return pattern.sub(TRANSCRIPT_USER_BLOCK, text, count=1)
    if anchor not in text:
        raise RuntimeError("transcript user block anchor missing")
    return text.replace(anchor, TRANSCRIPT_USER_BLOCK + anchor, 1)


def patch_transcript_text(text: str) -> str:
    text = ensure_transcript_helper_block(text)
    text = ensure_transcript_user_block(text)
    export_pattern = re.compile(
        r'export \{ resolveMirroredTranscriptText as i, appendExactAssistantMessageToSessionTranscript as n, resolveSessionTranscriptFile as r, appendAssistantMessageToSessionTranscript as t(?:, appendExactUserMessageToSessionTranscript as u, appendUserMessageToSessionTranscript as v)? \};'
    )
    export_line = 'export { resolveMirroredTranscriptText as i, appendExactAssistantMessageToSessionTranscript as n, resolveSessionTranscriptFile as r, appendAssistantMessageToSessionTranscript as t, appendExactUserMessageToSessionTranscript as u, appendUserMessageToSessionTranscript as v };'
    if export_pattern.search(text):
        text = export_pattern.sub(export_line, text, count=1)
    else:
        raise RuntimeError("transcript export anchor missing")
    return text


def patch_transcript_runtime_text(text: str, transcript_file_name: str) -> str:
    import_line = f'import {{ n as appendExactAssistantMessageToSessionTranscript, t as appendAssistantMessageToSessionTranscript, u as appendExactUserMessageToSessionTranscript, v as appendUserMessageToSessionTranscript }} from "./{transcript_file_name}";'
    export_line = f'export {{ appendAssistantMessageToSessionTranscript, appendExactAssistantMessageToSessionTranscript, appendUserMessageToSessionTranscript, appendExactUserMessageToSessionTranscript }};\nconst {MARKER} = "{PATCH_VERSION}";'
    import_pattern = re.compile(
        rf'import \{{ n as appendExactAssistantMessageToSessionTranscript, t as appendAssistantMessageToSessionTranscript(?:, u as appendExactUserMessageToSessionTranscript, v as appendUserMessageToSessionTranscript)? \}} from "\./{re.escape(transcript_file_name)}";'
    )
    export_pattern = re.compile(
        rf'export \{{ appendAssistantMessageToSessionTranscript, appendExactAssistantMessageToSessionTranscript(?:, appendUserMessageToSessionTranscript, appendExactUserMessageToSessionTranscript)? \}};\n?(?:const {MARKER} = ".*?";)?'
    )
    if not import_pattern.search(text):
        raise RuntimeError("transcript runtime import anchor missing")
    text = import_pattern.sub(import_line, text, count=1)
    if not export_pattern.search(text):
        raise RuntimeError("transcript runtime export anchor missing")
    text = export_pattern.sub(export_line, text, count=1)
    return text


def patch_gateway_text(text: str, transcript_runtime_file_name: str) -> str:
    helper_block = f'''const {MARKER} = "{PATCH_VERSION}";
let qqbotTranscriptRuntimePromise;
async function loadQQBotTranscriptRuntime() {{
\tqqbotTranscriptRuntimePromise ??= import("./{transcript_runtime_file_name}");
\treturn await qqbotTranscriptRuntimePromise;
}}
async function mirrorQQBotInboundMessageToTranscript(params) {{
\tconst sessionKey = typeof params?.sessionKey === "string" ? params.sessionKey.trim() : "";
\tconst text = typeof params?.text === "string" ? params.text.trim() : "";
\tif (!sessionKey || !text) return;
\ttry {{
\t\tconst {{ appendExactUserMessageToSessionTranscript }} = await loadQQBotTranscriptRuntime();
\t\tawait appendExactUserMessageToSessionTranscript({{
\t\t\tagentId: params.agentId,
\t\t\tsessionKey,
\t\t\tidempotencyKey: params.idempotencyKey,
\t\t\tmessage: {{
\t\t\t\trole: "user",
\t\t\t\tcontent: [{{
\t\t\t\t\ttype: "text",
\t\t\t\t\ttext
\t\t\t\t}}],
\t\t\t\ttimestamp: typeof params.timestamp === "number" && Number.isFinite(params.timestamp) ? params.timestamp : Date.now()
\t\t\t}}
\t\t}});
\t}} catch (err) {{
\t\tparams.log?.warn?.(`[qqbot:${{params.accountId}}] inbound transcript mirror failed: ${{err instanceof Error ? err.message : JSON.stringify(err)}}`);
\t}}
}}
'''
    import_pattern = re.compile(
        r'import \{ t as getQQBotRuntime \} from "\./runtime-[^"]+\.js";\n'
    )
    if MARKER in text:
        helper_pattern = re.compile(
            rf'const {MARKER} = ".*?";\nlet qqbotTranscriptRuntimePromise;\nasync function loadQQBotTranscriptRuntime\(\) \{{.*?\n\}}\nasync function mirrorQQBotInboundMessageToTranscript\(params\) \{{.*?\n\}}\n',
            re.S,
        )
        if not helper_pattern.search(text):
            raise RuntimeError("existing gateway helper block marker found but shape changed")
        text = helper_pattern.sub(helper_block, text, count=1)
    else:
        match = import_pattern.search(text)
        if not match:
            raise RuntimeError("gateway helper import anchor missing")
        insert_at = match.end()
        text = text[:insert_at] + helper_block + text[insert_at:]

    mirror_call = '''\t\t\t\tawait mirrorQQBotInboundMessageToTranscript({
\t\t\t\t\tagentId: route.agentId,
\t\t\t\t\tsessionKey: routedSessionKey,
\t\t\t\t\ttext: typeof ctxPayload.BodyForAgent === "string" && ctxPayload.BodyForAgent.trim() ? ctxPayload.BodyForAgent : userContent,
\t\t\t\t\ttimestamp: new Date(event.timestamp).getTime(),
\t\t\t\t\tidempotencyKey: event.messageId ? `qqbot:inbound:${event.messageId}` : currentMsgIdx ? `qqbot:inbound:${currentMsgIdx}` : void 0,
\t\t\t\t\taccountId: account.accountId,
\t\t\t\t\tlog
\t\t\t\t});
'''
    text = replace_once_if_needed(
        text,
        '\t\t\t\tconst replyCtx = {',
        mirror_call + '\t\t\t\tconst replyCtx = {',
        'await mirrorQQBotInboundMessageToTranscript({',
        "gateway inbound mirror call",
    )
    return text


def main() -> int:
    dist_dir = resolve_dist_dir()
    transcript_file = find_transcript_file(dist_dir)
    transcript_runtime_file = find_transcript_runtime_file(dist_dir, transcript_file)
    gateway_file = find_gateway_file(dist_dir)

    original_transcript = transcript_file.read_text(encoding="utf-8")
    patched_transcript = patch_transcript_text(original_transcript)
    if patched_transcript != original_transcript:
        transcript_file.write_text(patched_transcript, encoding="utf-8")
        log(f"patched {transcript_file.name} -> transcript {PATCH_VERSION}")
    else:
        log(f"transcript patch already present for {transcript_file.name} ({PATCH_VERSION})")

    original_runtime = transcript_runtime_file.read_text(encoding="utf-8")
    patched_runtime = patch_transcript_runtime_text(original_runtime, transcript_file.name)
    if patched_runtime != original_runtime:
        transcript_runtime_file.write_text(patched_runtime, encoding="utf-8")
        log(f"patched {transcript_runtime_file.name} -> runtime {PATCH_VERSION}")
    else:
        log(f"transcript runtime patch already present for {transcript_runtime_file.name} ({PATCH_VERSION})")

    original_gateway = gateway_file.read_text(encoding="utf-8")
    patched_gateway = patch_gateway_text(original_gateway, transcript_runtime_file.name)
    if patched_gateway != original_gateway:
        gateway_file.write_text(patched_gateway, encoding="utf-8")
        log(f"patched {gateway_file.name} -> gateway {PATCH_VERSION}")
    else:
        log(f"gateway patch already present for {gateway_file.name} ({PATCH_VERSION})")

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f"failed: {exc}")
        raise
