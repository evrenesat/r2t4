const test = require("node:test");
const assert = require("node:assert/strict");

const {
  parseNetflixGraphqlMetadata,
  parseNetflixMemberApiMetadata,
  parseNetflixMemberApiMetadataWithDiagnostics,
  parseShowNameFromTabTitle,
  promoteMovieMetadataWithTabTitle,
} = require("../lib/metadata_parser.js");

const SAMPLE_GRAPHQL_PAYLOAD = {
  data: {
    unifiedEntities: [
      {
        __typename: "Show",
        videoId: 70136122,
        title: "Weeds",
        currentEpisode: {
          __typename: "Episode",
          videoId: 70094484,
          number: 2,
          title: "Free Goat",
          parentSeason: {
            __typename: "Season",
            number: 1,
          },
        },
      },
    ],
  },
};

test("parses episode metadata from the Netflix GraphQL response", () => {
  assert.deepEqual(parseNetflixGraphqlMetadata(SAMPLE_GRAPHQL_PAYLOAD), {
    kind: "episode",
    entityType: "Show",
    videoId: 70094484,
    showTitle: "Weeds",
    movieTitle: null,
    seasonNumber: 1,
    episodeNumber: 2,
    episodeTitle: "Free Goat",
  });
});

test("parses movie metadata from the Netflix GraphQL response", () => {
  assert.deepEqual(
    parseNetflixGraphqlMetadata({
      data: {
        unifiedEntities: [
          {
            __typename: "Movie",
            videoId: 42,
            title: "Roma",
          },
        ],
      },
    }),
    {
      kind: "movie",
      entityType: "Movie",
      videoId: 42,
      showTitle: null,
      movieTitle: "Roma",
      seasonNumber: null,
      episodeNumber: null,
      episodeTitle: null,
    },
  );
});

test("returns null when the payload does not contain a unified entity", () => {
  assert.equal(parseNetflixGraphqlMetadata({ data: {} }), null);
});

test("returns null for empty or non-JSON GraphQL bodies", () => {
  assert.equal(parseNetflixGraphqlMetadata(""), null);
  assert.equal(parseNetflixGraphqlMetadata("not json"), null);
});

test("parses heuristic episode metadata from memberapi-like JSON", () => {
  assert.deepEqual(
    parseNetflixMemberApiMetadata(
      {
        videoId: 70094484,
        title: "Free Goat",
        seasonNumber: 1,
        episodeNumber: 2,
        series: {
          title: "Weeds",
        },
      },
      "70094484",
    ),
    {
      kind: "episode",
      entityType: "Episode",
      videoId: 70094484,
      showTitle: "Weeds",
      movieTitle: null,
      seasonNumber: 1,
      episodeNumber: 2,
      episodeTitle: "Free Goat",
    },
  );
});

test("uses the expected video id when memberapi-like JSON omits it", () => {
  assert.deepEqual(
    parseNetflixMemberApiMetadata(
      {
        payload: {
          title: "Roma",
        },
      },
      "42",
    ),
    {
      kind: "movie",
      entityType: "Movie",
      videoId: 42,
      showTitle: null,
      movieTitle: "Roma",
      seasonNumber: null,
      episodeNumber: null,
      episodeTitle: null,
    },
  );
});

test("detects episode from explicit entityType field", () => {
  const result = parseNetflixMemberApiMetadata(
    {
      videoId: 70212577,
      title: "Gossip Girl",
      entityType: "Show",
    },
    "70212577",
  );
  assert.equal(result.kind, "episode");
  assert.equal(result.showTitle, "Gossip Girl");
  assert.equal(result.movieTitle, null);
});

test("detects episode from type field with series value", () => {
  const result = parseNetflixMemberApiMetadata(
    {
      videoId: 70212577,
      title: "Gossip Girl",
      type: "series",
    },
    "70212577",
  );
  assert.equal(result.kind, "episode");
  assert.equal(result.showTitle, "Gossip Girl");
});

test("detects episode from show container in nested memberapi payload", () => {
  const result = parseNetflixMemberApiMetadata(
    {
      videoId: 70212577,
      title: "Pilot",
      show: {
        title: "Gossip Girl",
      },
    },
    "70212577",
  );
  assert.equal(result.kind, "episode");
  assert.equal(result.showTitle, "Gossip Girl");
  assert.equal(result.episodeTitle, "Pilot");
});

test("detects episode from numSeasons field", () => {
  const result = parseNetflixMemberApiMetadata(
    {
      videoId: 70212577,
      title: "Gossip Girl",
      numSeasons: 6,
    },
    "70212577",
  );
  assert.equal(result.kind, "episode");
  assert.equal(result.showTitle, "Gossip Girl");
});

test("detects episode from show container even when show title matches main title", () => {
  const result = parseNetflixMemberApiMetadata(
    {
      videoId: 70212577,
      title: "Gossip Girl",
      series: {
        title: "Gossip Girl",
      },
    },
    "70212577",
  );
  assert.equal(result.kind, "episode");
  assert.equal(result.showTitle, "Gossip Girl");
});

test("returns parser diagnostics for memberapi payloads", () => {
  const diagnostics = parseNetflixMemberApiMetadataWithDiagnostics(
    {
      videoId: 70094484,
      title: "Free Goat",
      seasonNumber: 1,
      episodeNumber: 2,
      series: {
        title: "Weeds",
      },
      entityType: "Episode",
    },
    "70094484",
  );

  assert.deepEqual(diagnostics.result, {
    kind: "episode",
    entityType: "Episode",
    videoId: 70094484,
    showTitle: "Weeds",
    movieTitle: null,
    seasonNumber: 1,
    episodeNumber: 2,
    episodeTitle: "Free Goat",
  });
  assert.ok(Array.isArray(diagnostics.candidates));
  assert.ok(diagnostics.candidates.length >= 1);
  assert.equal(diagnostics.candidates[0].score > 0, true);
  assert.equal(diagnostics.signals.hasSeriesEntityType, true);
  assert.equal(diagnostics.signals.hasSeriesCountField, false);
  assert.equal(diagnostics.selectedCandidateSource, "combined");
  assert.deepEqual(diagnostics.signals.showContainerTitlesFound, ["Weeds"]);
  assert.deepEqual(diagnostics.signals.entityTypesFound, ["Episode"]);
});

test("promotes exact requested video to episode from payload-level show context", () => {
  const diagnostics = parseNetflixMemberApiMetadataWithDiagnostics(
    {
      video: {
        type: "show",
        title: "Brooklyn Nine-Nine",
        currentEpisode: {
          videoId: 80011399,
          title: "Captain Peralta",
        },
        episodes: [
          {
            videoId: 80004161,
            title: "Pilot",
          },
        ],
      },
    },
    "80011399",
  );

  assert.deepEqual(diagnostics.result, {
    kind: "episode",
    entityType: "Episode",
    videoId: 80011399,
    showTitle: "Brooklyn Nine-Nine",
    movieTitle: null,
    seasonNumber: null,
    episodeNumber: null,
    episodeTitle: "Captain Peralta",
  });
  assert.equal(diagnostics.selectedCandidateSource, "context_promoted");
  assert.equal(diagnostics.candidates.some((candidate) => candidate.source === "context_promoted"), true);
});

test("parses season and episode metadata from Netflix tab titles", () => {
  assert.deepEqual(parseShowNameFromTabTitle("Bones S1:E18 The Man with the Bone | Netflix"), {
    showName: "Bones",
    episodeTitle: "The Man with the Bone",
    seasonNumber: 1,
    episodeNumber: 18,
  });
});

test("parses colon-delimited Netflix tab titles", () => {
  assert.deepEqual(parseShowNameFromTabTitle("Girl From Nowhere: The Reset | Netflix"), {
    showName: "Girl From Nowhere",
    episodeTitle: "The Reset",
    seasonNumber: null,
    episodeNumber: null,
  });
});

test("ignores plain movie-style Netflix tab titles", () => {
  assert.equal(parseShowNameFromTabTitle("Roma | Netflix"), null);
});

test("promotes movie-like memberapi payloads to episodes from season-marked tab titles", () => {
  const result = parseNetflixMemberApiMetadata(
    {
      videoId: 701,
      title: "The Man with the Bone",
    },
    "701",
    "Bones S1:E18 The Man with the Bone | Netflix",
  );

  assert.deepEqual(result, {
    kind: "episode",
    entityType: "Episode",
    videoId: 701,
    showTitle: "Bones",
    movieTitle: null,
    seasonNumber: 1,
    episodeNumber: 18,
    episodeTitle: "The Man with the Bone",
  });
});

test("promotes stored movie metadata from useful Netflix tab titles", () => {
  const promoted = promoteMovieMetadataWithTabTitle(
    {
      kind: "movie",
      entityType: "Movie",
      videoId: 701,
      showTitle: null,
      movieTitle: "The Man with the Bone",
      seasonNumber: null,
      episodeNumber: null,
      episodeTitle: null,
    },
    "Bones S1:E18 The Man with the Bone | Netflix",
  );

  assert.deepEqual(promoted, {
    source: "tab_title_promoted",
    kind: "episode",
    entityType: "Episode",
    videoId: 701,
    showTitle: "Bones",
    movieTitle: null,
    seasonNumber: 1,
    episodeNumber: 18,
    episodeTitle: "The Man with the Bone",
  });
});

test("does not promote movie metadata from generic Netflix tab titles", () => {
  const movieMetadata = {
    kind: "movie",
    entityType: "Movie",
    videoId: 42,
    showTitle: null,
    movieTitle: "Roma",
    seasonNumber: null,
    episodeNumber: null,
    episodeTitle: null,
  };

  assert.equal(promoteMovieMetadataWithTabTitle(movieMetadata, "Netflix"), movieMetadata);
});

test("promotes movie-like memberapi payloads to episodes from colon-delimited tab titles", () => {
  const result = parseNetflixMemberApiMetadata(
    {
      videoId: 702,
      title: "The Reset",
    },
    "702",
    "Girl From Nowhere: The Reset | Netflix",
  );

  assert.deepEqual(result, {
    kind: "episode",
    entityType: "Episode",
    videoId: 702,
    showTitle: "Girl From Nowhere",
    movieTitle: null,
    seasonNumber: null,
    episodeNumber: null,
    episodeTitle: "The Reset",
  });
});

test("does not reclassify movie payloads when tab title episode portion does not match", () => {
  const result = parseNetflixMemberApiMetadata(
    {
      videoId: 42,
      title: "Mission: Impossible",
    },
    "42",
    "Mission: Impossible | Netflix",
  );

  assert.deepEqual(result, {
    kind: "movie",
    entityType: "Movie",
    videoId: 42,
    showTitle: null,
    movieTitle: "Mission: Impossible",
    seasonNumber: null,
    episodeNumber: null,
    episodeTitle: null,
  });
});
