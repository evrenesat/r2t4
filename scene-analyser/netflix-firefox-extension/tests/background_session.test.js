const test = require("node:test");
const assert = require("node:assert/strict");

function createMockSession(sessionKey, watchId, closed) {
  return {
    sessionKey,
    watchId,
    watchUrl: `https://www.netflix.com/watch/${watchId}`,
    tabTitle: "Test Title",
    metadata: null,
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
