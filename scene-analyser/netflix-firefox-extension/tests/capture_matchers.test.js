const test = require("node:test");
const assert = require("node:assert/strict");

const {
  extractMetadataVideoIdFromUrl,
  extractSubtitleLanguage,
  extractWatchIdFromUrl,
  getHeaderValue,
  hasXmlContentType,
  isBifUrl,
  isGraphqlMetadataUrl,
  isMemberApiMetadataUrl,
  isLikelySubtitleUrl,
  isNetflixWatchUrl,
  isTtmlSubtitleXml,
} = require("../lib/capture_matchers.js");

const SAMPLE_SUBTITLE_XML = `<?xml version="1.0" encoding="utf-8"?>
<tt ttp:contentProfiles="http://www.w3.org/ns/ttml/profile/imsc1.1/text" xmlns="http://www.w3.org/ns/ttml" xmlns:nttm="http://www.netflix.com/ns/ttml#metadata" xmlns:tt="http://www.w3.org/ns/ttml" xmlns:ttp="http://www.w3.org/ns/ttml#parameter" xmlns:tts="http://www.w3.org/ns/ttml#styling" xmlns:xml="http://www.w3.org/XML/1998/namespace" ttp:tickRate="10000000" ttp:timeBase="media" xml:lang="en">
<head>
<metadata nttm:schemaVersion="0" nttm:textType="SUBS" nttm:uuid="a0604b88-39ad-441c-904e-32e4e3869b23"/>
</head>
<body>
<div>
<p begin="0t" end="1000000t">Hello</p>
</div>
</body>
</tt>`;

test("detects Netflix watch URLs and extracts watch IDs", () => {
  assert.equal(isNetflixWatchUrl("https://www.netflix.com/watch/70136122"), true);
  assert.equal(extractWatchIdFromUrl("https://www.netflix.com/watch/70136122"), "70136122");
  assert.equal(isNetflixWatchUrl("https://www.netflix.com/browse"), false);
  assert.equal(extractWatchIdFromUrl("https://www.netflix.com/browse"), null);
});

test("detects GraphQL and BIF URLs", () => {
  assert.equal(isGraphqlMetadataUrl("https://web.prod.cloud.netflix.com/graphql"), true);
  assert.equal(
    isMemberApiMetadataUrl(
      "https://www.netflix.com/nq/website/memberapi/release/metadata?movieid=70094486&materialize=true",
    ),
    true,
  );
  assert.equal(
    extractMetadataVideoIdFromUrl(
      "https://www.netflix.com/nq/website/memberapi/release/metadata?movieid=70094486&materialize=true",
    ),
    "70094486",
  );
  assert.equal(isGraphqlMetadataUrl("https://www.netflix.com/watch/70136122"), false);
  assert.equal(isBifUrl("https://occ-0-8673-768.1.nflxso.net/tp/tpa2/626/2029031213234286593.bif"), true);
  assert.equal(isBifUrl("https://occ-0-8673-768.1.nflxso.net/tp/tpa2/626/2029031213234286593.bif?x=1"), true);
  assert.equal(
    isLikelySubtitleUrl(
      "https://ipv4-c002-rtm001-glasoperator-isp.1.oca.nflxvideo.net/?o=1&v=32&e=1773011791&t=example",
    ),
    true,
  );
  assert.equal(
    isLikelySubtitleUrl(
      "https://ipv4-c002-rtm001-glasoperator-isp.1.oca.nflxvideo.net/range/0-4095?o=1&v=32",
    ),
    false,
  );
  assert.equal(isBifUrl("https://example.com/video.mp4"), false);
});

test("checks response headers and subtitle XML markers", () => {
  const headers = [
    { name: "Content-Type", value: "text/xml" },
    { name: "Cache-Control", value: "no-store" },
  ];
  assert.equal(getHeaderValue(headers, "content-type"), "text/xml");
  assert.equal(hasXmlContentType(headers), true);
  assert.equal(isTtmlSubtitleXml(SAMPLE_SUBTITLE_XML), true);
  assert.equal(extractSubtitleLanguage(SAMPLE_SUBTITLE_XML), "en");
  assert.equal(
    isTtmlSubtitleXml(
      SAMPLE_SUBTITLE_XML.replace('nttm:textType="SUBS"', "nttm:textType='SUBS'"),
    ),
    true,
  );
  assert.equal(
    isTtmlSubtitleXml(
      SAMPLE_SUBTITLE_XML.replace('<metadata nttm:schemaVersion="0" nttm:textType="SUBS" nttm:uuid="a0604b88-39ad-441c-904e-32e4e3869b23"/>', ""),
    ),
    true,
  );
  assert.equal(isTtmlSubtitleXml("<root/>"), false);
  assert.equal(extractSubtitleLanguage("<root/>"), "unknown");
});
