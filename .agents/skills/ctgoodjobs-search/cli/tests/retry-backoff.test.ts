import { afterEach, describe, expect, test } from "bun:test";
import { searchPost } from "../src/helpers";

const originalFetch = globalThis.fetch;
const originalSetTimeout = globalThis.setTimeout;

afterEach(() => {
  globalThis.fetch = originalFetch;
  globalThis.setTimeout = originalSetTimeout;
});

function instantTimers() {
  globalThis.setTimeout = ((fn: () => void) =>
    originalSetTimeout(fn, 0)) as unknown as typeof setTimeout;
}

function stubFetch(responses: Array<() => Response>): { calls: number } {
  const state = { calls: 0 };
  globalThis.fetch = (async () => {
    const i = Math.min(state.calls, responses.length - 1);
    state.calls++;
    return responses[i]();
  }) as unknown as typeof fetch;
  return state;
}

describe("searchPost retry/backoff", () => {
  test("retries a 429 and succeeds on the next attempt", async () => {
    instantTimers();
    const state = stubFetch([
      () => new Response('{"statusCode":429}', { status: 429 }),
      () =>
        new Response(
          '{"statusCode":200,"data":{"meta":{},"total":0,"jobs":[]}}',
          { status: 200 },
        ),
    ]);

    const result = await searchPost(
      { sid: "test", "channel-id": "1", "visitor-id": "test" },
      { keywords: "lawyer" },
    );
    expect(result.statusCode).toBe(200);
    expect(state.calls).toBe(2);
  });

  test("throws on 400 without retrying", async () => {
    const state = stubFetch([
      () => new Response('{"error":"bad request"}', { status: 400 }),
    ]);

    await expect(
      searchPost(
        { sid: "test", "channel-id": "1", "visitor-id": "test" },
        { keywords: "lawyer" },
      ),
    ).rejects.toThrow(/400/);
    expect(state.calls).toBe(1);
  });

  test("gives up after the initial attempt plus six retries on persistent 5xx", async () => {
    instantTimers();
    const state = stubFetch([
      () => new Response("", { status: 500 }),
    ]);

    await expect(
      searchPost(
        { sid: "test", "channel-id": "1", "visitor-id": "test" },
        { keywords: "lawyer" },
      ),
    ).rejects.toThrow(/500/);
    expect(state.calls).toBe(7);
  });
});
