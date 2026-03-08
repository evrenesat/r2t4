const test = require("node:test");
const assert = require("node:assert/strict");

const { createStateStore } = require("../lib/state_store.js");

function createFakeStorageArea() {
  const backingStore = {};
  return {
    async get(key) {
      if (typeof key === "string") {
        return { [key]: backingStore[key] };
      }
      return { ...backingStore };
    },
    async set(values) {
      Object.assign(backingStore, JSON.parse(JSON.stringify(values)));
    },
  };
}

test("persists and deletes per-tab capture state", async () => {
  const store = createStateStore(createFakeStorageArea());
  const tabState = {
    tabId: 7,
    captureEnabled: true,
    seenRequestUrls: ["https://example.com/subtitles.xml"],
  };

  await store.setTabState(7, tabState);
  assert.deepEqual(await store.getTabState(7), tabState);
  assert.deepEqual(await store.getAllTabStates(), { "7": tabState });

  await store.deleteTabState(7);
  assert.equal(await store.getTabState(7), null);
  assert.deepEqual(await store.getAllTabStates(), {});
});

test("persists global debug events", async () => {
  const store = createStateStore(createFakeStorageArea());
  const events = [{ stage: "headers_received", url: "https://example.com/file.bif" }];

  await store.setGlobalDebugEvents(events);
  assert.deepEqual(await store.getGlobalDebugEvents(), events);
});
