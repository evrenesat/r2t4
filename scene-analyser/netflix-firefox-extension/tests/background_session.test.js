const test = require("node:test");
const assert = require("node:assert/strict");
const { normalizeTabTitle } = require("../lib/file_naming.js");
const { promoteMovieMetadataWithTabTitle } = require("../lib/metadata_parser.js");

function createMockSession(sessionKey, watchId, closed) {
  return {
    sessionKey,
    watchId,
    watchUrl: `https://www.netflix.com/watch/${watchId}`,
    tabTitle: "Test Title",
    metadata: null,
    provisionalMetadata: null,
    startedAt: new Date().toISOString(),
    closed: Boolean(closed),
    closedAt: closed ? new Date().toISOString() : null,
    openRequestCount: 0,
    seenRequestUrls: [],
    pendingAssets: [],
    savedAssets: [],
    debugEvents: [],
  };
}

function createTabState(tabId, activeSessionKey) {
  return {
    tabId,
    captureEnabled: true,
    currentUrl: "",
    currentWatchId: null,
    currentTabTitle: "",
    activeSessionKey,
    seriesTitleHint: null,
    seriesHintWatchId: null,
    seriesHintPending: false,
    sessions: {},
  };
}

function closeSessionsByWatchId(tabState, watchId, _reason) {
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
  }
  return closedSessions;
}

function extractWatchIdFromUrl(url) {
  const match = typeof url === "string" ? url.match(/\/watch\/([^/?]+)/) : null;
  return match ? match[1] : null;
}

function isGenericTabTitle(tabTitle) {
  return !normalizeTabTitle(tabTitle);
}

function updateKnownNetflixTab(knownTabs, tabId, url, title) {
  const existingKnownTab = knownTabs.get(tabId) || null;
  const urlValue = typeof url === "string" && url ? url : existingKnownTab?.currentUrl || "";
  if (!urlValue) {
    knownTabs.delete(tabId);
    return;
  }
  const nextWatchId = extractWatchIdFromUrl(urlValue);
  const watchChanged = Boolean(existingKnownTab && existingKnownTab.watchId !== nextWatchId);
  const titleValue =
    typeof title === "string" && title
      ? title
      : watchChanged
        ? ""
        : existingKnownTab?.tabTitle || "";
  knownTabs.set(tabId, {
    currentUrl: urlValue,
    watchId: nextWatchId,
    tabTitle: titleValue,
  });
}

function diagnosticsShowEpisodeContext(diagnostics) {
  const hasSeriesSignals =
    Boolean(diagnostics.signals?.hasSeriesEntityType) ||
    Boolean(diagnostics.signals?.hasSeriesCountField) ||
    (Array.isArray(diagnostics.signals?.showContainerTitlesFound) && diagnostics.signals.showContainerTitlesFound.length > 0);
  return hasSeriesSignals && diagnostics.candidates.some((candidate) => candidate.kind === "episode" && candidate.showTitle);
}

function shouldDeferMetadataApplication(tabTitle, parsedMetadata, diagnostics, seriesHintInferred) {
  return (
    parsedMetadata.kind === "movie" &&
    !seriesHintInferred &&
    isGenericTabTitle(tabTitle) &&
    diagnosticsShowEpisodeContext(diagnostics)
  );
}

function finalizeProvisionalMetadata(session, tabTitle) {
  if (!session.provisionalMetadata) {
    return null;
  }
  const promoted = !isGenericTabTitle(tabTitle)
    ? promoteMovieMetadataWithTabTitle(session.provisionalMetadata.metadata, tabTitle)
    : session.provisionalMetadata.metadata;
  session.metadata = promoted;
  session.provisionalMetadata = null;
  return promoted;
}

test("closeSessionsByWatchId closes only sessions matching the given watch ID", () => {
  const tabState = createTabState(1, "1:AAA:1");
  const sessionA = createMockSession("1:AAA:1", "AAA", false);
  const sessionB = createMockSession("1:BBB:2", "BBB", false);
  tabState.sessions["1:AAA:1"] = sessionA;
  tabState.sessions["1:BBB:2"] = sessionB;
  tabState.activeSessionKey = "1:BBB:2";

  const closed = closeSessionsByWatchId(tabState, "AAA", "watch_changed");

  assert.equal(closed.length, 1);
  assert.equal(closed[0].sessionKey, "1:AAA:1");
  assert.equal(sessionA.closed, true);
  assert.equal(sessionB.closed, false);
  assert.equal(tabState.activeSessionKey, "1:BBB:2",
    "active session for different watchId should not be cleared");
});

test("closeSessionsByWatchId clears activeSessionKey when it matches the closed watch ID", () => {
  const tabState = createTabState(1, "1:AAA:1");
  const sessionA = createMockSession("1:AAA:1", "AAA", false);
  tabState.sessions["1:AAA:1"] = sessionA;
  tabState.activeSessionKey = "1:AAA:1";

  const closed = closeSessionsByWatchId(tabState, "AAA", "watch_changed");

  assert.equal(closed.length, 1);
  assert.equal(tabState.activeSessionKey, null);
});

test("closeSessionsByWatchId skips already-closed sessions", () => {
  const tabState = createTabState(1, null);
  const sessionA = createMockSession("1:AAA:1", "AAA", true);
  const sessionB = createMockSession("1:AAA:2", "AAA", false);
  tabState.sessions["1:AAA:1"] = sessionA;
  tabState.sessions["1:AAA:2"] = sessionB;

  const closed = closeSessionsByWatchId(tabState, "AAA", "watch_changed");

  assert.equal(closed.length, 1);
  assert.equal(closed[0].sessionKey, "1:AAA:2");
});

test("closeSessionsByWatchId returns empty array when no sessions match", () => {
  const tabState = createTabState(1, "1:BBB:1");
  const sessionB = createMockSession("1:BBB:1", "BBB", false);
  tabState.sessions["1:BBB:1"] = sessionB;

  const closed = closeSessionsByWatchId(tabState, "AAA", "watch_changed");

  assert.equal(closed.length, 0);
  assert.equal(sessionB.closed, false);
  assert.equal(tabState.activeSessionKey, "1:BBB:1");
});

test("race scenario: new session for next watchId survives when old watchId is closed", () => {
  const tabState = createTabState(1, "1:BBB:2");
  const oldSession = createMockSession("1:AAA:1", "AAA", false);
  const newSession = createMockSession("1:BBB:2", "BBB", false);
  tabState.sessions["1:AAA:1"] = oldSession;
  tabState.sessions["1:BBB:2"] = newSession;
  tabState.activeSessionKey = "1:BBB:2";

  const closed = closeSessionsByWatchId(tabState, "AAA", "watch_changed");

  assert.equal(closed.length, 1);
  assert.equal(closed[0].watchId, "AAA");
  assert.equal(newSession.closed, false,
    "new session for next watchId must not be closed");
  assert.equal(tabState.activeSessionKey, "1:BBB:2",
    "activeSessionKey must still point to the new session");
});

test("title-only updates keep the existing watch URL and use the new title", () => {
  const knownTabs = new Map();
  updateKnownNetflixTab(knownTabs, 1, "https://www.netflix.com/watch/AAA", "Netflix");
  updateKnownNetflixTab(knownTabs, 1, "", "Brooklyn Nine-Nine: Captain Peralta | Netflix");

  assert.deepEqual(knownTabs.get(1), {
    currentUrl: "https://www.netflix.com/watch/AAA",
    watchId: "AAA",
    tabTitle: "Brooklyn Nine-Nine: Captain Peralta | Netflix",
  });
});

test("watch changes clear stale titles until a new title arrives", () => {
  const knownTabs = new Map();
  updateKnownNetflixTab(knownTabs, 1, "https://www.netflix.com/watch/AAA", "Old Show | Netflix");
  updateKnownNetflixTab(knownTabs, 1, "https://www.netflix.com/watch/BBB", "");

  assert.deepEqual(knownTabs.get(1), {
    currentUrl: "https://www.netflix.com/watch/BBB",
    watchId: "BBB",
    tabTitle: "",
  });
});

test("ambiguous movie metadata stays provisional until a useful title arrives", () => {
  const parsedMetadata = {
    kind: "movie",
    entityType: "Movie",
    videoId: 80011399,
    showTitle: null,
    movieTitle: "Captain Peralta",
    seasonNumber: null,
    episodeNumber: null,
    episodeTitle: null,
  };
  const diagnostics = {
    signals: {
      hasSeriesEntityType: true,
      hasSeriesCountField: false,
      showContainerTitlesFound: [],
    },
    candidates: [
      { kind: "movie", showTitle: null },
      { kind: "episode", showTitle: "Brooklyn Nine-Nine" },
    ],
  };

  assert.equal(
    shouldDeferMetadataApplication("Netflix", parsedMetadata, diagnostics, false),
    true,
  );
});

test("late useful titles promote provisional movie metadata to episodes", () => {
  const session = createMockSession("1:AAA:1", "AAA", false);
  session.provisionalMetadata = {
    metadata: {
      kind: "movie",
      entityType: "Movie",
      videoId: 80011399,
      showTitle: null,
      movieTitle: "Captain Peralta",
      seasonNumber: null,
      episodeNumber: null,
      episodeTitle: null,
    },
  };

  const finalized = finalizeProvisionalMetadata(session, "Brooklyn Nine-Nine: Captain Peralta | Netflix");

  assert.deepEqual(finalized, {
    source: "tab_title_promoted",
    kind: "episode",
    entityType: "Episode",
    videoId: 80011399,
    showTitle: "Brooklyn Nine-Nine",
    movieTitle: null,
    seasonNumber: null,
    episodeNumber: null,
    episodeTitle: "Captain Peralta",
  });
  assert.equal(session.provisionalMetadata, null);
});

test("closed sessions fall back to provisional movie metadata when no better title arrives", () => {
  const session = createMockSession("1:AAA:1", "AAA", true);
  session.provisionalMetadata = {
    metadata: {
      kind: "movie",
      entityType: "Movie",
      videoId: 80011399,
      showTitle: null,
      movieTitle: "Captain Peralta",
      seasonNumber: null,
      episodeNumber: null,
      episodeTitle: null,
    },
  };

  const finalized = finalizeProvisionalMetadata(session, "Netflix");

  assert.deepEqual(finalized, {
    kind: "movie",
    entityType: "Movie",
    videoId: 80011399,
    showTitle: null,
    movieTitle: "Captain Peralta",
    seasonNumber: null,
    episodeNumber: null,
    episodeTitle: null,
  });
  assert.equal(session.provisionalMetadata, null);
});
