(function attachFileNaming(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.NetflixFileNaming = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function buildFileNaming() {
  const CAPTURE_ROOT_DIRECTORY = "Netflix_Captures";
  const NETFLIX_TITLE_SUFFIX_REGEX = /\s*[-|:]\s*Netflix\s*$/i;
  const NON_ALPHANUMERIC_REGEX = /[^a-z0-9]+/g;
  const LEADING_OR_TRAILING_HYPHENS_REGEX = /^-+|-+$/g;
  const FALLBACK_SLUG = "watch-unknown";
  const IGNORABLE_TAB_TITLES = new Set(["netflix"]);

  function normalizeSegment(value) {
    return String(value).padStart(2, "0");
  }

  function slugify(value) {
    if (typeof value !== "string") {
      return "";
    }
    return value
      .normalize("NFKD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(NON_ALPHANUMERIC_REGEX, "-")
      .replace(LEADING_OR_TRAILING_HYPHENS_REGEX, "");
  }

  function normalizeTabTitle(tabTitle) {
    if (typeof tabTitle !== "string") {
      return "";
    }
    const normalizedTitle = tabTitle.replace(NETFLIX_TITLE_SUFFIX_REGEX, "").trim();
    if (IGNORABLE_TAB_TITLES.has(normalizedTitle.toLowerCase())) {
      return "";
    }
    return normalizedTitle;
  }

  function hashString(value) {
    let hash = 0x811c9dc5;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 0x01000193);
      hash >>>= 0;
    }
    return hash.toString(16).padStart(8, "0");
  }

  function buildTitleSlug(metadata, tabTitle, watchId) {
    if (metadata && metadata.kind === "episode" && metadata.showTitle) {
      const episodeSegments = [metadata.showTitle];
      if (metadata.seasonNumber !== null && metadata.episodeNumber !== null) {
        episodeSegments.push(
          `s${normalizeSegment(metadata.seasonNumber)}e${normalizeSegment(metadata.episodeNumber)}`,
        );
      }
      if (metadata.episodeTitle) {
        episodeSegments.push(metadata.episodeTitle);
      }
      const episodeSlug = slugify(episodeSegments.join(" "));
      if (episodeSlug) {
        return episodeSlug;
      }
    }

    if (metadata && metadata.kind === "movie" && metadata.movieTitle) {
      const movieSlug = slugify(metadata.movieTitle);
      if (movieSlug) {
        return movieSlug;
      }
    }

    if (metadata && metadata.showTitle) {
      const showSlug = slugify(metadata.showTitle);
      if (showSlug) {
        return showSlug;
      }
    }

    const normalizedTabTitle = normalizeTabTitle(tabTitle);
    const tabSlug = slugify(normalizedTabTitle);
    if (tabSlug) {
      return tabSlug;
    }

    if (watchId) {
      return `watch-${watchId}`;
    }

    return FALLBACK_SLUG;
  }

  function buildBifFilename(titleSlug, sourceUrl) {
    return `${titleSlug}__bif__${hashString(sourceUrl)}.bif`;
  }

  function buildSubtitleFilename(titleSlug, language, sourceUrl) {
    const safeLanguage = slugify(language || "unknown") || "unknown";
    return `${titleSlug}__subtitle__${safeLanguage}__${hashString(sourceUrl)}.xml`;
  }

  function buildManifestFilename(titleSlug) {
    return `${titleSlug}__manifest.json`;
  }

  function buildDebugFilename(titleSlug) {
    return `${titleSlug}__debug.json`;
  }

  function buildGlobalDebugPath() {
    return `${CAPTURE_ROOT_DIRECTORY}/_debug/netflix_capture__global_debug.json`;
  }

  function buildDownloadPath(titleSlug, filename) {
    return `${CAPTURE_ROOT_DIRECTORY}/${titleSlug}/${filename}`;
  }

  return {
    CAPTURE_ROOT_DIRECTORY,
    FALLBACK_SLUG,
    buildBifFilename,
    buildDebugFilename,
    buildDownloadPath,
    buildGlobalDebugPath,
    buildManifestFilename,
    buildSubtitleFilename,
    buildTitleSlug,
    hashString,
    normalizeTabTitle,
    slugify,
  };
});
