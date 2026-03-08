const BACKGROUND_LOG_PREFIX = "[NetflixCapture]";
const OPTIONAL_HOST_PERMISSIONS = [
  "https://www.netflix.com/*",
  "https://web.prod.cloud.netflix.com/*",
  "https://*.nflxvideo.net/*",
  "https://*.nflxso.net/*",
];
const REQUEST_FILTER = {
  urls: OPTIONAL_HOST_PERMISSIONS,
};
const CAPTURE_BUFFER_LIMIT_BYTES = 20 * 1024 * 1024;
const OBJECT_URL_REVOKE_DELAY_MS = 60000;
const ENABLED_BADGE_TEXT = "ON";
const ENABLED_BADGE_COLOR = "#cc0000";
const REQUEST_KIND_BIF = "bif";
const REQUEST_KIND_SUBTITLE = "subtitle";
const REQUEST_KIND_GRAPHQL = "graphql";
const REQUEST_KIND_METADATA = "metadata";
const FILTER_STATUS_ACTIVE = "active";
const FILTER_STATUS_OVERFLOW = "overflow";
const FILTER_STATUS_ERROR = "error";
const FILTER_STATUS_COMPLETED = "completed";
const MAX_TAB_DEBUG_EVENTS = 600;
const MAX_GLOBAL_DEBUG_EVENTS = 3000;
const DEBUG_FLUSH_DELAY_MS = 750;
const METADATA_DIAGNOSTIC_CANDIDATE_LIMIT = 10;

const matcherApi = globalThis.NetflixCaptureMatchers;
const metadataApi = globalThis.NetflixMetadataParser;
const namingApi = globalThis.NetflixFileNaming;
const stateStoreApi = globalThis.NetflixStateStore;

const browserApi = globalThis.browser;
const stateStore = stateStoreApi.createStateStore(browserApi.storage.local);
const captureTabStates = new Map();
const knownNetflixTabs = new Map();
const activeFilters = new Map();
const capturePayloads = new Map();
const dirtySessionKeys = new Set();
let globalDebugEvents = [];
let debugFlushTimer = null;
let coreListenersRegistered = false;
let requestListenersRegistered = false;

function logInfo(message, extra) {
  if (extra === undefined) {
    console.log(BACKGROUND_LOG_PREFIX, message);
    return;
  }
  console.log(BACKGROUND_LOG_PREFIX, message, extra);
}

function logError(message, error) {
  console.error(BACKGROUND_LOG_PREFIX, message, error);
}

function cloneValue(value) {
  return JSON.parse(JSON.stringify(value));
}

function createTabState(tab) {
  return {
    tabId: tab.id,
    captureEnabled: true,
    currentUrl: typeof tab.url === "string" ? tab.url : "",
    currentWatchId: matcherApi.extractWatchIdFromUrl(tab.url || ""),
    currentTabTitle: typeof tab.title === "string" ? tab.title : "",
    activeSessionKey: null,
    seriesTitleHint: null,
    seriesHintWatchId: null,
    seriesHintPending: false,
    sessions: {},
  };
}

function normalizeSession(session) {
  if (!session || typeof session !== "object") {
    return null;
  }
  return {
    sessionKey: typeof session.sessionKey === "string" ? session.sessionKey : "",
    watchId: session.watchId ? String(session.watchId) : null,
    watchUrl: typeof session.watchUrl === "string" ? session.watchUrl : "",
    tabTitle: typeof session.tabTitle === "string" ? session.tabTitle : "",
    metadata: session.metadata && typeof session.metadata === "object" ? session.metadata : null,
    startedAt: typeof session.startedAt === "string" ? session.startedAt : new Date().toISOString(),
    closed: Boolean(session.closed),
    closedAt: typeof session.closedAt === "string" ? session.closedAt : null,
    openRequestCount:
      typeof session.openRequestCount === "number" && Number.isFinite(session.openRequestCount)
        ? session.openRequestCount
        : 0,
    seenRequestUrls: Array.isArray(session.seenRequestUrls) ? session.seenRequestUrls.slice() : [],
    pendingAssets: Array.isArray(session.pendingAssets) ? session.pendingAssets.slice() : [],
    savedAssets: Array.isArray(session.savedAssets) ? session.savedAssets.slice() : [],
    debugEvents: Array.isArray(session.debugEvents) ? session.debugEvents.slice() : [],
  };
}

function normalizeTabState(tabId, storedState) {
  const normalizedState = {
    tabId,
    captureEnabled: storedState?.captureEnabled !== false,
    currentUrl: typeof storedState?.currentUrl === "string" ? storedState.currentUrl : "",
    currentWatchId: storedState?.currentWatchId ? String(storedState.currentWatchId) : null,
    currentTabTitle: typeof storedState?.currentTabTitle === "string" ? storedState.currentTabTitle : "",
    activeSessionKey: typeof storedState?.activeSessionKey === "string" ? storedState.activeSessionKey : null,
    seriesTitleHint:
      typeof storedState?.seriesTitleHint === "string" && storedState.seriesTitleHint.trim()
        ? storedState.seriesTitleHint.trim()
        : null,
    seriesHintWatchId: storedState?.seriesHintWatchId ? String(storedState.seriesHintWatchId) : null,
    seriesHintPending: Boolean(storedState?.seriesHintPending),
    sessions: {},
  };
  const rawSessions = storedState?.sessions;
  if (rawSessions && typeof rawSessions === "object") {
    for (const [sessionKey, rawSession] of Object.entries(rawSessions)) {
      const normalizedSession = normalizeSession(rawSession);
      if (!normalizedSession) {
        continue;
      }
      normalizedSession.sessionKey = sessionKey;
      normalizedState.sessions[sessionKey] = normalizedSession;
    }
  }
  if (normalizedState.activeSessionKey && !normalizedState.sessions[normalizedState.activeSessionKey]) {
    normalizedState.activeSessionKey = null;
  }
  return normalizedState;
}

function createSessionKey(tabId, watchId) {
  return `${tabId}:${watchId}:${Date.now()}`;
}

function createSession(tabState) {
  const watchId = tabState.currentWatchId;
  return {
    sessionKey: createSessionKey(tabState.tabId, watchId),
    watchId,
    watchUrl: tabState.currentUrl,
    tabTitle: tabState.currentTabTitle,
    metadata: null,
    startedAt: new Date().toISOString(),
    closed: false,
    closedAt: null,
    openRequestCount: 0,
    seenRequestUrls: [],
    pendingAssets: [],
    savedAssets: [],
    debugEvents: [],
  };
}

function getKnownNetflixTab(tabId) {
  return knownNetflixTabs.get(tabId) || null;
}

function updateKnownNetflixTab(tabId, url, title) {
  if (typeof tabId !== "number") {
    return;
  }
  const urlValue = typeof url === "string" ? url : "";
  try {
    const parsedUrl = new URL(urlValue);
    if (parsedUrl.hostname !== matcherApi.NETFLIX_HOSTNAME) {
      knownNetflixTabs.delete(tabId);
      return;
    }
  } catch (_error) {
    knownNetflixTabs.delete(tabId);
    return;
  }
  knownNetflixTabs.set(tabId, {
    currentUrl: urlValue,
    watchId: matcherApi.extractWatchIdFromUrl(urlValue),
    tabTitle: typeof title === "string" ? title : "",
  });
}

function syncTabStateFromKnownContext(tabState) {
  const knownTab = getKnownNetflixTab(tabState.tabId);
  if (!knownTab) {
    tabState.currentUrl = "";
    tabState.currentWatchId = null;
    tabState.currentTabTitle = "";
    return;
  }
  tabState.currentUrl = knownTab.currentUrl;
  tabState.currentWatchId = knownTab.watchId;
  tabState.currentTabTitle = knownTab.tabTitle;
}

function getSession(tabState, sessionKey) {
  return tabState && tabState.sessions ? tabState.sessions[sessionKey] || null : null;
}

function getActiveSession(tabState) {
  if (!tabState || !tabState.activeSessionKey) {
    return null;
  }
  return getSession(tabState, tabState.activeSessionKey);
}

function computeSessionTitleSlug(session) {
  return namingApi.buildTitleSlug(session.metadata, session.tabTitle, session.watchId);
}

async function ensureEnabledTabStateForTab(tab) {
  if (!tab || typeof tab.id !== "number") {
    return null;
  }
  const url = typeof tab.url === "string" ? tab.url : "";
  if (!url.startsWith("https://www.netflix.com/")) {
    return null;
  }
  updateKnownNetflixTab(tab.id, url, tab.title || "");
  const existingState = captureTabStates.get(tab.id);
  if (existingState) {
    existingState.captureEnabled = true;
    syncTabStateFromKnownContext(existingState);
    await persistTabState(existingState);
    return existingState;
  }
  const createdState = createTabState(tab);
  await persistTabState(createdState);
  return createdState;
}

function trimArrayInPlace(items, limit) {
  if (items.length <= limit) {
    return;
  }
  items.splice(0, items.length - limit);
}

async function persistTabState(tabState) {
  captureTabStates.set(tabState.tabId, tabState);
  await stateStore.setTabState(tabState.tabId, normalizeTabState(tabState.tabId, tabState));
}

async function removeTabState(tabId) {
  captureTabStates.delete(tabId);
  await stateStore.deleteTabState(tabId);
}

async function initializeState() {
  const storedTabStates = await stateStore.getAllTabStates();
  for (const [tabId, tabState] of Object.entries(storedTabStates)) {
    captureTabStates.set(Number(tabId), normalizeTabState(Number(tabId), tabState));
  }
  globalDebugEvents = await stateStore.getGlobalDebugEvents();
}

async function setBadgeEnabled(tabId, enabled) {
  await browserApi.action.setBadgeText({
    tabId,
    text: enabled ? ENABLED_BADGE_TEXT : "",
  });
  if (enabled) {
    await browserApi.action.setBadgeBackgroundColor({
      tabId,
      color: ENABLED_BADGE_COLOR,
    });
  }
}

async function clearBadge(tabId) {
  await setBadgeEnabled(tabId, false);
}

async function ensureOptionalPermissions() {
  const permissions = {
    origins: OPTIONAL_HOST_PERMISSIONS,
  };
  const alreadyGranted = await browserApi.permissions.contains(permissions);
  if (alreadyGranted) {
    return true;
  }
  return browserApi.permissions.request(permissions);
}

function scheduleDebugFlush() {
  if (debugFlushTimer !== null) {
    return;
  }
  debugFlushTimer = setTimeout(() => {
    debugFlushTimer = null;
    void flushDebugLogs().catch((error) => {
      logError("Failed to flush debug logs.", error);
    });
  }, DEBUG_FLUSH_DELAY_MS);
}

async function appendGlobalDebugEvent(event) {
  const normalizedEvent = {
    timestamp: new Date().toISOString(),
    ...event,
  };
  globalDebugEvents.push(normalizedEvent);
  trimArrayInPlace(globalDebugEvents, MAX_GLOBAL_DEBUG_EVENTS);
  await stateStore.setGlobalDebugEvents(globalDebugEvents);
  scheduleDebugFlush();
}

async function appendSessionDebugEvent(tabState, sessionKey, event) {
  const session = getSession(tabState, sessionKey);
  if (!session) {
    await appendGlobalDebugEvent(event);
    return;
  }
  const normalizedEvent = {
    timestamp: new Date().toISOString(),
    watchId: session.watchId,
    titleSlug: computeSessionTitleSlug(session),
    ...event,
  };
  session.debugEvents.push(normalizedEvent);
  trimArrayInPlace(session.debugEvents, MAX_TAB_DEBUG_EVENTS);
  dirtySessionKeys.add(sessionKey);
  try {
    await persistTabState(tabState);
  } catch (error) {
    logError(`Failed to persist tab state for tab ${tabState.tabId}`, error);
  }
  if (event.requestKind !== "ignored") {
    await appendGlobalDebugEvent(normalizedEvent);
  }
}

function shouldWriteSessionDebug(session) {
  return session.debugEvents.some((event) => {
    return event.requestKind === REQUEST_KIND_BIF || event.requestKind === REQUEST_KIND_SUBTITLE;
  });
}

function buildManifestPayload(session) {
  return {
    generatedAt: new Date().toISOString(),
    watchUrl: session.watchUrl,
    watchId: session.watchId,
    tabTitle: session.tabTitle,
    metadata: session.metadata,
    assets: session.savedAssets,
  };
}

function deriveSeriesTitleFromMetadata(metadata) {
  if (!metadata || typeof metadata !== "object") {
    return null;
  }
  if (typeof metadata.showTitle === "string" && metadata.showTitle.trim()) {
    return metadata.showTitle.trim();
  }
  return null;
}

function applySeriesHintToMetadata(tabState, session, parsedMetadata) {
  const seriesTitleHint =
    typeof tabState.seriesTitleHint === "string" && tabState.seriesTitleHint.trim()
      ? tabState.seriesTitleHint.trim()
      : null;
  if (
    !tabState.seriesHintPending ||
    !seriesTitleHint ||
    !parsedMetadata ||
    parsedMetadata.kind !== "movie" ||
    typeof parsedMetadata.movieTitle !== "string" ||
    !parsedMetadata.movieTitle.trim() ||
    parsedMetadata.movieTitle.trim() === seriesTitleHint
  ) {
    return {
      metadata: parsedMetadata,
      inferred: false,
    };
  }
  return {
    metadata: {
      ...parsedMetadata,
      kind: "episode",
      entityType: "Episode",
      showTitle: seriesTitleHint,
      movieTitle: null,
      episodeTitle: parsedMetadata.movieTitle.trim(),
    },
    inferred: true,
  };
}

function buildDebugPayload(session) {
  return {
    generatedAt: new Date().toISOString(),
    titleSlug: computeSessionTitleSlug(session),
    context: {
      watchUrl: session.watchUrl,
      watchId: session.watchId,
      tabTitle: session.tabTitle,
      metadata: session.metadata,
    },
    debugEvents: session.debugEvents,
    assets: session.savedAssets,
  };
}

function buildObjectUrlFromBytes(bytes, mimeType) {
  const blob = new Blob([bytes], { type: mimeType });
  return URL.createObjectURL(blob);
}

async function startDownload(downloadPath, bytes, mimeType) {
  const objectUrl = buildObjectUrlFromBytes(bytes, mimeType);
  try {
    await browserApi.downloads.download({
      url: objectUrl,
      filename: downloadPath,
      saveAs: false,
      conflictAction: "overwrite",
    });
  } finally {
    setTimeout(() => {
      URL.revokeObjectURL(objectUrl);
    }, OBJECT_URL_REVOKE_DELAY_MS);
  }
}

async function writeManifestForSession(session) {
  if (session.savedAssets.length === 0) {
    return;
  }
  const titleSlug = computeSessionTitleSlug(session);
  const manifestBytes = new TextEncoder().encode(
    JSON.stringify(buildManifestPayload(session), null, 2),
  );
  await startDownload(
    namingApi.buildDownloadPath(titleSlug, namingApi.buildManifestFilename(titleSlug)),
    manifestBytes,
    "application/json",
  );
}

async function writeDebugForSession(session) {
  if (!shouldWriteSessionDebug(session)) {
    return;
  }
  const titleSlug = computeSessionTitleSlug(session);
  const debugBytes = new TextEncoder().encode(
    JSON.stringify(buildDebugPayload(session), null, 2),
  );
  await startDownload(
    namingApi.buildDownloadPath(titleSlug, namingApi.buildDebugFilename(titleSlug)),
    debugBytes,
    "application/json",
  );
}

async function writeGlobalDebugLog() {
  const debugBytes = new TextEncoder().encode(
    JSON.stringify(
      {
        generatedAt: new Date().toISOString(),
        eventCount: globalDebugEvents.length,
        events: globalDebugEvents,
      },
      null,
      2,
    ),
  );
  await startDownload(namingApi.buildGlobalDebugPath(), debugBytes, "application/json");
}

async function flushDebugLogs() {
  await writeGlobalDebugLog();
  const dirtyKeys = Array.from(dirtySessionKeys);
  dirtySessionKeys.clear();
  for (const sessionKey of dirtyKeys) {
    const tabId = Number(sessionKey.split(":")[0]);
    const tabState = captureTabStates.get(tabId);
    if (!tabState) {
      continue;
    }
    const session = getSession(tabState, sessionKey);
    if (!session) {
      continue;
    }
    await writeDebugForSession(session);
  }
}

function classifyRequestFromUrl(details) {
  if (matcherApi.isGraphqlMetadataUrl(details.url)) {
    return REQUEST_KIND_GRAPHQL;
  }
  if (matcherApi.isMemberApiMetadataUrl(details.url)) {
    return REQUEST_KIND_METADATA;
  }
  if (matcherApi.isBifUrl(details.url)) {
    return REQUEST_KIND_BIF;
  }
  if (matcherApi.isLikelySubtitleUrl(details.url)) {
    return REQUEST_KIND_SUBTITLE;
  }
  return null;
}

function classifyRequestFromHeaders(details) {
  if (matcherApi.isGraphqlMetadataUrl(details.url)) {
    return REQUEST_KIND_GRAPHQL;
  }
  if (matcherApi.isMemberApiMetadataUrl(details.url)) {
    return REQUEST_KIND_METADATA;
  }
  if (matcherApi.isBifUrl(details.url)) {
    return REQUEST_KIND_BIF;
  }
  if (matcherApi.hasXmlContentType(Array.isArray(details.responseHeaders) ? details.responseHeaders : [])) {
    return REQUEST_KIND_SUBTITLE;
  }
  return null;
}

function getHeaderValue(details, name) {
  return matcherApi.getHeaderValue(Array.isArray(details.responseHeaders) ? details.responseHeaders : [], name);
}

function buildBodyPreview(bodyText) {
  if (typeof bodyText !== "string") {
    return "";
  }
  return bodyText.replace(/\s+/g, " ").trim().slice(0, 180);
}

function extractTopLevelPayloadKeys(bodyText) {
  if (typeof bodyText !== "string") {
    return [];
  }
  try {
    const payload = JSON.parse(bodyText);
    return payload && typeof payload === "object" && !Array.isArray(payload) ? Object.keys(payload) : [];
  } catch (_error) {
    return [];
  }
}

function summarizeDiagnosticCandidates(candidates) {
  if (!Array.isArray(candidates)) {
    return [];
  }
  return candidates.slice(0, METADATA_DIAGNOSTIC_CANDIDATE_LIMIT).map((candidate) => {
    return {
      source: candidate.source || null,
      score: candidate.score,
      kind: candidate.kind,
      entityType: candidate.entityType,
      videoId: candidate.videoId,
      showTitle: candidate.showTitle,
      movieTitle: candidate.movieTitle,
      seasonNumber: candidate.seasonNumber,
      episodeNumber: candidate.episodeNumber,
      episodeTitle: candidate.episodeTitle,
    };
  });
}

function metadataFieldCount(metadata) {
  if (!metadata || typeof metadata !== "object") {
    return 0;
  }
  let count = 0;
  for (const key of ["showTitle", "movieTitle", "episodeTitle", "seasonNumber", "episodeNumber"]) {
    if (metadata[key] !== null && metadata[key] !== undefined && metadata[key] !== "") {
      count += 1;
    }
  }
  return count;
}

function chooseMetadataApplication(session, parsedMetadata, requestVideoId) {
  if (!parsedMetadata) {
    return {
      apply: false,
      reason: "metadata_parse_returned_null",
    };
  }

  const watchId = String(session.watchId || "");
  const metadataVideoId = String(parsedMetadata.videoId || "");
  const requestScopedVideoId = String(requestVideoId || "");
  const exactMatch = Boolean(watchId && (metadataVideoId === watchId || requestScopedVideoId === watchId));
  const existingMetadata = session.metadata;
  const existingExactMatch = Boolean(
    existingMetadata &&
      watchId &&
      (String(existingMetadata.videoId || "") === watchId || String(existingMetadata.requestVideoId || "") === watchId),
  );

  if (!existingMetadata) {
    return {
      apply: true,
      reason: exactMatch ? "exact_match" : "first_metadata_candidate",
    };
  }

  if (exactMatch && !existingExactMatch) {
    return {
      apply: true,
      reason: "exact_match_replaces_fallback",
    };
  }

  if (exactMatch === existingExactMatch && metadataFieldCount(parsedMetadata) > metadataFieldCount(existingMetadata)) {
    return {
      apply: true,
      reason: "richer_metadata_candidate",
    };
  }

  return {
    apply: false,
    reason: exactMatch ? "existing_metadata_not_weaker" : "fallback_metadata_not_needed",
  };
}

async function applyMetadataToSession(tabState, session, requestKind, requestUrl, parsedMetadata, requestVideoId) {
  const hintedMetadataResult = applySeriesHintToMetadata(tabState, session, parsedMetadata);
  const candidateMetadata = hintedMetadataResult.metadata;
  const decision = chooseMetadataApplication(session, candidateMetadata, requestVideoId);
  if (!decision.apply) {
    await appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "metadata_skipped",
      requestKind,
      url: requestUrl,
      reason: decision.reason,
      metadataVideoId: candidateMetadata?.videoId ?? null,
      watchId: session.watchId,
      requestVideoId: requestVideoId || null,
    });
    return false;
  }

  session.metadata = {
    ...candidateMetadata,
    requestVideoId: requestVideoId || null,
  };
  const resolvedSeriesTitle = deriveSeriesTitleFromMetadata(session.metadata);
  tabState.seriesTitleHint = resolvedSeriesTitle;
  tabState.seriesHintWatchId = session.watchId;
  tabState.seriesHintPending = false;
  await persistTabState(tabState);
  await appendSessionDebugEvent(tabState, session.sessionKey, {
    stage: "metadata_applied",
    requestKind,
    url: requestUrl,
    reason: decision.reason,
    metadataKind: candidateMetadata.kind,
    videoId: candidateMetadata.videoId,
    requestVideoId: requestVideoId || null,
    inferredFromSeriesHint: hintedMetadataResult.inferred,
  });
  await flushSessionAssets(tabState, session);
  return true;
}

function ensureActiveSession(tabState) {
  if (!tabState.currentWatchId) {
    return null;
  }
  const activeSession = getActiveSession(tabState);
  if (activeSession && !activeSession.closed && activeSession.watchId === tabState.currentWatchId) {
    activeSession.watchUrl = tabState.currentUrl;
    activeSession.tabTitle = tabState.currentTabTitle;
    return activeSession;
  }
  const session = createSession(tabState);
  tabState.sessions[session.sessionKey] = session;
  tabState.activeSessionKey = session.sessionKey;
  void appendSessionDebugEvent(tabState, session.sessionKey, {
    stage: "session_started",
    reason: "watch_entered",
    requestKind: null,
    url: session.watchUrl,
  }).catch((error) => {
    logError(`Failed to record session start for tab ${tabState.tabId}`, error);
  });
  return session;
}

function closeActiveSession(tabState, reason) {
  const activeSession = getActiveSession(tabState);
  if (!activeSession || activeSession.closed) {
    tabState.activeSessionKey = null;
    return null;
  }
  activeSession.closed = true;
  activeSession.closedAt = new Date().toISOString();
  tabState.activeSessionKey = null;
  void appendSessionDebugEvent(tabState, activeSession.sessionKey, {
    stage: "session_closed",
    reason,
    requestKind: null,
    url: activeSession.watchUrl,
  }).catch((error) => {
    logError(`Failed to record session close for tab ${tabState.tabId}`, error);
  });
  return activeSession;
}

function closeSessionsByWatchId(tabState, watchId, reason) {
  const closedSessions = [];
  for (const session of Object.values(tabState.sessions)) {
    if (session.closed || session.watchId !== watchId) {
      continue;
    }
    session.closed = true;
    session.closedAt = new Date().toISOString();
    if (tabState.activeSessionKey === session.sessionKey) {
      tabState.activeSessionKey = null;
    }
    closedSessions.push(session);
    void appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "session_closed",
      reason,
      requestKind: null,
      url: session.watchUrl,
    }).catch((error) => {
      logError(`Failed to record session close for tab ${tabState.tabId}`, error);
    });
  }
  return closedSessions;
}

function createPendingAssetRecord(session, kind, sourceUrl, language, bytes) {
  const assetKey = `${session.sessionKey}:${kind}:${Date.now()}:${Math.random().toString(16).slice(2, 8)}`;
  return {
    assetKey,
    kind,
    sourceUrl,
    language: language || null,
    byteLength: bytes.byteLength,
  };
}

async function flushSessionAssets(tabState, session) {
  const canFinalize = Boolean(session.metadata) || (session.closed && session.openRequestCount === 0);
  if (!canFinalize || session.pendingAssets.length === 0) {
    return;
  }
  const titleSlug = computeSessionTitleSlug(session);
  while (session.pendingAssets.length > 0) {
    const asset = session.pendingAssets.shift();
    const payload = capturePayloads.get(asset.assetKey);
    if (!payload) {
      await appendSessionDebugEvent(tabState, session.sessionKey, {
        stage: "asset_skipped",
        requestKind: asset.kind,
        reason: "payload_missing",
        url: asset.sourceUrl,
      });
      continue;
    }
    let filename;
    let mimeType;
    if (asset.kind === REQUEST_KIND_BIF) {
      filename = namingApi.buildBifFilename(titleSlug, asset.sourceUrl);
      mimeType = "application/octet-stream";
    } else {
      filename = namingApi.buildSubtitleFilename(titleSlug, asset.language, asset.sourceUrl);
      mimeType = "text/xml";
    }
    const downloadPath = namingApi.buildDownloadPath(titleSlug, filename);
    await startDownload(downloadPath, payload.bytes, mimeType);
    session.savedAssets.push({
      capturedAt: new Date().toISOString(),
      kind: asset.kind,
      sourceUrl: asset.sourceUrl,
      filename,
      downloadPath,
      language: asset.language,
      titleSlug,
    });
    capturePayloads.delete(asset.assetKey);
    await appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "asset_saved",
      requestKind: asset.kind,
      url: asset.sourceUrl,
      bytes: payload.bytes.byteLength,
      language: asset.language,
    });
  }
  await writeManifestForSession(session);
  dirtySessionKeys.add(session.sessionKey);
  await persistTabState(tabState);
  scheduleDebugFlush();
}

function concatenateChunks(chunks, totalBytes) {
  const output = new Uint8Array(totalBytes);
  let offset = 0;
  for (const chunk of chunks) {
    output.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return output;
}

async function processGraphqlCapture(tabState, session, bodyText, bytes) {
  const parsedMetadata = metadataApi.parseNetflixGraphqlMetadata(bodyText);
  await appendSessionDebugEvent(tabState, session.sessionKey, {
    stage: "request_completed",
    requestKind: REQUEST_KIND_GRAPHQL,
    url: "https://web.prod.cloud.netflix.com/graphql",
    bytes: bytes.byteLength,
    metadataParsed: Boolean(parsedMetadata),
  });
  if (!parsedMetadata) {
    await appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "metadata_skipped",
      requestKind: REQUEST_KIND_GRAPHQL,
      url: "https://web.prod.cloud.netflix.com/graphql",
      reason: "metadata_parse_returned_null",
      bodyPreview: buildBodyPreview(bodyText),
    });
    return;
  }
  await applyMetadataToSession(
    tabState,
    session,
    REQUEST_KIND_GRAPHQL,
    "https://web.prod.cloud.netflix.com/graphql",
    parsedMetadata,
    parsedMetadata.videoId,
  );
}

async function processMetadataCapture(tabState, session, requestEntry, bodyText, bytes) {
  const requestVideoId = matcherApi.extractMetadataVideoIdFromUrl(requestEntry.url);
  const parsedMetadata = metadataApi.parseNetflixMemberApiMetadata(bodyText, requestVideoId, session.tabTitle);
  await appendSessionDebugEvent(tabState, session.sessionKey, {
    stage: "request_completed",
    requestKind: REQUEST_KIND_METADATA,
    url: requestEntry.url,
    bytes: bytes.byteLength,
    metadataParsed: Boolean(parsedMetadata),
    requestVideoId: requestVideoId || null,
  });
  if (!parsedMetadata) {
    await appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "metadata_skipped",
      requestKind: REQUEST_KIND_METADATA,
      url: requestEntry.url,
      reason: "metadata_parse_returned_null",
      requestVideoId: requestVideoId || null,
      bodyPreview: buildBodyPreview(bodyText),
    });
    return;
  }
  await appendSessionDebugEvent(tabState, session.sessionKey, {
    stage: "metadata_attempt",
    requestKind: REQUEST_KIND_METADATA,
    url: requestEntry.url,
    kind: parsedMetadata.kind,
    videoId: parsedMetadata.videoId,
    showTitle: parsedMetadata.showTitle,
    movieTitle: parsedMetadata.movieTitle,
    episodeTitle: parsedMetadata.episodeTitle,
    seasonNumber: parsedMetadata.seasonNumber,
    episodeNumber: parsedMetadata.episodeNumber,
    requestVideoId: requestVideoId || null,
  });
  if (parsedMetadata.kind === "movie") {
    const diagnostics = metadataApi.parseNetflixMemberApiMetadataWithDiagnostics(
      bodyText,
      requestVideoId,
      session.tabTitle,
    );
    await appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "metadata_diagnostics",
      requestKind: REQUEST_KIND_METADATA,
      url: requestEntry.url,
      requestVideoId: requestVideoId || null,
      payloadTopKeys: extractTopLevelPayloadKeys(bodyText),
      signals: diagnostics.signals,
      candidateCount: diagnostics.candidates.length,
      candidates: summarizeDiagnosticCandidates(diagnostics.candidates),
    });
  }
  try {
    await applyMetadataToSession(
      tabState,
      session,
      REQUEST_KIND_METADATA,
      requestEntry.url,
      parsedMetadata,
      requestVideoId,
    );
  } catch (error) {
    logError(`Metadata application failed for tab ${tabState.tabId}`, error);
    void appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "metadata_apply_error",
      requestKind: REQUEST_KIND_METADATA,
      url: requestEntry.url,
      error: String(error && error.message ? error.message : error),
    }).catch(() => {});
    throw error;
  }
}

async function processBifCapture(tabState, session, requestEntry, bytes) {
  await appendSessionDebugEvent(tabState, session.sessionKey, {
    stage: "request_completed",
    requestKind: REQUEST_KIND_BIF,
    url: requestEntry.url,
    bytes: bytes.byteLength,
  });
  const pendingAsset = createPendingAssetRecord(session, REQUEST_KIND_BIF, requestEntry.url, null, bytes);
  capturePayloads.set(pendingAsset.assetKey, { bytes });
  session.pendingAssets.push(pendingAsset);
  await persistTabState(tabState);
  await flushSessionAssets(tabState, session);
}

async function processSubtitleCapture(tabState, session, requestEntry, bytes) {
  await appendSessionDebugEvent(tabState, session.sessionKey, {
    stage: "request_completed",
    requestKind: REQUEST_KIND_SUBTITLE,
    url: requestEntry.url,
    bytes: bytes.byteLength,
  });
  const contentType = requestEntry.responseInfo?.contentType || null;
  if (contentType && !contentType.toLowerCase().includes("xml")) {
    await appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "subtitle_rejected",
      requestKind: REQUEST_KIND_SUBTITLE,
      url: requestEntry.url,
      reason: "response_content_type_not_xml",
      contentType,
    });
    return;
  }
  const bodyText = new TextDecoder("utf-8").decode(bytes);
  if (!matcherApi.isTtmlSubtitleXml(bodyText)) {
    await appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "subtitle_rejected",
      requestKind: REQUEST_KIND_SUBTITLE,
      url: requestEntry.url,
      reason: "ttml_subs_markers_missing",
      bytes: bytes.byteLength,
      bodyPreview: buildBodyPreview(bodyText),
    });
    return;
  }
  const language = matcherApi.extractSubtitleLanguage(bodyText);
  const pendingAsset = createPendingAssetRecord(session, REQUEST_KIND_SUBTITLE, requestEntry.url, language, bytes);
  capturePayloads.set(pendingAsset.assetKey, { bytes });
  session.pendingAssets.push(pendingAsset);
  await persistTabState(tabState);
  await flushSessionAssets(tabState, session);
}

async function finalizeRequest(requestEntry) {
  const tabState = captureTabStates.get(requestEntry.tabId);
  if (!tabState) {
    return;
  }
  const session = getSession(tabState, requestEntry.sessionKey);
  if (!session) {
    return;
  }
  session.openRequestCount = Math.max(0, session.openRequestCount - 1);
  const bytes = concatenateChunks(requestEntry.chunks, requestEntry.totalBytes);
  try {
    if (requestEntry.kind === REQUEST_KIND_GRAPHQL) {
      const bodyText = new TextDecoder("utf-8").decode(bytes);
      await processGraphqlCapture(tabState, session, bodyText, bytes);
    } else if (requestEntry.kind === REQUEST_KIND_METADATA) {
      const bodyText = new TextDecoder("utf-8").decode(bytes);
      await processMetadataCapture(tabState, session, requestEntry, bodyText, bytes);
    } else if (requestEntry.kind === REQUEST_KIND_BIF) {
      await processBifCapture(tabState, session, requestEntry, bytes);
    } else if (requestEntry.kind === REQUEST_KIND_SUBTITLE) {
      await processSubtitleCapture(tabState, session, requestEntry, bytes);
    }
    await persistTabState(tabState);
    if (session.closed) {
      await flushSessionAssets(tabState, session);
    }
  } catch (error) {
    logError(`Failed to finalize ${requestEntry.kind} capture for ${requestEntry.url}`, error);
    void appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "finalize_error",
      requestKind: requestEntry.kind,
      url: requestEntry.url,
      error: String(error && error.message ? error.message : error),
    }).catch(() => {});
    throw error;
  }
}

function finalizeRequestEntry(requestId) {
  const requestEntry = activeFilters.get(requestId);
  activeFilters.delete(requestId);
  return requestEntry;
}

function createFilter(details, kind, sessionKey) {
  const filter = browserApi.webRequest.filterResponseData(details.requestId);
  const requestEntry = {
    requestId: details.requestId,
    tabId: details.tabId,
    sessionKey,
    url: details.url,
    kind,
    status: FILTER_STATUS_ACTIVE,
    chunks: [],
    totalBytes: 0,
    responseInfo: null,
  };
  activeFilters.set(details.requestId, requestEntry);

  filter.ondata = (event) => {
    try {
      filter.write(event.data);
      if (requestEntry.status !== FILTER_STATUS_ACTIVE) {
        return;
      }
      requestEntry.totalBytes += event.data.byteLength;
      if (requestEntry.totalBytes > CAPTURE_BUFFER_LIMIT_BYTES) {
        requestEntry.status = FILTER_STATUS_OVERFLOW;
        requestEntry.chunks = [];
        const tabState = captureTabStates.get(details.tabId);
        if (tabState) {
          void appendSessionDebugEvent(tabState, sessionKey, {
            stage: "request_dropped",
            requestKind: kind,
            url: details.url,
            reason: "buffer_limit_exceeded",
            bytes: requestEntry.totalBytes,
          }).catch((error) => {
            logError(`Failed to log buffer overflow for ${details.url}`, error);
          });
        }
        return;
      }
      requestEntry.chunks.push(new Uint8Array(event.data));
    } catch (error) {
      requestEntry.status = FILTER_STATUS_ERROR;
      logError(`Failed to process response chunk for ${details.url}`, error);
      try {
        filter.disconnect();
      } catch (disconnectError) {
        logError(`Failed to disconnect filter for ${details.url}`, disconnectError);
      }
    }
  };

  filter.onerror = (event) => {
    requestEntry.status = FILTER_STATUS_ERROR;
    logError(`Stream filter error for ${details.url}`, event);
    const tabState = captureTabStates.get(details.tabId);
    if (tabState) {
      void appendSessionDebugEvent(tabState, sessionKey, {
        stage: "request_dropped",
        requestKind: kind,
        url: details.url,
        reason: "stream_filter_error",
      }).catch((error) => {
        logError(`Failed to log stream error for ${details.url}`, error);
      });
    }
  };

  filter.onstop = () => {
    try {
      filter.close();
    } catch (error) {
      logError(`Failed to close stream filter for ${details.url}`, error);
    }
    requestEntry.status =
      requestEntry.status === FILTER_STATUS_ACTIVE ? FILTER_STATUS_COMPLETED : requestEntry.status;
    const finalizedEntry = finalizeRequestEntry(details.requestId);
    if (!finalizedEntry || finalizedEntry.status !== FILTER_STATUS_COMPLETED) {
      return;
    }
    void finalizeRequest(finalizedEntry).catch((error) => {
      logError(`Failed to finalize capture for ${details.url}`, error);
    });
  };
}

function handleBeforeRequest(details) {
  const tabState = captureTabStates.get(details.tabId);
  if (!tabState || !tabState.captureEnabled) {
    return;
  }
  syncTabStateFromKnownContext(tabState);
  const knownTab = getKnownNetflixTab(details.tabId);
  if (!knownTab || !matcherApi.isNetflixWatchUrl(knownTab.currentUrl || "")) {
    return;
  }
  const requestKind = classifyRequestFromUrl(details);
  if (!requestKind) {
    return;
  }
  const session = ensureActiveSession(tabState);
  if (!session) {
    return;
  }
  if (requestKind !== REQUEST_KIND_GRAPHQL) {
    if (session.seenRequestUrls.includes(details.url)) {
      void appendSessionDebugEvent(tabState, session.sessionKey, {
        stage: "request_skipped",
        requestKind,
        url: details.url,
        reason: "duplicate_url_in_session",
      }).catch((error) => {
        logError(`Failed to log duplicate request for ${details.url}`, error);
      });
      return;
    }
    session.seenRequestUrls.push(details.url);
  }
  session.openRequestCount += 1;
  void persistTabState(tabState).catch((error) => {
    logError(`Failed to persist request state for tab ${details.tabId}`, error);
  });
  createFilter(details, requestKind, session.sessionKey);
}

function handleHeadersReceived(details) {
  const tabState = captureTabStates.get(details.tabId);
  if (!tabState || !tabState.captureEnabled) {
    return;
  }
  const requestEntry = activeFilters.get(details.requestId);
  const sessionKey = requestEntry ? requestEntry.sessionKey : tabState.activeSessionKey;
  const contentType = getHeaderValue(details, "content-type");
  const requestKind = classifyRequestFromHeaders(details) || "ignored";
  if (sessionKey) {
    void appendSessionDebugEvent(tabState, sessionKey, {
      stage: "headers_received",
      requestKind,
      url: details.url,
      contentType,
      statusCode: details.statusCode,
    }).catch((error) => {
      logError(`Failed to log headers for ${details.url}`, error);
    });
  }
  if (requestEntry) {
    requestEntry.responseInfo = {
      contentType,
      statusCode: details.statusCode,
    };
  }
}

async function closeAllSessions(tabState, reason) {
  const activeSession = closeActiveSession(tabState, reason);
  if (activeSession) {
    await persistTabState(tabState);
    await flushSessionAssets(tabState, activeSession);
  }
  for (const session of Object.values(tabState.sessions)) {
    if (!session.closed) {
      session.closed = true;
      session.closedAt = new Date().toISOString();
      await appendSessionDebugEvent(tabState, session.sessionKey, {
        stage: "session_closed",
        reason,
        requestKind: null,
        url: session.watchUrl,
      });
      await flushSessionAssets(tabState, session);
    }
  }
}

async function disableCaptureForTab(tabId) {
  const tabState = captureTabStates.get(tabId);
  if (!tabState) {
    try {
      await clearBadge(tabId);
    } catch (_error) {
      return;
    }
    return;
  }
  tabState.captureEnabled = false;
  tabState.seriesTitleHint = null;
  tabState.seriesHintWatchId = null;
  tabState.seriesHintPending = false;
  await closeAllSessions(tabState, "user_disabled");
  await persistTabState(tabState);
  await appendGlobalDebugEvent({
    stage: "capture_disabled",
    tabId,
  });
  await flushDebugLogs();
  try {
    await clearBadge(tabId);
  } catch (_error) {
    return;
  }
  logInfo(`Capture disabled for tab ${tabId}`);
}

async function enableCaptureForTab(tab) {
  const hasPermissions = await ensureOptionalPermissions();
  if (!hasPermissions) {
    return;
  }
  await ensureListenersRegistered();
  updateKnownNetflixTab(tab.id, tab.url || "", tab.title || "");
  const tabState = (await ensureEnabledTabStateForTab(tab)) || createTabState(tab);
  tabState.captureEnabled = true;
  syncTabStateFromKnownContext(tabState);
  const session = ensureActiveSession(tabState);
  await persistTabState(tabState);
  await setBadgeEnabled(tab.id, true);
  if (session) {
    await appendSessionDebugEvent(tabState, session.sessionKey, {
      stage: "capture_enabled",
      requestKind: null,
      url: tab.url || "",
    });
  } else {
    await appendGlobalDebugEvent({
      stage: "capture_enabled",
      tabId: tab.id,
      url: tab.url || "",
    });
  }
  logInfo(`Capture enabled for tab ${tab.id}`, { url: tab.url });
}

async function handleActionClicked(tab) {
  if (!tab || typeof tab.id !== "number") {
    return;
  }
  updateKnownNetflixTab(tab.id, tab.url || "", tab.title || "");
  if (!(tab.url || "").startsWith("https://www.netflix.com/")) {
    return;
  }
  const existingState = captureTabStates.get(tab.id);
  if (existingState && existingState.captureEnabled) {
    await disableCaptureForTab(tab.id);
    return;
  }
  await enableCaptureForTab(tab);
}

async function handleTabUpdated(tabId, changeInfo, tab) {
  updateKnownNetflixTab(tabId, tab?.url || changeInfo.url || "", tab?.title || "");
  let tabState = captureTabStates.get(tabId) || null;
  let autoEnabled = false;
  if (!tabState && tab && (tab.url || "").startsWith("https://www.netflix.com/")) {
    tabState = await ensureEnabledTabStateForTab(tab);
    autoEnabled = Boolean(tabState && tabState.captureEnabled);
  }
  if (!tabState) {
    return;
  }
  const previousWatchId = tabState.currentWatchId;
  syncTabStateFromKnownContext(tabState);
  const nextWatchId = tabState.currentWatchId;
  if (!tabState.captureEnabled) {
    await persistTabState(tabState);
    return;
  }
  if (previousWatchId !== nextWatchId) {
    const transitionReason = previousWatchId && nextWatchId ? "watch_changed" : "left_watch_page";
    const closedSessions = previousWatchId
      ? closeSessionsByWatchId(tabState, previousWatchId, transitionReason)
      : [];
    const hintSession = closedSessions.find((session) => deriveSeriesTitleFromMetadata(session.metadata));
    if (hintSession && transitionReason === "watch_changed") {
      tabState.seriesTitleHint = deriveSeriesTitleFromMetadata(hintSession.metadata);
      tabState.seriesHintWatchId = hintSession.watchId;
      tabState.seriesHintPending = true;
    }
    for (const closedSession of closedSessions) {
      await flushSessionAssets(tabState, closedSession);
    }
    if (transitionReason === "left_watch_page") {
      tabState.seriesTitleHint = null;
      tabState.seriesHintWatchId = null;
      tabState.seriesHintPending = false;
    }
    if (nextWatchId) {
      ensureActiveSession(tabState);
    }
  } else {
    const activeSession = getActiveSession(tabState);
    if (activeSession) {
      activeSession.watchUrl = tabState.currentUrl;
      activeSession.tabTitle = tabState.currentTabTitle;
    }
  }
  await persistTabState(tabState);
  if (autoEnabled) {
    await setBadgeEnabled(tabId, true);
  }
  const activeSession = getActiveSession(tabState);
  if (activeSession) {
    await appendSessionDebugEvent(tabState, activeSession.sessionKey, {
      stage: "tab_updated",
      requestKind: null,
      url: tabState.currentUrl,
    });
  } else {
    await appendGlobalDebugEvent({
      stage: "tab_updated",
      tabId,
      url: tabState.currentUrl,
    });
  }
}

async function handleTabRemoved(tabId) {
  knownNetflixTabs.delete(tabId);
  await removeTabState(tabId);
  try {
    await clearBadge(tabId);
  } catch (_error) {
    return;
  }
}

function registerCoreListeners() {
  if (coreListenersRegistered) {
    return;
  }
  browserApi.action.onClicked.addListener(handleActionClicked);
  browserApi.tabs.onUpdated.addListener(handleTabUpdated);
  browserApi.tabs.onRemoved.addListener(handleTabRemoved);
  coreListenersRegistered = true;
}

function registerRequestListeners() {
  if (requestListenersRegistered) {
    return;
  }
  browserApi.webRequest.onBeforeRequest.addListener(
    handleBeforeRequest,
    REQUEST_FILTER,
    ["blocking"],
  );
  browserApi.webRequest.onHeadersReceived.addListener(
    handleHeadersReceived,
    REQUEST_FILTER,
    ["blocking", "responseHeaders"],
  );
  requestListenersRegistered = true;
}

async function ensureListenersRegistered() {
  registerCoreListeners();
  registerRequestListeners();
}

async function restoreBadgeState() {
  for (const [tabId, tabState] of captureTabStates.entries()) {
    try {
      await setBadgeEnabled(tabId, Boolean(tabState.captureEnabled));
    } catch (_error) {
      logInfo(`Skipping badge restore for stale tab ${tabId}`);
    }
  }
}

async function bootstrap() {
  await initializeState();
  const existingTabs = await browserApi.tabs.query({
    url: ["https://www.netflix.com/*"],
  });
  const realTabIds = new Set(existingTabs.map((tab) => tab.id));
  for (const tabId of Array.from(captureTabStates.keys())) {
    if (!realTabIds.has(tabId)) {
      await removeTabState(tabId);
    }
  }
  for (const tab of existingTabs) {
    updateKnownNetflixTab(tab.id, tab.url || "", tab.title || "");
    const existingState = captureTabStates.get(tab.id);
    if (!existingState) {
      await ensureEnabledTabStateForTab(tab);
      continue;
    }
    syncTabStateFromKnownContext(existingState);
    await persistTabState(existingState);
  }
  registerCoreListeners();
  const hasPermissions = await browserApi.permissions.contains({
    origins: OPTIONAL_HOST_PERMISSIONS,
  });
  if (hasPermissions) {
    registerRequestListeners();
  }
  for (const tabState of captureTabStates.values()) {
    syncTabStateFromKnownContext(tabState);
    if (!tabState.currentWatchId) {
      tabState.activeSessionKey = null;
    }
  }
  await restoreBadgeState();
  scheduleDebugFlush();
}

void bootstrap().catch((error) => {
  logError("Failed to bootstrap extension background script.", error);
});
