const test = require("node:test");
const assert = require("node:assert/strict");

const {
  FALLBACK_SLUG,
  TITLE_SEGMENT_SEPARATOR,
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
} = require("../lib/file_naming.js");

test("slugifies episode and movie metadata", () => {
  assert.equal(
    buildTitleSlug(
      {
        kind: "episode",
        showTitle: "Weeds",
        seasonNumber: 1,
        episodeNumber: 2,
        episodeTitle: "Free Goat",
      },
      "ignored",
      "1234",
    ),
    "weeds__s01e02__free-goat",
  );
  assert.equal(
    buildTitleSlug(
      {
        kind: "movie",
        movieTitle: "Amélie",
      },
      "ignored",
      "1234",
    ),
    "amelie",
  );
  assert.equal(
    buildTitleSlug(
      {
        kind: "episode",
        showTitle: "Weeds",
        seasonNumber: null,
        episodeNumber: null,
        episodeTitle: "Free Goat",
      },
      "ignored",
      "1234",
    ),
    "weeds__free-goat",
  );
  assert.equal(
    buildTitleSlug(
      {
        kind: "episode",
        showTitle: "Weeds",
        seasonNumber: null,
        episodeNumber: null,
        episodeTitle: null,
      },
      "ignored",
      "1234",
    ),
    "weeds",
  );
});

test("falls back to tab title or watch id when metadata is unavailable", () => {
  assert.equal(buildTitleSlug(null, "Weeds: Free Goat - Netflix", "1234"), "weeds-free-goat");
  assert.equal(buildTitleSlug(null, "", "1234"), "watch-1234");
  assert.equal(buildTitleSlug(null, "Netflix", "1234"), "watch-1234");
  assert.equal(buildTitleSlug(null, "", null), FALLBACK_SLUG);
  assert.equal(normalizeTabTitle("Weeds - Netflix"), "Weeds");
  assert.equal(normalizeTabTitle("Netflix"), "");
  assert.equal(slugify("A Sky / Asky"), "a-sky-asky");
});

test("builds deterministic filenames and download paths", () => {
  const slug = `weeds${TITLE_SEGMENT_SEPARATOR}s01e02${TITLE_SEGMENT_SEPARATOR}free-goat`;
  const url = "https://example.com/file.bif";
  assert.equal(buildBifFilename(slug, url), `${slug}__bif__${hashString(url)}.bif`);
  assert.equal(
    buildSubtitleFilename(slug, "en", "https://example.com/subtitles.xml"),
    `${slug}__subtitle__en__${hashString("https://example.com/subtitles.xml")}.xml`,
  );
  assert.equal(buildManifestFilename(slug), `${slug}__manifest.json`);
  assert.equal(buildDebugFilename(slug), `${slug}__debug.json`);
  assert.equal(
    buildDownloadPath(slug, "asset.bin"),
    "Netflix_Captures/weeds__s01e02__free-goat/asset.bin",
  );
  assert.equal(buildGlobalDebugPath(), "Netflix_Captures/_debug/netflix_capture__global_debug.json");
});
