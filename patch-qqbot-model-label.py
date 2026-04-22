#!/usr/bin/env python3
from pathlib import Path
import re

DIST_DIR = Path('/app/dist')
MARKER = 'OPENCLAW_MODEL_REPLY_PREFIX_PATCH'
PATCH_VERSION = '2026-04-22.4'
HELPER_ANCHOR = '/** Shared helper for sending chunked text replies. */'
DELIVER_ANCHOR = 'if (await handleStructuredPayload(replyCtx, replyText, recordOutboundActivity)) return;'
HELPER_BLOCK = r'''const OPENCLAW_MODEL_REPLY_PREFIX_PATCH = "2026-04-22.4";
const OPENCLAW_HOME_DIR = process.env.HOME || "/home/node";
const OPENCLAW_CONFIG_FILE = path.join(OPENCLAW_HOME_DIR, ".openclaw", "openclaw.json");
const OPENCLAW_SESSION_STORE_FILE = path.join(OPENCLAW_HOME_DIR, ".openclaw", "agents", "main", "sessions", "sessions.json");
function readJsonFileSafe(filePath) {
	try {
		return JSON.parse(fs.readFileSync(filePath, "utf8"));
	} catch {
		return null;
	}
}
function normalizeModelRefPart(value) {
	return normalizeOptionalString(value) ?? "";
}
function parseModelRef(raw) {
	const value = normalizeModelRefPart(raw);
	if (!value) return null;
	const slashIndex = value.indexOf("/");
	if (slashIndex <= 0 || slashIndex >= value.length - 1) return null;
	return {
		provider: value.slice(0, slashIndex),
		model: value.slice(slashIndex + 1)
	};
}
function findSessionEntry(store, sessionKey) {
	if (!store || !sessionKey) return null;
	if (store[sessionKey]) return store[sessionKey];
	const lowered = String(sessionKey).toLowerCase();
	for (const [key, entry] of Object.entries(store)) if (String(key).toLowerCase() === lowered) return entry;
	return null;
}
function resolveDefaultModelRef(cfg, agentId) {
	const agentDefaults = cfg?.agents?.defaults ?? {};
	const agentCfg = agentId ? cfg?.agents?.[agentId] ?? {} : {};
	return parseModelRef(agentCfg?.model?.primary) ?? parseModelRef(agentDefaults?.model?.primary) ?? null;
}
function pickSessionModelRef(entry, cfg) {
	if (!entry || typeof entry !== "object") return null;
	const provider = normalizeModelRefPart(entry.modelProvider) || normalizeModelRefPart(entry.provider) || normalizeModelRefPart(entry.deliveryContext?.modelProvider);
	const model = normalizeModelRefPart(entry.model) || normalizeModelRefPart(entry.selectedModel) || normalizeModelRefPart(entry.deliveryContext?.model);
	if (!model) return null;
	const parsed = parseModelRef(model);
	if (parsed) return parsed;
	return {
		provider: provider || null,
		model
	};
}
function resolveSessionModelRef(store, sessionKey, cfg, agentId) {
	const sessionEntry = pickSessionModelRef(findSessionEntry(store, sessionKey), cfg);
	if (sessionEntry?.model) return sessionEntry;
	const mainKey = `agent:${agentId || "main"}:main`;
	const mainEntry = pickSessionModelRef(findSessionEntry(store, mainKey) ?? findSessionEntry(store, "agent:main:main"), cfg);
	if (mainEntry?.model) return mainEntry;
	return resolveDefaultModelRef(cfg, agentId);
}
function resolveConfiguredModelAlias(cfg, provider, model) {
	const normalizedProvider = normalizeModelRefPart(provider);
	const normalizedModel = normalizeModelRefPart(model);
	if (!normalizedModel) return null;
	const providerCandidates = [];
	if (normalizedProvider) {
		providerCandidates.push(normalizedProvider);
		const trimmedProvider = normalizedProvider.includes(":") ? normalizedProvider.split(":").pop() : "";
		if (trimmedProvider && !providerCandidates.includes(trimmedProvider)) providerCandidates.push(trimmedProvider);
	}
	for (const providerId of providerCandidates) {
		const directAlias = normalizeModelRefPart(cfg?.agents?.defaults?.models?.[`${providerId}/${normalizedModel}`]?.alias);
		if (directAlias) return directAlias;
	}
	const directAlias = normalizeModelRefPart(cfg?.agents?.defaults?.models?.[normalizedModel]?.alias);
	if (directAlias) return directAlias;
	for (const providerId of providerCandidates) {
		const providerModels = cfg?.models?.providers?.[providerId]?.models;
		if (!Array.isArray(providerModels)) continue;
		for (const entry of providerModels) {
			const entryId = normalizeModelRefPart(entry?.id);
			if (!entryId) continue;
			if (entryId === normalizedModel || entryId.endsWith(`/${normalizedModel}`) || normalizedModel.endsWith(`/${entryId}`)) {
				return normalizeModelRefPart(entry?.name) || entryId;
			}
		}
	}
	let matched = null;
	for (const [providerId, providerCfg] of Object.entries(cfg?.models?.providers ?? {})) {
		const configuredModels = providerCfg?.models;
		if (!Array.isArray(configuredModels)) continue;
		for (const entry of configuredModels) {
			const entryId = normalizeModelRefPart(entry?.id);
			if (!entryId) continue;
			if (entryId === normalizedModel || entryId.endsWith(`/${normalizedModel}`) || normalizedModel.endsWith(`/${entryId}`)) {
				const candidate = normalizeModelRefPart(entry?.name) || entryId || providerId;
				if (matched && matched !== candidate) return normalizedModel.includes("/") ? normalizedModel.slice(normalizedModel.lastIndexOf("/") + 1) : normalizedModel;
				matched = candidate;
			}
		}
	}
	if (matched) return matched;
	return normalizedModel.includes("/") ? normalizedModel.slice(normalizedModel.lastIndexOf("/") + 1) : normalizedModel;
}
function applyModelReplyPrefix(replyText, sessionKey, cfg, agentId) {
	const text = typeof replyText === "string" ? replyText : normalizeOptionalString(replyText) ?? "";
	if (!text.trim()) return replyText;
	const sessionStore = readJsonFileSafe(OPENCLAW_SESSION_STORE_FILE) ?? {};
	const persistedConfig = readJsonFileSafe(OPENCLAW_CONFIG_FILE) ?? {};
	const sessionConfig = cfg ?? persistedConfig;
	const modelRef = resolveSessionModelRef(sessionStore, sessionKey, sessionConfig, agentId);
	const alias = resolveConfiguredModelAlias(persistedConfig, modelRef?.provider, modelRef?.model);
	if (!alias) return text;
	const prefix = `\u3010${alias}\u3011`;
	if (text.startsWith(prefix)) return text;
	return `${prefix}${text}`;
}
'''


def locate_gateway():
    matches = sorted((DIST_DIR / 'extensions' / 'qqbot').glob('gateway-*.js'))
    if not matches:
        raise RuntimeError('qqbot gateway chunk not found')
    if len(matches) > 1:
        return max(matches, key=lambda p: p.stat().st_mtime)
    return matches[0]


def replace_once(text: str, old: str, new: str, name: str) -> str:
    if old not in text:
        raise RuntimeError(f'{name} anchor missing')
    return text.replace(old, new, 1)


def patch_once(text: str) -> str:
    if MARKER in text:
        return text
    text = replace_once(text, HELPER_ANCHOR, HELPER_BLOCK + '\n' + HELPER_ANCHOR, 'helper block')
    text = replace_once(
        text,
        DELIVER_ANCHOR,
        DELIVER_ANCHOR + '\n\t\t\t\t\t\t\t\t\treplyText = applyModelReplyPrefix(replyText, route.sessionKey, cfg, route.agentId);',
        'deliver prefix injection'
    )
    return text


def main():
    gateway_file = locate_gateway()
    original = gateway_file.read_text(encoding='utf-8')
    patched = patch_once(original)
    if patched == original:
        print(f'[qqbot-model-label] already patched: {gateway_file.name}')
        return 0
    gateway_file.write_text(patched, encoding='utf-8')
    print(f'[qqbot-model-label] patched {gateway_file.name} -> {PATCH_VERSION}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
