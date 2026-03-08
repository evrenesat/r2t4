(function attachMetadataParser(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.NetflixMetadataParser = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function buildMetadataParser() {
  const TITLE_KEYS = ["title", "name", "longTitle", "shortTitle"];
  const SHOW_TITLE_KEYS = ["showTitle", "seriesTitle", "parentTitle", "seriesName", "showName"];
  const EPISODE_TITLE_KEYS = ["episodeTitle", "subtitle", "subTitle"];
  const VIDEO_ID_KEYS = ["videoId", "movieid", "movieId", "episodeId", "id"];
  const SEASON_NUMBER_KEYS = ["seasonNumber", "seasonNum", "season"];
  const EPISODE_NUMBER_KEYS = ["episodeNumber", "episodeNum", "episode"];
  const SHOW_CONTAINER_KEYS = ["show", "series", "parent", "parentShow", "ancestor", "seriesMetadata"];
  const SERIES_COUNT_KEYS = ["numSeasons", "numberOfEpisodes", "numEpisodes", "seasonCount", "episodeCount"];
  const ENTITY_TYPE_KEYS = ["type", "entityType", "__typename", "videoType"];
  const EPISODE_ENTITY_VALUES = new Set(["episode", "show", "series", "tvseries", "miniseries", "Episode", "Show"]);
  const MAX_METADATA_SEARCH_DEPTH = 8;

  function parseJsonBody(input) {
    if (typeof input === "string") {
      const trimmedInput = input.trim();
      if (!trimmedInput) {
        return null;
      }
      try {
        return JSON.parse(trimmedInput);
      } catch (_error) {
        return null;
      }
    }
    return input && typeof input === "object" ? input : null;
  }

  function toNullableNumber(value) {
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
    if (typeof value === "string" && /^\d+$/.test(value.trim())) {
      const parsedValue = Number.parseInt(value.trim(), 10);
      return Number.isFinite(parsedValue) ? parsedValue : null;
    }
    return null;
  }

  function getStringValue(object, keys) {
    if (!object || typeof object !== "object" || Array.isArray(object)) {
      return null;
    }
    for (const key of keys) {
      if (typeof object[key] === "string" && object[key].trim()) {
        return object[key].trim();
      }
    }
    return null;
  }

  function getNumberValue(object, keys) {
    if (!object || typeof object !== "object" || Array.isArray(object)) {
      return null;
    }
    for (const key of keys) {
      const numericValue = toNullableNumber(object[key]);
      if (numericValue !== null) {
        return numericValue;
      }
    }
    return null;
  }

  function buildMetadataResult(candidate) {
    if (!candidate) {
      return null;
    }
    return {
      kind: candidate.kind,
      entityType: candidate.entityType,
      videoId: candidate.videoId,
      showTitle: candidate.showTitle,
      movieTitle: candidate.movieTitle,
      seasonNumber: candidate.seasonNumber,
      episodeNumber: candidate.episodeNumber,
      episodeTitle: candidate.episodeTitle,
    };
  }

  function candidateScore(candidate, expectedVideoId) {
    let score = 0;
    if (candidate.videoId !== null && expectedVideoId !== null && candidate.videoId === expectedVideoId) {
      score += 50;
    }
    if (candidate.showTitle) {
      score += 20;
    }
    if (candidate.movieTitle) {
      score += 18;
    }
    if (candidate.episodeTitle) {
      score += 16;
    }
    if (candidate.seasonNumber !== null) {
      score += 8;
    }
    if (candidate.episodeNumber !== null) {
      score += 8;
    }
    if (candidate.kind === "episode") {
      score += 10;
    }
    return score;
  }

  function hasSeriesEntityType(node) {
    for (const key of ENTITY_TYPE_KEYS) {
      const value = node[key];
      if (typeof value === "string" && EPISODE_ENTITY_VALUES.has(value)) {
        return true;
      }
    }
    return false;
  }

  function isShowLevelEntityType(node) {
    for (const key of ENTITY_TYPE_KEYS) {
      const value = node[key];
      if (typeof value !== "string") continue;
      const lower = value.toLowerCase();
      if (lower === "show" || lower === "series" || lower === "tvseries" || lower === "miniseries") {
        return true;
      }
    }
    return false;
  }

  function hasSeriesCountField(node) {
    for (const key of SERIES_COUNT_KEYS) {
      if (toNullableNumber(node[key]) !== null) {
        return true;
      }
    }
    return false;
  }

  function buildHeuristicCandidate(node, expectedVideoId) {
    if (!node || typeof node !== "object" || Array.isArray(node)) {
      return null;
    }

    const showTitle = getStringValue(node, SHOW_TITLE_KEYS);
    const mainTitle = getStringValue(node, TITLE_KEYS);
    const explicitEpisodeTitle = getStringValue(node, EPISODE_TITLE_KEYS);
    const seasonNumber =
      getNumberValue(node, SEASON_NUMBER_KEYS) ||
      getNumberValue(node.season, ["number"]) ||
      null;
    const episodeNumber =
      getNumberValue(node, EPISODE_NUMBER_KEYS) ||
      getNumberValue(node.episode, ["number"]) ||
      null;
    const directVideoId = getNumberValue(node, VIDEO_ID_KEYS);
    const videoId = directVideoId !== null ? directVideoId : expectedVideoId;
    const hasEpisodeSignals =
      explicitEpisodeTitle !== null ||
      seasonNumber !== null ||
      episodeNumber !== null ||
      hasSeriesEntityType(node) ||
      hasSeriesCountField(node) ||
      (showTitle !== null && mainTitle !== null && showTitle !== mainTitle);
    const entityType = hasEpisodeSignals ? "Episode" : "Movie";
    const movieTitle = !hasEpisodeSignals ? mainTitle : null;
    const showLevelType = isShowLevelEntityType(node) || hasSeriesCountField(node);
    const episodeTitle = hasEpisodeSignals
      ? explicitEpisodeTitle || (mainTitle && mainTitle !== showTitle && !showLevelType ? mainTitle : null)
      : null;
    const normalizedShowTitle = hasEpisodeSignals
      ? showTitle || (episodeTitle ? null : mainTitle) || null
      : null;

    if (!normalizedShowTitle && !movieTitle && !episodeTitle) {
      return null;
    }

    return {
      kind: hasEpisodeSignals ? "episode" : "movie",
      entityType,
      videoId,
      showTitle: normalizedShowTitle,
      movieTitle,
      seasonNumber,
      episodeNumber,
      episodeTitle,
    };
  }

  function collectScalarValues(node, depth, valuesByKey) {
    if (!node || typeof node !== "object" || depth > MAX_METADATA_SEARCH_DEPTH) {
      return;
    }
    if (Array.isArray(node)) {
      for (const item of node) {
        collectScalarValues(item, depth + 1, valuesByKey);
      }
      return;
    }
    for (const [key, value] of Object.entries(node)) {
      if (typeof value === "string" && value.trim()) {
        if (!valuesByKey[key]) {
          valuesByKey[key] = [];
        }
        valuesByKey[key].push(value.trim());
        continue;
      }
      const numericValue = toNullableNumber(value);
      if (numericValue !== null) {
        if (!valuesByKey[key]) {
          valuesByKey[key] = [];
        }
        valuesByKey[key].push(numericValue);
        continue;
      }
      collectScalarValues(value, depth + 1, valuesByKey);
    }
  }

  function collectShowContainerTitles(node, depth, collectedTitles) {
    if (!node || typeof node !== "object" || depth > MAX_METADATA_SEARCH_DEPTH) {
      return;
    }
    if (Array.isArray(node)) {
      for (const item of node) {
        collectShowContainerTitles(item, depth + 1, collectedTitles);
      }
      return;
    }
    for (const [key, value] of Object.entries(node)) {
      if (SHOW_CONTAINER_KEYS.includes(key) && value && typeof value === "object" && !Array.isArray(value)) {
        const title = getStringValue(value, TITLE_KEYS);
        if (title) {
          collectedTitles.push(title);
        }
      }
      collectShowContainerTitles(value, depth + 1, collectedTitles);
    }
  }

  function getFirstCollectedValue(valuesByKey, keys, allowNumeric) {
    for (const key of keys) {
      const values = valuesByKey[key];
      if (!Array.isArray(values) || values.length === 0) {
        continue;
      }
      for (const value of values) {
        if (typeof value === "string" && value.trim()) {
          return value.trim();
        }
        if (allowNumeric && typeof value === "number" && Number.isFinite(value)) {
          return value;
        }
      }
    }
    return null;
  }

  function buildCombinedCandidate(payload, expectedVideoId) {
    const valuesByKey = {};
    const showContainerTitles = [];
    collectScalarValues(payload, 0, valuesByKey);
    collectShowContainerTitles(payload, 0, showContainerTitles);

    const directShowTitle = getFirstCollectedValue(valuesByKey, SHOW_TITLE_KEYS, false);
    const showTitle = directShowTitle || showContainerTitles[0] || null;
    const mainTitle = getFirstCollectedValue(valuesByKey, TITLE_KEYS, false);
    const explicitEpisodeTitle = getFirstCollectedValue(valuesByKey, EPISODE_TITLE_KEYS, false);
    const seasonNumber = getFirstCollectedValue(valuesByKey, SEASON_NUMBER_KEYS, true);
    const episodeNumber = getFirstCollectedValue(valuesByKey, EPISODE_NUMBER_KEYS, true);
    const directVideoId = getFirstCollectedValue(valuesByKey, VIDEO_ID_KEYS, true);
    const videoId = directVideoId !== null ? directVideoId : expectedVideoId;
    const hasSeriesTypeValue = ENTITY_TYPE_KEYS.some((key) => {
      const values = valuesByKey[key];
      return Array.isArray(values) && values.some((v) => typeof v === "string" && EPISODE_ENTITY_VALUES.has(v));
    });
    const seriesTypeIsShowLevel = ENTITY_TYPE_KEYS.some((key) => {
      const values = valuesByKey[key];
      return Array.isArray(values) && values.some((v) => {
        if (typeof v !== "string") return false;
        const lower = v.toLowerCase();
        return lower === "show" || lower === "series" || lower === "tvseries" || lower === "miniseries";
      });
    });
    const hasSeriesCountValue = SERIES_COUNT_KEYS.some((key) => {
      const values = valuesByKey[key];
      return Array.isArray(values) && values.some((v) => typeof v === "number" && v > 0);
    });
    const hasEpisodeSignals =
      explicitEpisodeTitle !== null ||
      seasonNumber !== null ||
      episodeNumber !== null ||
      showContainerTitles.length > 0 ||
      hasSeriesTypeValue ||
      hasSeriesCountValue ||
      (showTitle !== null && mainTitle !== null && showTitle !== mainTitle);

    if (hasEpisodeSignals) {
      const episodeTitle =
        explicitEpisodeTitle || (mainTitle && mainTitle !== showTitle && !seriesTypeIsShowLevel && !hasSeriesCountValue ? mainTitle : null);
      const normalizedShowTitle = showTitle || (episodeTitle ? null : mainTitle) || null;
      if (!normalizedShowTitle && !episodeTitle) {
        return null;
      }
      return {
        kind: "episode",
        entityType: "Episode",
        videoId,
        showTitle: normalizedShowTitle,
        movieTitle: null,
        seasonNumber: seasonNumber !== null ? seasonNumber : null,
        episodeNumber: episodeNumber !== null ? episodeNumber : null,
        episodeTitle,
      };
    }

    if (!mainTitle) {
      return null;
    }

    return {
      kind: "movie",
      entityType: "Movie",
      videoId,
      showTitle: null,
      movieTitle: mainTitle,
      seasonNumber: null,
      episodeNumber: null,
      episodeTitle: null,
    };
  }

  function collectHeuristicCandidates(node, expectedVideoId, depth, candidates) {
    if (!node || typeof node !== "object" || depth > MAX_METADATA_SEARCH_DEPTH) {
      return;
    }
    if (Array.isArray(node)) {
      for (const item of node) {
        collectHeuristicCandidates(item, expectedVideoId, depth + 1, candidates);
      }
      return;
    }
    const candidate = buildHeuristicCandidate(node, expectedVideoId);
    if (candidate) {
      candidates.push(candidate);
    }
    for (const value of Object.values(node)) {
      collectHeuristicCandidates(value, expectedVideoId, depth + 1, candidates);
    }
  }

  function parseNetflixMemberApiMetadata(input, expectedVideoIdInput) {
    const payload = parseJsonBody(input);
    if (!payload) {
      return null;
    }
    const expectedVideoId = toNullableNumber(expectedVideoIdInput);
    const candidates = [];
    const combinedCandidate = buildCombinedCandidate(payload, expectedVideoId);
    if (combinedCandidate) {
      candidates.push(combinedCandidate);
    }
    collectHeuristicCandidates(payload, expectedVideoId, 0, candidates);
    if (candidates.length === 0) {
      return null;
    }
    candidates.sort((leftCandidate, rightCandidate) => {
      return candidateScore(rightCandidate, expectedVideoId) - candidateScore(leftCandidate, expectedVideoId);
    });
    return buildMetadataResult(candidates[0]);
  }

  function parseNetflixGraphqlMetadata(input) {
    const payload = parseJsonBody(input);
    if (!payload) {
      return null;
    }
    const entity = payload?.data?.unifiedEntities?.[0];
    if (!entity || typeof entity !== "object") {
      return null;
    }

    if (entity.__typename === "Movie") {
      return {
        kind: "movie",
        entityType: "Movie",
        videoId: toNullableNumber(entity.videoId),
        showTitle: null,
        movieTitle: typeof entity.title === "string" ? entity.title : null,
        seasonNumber: null,
        episodeNumber: null,
        episodeTitle: null,
      };
    }

    if (entity.__typename === "Show") {
      const episode = entity.currentEpisode && typeof entity.currentEpisode === "object" ? entity.currentEpisode : null;
      const parentSeason =
        episode && episode.parentSeason && typeof episode.parentSeason === "object"
          ? episode.parentSeason
          : null;
      return {
        kind: episode ? "episode" : "show",
        entityType: "Show",
        videoId: toNullableNumber(episode?.videoId) ?? toNullableNumber(entity.videoId),
        showTitle: typeof entity.title === "string" ? entity.title : null,
        movieTitle: null,
        seasonNumber: toNullableNumber(parentSeason?.number),
        episodeNumber: toNullableNumber(episode?.number),
        episodeTitle: typeof episode?.title === "string" ? episode.title : null,
      };
    }

    return {
      kind: "unknown",
      entityType: typeof entity.__typename === "string" ? entity.__typename : "Unknown",
      videoId: toNullableNumber(entity.videoId),
      showTitle: typeof entity.title === "string" ? entity.title : null,
      movieTitle: null,
      seasonNumber: null,
      episodeNumber: null,
      episodeTitle: null,
    };
  }

  return {
    parseNetflixMemberApiMetadata,
    parseNetflixGraphqlMetadata,
  };
});
