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
  const MATCHING_VIDEO_ID_SCORE = 50;
  const SHOW_TITLE_SCORE = 20;
  const MOVIE_TITLE_SCORE = 18;
  const EPISODE_TITLE_SCORE = 16;
  const SEASON_NUMBER_SCORE = 8;
  const EPISODE_NUMBER_SCORE = 8;
  const EPISODE_BASE_SCORE = 10;
  const COMPLETE_EPISODE_SCORE = 25;
  const NETFLIX_TITLE_SUFFIX_PATTERNS = [/\s+\|\s+Netflix$/i, /\s+-\s+Netflix$/i];
  const TAB_TITLE_SEASON_EPISODE_PATTERN = /^(.+?)\s+S(\d+):E(\d+)(?:\s+(.+))?$/i;
  const TAB_TITLE_COLON_PATTERN = /^(.+?):\s+(.+)$/;
  const TAB_TITLE_DASH_PATTERN = /^(.+?)\s+-\s+(.+)$/;

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
      score += MATCHING_VIDEO_ID_SCORE;
    }
    if (candidate.showTitle) {
      score += SHOW_TITLE_SCORE;
    }
    if (candidate.movieTitle) {
      score += MOVIE_TITLE_SCORE;
    }
    if (candidate.episodeTitle) {
      score += EPISODE_TITLE_SCORE;
    }
    if (candidate.seasonNumber !== null) {
      score += SEASON_NUMBER_SCORE;
    }
    if (candidate.episodeNumber !== null) {
      score += EPISODE_NUMBER_SCORE;
    }
    if (candidate.kind === "episode") {
      score += candidate.showTitle && candidate.episodeTitle ? COMPLETE_EPISODE_SCORE : EPISODE_BASE_SCORE;
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

  function collectDirectShowContainerTitles(node) {
    if (!node || typeof node !== "object" || Array.isArray(node)) {
      return [];
    }
    const titles = [];
    for (const [key, value] of Object.entries(node)) {
      if (!SHOW_CONTAINER_KEYS.includes(key) || !value || typeof value !== "object" || Array.isArray(value)) {
        continue;
      }
      const title = getStringValue(value, TITLE_KEYS);
      if (title) {
        titles.push(title);
      }
    }
    return titles;
  }

  function buildHeuristicCandidate(node, expectedVideoId, inheritedShowContainerTitles) {
    if (!node || typeof node !== "object" || Array.isArray(node)) {
      return null;
    }

    const inheritedShowTitle =
      Array.isArray(inheritedShowContainerTitles) && inheritedShowContainerTitles.length > 0
        ? inheritedShowContainerTitles[0]
        : null;
    const showTitle = getStringValue(node, SHOW_TITLE_KEYS) || inheritedShowTitle;
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
      source: "heuristic",
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

  function collectPayloadAnalysis(payload) {
    const valuesByKey = {};
    const showContainerTitles = [];
    collectScalarValues(payload, 0, valuesByKey);
    collectShowContainerTitles(payload, 0, showContainerTitles);
    const entityTypesFound = [];
    for (const key of ENTITY_TYPE_KEYS) {
      const values = valuesByKey[key];
      if (!Array.isArray(values)) {
        continue;
      }
      for (const value of values) {
        if (typeof value !== "string" || entityTypesFound.includes(value)) {
          continue;
        }
        entityTypesFound.push(value);
      }
    }
    const hasSeriesEntityType = entityTypesFound.some((value) => EPISODE_ENTITY_VALUES.has(value));
    const hasSeriesCountField = SERIES_COUNT_KEYS.some((key) => {
      const values = valuesByKey[key];
      return Array.isArray(values) && values.some((value) => typeof value === "number" && value > 0);
    });
    return {
      valuesByKey,
      showContainerTitles,
      entityTypesFound,
      hasSeriesEntityType,
      hasSeriesCountField,
    };
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

  function buildCombinedCandidate(payload, expectedVideoId, payloadAnalysis) {
    const analysis = payloadAnalysis || collectPayloadAnalysis(payload);
    const { valuesByKey, showContainerTitles } = analysis;

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
        source: "combined",
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
      source: "combined",
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

  function collectHeuristicCandidates(node, expectedVideoId, depth, candidates, inheritedShowContainerTitles) {
    if (!node || typeof node !== "object" || depth > MAX_METADATA_SEARCH_DEPTH) {
      return;
    }
    if (Array.isArray(node)) {
      for (const item of node) {
        collectHeuristicCandidates(item, expectedVideoId, depth + 1, candidates, inheritedShowContainerTitles);
      }
      return;
    }
    const nextShowContainerTitles = [
      ...collectDirectShowContainerTitles(node),
      ...(Array.isArray(inheritedShowContainerTitles) ? inheritedShowContainerTitles : []),
    ];
    const candidate = buildHeuristicCandidate(node, expectedVideoId, nextShowContainerTitles);
    if (candidate) {
      candidates.push(candidate);
    }
    for (const value of Object.values(node)) {
      collectHeuristicCandidates(value, expectedVideoId, depth + 1, candidates, nextShowContainerTitles);
    }
  }

  function stripNetflixTabTitleSuffix(tabTitle) {
    if (typeof tabTitle !== "string") {
      return null;
    }
    let strippedTitle = tabTitle.trim();
    if (!strippedTitle) {
      return null;
    }
    for (const pattern of NETFLIX_TITLE_SUFFIX_PATTERNS) {
      strippedTitle = strippedTitle.replace(pattern, "").trim();
    }
    return strippedTitle || null;
  }

  function normalizeComparisonText(value) {
    if (typeof value !== "string") {
      return null;
    }
    const normalized = value.trim().toLowerCase().replace(/\s+/g, " ");
    return normalized || null;
  }

  function parseShowNameFromTabTitle(tabTitle) {
    const strippedTitle = stripNetflixTabTitleSuffix(tabTitle);
    if (!strippedTitle || strippedTitle.toLowerCase() === "netflix") {
      return null;
    }

    const seasonEpisodeMatch = strippedTitle.match(TAB_TITLE_SEASON_EPISODE_PATTERN);
    if (seasonEpisodeMatch) {
      const showName = seasonEpisodeMatch[1].trim();
      const seasonNumber = toNullableNumber(seasonEpisodeMatch[2]);
      const episodeNumber = toNullableNumber(seasonEpisodeMatch[3]);
      const episodeTitle = typeof seasonEpisodeMatch[4] === "string" ? seasonEpisodeMatch[4].trim() || null : null;
      if (showName && (seasonNumber !== null || episodeNumber !== null || episodeTitle)) {
        return {
          showName,
          episodeTitle,
          seasonNumber,
          episodeNumber,
        };
      }
    }

    const colonMatch = strippedTitle.match(TAB_TITLE_COLON_PATTERN);
    if (colonMatch) {
      const showName = colonMatch[1].trim();
      const episodeTitle = colonMatch[2].trim();
      if (showName && episodeTitle) {
        return {
          showName,
          episodeTitle,
          seasonNumber: null,
          episodeNumber: null,
        };
      }
    }

    const dashMatch = strippedTitle.match(TAB_TITLE_DASH_PATTERN);
    if (dashMatch) {
      const showName = dashMatch[1].trim();
      const episodeTitle = dashMatch[2].trim();
      if (showName && episodeTitle) {
        return {
          showName,
          episodeTitle,
          seasonNumber: null,
          episodeNumber: null,
        };
      }
    }

    return null;
  }

  function promoteMovieResultFromTabTitle(result, tabTitleMetadata) {
    if (!result || result.kind !== "movie" || !tabTitleMetadata) {
      return result;
    }
    const normalizedMovieTitle = normalizeComparisonText(result.movieTitle);
    const normalizedShowName = normalizeComparisonText(tabTitleMetadata.showName);
    const normalizedEpisodeTitle = normalizeComparisonText(tabTitleMetadata.episodeTitle);
    if (!normalizedMovieTitle || !normalizedShowName || normalizedShowName === normalizedMovieTitle) {
      return result;
    }
    const shouldPromote =
      normalizedEpisodeTitle === normalizedMovieTitle ||
      (normalizedEpisodeTitle === null &&
        (tabTitleMetadata.seasonNumber !== null || tabTitleMetadata.episodeNumber !== null));
    if (!shouldPromote) {
      return result;
    }
    return {
      kind: "episode",
      entityType: "Episode",
      videoId: result.videoId,
      showTitle: tabTitleMetadata.showName,
      movieTitle: null,
      seasonNumber: result.seasonNumber !== null ? result.seasonNumber : tabTitleMetadata.seasonNumber,
      episodeNumber: result.episodeNumber !== null ? result.episodeNumber : tabTitleMetadata.episodeNumber,
      episodeTitle: tabTitleMetadata.episodeTitle || result.movieTitle,
    };
  }

  function buildCandidateDiagnostics(candidates, expectedVideoId) {
    return candidates.map((candidate) => {
      return {
        source: candidate.source || null,
        score: candidateScore(candidate, expectedVideoId),
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

  function analyzeNetflixMemberApiMetadata(input, expectedVideoIdInput, tabTitle) {
    const payload = parseJsonBody(input);
    if (!payload) {
      return {
        result: null,
        candidates: [],
        signals: {
          hasSeriesEntityType: false,
          hasSeriesCountField: false,
          showContainerTitlesFound: [],
          entityTypesFound: [],
        },
      };
    }
    const expectedVideoId = toNullableNumber(expectedVideoIdInput);
    const payloadAnalysis = collectPayloadAnalysis(payload);
    const candidates = [];
    const combinedCandidate = buildCombinedCandidate(payload, expectedVideoId, payloadAnalysis);
    if (combinedCandidate) {
      candidates.push(combinedCandidate);
    }
    collectHeuristicCandidates(payload, expectedVideoId, 0, candidates, []);
    candidates.sort((leftCandidate, rightCandidate) => {
      return candidateScore(rightCandidate, expectedVideoId) - candidateScore(leftCandidate, expectedVideoId);
    });
    const result = candidates.length === 0 ? null : buildMetadataResult(candidates[0]);
    const tabTitleMetadata = parseShowNameFromTabTitle(tabTitle);
    return {
      result: promoteMovieResultFromTabTitle(result, tabTitleMetadata),
      candidates: buildCandidateDiagnostics(candidates, expectedVideoId),
      signals: {
        hasSeriesEntityType: payloadAnalysis.hasSeriesEntityType,
        hasSeriesCountField: payloadAnalysis.hasSeriesCountField,
        showContainerTitlesFound: payloadAnalysis.showContainerTitles,
        entityTypesFound: payloadAnalysis.entityTypesFound,
      },
    };
  }

  function parseNetflixMemberApiMetadata(input, expectedVideoIdInput, tabTitle) {
    return analyzeNetflixMemberApiMetadata(input, expectedVideoIdInput, tabTitle).result;
  }

  function parseNetflixMemberApiMetadataWithDiagnostics(input, expectedVideoIdInput, tabTitle) {
    return analyzeNetflixMemberApiMetadata(input, expectedVideoIdInput, tabTitle);
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
    parseNetflixMemberApiMetadataWithDiagnostics,
    parseNetflixGraphqlMetadata,
    parseShowNameFromTabTitle,
  };
});
