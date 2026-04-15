#!/usr/bin/env python3
from pathlib import Path

PATCH_MARKER = "MAX_HEARTBEAT_FAILURES = 2"


def replace_once(text: str, old: str, new: str, label: str, path: Path) -> str:
    if old not in text:
        raise RuntimeError(f"{path}: missing expected snippet for {label}")
    return text.replace(old, new, 1)


def locate_gateway_file() -> Path:
    candidates = sorted(Path("/app/dist").glob("gateway-*.js"))
    for path in candidates:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if "WebSocket closed:" in text and "Attempting to resume session" in text:
            return path
    raise RuntimeError("Could not locate compiled qqbot gateway chunk under /app/dist")


def patch_gateway_js(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if PATCH_MARKER in text:
        print(f"{path}: already patched")
        return

    text = replace_once(
        text,
        """let heartbeatInterval = null;
\tlet sessionId = null;""",
        """let heartbeatInterval = null;
\tlet heartbeatAckTimer = null;
\tlet heartbeatTimeoutMs = 0;
\tlet lastHeartbeatSentAt = 0;
\tlet lastHeartbeatAckAt = Date.now();
\tlet heartbeatFailures = 0;
\tconst MAX_HEARTBEAT_FAILURES = 2;
\tconst MIN_HEARTBEAT_TIMEOUT_MS = 45e3;
\tconst clearHeartbeatAckTimer = () => {
\t\tif (heartbeatAckTimer) {
\t\t\tclearTimeout(heartbeatAckTimer);
\t\t\theartbeatAckTimer = null;
\t\t}
\t};
\tconst forceHeartbeatReconnect = (ws) => {
\t\tlog?.warn?.(`[qqbot:${account.accountId}] Heartbeat ACK missing, forcing reconnect`);
\t\tif (heartbeatInterval) {
\t\t\tclearInterval(heartbeatInterval);
\t\t\theartbeatInterval = null;
\t\t}
\t\tclearHeartbeatAckTimer();
\t\theartbeatFailures = 0;
\t\theartbeatTimeoutMs = 0;
\t\tlastHeartbeatSentAt = 0;
\t\tif (currentWs === ws) currentWs = null;
\t\ttry {
\t\t\tif (typeof ws.terminate === "function") ws.terminate();
\t\t\telse ws.close();
\t\t} catch (err) {
\t\t\tlog?.error(`[qqbot:${account.accountId}] Failed to force-close stale socket: ${err instanceof Error ? err.message : JSON.stringify(err)}`);
\t\t}
\t};
\tconst armHeartbeatAckTimer = (ws) => {
\t\tclearHeartbeatAckTimer();
\t\tif (heartbeatTimeoutMs <= 0) return;
\t\theartbeatAckTimer = setTimeout(() => {
\t\t\tif (isAborted) return;
\t\t\tif (currentWs !== ws) return;
\t\t\tif (ws.readyState !== WebSocket.OPEN) return;
\t\t\tif (lastHeartbeatAckAt >= lastHeartbeatSentAt) return;
\t\t\theartbeatFailures++;
\t\t\tlog?.warn?.(`[qqbot:${account.accountId}] Heartbeat ACK timeout after ${heartbeatTimeoutMs}ms (failure ${heartbeatFailures}/${MAX_HEARTBEAT_FAILURES})`);
\t\t\tif (heartbeatFailures < MAX_HEARTBEAT_FAILURES) {
\t\t\t\tlastHeartbeatSentAt = Date.now();
\t\t\t\ttry {
\t\t\t\t\tws.send(JSON.stringify({
\t\t\t\t\t\top: 1,
\t\t\t\t\t\td: lastSeq
\t\t\t\t\t}));
\t\t\t\t\tlog?.info(`[qqbot:${account.accountId}] Heartbeat re-sent after ACK timeout`);
\t\t\t\t\tarmHeartbeatAckTimer(ws);
\t\t\t\t\treturn;
\t\t\t\t} catch (err) {
\t\t\t\t\tlog?.error(`[qqbot:${account.accountId}] Failed to re-send heartbeat after ACK timeout: ${err instanceof Error ? err.message : JSON.stringify(err)}`);
\t\t\t\t}
\t\t\t}
\t\t\tforceHeartbeatReconnect(ws);
\t\t}, heartbeatTimeoutMs);
\t};
\tlet sessionId = null;""",
        "heartbeat declarations",
        path,
    )

    text = replace_once(
        text,
        """\t\tif (heartbeatInterval) {
\t\t\tclearInterval(heartbeatInterval);
\t\t\theartbeatInterval = null;
\t\t}
\t\tif (currentWs && (currentWs.readyState === WebSocket.OPEN || currentWs.readyState === WebSocket.CONNECTING)) currentWs.close();""",
        """\t\tif (heartbeatInterval) {
\t\t\tclearInterval(heartbeatInterval);
\t\t\theartbeatInterval = null;
\t\t}
\t\tclearHeartbeatAckTimer();
\t\theartbeatFailures = 0;
\t\theartbeatTimeoutMs = 0;
\t\tlastHeartbeatSentAt = 0;
\t\tlastHeartbeatAckAt = Date.now();
\t\tif (currentWs && (currentWs.readyState === WebSocket.OPEN || currentWs.readyState === WebSocket.CONNECTING)) currentWs.close();""",
        "cleanup",
        path,
    )

    text = replace_once(
        text,
        """\t\t\t\tisConnecting = false;
\t\t\t\treconnectAttempts = 0;
\t\t\t\tlastConnectTime = Date.now();
\t\t\t\tmsgQueue.startProcessor(handleMessage);
\t\t\t\tstartBackgroundTokenRefresh(account.appId, account.clientSecret, { log });""",
        """\t\t\t\tisConnecting = false;
\t\t\t\treconnectAttempts = 0;
\t\t\t\tlastConnectTime = Date.now();
\t\t\t\tlastHeartbeatAckAt = Date.now();
\t\t\t\tlastHeartbeatSentAt = 0;
\t\t\t\theartbeatFailures = 0;
\t\t\t\tclearHeartbeatAckTimer();
\t\t\t\tmsgQueue.startProcessor(handleMessage);
\t\t\t\tstartBackgroundTokenRefresh(account.appId, account.clientSecret, { log });""",
        "open reset",
        path,
    )

    text = replace_once(
        text,
        """\t\t\t\t\t\t\tconst interval = d.heartbeat_interval;
\t\t\t\t\t\t\tif (heartbeatInterval) clearInterval(heartbeatInterval);
\t\t\t\t\t\t\theartbeatInterval = setInterval(() => {
\t\t\t\t\t\t\t\tif (ws.readyState === WebSocket.OPEN) {
\t\t\t\t\t\t\t\t\tws.send(JSON.stringify({
\t\t\t\t\t\t\t\t\t\top: 1,
\t\t\t\t\t\t\t\t\t\td: lastSeq
\t\t\t\t\t\t\t\t\t}));
\t\t\t\t\t\t\t\t\tlog?.debug?.(`[qqbot:${account.accountId}] Heartbeat sent`);
\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t}, interval);""",
        """\t\t\t\t\t\t\tconst interval = d.heartbeat_interval;
\t\t\t\t\t\t\tif (heartbeatInterval) clearInterval(heartbeatInterval);
\t\t\t\t\t\t\theartbeatTimeoutMs = Math.max(Math.floor(interval * 1.5), MIN_HEARTBEAT_TIMEOUT_MS);
\t\t\t\t\t\t\tlastHeartbeatAckAt = Date.now();
\t\t\t\t\t\t\tlastHeartbeatSentAt = 0;
\t\t\t\t\t\t\theartbeatFailures = 0;
\t\t\t\t\t\t\tclearHeartbeatAckTimer();
\t\t\t\t\t\t\theartbeatInterval = setInterval(() => {
\t\t\t\t\t\t\t\tif (ws.readyState === WebSocket.OPEN) {
\t\t\t\t\t\t\t\t\tlastHeartbeatSentAt = Date.now();
\t\t\t\t\t\t\t\t\tws.send(JSON.stringify({
\t\t\t\t\t\t\t\t\t\top: 1,
\t\t\t\t\t\t\t\t\t\td: lastSeq
\t\t\t\t\t\t\t\t\t}));
\t\t\t\t\t\t\t\t\tlog?.debug?.(`[qqbot:${account.accountId}] Heartbeat sent`);
\t\t\t\t\t\t\t\t\tarmHeartbeatAckTimer(ws);
\t\t\t\t\t\t\t\t}
\t\t\t\t\t\t\t}, interval);""",
        "heartbeat timer",
        path,
    )

    text = replace_once(
        text,
        """\t\t\t\t\t\tcase 11:
\t\t\t\t\t\t\tlog?.debug?.(`[qqbot:${account.accountId}] Heartbeat ACK`);
\t\t\t\t\t\t\tbreak;""",
        """\t\t\t\t\t\tcase 11:
\t\t\t\t\t\t\tlastHeartbeatAckAt = Date.now();
\t\t\t\t\t\t\theartbeatFailures = 0;
\t\t\t\t\t\t\tclearHeartbeatAckTimer();
\t\t\t\t\t\t\tlog?.debug?.(`[qqbot:${account.accountId}] Heartbeat ACK`);
\t\t\t\t\t\t\tbreak;""",
        "heartbeat ack",
        path,
    )

    path.write_text(text, encoding="utf-8")
    print(f"{path}: patched successfully")


if __name__ == "__main__":
    patch_gateway_js(locate_gateway_file())
