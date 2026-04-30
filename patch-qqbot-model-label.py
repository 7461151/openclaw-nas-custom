#!/usr/bin/env python3
from pathlib import Path
import re

DIST_DIR = Path("/app/dist")
MARKER = "OPENCLAW_MODEL_REPLY_PREFIX_PATCH"
PATCH_VERSION = "2026-04-30.2"
HELPER_ANCHORS = [
    "/** Shared helper for sending chunked text replies. */",
    "async function parseAndSendMediaTags(replyText, event, actx, sendWithRetry, consumeQuoteRef, deps) {",
    "async function parseAndSendMediaTags(replyText, event, actx, sendWithRetry, consumeQuoteRef) {",
]
BASE_SNIPPET_GROUPS = [
    [
        "async function parseAndSendMediaTags(replyText, event, actx, sendWithRetry, consumeQuoteRef) {",
        "async function sendPlainReply(payload, replyText, event, actx, sendWithRetry, consumeQuoteRef, toolMediaUrls) {",
        "async function sendPlainTextReply(params) {",
        "pluginRuntime.channel.reply.dispatchReplyWithBufferedBlockDispatcher({",
        'replyOptions: { disableBlockStreaming: account.config.streaming?.mode === "off" }',
    ],
    [
        "async function parseAndSendMediaTags(",
        "async function sendPlainReply(",
        "async function sendPlainTextReply(",
        "dispatchReplyWithBufferedBlockDispatcher({",
        'Provider: "qqbot"',
    ],
]

HELPER_BLOCK = r'''const OPENCLAW_MODEL_REPLY_PREFIX_PATCH = "2026-04-30.2";
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
function findSessionEntry(store, sessionKey) {
	if (!store || !sessionKey) return null;
	if (store[sessionKey]) return store[sessionKey];
	const lowerKey = String(sessionKey).toLowerCase();
	for (const [candidateKey, entry] of Object.entries(store)) if (String(candidateKey).toLowerCase() === lowerKey) return entry;
	return null;
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
function readNestedNormalizedValue(source, pathSegments) {
	let current = source;
	for (const segment of pathSegments) {
		if (!current || typeof current !== "object") return null;
		current = current[segment];
	}
	return normalizeModelRefPart(current);
}
function firstNestedNormalizedValue(source, paths) {
	for (const candidatePath of paths) {
		const value = readNestedNormalizedValue(source, candidatePath);
		if (value) return value;
	}
	return null;
}
function resolveDefaultModelRef(cfg, agentId) {
	const agentDefaults = cfg?.agents?.defaults ?? {};
	const agentCfg = agentId ? cfg?.agents?.[agentId] ?? {} : {};
	return parseModelRef(agentCfg?.model?.primary) ?? parseModelRef(agentDefaults?.model?.primary) ?? null;
}
function inferProviderFromConfiguredModels(cfg, model) {
	const parsedModelRef = parseModelRef(model);
	const normalizedModel = normalizeModelRefPart(parsedModelRef?.model ?? model);
	if (!normalizedModel) return null;
	if (normalizeModelRefPart(parsedModelRef?.provider)) return parsedModelRef.provider;
	const providers = cfg?.models?.providers ?? {};
	let matchedProvider = null;
	let matchCount = 0;
	for (const [providerId, providerCfg] of Object.entries(providers)) {
		const configuredModels = providerCfg?.models;
		if (!Array.isArray(configuredModels)) continue;
		if (configuredModels.some((entry) => {
			const entryId = normalizeModelRefPart(entry?.id);
			return entryId === normalizedModel || entryId.endsWith(`/${normalizedModel}`) || normalizedModel.endsWith(`/${entryId}`);
		})) {
			matchedProvider = providerId;
			matchCount += 1;
			if (matchCount > 1) return null;
		}
	}
	return matchCount === 1 ? matchedProvider : null;
}
function resolveConfiguredModelDisplayName(cfg, provider, model) {
	const parsedModelRef = parseModelRef(model);
	const normalizedModel = normalizeModelRefPart(parsedModelRef?.model ?? model);
	if (!normalizedModel) return null;
	const normalizedProvider = normalizeModelRefPart(provider) || normalizeModelRefPart(parsedModelRef?.provider) || inferProviderFromConfiguredModels(cfg, normalizedModel) || "";
	const providerCandidates = [];
	if (normalizedProvider) {
		providerCandidates.push(normalizedProvider);
		const trimmedProvider = normalizedProvider.includes(":") ? normalizedProvider.split(":").pop() : "";
		if (trimmedProvider && !providerCandidates.includes(trimmedProvider)) providerCandidates.push(trimmedProvider);
	}
	for (const providerId of providerCandidates) {
		const alias = normalizeModelRefPart(cfg?.agents?.defaults?.models?.[`${providerId}/${normalizedModel}`]?.alias);
		if (alias) return alias;
	}
	const directAlias = normalizeModelRefPart(cfg?.agents?.defaults?.models?.[normalizedModel]?.alias);
	if (directAlias) return directAlias;
	for (const providerId of providerCandidates) {
		const configuredModels = cfg?.models?.providers?.[providerId]?.models;
		if (!Array.isArray(configuredModels)) continue;
		for (const entry of configuredModels) {
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
			provider: overrideProvider || inferProviderFromConfiguredModels(cfg, overrideModel) || "",
			model: overrideModel
		};
	}
	const modelValue = firstNestedNormalizedValue(entry, [
		["selectedModel"],
		["model"],
		["deliveryContext", "model"],
		["deliveryContext", "selectedModel"]
	]);
	if (!modelValue) return null;
	const parsedModelRef = parseModelRef(modelValue);
	if (parsedModelRef) return parsedModelRef;
	const providerValue = firstNestedNormalizedValue(entry, [
		["selectedProvider"],
		["modelProvider"],
		["provider"],
		["deliveryContext", "modelProvider"],
		["deliveryContext", "provider"],
		["deliveryContext", "selectedProvider"]
	]);
	return {
		provider: providerValue || inferProviderFromConfiguredModels(cfg, modelValue) || "",
		model: modelValue
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
	const modelValue = sessionRef?.model ?? mainRef?.model ?? defaultRef.model ?? "";
	if (!modelValue) return null;
	return resolveConfiguredModelDisplayName(config, provider, modelValue);
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
	const modelValue = firstNestedNormalizedValue(selection, [
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
	if (!modelValue) return null;
	const parsedModelRef = parseModelRef(modelValue);
	if (parsedModelRef) return parsedModelRef;
	const providerValue = firstNestedNormalizedValue(selection, [
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
		provider: providerValue || inferProviderFromConfiguredModels(config, modelValue) || "",
		model: modelValue
	};
}
function resolveRuntimeReplyModelLabel(cfg, selection) {
	const config = cfg ?? readJsonFileSafe(OPENCLAW_CONFIG_FILE) ?? {};
	const runtimeRef = resolveRuntimeModelRef(config, selection);
	if (!runtimeRef?.model) return null;
	return resolveConfiguredModelDisplayName(config, runtimeRef.provider, runtimeRef.model);
}
function buildModelReplyHeader(modelLabel) {
	const normalized = normalizeModelRefPart(modelLabel);
	if (!normalized) return "";
	return `\u3010${normalized}\u3011\n`;
}
function looksLikeModelReplyHeader(value) {
	const normalized = normalizeModelRefPart(value);
	if (!normalized) return false;
	if (/^[\w.-]+\/[\w.:@+-]+$/i.test(normalized)) return true;
	return /(?:gpt|claude|sonnet|opus|haiku|qwen|deepseek|doubao|kimi|glm|gemini|mimo|bk|backup|token|model)/i.test(normalized);
}
function openclawQqbotShortModelName(fullModel) {
	const value = normalizeModelRefPart(fullModel);
	if (!value) return void 0;
	const slash = value.lastIndexOf("/");
	return (slash >= 0 ? value.slice(slash + 1) : value).replace(/-\d{8}$/, "").replace(/-latest$/, "");
}
function openclawQqbotCreateResponsePrefixContext(cfg, agentId) {
	const identityName = normalizeOptionalString(cfg?.agents?.[agentId]?.identity?.name) ?? normalizeOptionalString(cfg?.identity?.name);
	const prefixContext = { identityName };
	const onModelSelected = (selection) => {
		const runtimeRef = resolveRuntimeModelRef(cfg, selection);
		const provider = normalizeModelRefPart(runtimeRef?.provider);
		const model = normalizeModelRefPart(runtimeRef?.model);
		if (provider) prefixContext.provider = provider;
		if (model) {
			prefixContext.model = openclawQqbotShortModelName(model);
			prefixContext.modelFull = provider ? `${provider}/${model}` : model;
		}
		prefixContext.thinkingLevel = normalizeModelRefPart(selection?.thinkLevel) || "off";
	};
	return { prefixContext, onModelSelected, responsePrefixContextProvider: () => prefixContext };
}
function stripLeadingModelReplyHeaders(text) {
	let stripped = normalizeOptionalString(text) ?? "";
	while (true) {
		stripped = stripped.trimStart();
		if (stripped.startsWith("\u3010")) {
			const headerEnd = stripped.indexOf("\u3011");
			if (headerEnd <= 0 || headerEnd > 80) break;
			const header = stripped.slice(1, headerEnd);
			if (!looksLikeModelReplyHeader(header)) break;
			stripped = stripped.slice(headerEnd + 1);
			continue;
		}
		if (stripped.startsWith("[")) {
			const headerEnd = stripped.indexOf("]");
			if (headerEnd <= 0 || headerEnd > 80) break;
			const header = stripped.slice(1, headerEnd);
			if (!looksLikeModelReplyHeader(header)) break;
			stripped = stripped.slice(headerEnd + 1);
			continue;
		}
		break;
	}
	return stripped;
}
function prependModelReplyHeader(text, modelLabel) {
	const header = buildModelReplyHeader(modelLabel);
	if (!header) return text;
	return header + stripLeadingModelReplyHeaders(text);
}
function stageQQBotLocalMediaPath(mediaPath, log, prefix) {
	const normalizedPath = normalizePath(normalizeOptionalString(mediaPath) ?? "");
	if (!normalizedPath || !isLocalPath(normalizedPath)) return normalizedPath;
	const allowedPath = resolveQQBotPayloadLocalFilePath(normalizedPath);
	if (allowedPath) return allowedPath;
	try {
		const resolvedPath = path.resolve(normalizedPath);
		if (!fs.existsSync(resolvedPath)) return normalizedPath;
		const extension = path.extname(resolvedPath);
		const baseName = sanitizeFileName(path.basename(resolvedPath, extension)) || "media";
		const stagedDir = getQQBotMediaDir("outbound");
		const stagedName = `${baseName}-${crypto.randomUUID()}${extension}`;
		const stagedPath = path.join(stagedDir, stagedName);
		fs.copyFileSync(resolvedPath, stagedPath);
		const allowedStagedPath = resolveQQBotPayloadLocalFilePath(stagedPath);
		if (allowedStagedPath) {
			log?.info(`${prefix} Staged local media for QQ send: ${normalizedPath} -> ${allowedStagedPath}`);
			return allowedStagedPath;
		}
	} catch (error) {
		log?.error(`${prefix} Failed to stage local media ${normalizedPath}: ${String(error)}`);
	}
	return normalizedPath;
}
function stageQQBotLocalMediaUrls(mediaUrls, log, prefix) {
	const stagedUrls = [];
	for (const mediaUrl of mediaUrls ?? []) {
		const normalizedUrl = normalizeOptionalString(mediaUrl);
		if (!normalizedUrl) continue;
		const stagedUrl = isLocalPath(normalizedUrl) ? stageQQBotLocalMediaPath(normalizedUrl, log, prefix) : normalizedUrl;
		if (stagedUrl && !stagedUrls.includes(stagedUrl)) stagedUrls.push(stagedUrl);
	}
	return stagedUrls;
}
'''


def log(message: str) -> None:
    print(f"[qqbot-model-label] {message}")


def matches_gateway_signature(path: Path, text: str) -> bool:
    normalized_path = str(path).replace("\\", "/").lower()
    is_qqbot_gateway = "/qqbot/" in normalized_path or 'Provider: "qqbot"' in text or 'channel: "qqbot"' in text
    return is_qqbot_gateway and any(all(snippet in text for snippet in group) for group in BASE_SNIPPET_GROUPS)


def find_gateway_file() -> Path:
    patched_candidates = []
    fresh_candidates = []
    for path in sorted(DIST_DIR.rglob("gateway-*.js")):
        try:
            text = path.read_text(encoding="utf-8")
        except Exception:
            continue
        if not matches_gateway_signature(path, text):
            continue
        if (MARKER in text or "QQBOT_MODEL_LABEL_PATCH" in text or "OPENCLAW_QQBOT_DYNAMIC_PREFIX_PATCH" in text) and "dispatchReplyWithBufferedBlockDispatcher({" in text:
            patched_candidates.append(path)
            continue
        fresh_candidates.append(path)
    if patched_candidates:
        return patched_candidates[0]
    if fresh_candidates:
        return fresh_candidates[0]
    raise RuntimeError("gateway target not found")


def ensure_helper_block(text: str) -> str:
    helper_pattern = re.compile(
        r'const (?:QQBOT_MODEL_LABEL_PATCH|OPENCLAW_MODEL_REPLY_PREFIX_PATCH|OPENCLAW_QQBOT_DYNAMIC_PREFIX_PATCH) = ".*?";\n'
        r'.*?function stageQQBotLocalMediaUrls\(mediaUrls, log, prefix\) \{\n.*?\n\}\n',
        re.S,
    )
    text = helper_pattern.sub("", text)
    for anchor in HELPER_ANCHORS:
        if anchor in text:
            return text.replace(anchor, HELPER_BLOCK + "\n" + anchor, 1)
    raise RuntimeError("shared helper anchor missing")


def replace_once_if_needed(text: str, old: str, new: str, marker: str, name: str) -> str:
    if marker in text:
        return text
    if old not in text:
        raise RuntimeError(f"{name} anchor missing")
    return text.replace(old, new, 1)


def replace_variant_if_needed(text: str, variants: list[tuple[str, str]], marker: str, name: str) -> str:
    if marker in text:
        return text
    for old, new in variants:
        if old in text:
            return text.replace(old, new, 1)
    raise RuntimeError(f"{name} anchor missing")


def patch_once(text: str) -> str:
    if (
        MARKER in text
        and "const { account, log, modelLabel } = actx;" in text
        and "const { account, qualifiedTarget, log, modelLabel } = actx;" in text
        and "stageQQBotLocalMediaUrls(localMediaToSend, log, prefix);" in text
        and "modelLabel: currentModelLabel" in text
        and "onModelSelected: (selection) => {" in text
        and f'{MARKER} = "{PATCH_VERSION}"' in text
        and "looksLikeModelReplyHeader" in text
        and "responsePrefix: undefined" in text
        and text.count(f"const {MARKER}") == 1
    ):
        return text

    text = ensure_helper_block(text)
    has_routed_session_key = 'const routedSessionKey = event.type === "c2c" ?' in text
    has_inbound_route_session_key = "inbound.route.sessionKey" in text
    session_key_expr = "routedSessionKey" if has_routed_session_key else "inbound.route.sessionKey" if has_inbound_route_session_key else "route.sessionKey"
    agent_id_expr = "inbound.route.agentId" if "inbound.route.agentId" in text else "route.agentId"

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
        lambda match: (
            f"{match.group(1)}let currentModelLabel = resolveReplyModelLabel(routedSessionKey, cfg, route.agentId);\n"
            f"{match.group(1)}const updateCurrentModelLabel = (selection) => {{\n"
            f"{match.group(1)}\tconst runtimeModelLabel = resolveRuntimeReplyModelLabel(cfg, selection);\n"
            f"{match.group(1)}\tif (runtimeModelLabel) currentModelLabel = runtimeModelLabel;\n"
            f"{match.group(1)}}};\n"
        ),
        text,
        count=1,
    )

    text = replace_once_if_needed(
        text,
        '\tconst messagesConfig = runtime.channel.reply.resolveEffectiveMessagesConfig(cfg, inbound.route.agentId);\n\tconst useOfficialC2cStream = shouldUseOfficialC2cStream(account, event.type === "c2c" ? "c2c" : event.type === "group" ? "group" : "channel");',
        '\tconst messagesConfig = runtime.channel.reply.resolveEffectiveMessagesConfig(cfg, inbound.route.agentId);\n\tconst dynamicPrefix = openclawQqbotCreateResponsePrefixContext(cfg, inbound.route.agentId);\n\tconst useOfficialC2cStream = shouldUseOfficialC2cStream(account, event.type === "c2c" ? "c2c" : event.type === "group" ? "group" : "channel");',
        "const dynamicPrefix = openclawQqbotCreateResponsePrefixContext",
        "dynamic response prefix context",
    )

    text = replace_once_if_needed(
        text,
        '\t\tdispatcherOptions: {\n\t\t\tresponsePrefix: messagesConfig.responsePrefix,\n\t\t\tdeliver: async (payload, info) => {',
        '\t\tdispatcherOptions: {\n\t\t\tresponsePrefix: undefined,\n\t\t\tresponsePrefixContextProvider: dynamicPrefix.responsePrefixContextProvider,\n\t\t\tdeliver: async (payload, info) => {',
        "responsePrefixContextProvider: dynamicPrefix.responsePrefixContextProvider",
        "dynamic response prefix provider",
    )
    text = text.replace(
        "\t\t\tresponsePrefix: messagesConfig.responsePrefix,\n\t\t\tresponsePrefixContextProvider: dynamicPrefix.responsePrefixContextProvider,",
        "\t\t\tresponsePrefix: undefined,\n\t\t\tresponsePrefixContextProvider: dynamicPrefix.responsePrefixContextProvider,",
        1,
    )

    text = replace_variant_if_needed(
        text,
        [
            (
                'const { account, log } = actx;\n\tconst prefix = `[qqbot:${account.accountId}]`;\n\tconst text = normalizeMediaTags(replyText);',
                'const { account, log, modelLabel } = actx;\n\tconst prefix = `[qqbot:${account.accountId}]`;\n\tconst modelReplyHeader = buildModelReplyHeader(modelLabel);\n\tconst text = normalizeMediaTags(replyText);',
            ),
            (
                'const { account, log } = actx;\n\tconst text = normalizeMediaTags(replyText);',
                'const { account, log, modelLabel } = actx;\n\tconst prefix = `[qqbot:${account.accountId}]`;\n\tconst modelReplyHeader = buildModelReplyHeader(modelLabel);\n\tconst text = normalizeMediaTags(replyText);',
            ),
        ],
        'const { account, log, modelLabel } = actx;',
        "parseAndSendMediaTags actx",
    )

    text = replace_variant_if_needed(
        text,
        [
            (
                '\t\tlet mediaPath = decodeMediaPath(normalizeOptionalString(match[2]) ?? "", log, prefix);\n\t\tif (mediaPath) {',
                '\t\tlet mediaPath = decodeMediaPath(normalizeOptionalString(match[2]) ?? "", log, prefix);\n\t\tif (mediaPath && isLocalPath(mediaPath)) mediaPath = stageQQBotLocalMediaPath(mediaPath, log, prefix);\n\t\tif (mediaPath) {',
            ),
            (
                '\t\tconst mediaPath = decodeMediaPath(normalizeOptionalString(match[2]) ?? "", log);\n\t\tif (mediaPath) {',
                '\t\tlet mediaPath = decodeMediaPath(normalizeOptionalString(match[2]) ?? "", log);\n\t\tif (mediaPath && isLocalPath(mediaPath)) mediaPath = stageQQBotLocalMediaPath(mediaPath, log, prefix);\n\t\tif (mediaPath) {',
            ),
        ],
        "stageQQBotLocalMediaPath(mediaPath, log, prefix);",
        "parseAndSendMediaTags local media staging",
    )

    text = replace_variant_if_needed(
        text,
        [
            (
                '\tconst mediaTarget = resolveMediaTargetContext(event, account);',
                '\tif (modelReplyHeader) {\n\t\tif (sendQueue[0]?.type === "text") sendQueue[0].content = prependModelReplyHeader(sendQueue[0].content, modelLabel);\n\t\telse sendQueue.unshift({\n\t\t\ttype: "text",\n\t\t\tcontent: modelReplyHeader.trim()\n\t\t});\n\t}\n\tconst mediaTarget = resolveMediaTargetContext(event, account);',
            ),
        ],
        "if (modelReplyHeader) {",
        "parseAndSendMediaTags header injection",
    )

    text = replace_variant_if_needed(
        text,
        [
            (
                'const { account, qualifiedTarget, log } = actx;\n\tconst prefix = `[qqbot:${account.accountId}]`;',
                'const { account, qualifiedTarget, log, modelLabel } = actx;\n\tconst prefix = `[qqbot:${account.accountId}]`;',
            ),
            (
                'const { account, qualifiedTarget, log } = actx;\n\tconst collectedImageUrls = [];',
                'const { account, qualifiedTarget, log, modelLabel } = actx;\n\tconst prefix = `[qqbot:${account.accountId}]`;\n\tconst collectedImageUrls = [];',
            ),
        ],
        "const { account, qualifiedTarget, log, modelLabel } = actx;",
        "sendPlainReply actx",
    )

    text = replace_variant_if_needed(
        text,
        [
            (
                '\tfor (const m of mdMatches) {\n\t\tconst url = m[2]?.trim();\n\t\tif (url && !url.startsWith("http://") && !url.startsWith("https://") && !isLocalPath(url)) textWithoutImages = textWithoutImages.replace(m[0], "").trim();\n\t}\n\tif (useMarkdown) await sendMarkdownReply({',
                '\tfor (const m of mdMatches) {\n\t\tconst url = m[2]?.trim();\n\t\tif (url && !url.startsWith("http://") && !url.startsWith("https://") && !isLocalPath(url)) textWithoutImages = textWithoutImages.replace(m[0], "").trim();\n\t}\n\ttextWithoutImages = prependModelReplyHeader(textWithoutImages, modelLabel);\n\tif (useMarkdown) await sendMarkdownReply({',
            ),
            (
                '\tfor (const m of mdMatches) {\n\t\tconst url = m[2]?.trim();\n\t\tif (url && !url.startsWith("http://") && !url.startsWith("https://") && !isLocalPath(url)) textWithoutImages = textWithoutImages.replace(m[0], "").trim();\n\t}\n\tif (useMarkdown) await sendMarkdownReply(textWithoutImages, collectedImageUrls, mdMatches, bareUrlMatches, event, actx, sendWithRetry, consumeQuoteRef, deps);',
                '\tfor (const m of mdMatches) {\n\t\tconst url = m[2]?.trim();\n\t\tif (url && !url.startsWith("http://") && !url.startsWith("https://") && !isLocalPath(url)) textWithoutImages = textWithoutImages.replace(m[0], "").trim();\n\t}\n\ttextWithoutImages = prependModelReplyHeader(textWithoutImages, modelLabel);\n\tif (useMarkdown) await sendMarkdownReply(textWithoutImages, collectedImageUrls, mdMatches, bareUrlMatches, event, actx, sendWithRetry, consumeQuoteRef, deps);',
            ),
        ],
        "textWithoutImages = prependModelReplyHeader(textWithoutImages, modelLabel);",
        "sendPlainReply header injection",
    )

    text = replace_once_if_needed(
        text,
        '\tif (localMediaToSend.length > 0) {',
        '\tconst stagedLocalMediaToSend = stageQQBotLocalMediaUrls(localMediaToSend, log, prefix);\n\tif (stagedLocalMediaToSend.length > 0) {',
        "const stagedLocalMediaToSend = stageQQBotLocalMediaUrls(localMediaToSend, log, prefix);",
        "sendPlainReply local media staging",
    )

    text = replace_once_if_needed(
        text,
        '\t\t\tmediaUrls: localMediaToSend,',
        '\t\t\tmediaUrls: stagedLocalMediaToSend,',
        "mediaUrls: stagedLocalMediaToSend,",
        "sendPlainReply local media url injection",
    )

    text = replace_once_if_needed(
        text,
        '\tif (toolMediaUrls.length > 0) {',
        '\tconst stagedToolMediaUrls = stageQQBotLocalMediaUrls(toolMediaUrls, log, prefix);\n\tif (stagedToolMediaUrls.length > 0) {',
        "const stagedToolMediaUrls = stageQQBotLocalMediaUrls(toolMediaUrls, log, prefix);",
        "sendPlainReply tool media staging",
    )

    text = replace_once_if_needed(
        text,
        '\t\t\tmediaUrls: toolMediaUrls,',
        '\t\t\tmediaUrls: stagedToolMediaUrls,',
        "mediaUrls: stagedToolMediaUrls,",
        "sendPlainReply tool media url injection",
    )

    text = replace_variant_if_needed(
        text,
        [
            (
                '\tif (result && event.type !== "c2c") result = result.replace(/([a-zA-Z0-9])\\.([a-zA-Z0-9])/g, "$1_$2");\n\ttry {',
                '\tif (result && event.type !== "c2c") result = result.replace(/([a-zA-Z0-9])\\.([a-zA-Z0-9])/g, "$1_$2");\n\tlet leadingModelHeader = "";\n\tif (imageUrls.length > 0) {\n\t\tconst trimmedResult = result.trimStart();\n\t\tif (trimmedResult.startsWith("\\u3010")) {\n\t\t\tconst headerEnd = trimmedResult.indexOf("\\u3011");\n\t\t\tif (headerEnd > 0 && headerEnd <= 61) {\n\t\t\t\tleadingModelHeader = trimmedResult.slice(0, headerEnd + 1);\n\t\t\t\tresult = trimmedResult.slice(headerEnd + 1).trimStart();\n\t\t\t}\n\t\t}\n\t}\n\tif (leadingModelHeader) {\n\t\tawait sendTextChunksWithRetry({\n\t\t\taccount,\n\t\t\tevent,\n\t\t\tchunks: deps.chunkText(leadingModelHeader, TEXT_CHUNK_LIMIT),\n\t\t\tsendWithRetry,\n\t\t\tconsumeQuoteRef,\n\t\t\tallowDm: false,\n\t\t\tlog,\n\t\t\tonSuccess: (chunk) => `Sent model header chunk (${chunk.length} chars) (${event.type})`,\n\t\t\tonError: (err) => `Failed to send model header: ${formatErrorMessage(err)}`\n\t\t});\n\t}\n\ttry {',
            ),
            (
                '\tif (result && event.type !== "c2c") result = result.replace(/([a-zA-Z0-9])\\.([a-zA-Z0-9])/g, "$1_$2");\n\tlet leadingModelHeader = "";\n\tif (params.imageUrls.length > 0) {',
                '\tif (result && event.type !== "c2c") result = result.replace(/([a-zA-Z0-9])\\.([a-zA-Z0-9])/g, "$1_$2");\n\tlet leadingModelHeader = "";\n\tif (params.imageUrls.length > 0) {',
            ),
        ],
        'let leadingModelHeader = "";',
        "sendPlainTextReply header split",
    )

    if "let currentModelLabel = resolveReplyModelLabel(" not in text:
        pattern = re.compile(r'(?m)^([ \t]*)const dispatchPromise = ((?:pluginRuntime|runtime))\.channel\.reply\.dispatchReplyWithBufferedBlockDispatcher\(\{')
        match = pattern.search(text)
        if not match:
            raise RuntimeError("dispatchPromise anchor missing")
        indent = match.group(1)
        runtime_name = match.group(2)
        injection = (
            f"{indent}let currentModelLabel = resolveReplyModelLabel({session_key_expr}, cfg, {agent_id_expr});\n"
            f"{indent}const updateCurrentModelLabel = (selection) => {{\n"
            f"{indent}\tconst runtimeModelLabel = resolveRuntimeReplyModelLabel(cfg, selection);\n"
            f"{indent}\tif (runtimeModelLabel) currentModelLabel = runtimeModelLabel;\n"
            f"{indent}}};\n"
            f"{indent}const dispatchPromise = {runtime_name}.channel.reply.dispatchReplyWithBufferedBlockDispatcher({{"
        )
        text = pattern.sub(lambda _m: injection, text, count=1)

    if "modelLabel: currentModelLabel" not in text:
        deliver_actx_pattern = re.compile(
            r'const deliverActx = \{\n'
            r'(?P<indent>[ \t]*)account,\n'
            r'(?P=indent)qualifiedTarget,\n'
            r'(?P=indent)log(?:,\n(?P=indent)sessionKey: (?P<session>[^\n,]+))?\n'
            r'(?P<closing>[ \t]*)\};'
        )
        deliver_match = deliver_actx_pattern.search(text)
        if not deliver_match:
            raise RuntimeError("deliverActx anchor missing")
        indent = deliver_match.group("indent")
        closing_indent = deliver_match.group("closing")
        existing_session_expr = deliver_match.group("session") or session_key_expr
        deliver_replacement = (
            "const deliverActx = {\n"
            f"{indent}account,\n"
            f"{indent}qualifiedTarget,\n"
            f"{indent}log,\n"
            f"{indent}sessionKey: {existing_session_expr},\n"
            f"{indent}modelLabel: currentModelLabel\n"
            f"{closing_indent}}};"
        )
        text = deliver_actx_pattern.sub(deliver_replacement, text, count=1)

    if "onModelSelected:" not in text:
        compact_old = 'replyOptions: { disableBlockStreaming: account.config.streaming?.mode === "off" }'
        compact_new = 'replyOptions: {\n\t\t\t\t\t\t\tdisableBlockStreaming: account.config.streaming?.mode === "off",\n\t\t\t\t\t\t\tonModelSelected: (selection) => {\n\t\t\t\t\t\t\t\tdynamicPrefix.onModelSelected(selection);\n\t\t\t\t\t\t\t\tupdateCurrentModelLabel(selection);\n\t\t\t\t\t\t\t}\n\t\t\t\t\t\t}'
        multiline_old = '\t\treplyOptions: {\n\t\t\tdisableBlockStreaming: useOfficialC2cStream ? true : (() => {'
        multiline_new = '\t\treplyOptions: {\n\t\t\tonModelSelected: (selection) => {\n\t\t\t\tdynamicPrefix.onModelSelected(selection);\n\t\t\t\tupdateCurrentModelLabel(selection);\n\t\t\t},\n\t\t\tdisableBlockStreaming: useOfficialC2cStream ? true : (() => {'
        if compact_old in text:
            text = text.replace(compact_old, compact_new, 1)
        elif multiline_old in text:
            text = text.replace(multiline_old, multiline_new, 1)
        else:
            raise RuntimeError("replyOptions anchor missing")

    return text


def main() -> int:
    gateway_file = find_gateway_file()
    original = gateway_file.read_text(encoding="utf-8")
    patched = patch_once(original)
    if patched == original:
        log(f"already patched: {gateway_file.name} ({PATCH_VERSION})")
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
