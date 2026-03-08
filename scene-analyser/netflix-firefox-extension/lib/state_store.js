(function attachStateStore(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.NetflixStateStore = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function buildStateStore() {
  const STORAGE_KEY = "captureTabStates";
  const GLOBAL_DEBUG_EVENTS_KEY = "captureGlobalDebugEvents";

  function cloneValue(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function normalizeTabId(tabId) {
    return String(tabId);
  }

  function createStateStore(storageArea) {
    if (!storageArea || typeof storageArea.get !== "function" || typeof storageArea.set !== "function") {
      throw new Error("A storage area with async get/set methods is required.");
    }

    async function getAllTabStates() {
      const result = await storageArea.get(STORAGE_KEY);
      const storedStates = result && typeof result === "object" ? result[STORAGE_KEY] : {};
      return storedStates && typeof storedStates === "object" ? cloneValue(storedStates) : {};
    }

    async function setAllTabStates(tabStates) {
      await storageArea.set({
        [STORAGE_KEY]: cloneValue(tabStates),
      });
    }

    async function getTabState(tabId) {
      const tabStates = await getAllTabStates();
      const key = normalizeTabId(tabId);
      return key in tabStates ? cloneValue(tabStates[key]) : null;
    }

    async function getGlobalDebugEvents() {
      const result = await storageArea.get(GLOBAL_DEBUG_EVENTS_KEY);
      const storedEvents = result && typeof result === "object" ? result[GLOBAL_DEBUG_EVENTS_KEY] : [];
      return Array.isArray(storedEvents) ? cloneValue(storedEvents) : [];
    }

    async function setTabState(tabId, tabState) {
      const tabStates = await getAllTabStates();
      tabStates[normalizeTabId(tabId)] = cloneValue(tabState);
      await setAllTabStates(tabStates);
    }

    async function deleteTabState(tabId) {
      const tabStates = await getAllTabStates();
      delete tabStates[normalizeTabId(tabId)];
      await setAllTabStates(tabStates);
    }

    async function setGlobalDebugEvents(events) {
      await storageArea.set({
        [GLOBAL_DEBUG_EVENTS_KEY]: cloneValue(events),
      });
    }

    return {
      deleteTabState,
      getAllTabStates,
      getGlobalDebugEvents,
      getTabState,
      setGlobalDebugEvents,
      setAllTabStates,
      setTabState,
      GLOBAL_DEBUG_EVENTS_KEY,
      STORAGE_KEY,
    };
  }

  return {
    GLOBAL_DEBUG_EVENTS_KEY,
    STORAGE_KEY,
    createStateStore,
  };
});
