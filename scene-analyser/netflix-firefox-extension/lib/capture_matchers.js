(function attachCaptureMatchers(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.NetflixCaptureMatchers = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function buildCaptureMatchers() {
  const NETFLIX_HOSTNAME = "www.netflix.com";
  const NETFLIX_GRAPHQL_HOSTNAME = "web.prod.cloud.netflix.com";
  const NETFLIX_GRAPHQL_PATHNAME = "/graphql";
  const NETFLIX_MEMBERAPI_METADATA_PATHNAME = "/nq/website/memberapi/release/metadata";
  const NETFLIX_LICENSED_MANIFEST_PATH_PREFIX = "/msl/playapi/cadmium/licensedmanifest/";
  const WATCH_PATH_REGEX = /^\/watch\/(\d+)(?:[/?#]|$)/;
  const BIF_URL_REGEX = /\.bif(?:$|[?#])/i;
  const TTML_NAMESPACE_MARKER = "http://www.w3.org/ns/ttml";
  const NETFLIX_SUBTITLE_TEXT_TYPE_REGEX = /\btextType=["']SUBS["']/i;
  const XML_LANGUAGE_REGEX = /\bxml:lang="([^"]+)"/i;
  const TIMED_TEXT_ROOT_REGEX = /<(?:tt|timedtext)(?:\s|>)/i;
  const TIMED_TEXT_CUE_REGEX = /<(?:p|span|div)(?:\s|>)/i;

  function safelyParseUrl(value) {
    try {
      return new URL(value);
    } catch (_error) {
      return null;
    }
  }

  function isNetflixWatchUrl(url) {
    const parsedUrl = safelyParseUrl(url);
    return Boolean(
      parsedUrl &&
        parsedUrl.hostname === NETFLIX_HOSTNAME &&
        WATCH_PATH_REGEX.test(parsedUrl.pathname + parsedUrl.search + parsedUrl.hash),
    );
  }

  function extractWatchIdFromUrl(url) {
    const parsedUrl = safelyParseUrl(url);
    if (!parsedUrl || parsedUrl.hostname !== NETFLIX_HOSTNAME) {
      return null;
    }
    const match = WATCH_PATH_REGEX.exec(parsedUrl.pathname + parsedUrl.search + parsedUrl.hash);
    return match ? match[1] : null;
  }

  function isGraphqlMetadataUrl(url) {
    const parsedUrl = safelyParseUrl(url);
    return Boolean(
      parsedUrl &&
        parsedUrl.hostname === NETFLIX_GRAPHQL_HOSTNAME &&
        parsedUrl.pathname === NETFLIX_GRAPHQL_PATHNAME,
    );
  }

  function isMemberApiMetadataUrl(url) {
    const parsedUrl = safelyParseUrl(url);
    return Boolean(
      parsedUrl &&
        parsedUrl.hostname === NETFLIX_HOSTNAME &&
        parsedUrl.pathname === NETFLIX_MEMBERAPI_METADATA_PATHNAME,
    );
  }

  function isLicensedManifestUrl(url) {
    const parsedUrl = safelyParseUrl(url);
    return Boolean(
      parsedUrl &&
        parsedUrl.hostname === NETFLIX_HOSTNAME &&
        parsedUrl.pathname.startsWith(NETFLIX_LICENSED_MANIFEST_PATH_PREFIX) &&
        parsedUrl.searchParams.has("mainContentViewableId"),
    );
  }

  function extractMetadataVideoIdFromUrl(url) {
    const parsedUrl = safelyParseUrl(url);
    if (!parsedUrl) {
      return null;
    }
    if (isMemberApiMetadataUrl(url)) {
      return parsedUrl.searchParams.get("movieid");
    }
    if (isLicensedManifestUrl(url)) {
      return parsedUrl.searchParams.get("mainContentViewableId");
    }
    return null;
  }

  function isBifUrl(url) {
    const parsedUrl = safelyParseUrl(url);
    return Boolean(parsedUrl && BIF_URL_REGEX.test(parsedUrl.pathname + parsedUrl.search));
  }

  function isLikelySubtitleUrl(url) {
    const parsedUrl = safelyParseUrl(url);
    return Boolean(
      parsedUrl &&
        parsedUrl.hostname.endsWith(".nflxvideo.net") &&
        parsedUrl.pathname === "/" &&
        parsedUrl.searchParams.has("o") &&
        parsedUrl.searchParams.has("v"),
    );
  }

  function getHeaderValue(headers, name) {
    if (!Array.isArray(headers)) {
      return null;
    }
    const targetName = String(name).toLowerCase();
    const matchingHeader = headers.find((header) => {
      if (!header || typeof header.name !== "string") {
        return false;
      }
      return header.name.toLowerCase() === targetName;
    });
    return matchingHeader && typeof matchingHeader.value === "string" ? matchingHeader.value : null;
  }

  function hasXmlContentType(headers) {
    const contentType = getHeaderValue(headers, "content-type");
    return typeof contentType === "string" && contentType.toLowerCase().includes("xml");
  }

  function isTtmlSubtitleXml(bodyText) {
    if (typeof bodyText !== "string") {
      return false;
    }
    const trimmedBody = bodyText.trim();
    if (!trimmedBody.startsWith("<?xml") && !TIMED_TEXT_ROOT_REGEX.test(trimmedBody)) {
      return false;
    }
    if (!TIMED_TEXT_ROOT_REGEX.test(trimmedBody)) {
      return false;
    }
    if (!TIMED_TEXT_CUE_REGEX.test(trimmedBody)) {
      return false;
    }
    return (
      bodyText.includes(TTML_NAMESPACE_MARKER) ||
      NETFLIX_SUBTITLE_TEXT_TYPE_REGEX.test(bodyText) ||
      XML_LANGUAGE_REGEX.test(bodyText)
    );
  }

  function extractSubtitleLanguage(bodyText) {
    if (typeof bodyText !== "string") {
      return "unknown";
    }
    const match = XML_LANGUAGE_REGEX.exec(bodyText);
    if (!match || !match[1]) {
      return "unknown";
    }
    return match[1].trim().toLowerCase() || "unknown";
  }

  return {
    BIF_URL_REGEX,
    NETFLIX_MEMBERAPI_METADATA_PATHNAME,
    NETFLIX_LICENSED_MANIFEST_PATH_PREFIX,
    NETFLIX_GRAPHQL_HOSTNAME,
    NETFLIX_GRAPHQL_PATHNAME,
    NETFLIX_HOSTNAME,
    NETFLIX_SUBTITLE_TEXT_TYPE_REGEX,
    TTML_NAMESPACE_MARKER,
    WATCH_PATH_REGEX,
    extractMetadataVideoIdFromUrl,
    extractSubtitleLanguage,
    extractWatchIdFromUrl,
    getHeaderValue,
    hasXmlContentType,
    isBifUrl,
    isGraphqlMetadataUrl,
    isLicensedManifestUrl,
    isMemberApiMetadataUrl,
    isLikelySubtitleUrl,
    isNetflixWatchUrl,
    isTtmlSubtitleXml,
  };
});
