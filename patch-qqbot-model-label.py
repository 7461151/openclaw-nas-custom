#!/usr/bin/env python3
from pathlib import Path
import re

DIST_DIR = Path('/app/dist')
MARKER = 'QQBOT_MODEL_LABEL_PATCH'
PATCH_VERSION = '2026-04-15.2'
BASE_SNIPPETS = [
    'async function parseAndSendMediaTags(replyText, event, actx, sendWithRetry, consumeQuoteRef) {',
    'async function sendPlainReply(payload, replyText, event, actx, sendWithRetry, consumeQuoteRef, toolMediaUrls) {',
    'async function sendPlainTextReply(textWithoutImages, imageUrls, mdMatches, bareUrlMatches, event, actx, sendWithRetry, consumeQuoteRef) {',
    'pluginRuntime.channel.reply.dispatchReplyWithBufferedBlockDispatcher({',
    'replyOptions: { disableBlockStreaming: account.config.streaming?.mode === "off" }',
]

HELPER_BLOCK = '''const QQBOT_MODEL_LABEL_PATCH = "2026-04-15.2";
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
function findSessionEntry(store, sessionKey) {
	if (!store || !sessionKey) return null;
	if (store[sessionKey]) return store[sessionKey];
	const lowerKey = sessionKey.toLowerCase();
	for (const [candidateKey, entry] of Object.entries(store)) {
		if (candidateKey.toLowerCase() === lowerKey) return entry;
	}
	return null;
}
function parseModelRef(raw) {
	const value = normalizeOptionalString(raw);
	if (!value) return null;
	const slashIndex = value.indexOf("/");
	if (slashIndex <= 0 || slashIndex === value.length - 1) return null;
	return {
		provider: value.slice(0, slashIndex),
		model: value.slice(slashIndex + 1)
	};
}
function readNestedNormalizedValue(source, path) {
	let current = source;
	for (const segment of path) {
		if (!current || typeof current !== "object") return null;
		current = current[segment];
	}
	return normalizeOptionalString(current);
}
function firstNestedNormalizedValue(source, paths) {
	for (const path of paths) {
		const value = readNestedNormalizedValue(source, path);
		if (value) return value;
	}
	return null;
}
function resolveDefaultModelRef(cfg, agentId) {
	const agentDefaults = cfg?.agents?.defaults ?? {};
	const agentCfg = agentId ? cfg?.agents?.[agentId] ?? {} : {};
	return parseModelRef(agentCfg?.model?.primary) ?? parseModelRef(agentDefaults?.model?.primary);
}
function resolveConfiguredModelDisplayName(cfg, provider, model) {
	const parsedModelRef = parseModelRef(model);
	const normalizedModel = normalizeOptionalString(parsedModelRef?.model ?? model);
	if (!normalizedModel) return null;
	const normalizedProvider = normalizeOptionalString(provider) ?? normalizeOptionalString(parsedModelRef?.provider) ?? inferProviderFromConfiguredModels(cfg, normalizedModel) ?? "";
	const aliasEntry = cfg?.agents?.defaults?.models?.[`${normalizedProvider}/${normalizedModel}`];
	const alias = normalizeOptionalString(aliasEntry?.alias);
	if (alias) return alias;
	const configuredModels = cfg?.models?.providers?.[normalizedProvider]?.models;
	if (Array.isArray(configuredModels)) {
		for (const entry of configuredModels) {
			if (normalizeOptionalString(entry?.id) === normalizedModel) {
				return normalizeOptionalString(entry?.name) ?? normalizedModel;
			}
		}
	}
	return normalizedModel;
}
function inferProviderFromConfiguredModels(cfg, model) {
	const parsedModelRef = parseModelRef(model);
	const normalizedModel = normalizeOptionalString(parsedModelRef?.model ?? model);
	if (!normalizedModel) return null;
	if (normalizeOptionalString(parsedModelRef?.provider)) return parsedModelRef.provider;
	const providers = cfg?.models?.providers ?? {};
	let matchedProvider = null;
	let matchCount = 0;
	for (const [providerId, providerCfg] of Object.entries(providers)) {
		const configuredModels = providerCfg?.models;
		if (!Array.isArray(configuredModels)) continue;
		if (configuredModels.some((entry) => normalizeOptionalString(entry?.id) === normalizedModel)) {
			matchedProvider = providerId;
			matchCount += 1;
			if (matchCount > 1) return null;
		}
	}
	return matchCount === 1 ? matchedProvider : null;
}
function resolveStoredModelRef(entry, cfg) {
	if (!entry || typeof entry !== "object") return null;
	const fullRef = firstNestedNormalizedValue(entry, [
		["selectedModelFull"],
		["selectedModelRef"],
		["modelFull"],
		["modelRef"],
		["deliveryContext", "modelFull"],
		["deliveryContext", "modelRef"],
		["deliveryContext", "selectedModelFull"],
		["deliveryContext", "selectedModelRef"]
	]);
	const parsedFullRef = parseModelRef(fullRef);
	if (parsedFullRef) return parsedFullRef;
	const overrideModel = firstNestedNormalizedValue(entry, [
		["modelOverride"],
		["deliveryContext", "modelOverride"]
	]);
	if (overrideModel) {
		const parsedOverrideRef = parseModelRef(overrideModel);
		if (parsedOverrideRef) return parsedOverrideRef;
		const overrideProvider = firstNestedNormalizedValue(entry, [
			["providerOverride"],
			["modelOverrideProvider"],
			["deliveryContext", "providerOverride"],
			["deliveryContext", "modelOverrideProvider"]
		]);
		return {
			provider: overrideProvider ?? inferProviderFromConfiguredModels(cfg, overrideModel) ?? "",
			model: overrideModel
		};
	}
	const model = firstNestedNormalizedValue(entry, [
		["selectedModel"],
		["model"],
		["deliveryContext", "model"],
		["deliveryContext", "selectedModel"]
	]);
	if (!model) return null;
	const parsedModelRef = parseModelRef(model);
	if (parsedModelRef) return parsedModelRef;
	const provider = firstNestedNormalizedValue(entry, [
		["selectedProvider"],
		["modelProvider"],
		["provider"],
		["deliveryContext", "modelProvider"],
		["deliveryContext", "provider"],
		["deliveryContext", "selectedProvider"]
	]);
	return {
		provider: provider ?? inferProviderFromConfiguredModels(cfg, model) ?? "",
		model
	};
}
function resolveReplyModelLabel(sessionKey, cfg, agentId) {
	const store = readJsonFileSafe(OPENCLAW_SESSION_STORE_FILE) ?? {};
	const sessionEntry = findSessionEntry(store, sessionKey) ?? {};
	const mainEntry = findSessionEntry(store, `agent:${agentId || "main"}:main`) ?? findSessionEntry(store, "agent:main:main") ?? {};
	const config = cfg ?? readJsonFileSafe(OPENCLAW_CONFIG_FILE) ?? {};
	const defaultRef = resolveDefaultModelRef(config, agentId) ?? {};
	const sessionRef = resolveStoredModelRef(sessionEntry, config);
	const mainRef = resolveStoredModelRef(mainEntry, config);
	const provider = sessionRef?.provider ?? mainRef?.provider ?? defaultRef.provider ?? "";
	const model = sessionRef?.model ?? mainRef?.model ?? defaultRef.model ?? "";
	if (!model) return null;
	return resolveConfiguredModelDisplayName(config, provider, model);
}
function resolveRuntimeModelRef(cfg, selection) {
	const config = cfg ?? readJsonFileSafe(OPENCLAW_CONFIG_FILE) ?? {};
	const fullRef = firstNestedNormalizedValue(selection, [
		["modelFull"],
		["modelRef"],
		["selectedModelFull"],
		["selectedModelRef"],
		["fullModel"],
		["primaryModel"],
		["primaryModelRef"],
		["agentMeta", "modelFull"],
		["meta", "agentMeta", "modelFull"],
		["meta", "modelFull"]
	]);
	const parsedFullRef = parseModelRef(fullRef);
	if (parsedFullRef) return parsedFullRef;
	const model = firstNestedNormalizedValue(selection, [
		["model"],
		["modelId"],
		["selectedModel"],
		["selectedModelId"],
		["modelName"],
		["id"],
		["name"],
		["agentMeta", "model"],
		["meta", "agentMeta", "model"],
		["meta", "model"],
		["selection", "model"],
		["selection", "modelId"],
		["current", "model"],
		["current", "modelId"]
	]);
	if (!model) return null;
	const parsedModelRef = parseModelRef(model);
	if (parsedModelRef) return parsedModelRef;
	const provider = firstNestedNormalizedValue(selection, [
		["provider"],
		["providerId"],
		["modelProvider"],
		["selectedProvider"],
		["selectedModelProvider"],
		["agentMeta", "provider"],
		["meta", "agentMeta", "provider"],
		["meta", "provider"],
		["selection", "provider"],
		["selection", "providerId"],
		["current", "provider"],
		["current", "providerId"]
	]);
	return {
		provider: provider ?? inferProviderFromConfiguredModels(config, model) ?? "",
		model
	};
}
function resolveRuntimeReplyModelLabel(cfg, selection) {
	const config = cfg ?? readJsonFileSafe(OPENCLAW_CONFIG_FILE) ?? {};
	const runtimeRef = resolveRuntimeModelRef(config, selection);
	if (!runtimeRef?.model) return null;
	return resolveConfiguredModelDisplayName(config, runtimeRef.provider, runtimeRef.model);
}
function buildModelReplyHeader(modelLabel) {
	const normalized = normalizeOptionalString(modelLabel);
	if (!normalized) return "";
	return `\u3010${normalized}\u3011\n`;
}
function stripLeadingModelReplyHeaders(text) {
	let stripped = normalizeOptionalString(text) ?? "";
	stripped = stripped.trimStart();
	while (stripped.startsWith("\u3010")) {
		const headerEnd = stripped.indexOf("\u3011");
		if (headerEnd <= 0 || headerEnd > 61) break;
		stripped = stripped.slice(headerEnd + 1).trimStart();
	}
	return stripped;
}
function prependModelReplyHeader(text, modelLabel) {
	const header = buildModelReplyHeader(modelLabel);
	if (!header) return text;
	return header + stripLeadingModelReplyHeaders(text);
}
'''


def log(msg):
    print(f'[qqbot-model-label] {msg}')


def find_gateway_file():
    patched_candidates = []
    fresh_candidates = []
    for path in sorted(DIST_DIR.glob('gateway-*.js')):
        try:
            text = path.read_text(encoding='utf-8')
        except Exception:
            continue
        if MARKER in text and 'dispatchReplyWithBufferedBlockDispatcher({' in text:
            patched_candidates.append(path)
            continue
        if all(snippet in text for snippet in BASE_SNIPPETS):
            fresh_candidates.append(path)
    if patched_candidates:
        return patched_candidates[0]
    if fresh_candidates:
        return fresh_candidates[0]
    raise RuntimeError('gateway target not found')


def ensure_helper_block(text: str) -> str:
    anchor = 'function resolveQQBotMediaTargetContext(event, account, prefix) {'
    if MARKER in text:
        pattern = re.compile(r'const QQBOT_MODEL_LABEL_PATCH = ".*?";\n.*?(?=function resolveQQBotMediaTargetContext\(event, account, prefix\) \{)', re.S)
        if not pattern.search(text):
            raise RuntimeError('patched helper block anchor missing')
        return pattern.sub(lambda m: HELPER_BLOCK + '\n', text, count=1)
    if anchor not in text:
        raise RuntimeError('resolveQQBotMediaTargetContext anchor missing')
    return text.replace(anchor, HELPER_BLOCK + '\n' + anchor, 1)


def replace_once_if_needed(text: str, old: str, new: str, marker: str, name: str) -> str:
    if marker in text:
        return text
    if old not in text:
        raise RuntimeError(f'{name} anchor missing')
    return text.replace(old, new, 1)


def patch_once(text: str) -> str:
    text = ensure_helper_block(text)
    has_routed_session_key = 'const routedSessionKey = event.type === "c2c" ?' in text
    session_key_expr = "routedSessionKey" if has_routed_session_key else "route.sessionKey"
    duplicate_current_model_pattern = re.compile(
        r'(?m)^([ \t]*)let currentModelLabel = resolveReplyModelLabel\(routedSessionKey, cfg, route\.agentId\);\n'
        r'\1const updateCurrentModelLabel = \(selection\) => \{\n'
        r'\1\tconst runtimeModelLabel = resolveRuntimeReplyModelLabel\(cfg, selection\);\n'
        r'\1\tif \(runtimeModelLabel\) currentModelLabel = runtimeModelLabel;\n'
        r'\1\};\n'
        r'\1let currentModelLabel = resolveReplyModelLabel\(route\.sessionKey, cfg, route\.agentId\);\n'
        r'\1const updateCurrentModelLabel = \(selection\) => \{\n'
        r'\1\tconst runtimeModelLabel = resolveRuntimeReplyModelLabel\(cfg, selection\);\n'
        r'\1\tif \(runtimeModelLabel\) currentModelLabel = runtimeModelLabel;\n'
        r'\1\};\n'
    )
    text = duplicate_current_model_pattern.sub(
        lambda m: (
            f"{m.group(1)}let currentModelLabel = resolveReplyModelLabel(routedSessionKey, cfg, route.agentId);\n"
            f"{m.group(1)}const updateCurrentModelLabel = (selection) => {{\n"
            f"{m.group(1)}\tconst runtimeModelLabel = resolveRuntimeReplyModelLabel(cfg, selection);\n"
            f"{m.group(1)}\tif (runtimeModelLabel) currentModelLabel = runtimeModelLabel;\n"
            f"{m.group(1)}}};\n"
        ),
        text,
        count=1,
    )

    text = replace_once_if_needed(
        text,
        'const { account, log } = actx;\n\tconst prefix = `[qqbot:${account.accountId}]`;\n\tconst text = normalizeMediaTags(replyText);',
        'const { account, log, modelLabel } = actx;\n\tconst prefix = `[qqbot:${account.accountId}]`;\n\tconst modelReplyHeader = buildModelReplyHeader(modelLabel);\n\tconst text = normalizeMediaTags(replyText);',
        'const { account, log, modelLabel } = actx;',
        'parseAndSendMediaTags',
    )

    text = replace_once_if_needed(
        text,
        '\tlog?.info(`${prefix} Send queue: ${sendQueue.map((item) => item.type).join(" -> ")}`);',
        '\tif (modelReplyHeader) {\n\t\tif (sendQueue[0]?.type === "text") sendQueue[0].content = prependModelReplyHeader(sendQueue[0].content, modelLabel);\n\t\telse sendQueue.unshift({\n\t\t\ttype: "text",\n\t\t\tcontent: modelReplyHeader.trim()\n\t\t});\n\t}\n\tlog?.info(`${prefix} Send queue: ${sendQueue.map((item) => item.type).join(" -> ")}`);',
        'if (modelReplyHeader) {',
        'send queue',
    )

    text = replace_once_if_needed(
        text,
        '\tfor (const m of mdMatches) {\n\t\tconst url = m[2]?.trim();\n\t\tif (url && !url.startsWith("http://") && !url.startsWith("https://") && !isLocalPath(url)) textWithoutImages = textWithoutImages.replace(m[0], "").trim();\n\t}\n\tif (useMarkdown) await sendMarkdownReply(textWithoutImages, collectedImageUrls, mdMatches, bareUrlMatches, event, actx, sendWithRetry, consumeQuoteRef);',
        '\tfor (const m of mdMatches) {\n\t\tconst url = m[2]?.trim();\n\t\tif (url && !url.startsWith("http://") && !url.startsWith("https://") && !isLocalPath(url)) textWithoutImages = textWithoutImages.replace(m[0], "").trim();\n\t}\n\ttextWithoutImages = prependModelReplyHeader(textWithoutImages, actx.modelLabel);\n\tif (useMarkdown) await sendMarkdownReply(textWithoutImages, collectedImageUrls, mdMatches, bareUrlMatches, event, actx, sendWithRetry, consumeQuoteRef);',
        'textWithoutImages = prependModelReplyHeader(textWithoutImages, actx.modelLabel);',
        'sendPlainReply',
    )

    text = replace_once_if_needed(
        text,
        '\tif (result && event.type !== "c2c") result = result.replace(/([a-zA-Z0-9])\\.([a-zA-Z0-9])/g, "$1_$2");\n\ttry {',
        '\tif (result && event.type !== "c2c") result = result.replace(/([a-zA-Z0-9])\\.([a-zA-Z0-9])/g, "$1_$2");\n\tlet leadingModelHeader = "";\n\tif (imageUrls.length > 0) {\n\t\tconst trimmedResult = result.trimStart();\n\t\tif (trimmedResult.startsWith("\\u3010")) {\n\t\t\tconst headerEnd = trimmedResult.indexOf("\\u3011");\n\t\t\tif (headerEnd > 0 && headerEnd <= 61) {\n\t\t\t\tleadingModelHeader = trimmedResult.slice(0, headerEnd + 1);\n\t\t\t\tresult = trimmedResult.slice(headerEnd + 1).trimStart();\n\t\t\t}\n\t\t}\n\t}\n\tif (leadingModelHeader) {\n\t\tawait sendQQBotTextChunksWithRetry({\n\t\t\taccount,\n\t\t\tevent,\n\t\t\tchunks: chunkText(leadingModelHeader, TEXT_CHUNK_LIMIT),\n\t\t\tsendWithRetry,\n\t\t\tconsumeQuoteRef,\n\t\t\tallowDm: false,\n\t\t\tlog,\n\t\t\tonSuccess: (chunk) => `${prefix} Sent model header chunk (${chunk.length} chars) (${event.type})`,\n\t\t\tonError: (err) => `${prefix} Failed to send model header: ${String(err)}`\n\t\t});\n\t}\n\ttry {',
        'let leadingModelHeader = "";',
        'sendPlainTextReply',
    )

    if 'let currentModelLabel = resolveReplyModelLabel(' not in text:
        pattern = re.compile(r'(?m)^([ \t]*)const dispatchPromise = pluginRuntime\.channel\.reply\.dispatchReplyWithBufferedBlockDispatcher\(\{')
        match = pattern.search(text)
        if not match:
            raise RuntimeError('dispatchPromise anchor missing')
        indent = match.group(1)
        injection = (
            f"{indent}let currentModelLabel = resolveReplyModelLabel({session_key_expr}, cfg, route.agentId);\n"
            f"{indent}const updateCurrentModelLabel = (selection) => {{\n"
            f"{indent}\tconst runtimeModelLabel = resolveRuntimeReplyModelLabel(cfg, selection);\n"
            f"{indent}\tif (runtimeModelLabel) currentModelLabel = runtimeModelLabel;\n"
            f"{indent}}};\n"
            f"{indent}const dispatchPromise = pluginRuntime.channel.reply.dispatchReplyWithBufferedBlockDispatcher({{"
        )
        text = pattern.sub(lambda m: injection, text, count=1)

    old_deliver_variants = [
        (
            'const modelLabel = resolveReplyModelLabel(route.sessionKey, cfg, route.agentId);\n\t\t\t\t\t\t\t\tconst deliverActx = {\n\t\t\t\t\t\t\t\t\taccount,\n\t\t\t\t\t\t\t\t\tqualifiedTarget,\n\t\t\t\t\t\t\t\t\tlog,\n\t\t\t\t\t\t\t\t\tsessionKey: route.sessionKey,\n\t\t\t\t\t\t\t\t\tmodelLabel\n\t\t\t\t\t\t\t\t};',
            'const deliverActx = {\n\t\t\t\t\t\t\t\t\taccount,\n\t\t\t\t\t\t\t\t\tqualifiedTarget,\n\t\t\t\t\t\t\t\t\tlog,\n\t\t\t\t\t\t\t\t\tsessionKey: route.sessionKey,\n\t\t\t\t\t\t\t\t\tmodelLabel: currentModelLabel\n\t\t\t\t\t\t\t\t};',
        ),
        (
            'const modelLabel = resolveReplyModelLabel(routedSessionKey, cfg, route.agentId);\n\t\t\t\t\t\t\t\tconst deliverActx = {\n\t\t\t\t\t\t\t\t\taccount,\n\t\t\t\t\t\t\t\t\tqualifiedTarget,\n\t\t\t\t\t\t\t\t\tlog,\n\t\t\t\t\t\t\t\t\tsessionKey: routedSessionKey,\n\t\t\t\t\t\t\t\t\tmodelLabel\n\t\t\t\t\t\t\t\t};',
            'const deliverActx = {\n\t\t\t\t\t\t\t\t\taccount,\n\t\t\t\t\t\t\t\t\tqualifiedTarget,\n\t\t\t\t\t\t\t\t\tlog,\n\t\t\t\t\t\t\t\t\tsessionKey: routedSessionKey,\n\t\t\t\t\t\t\t\t\tmodelLabel: currentModelLabel\n\t\t\t\t\t\t\t\t};',
        ),
    ]
    if 'modelLabel: currentModelLabel' not in text:
        for old_deliver, new_deliver in old_deliver_variants:
            if old_deliver in text:
                text = text.replace(old_deliver, new_deliver, 1)
                break
        else:
            base_deliver_variants = [
                (
                    'const deliverActx = {\n\t\t\t\t\t\t\t\t\taccount,\n\t\t\t\t\t\t\t\t\tqualifiedTarget,\n\t\t\t\t\t\t\t\t\tlog\n\t\t\t\t\t\t\t\t};',
                    'const deliverActx = {\n\t\t\t\t\t\t\t\t\taccount,\n\t\t\t\t\t\t\t\t\tqualifiedTarget,\n\t\t\t\t\t\t\t\t\tlog,\n\t\t\t\t\t\t\t\t\tsessionKey: route.sessionKey,\n\t\t\t\t\t\t\t\t\tmodelLabel: currentModelLabel\n\t\t\t\t\t\t\t\t};',
                ),
                (
                    'const deliverActx = {\n\t\t\t\t\t\t\t\t\taccount,\n\t\t\t\t\t\t\t\t\tqualifiedTarget,\n\t\t\t\t\t\t\t\t\tlog,\n\t\t\t\t\t\t\t\t\tsessionKey: routedSessionKey\n\t\t\t\t\t\t\t\t};',
                    'const deliverActx = {\n\t\t\t\t\t\t\t\t\taccount,\n\t\t\t\t\t\t\t\t\tqualifiedTarget,\n\t\t\t\t\t\t\t\t\tlog,\n\t\t\t\t\t\t\t\t\tsessionKey: routedSessionKey,\n\t\t\t\t\t\t\t\t\tmodelLabel: currentModelLabel\n\t\t\t\t\t\t\t\t};',
                ),
                (
                    'const deliverActx = {\n\t\t\t\t\t\t\t\t\taccount,\n\t\t\t\t\t\t\t\t\tqualifiedTarget,\n\t\t\t\t\t\t\t\t\tlog,\n\t\t\t\t\t\t\t\t\tsessionKey: route.sessionKey\n\t\t\t\t\t\t\t\t};',
                    'const deliverActx = {\n\t\t\t\t\t\t\t\t\taccount,\n\t\t\t\t\t\t\t\t\tqualifiedTarget,\n\t\t\t\t\t\t\t\t\tlog,\n\t\t\t\t\t\t\t\t\tsessionKey: route.sessionKey,\n\t\t\t\t\t\t\t\t\tmodelLabel: currentModelLabel\n\t\t\t\t\t\t\t\t};',
                ),
            ]
            for base_deliver, upgraded_deliver in base_deliver_variants:
                if base_deliver in text:
                    text = text.replace(base_deliver, upgraded_deliver, 1)
                    break
            else:
                raise RuntimeError('deliverActx anchor missing')

    if 'onModelSelected: (selection) => {' not in text:
        old_reply_options = 'replyOptions: { disableBlockStreaming: account.config.streaming?.mode === "off" }'
        new_reply_options = 'replyOptions: {\n\t\t\t\t\t\t\tdisableBlockStreaming: account.config.streaming?.mode === "off",\n\t\t\t\t\t\t\tonModelSelected: (selection) => {\n\t\t\t\t\t\t\t\tupdateCurrentModelLabel(selection);\n\t\t\t\t\t\t\t}\n\t\t\t\t\t\t}'
        if old_reply_options not in text:
            raise RuntimeError('replyOptions anchor missing')
        text = text.replace(old_reply_options, new_reply_options, 1)

    return text


def main() -> int:
    gateway_file = find_gateway_file()
    original = gateway_file.read_text(encoding='utf-8')
    patched = patch_once(original)
    if patched == original:
        log(f'patch already present for {gateway_file.name} ({PATCH_VERSION})')
        return 0
    gateway_file.write_text(patched, encoding='utf-8')
    log(f'patched {gateway_file.name} -> {PATCH_VERSION}')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        log(f'failed: {exc}')
        raise
