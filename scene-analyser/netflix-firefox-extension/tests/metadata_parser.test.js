const test = require("node:test");
const assert = require("node:assert/strict");

const {
  parseNetflixGraphqlMetadata,
  parseNetflixMemberApiMetadata,
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
