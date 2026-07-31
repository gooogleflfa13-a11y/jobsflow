import { afterEach, describe, expect, test } from "bun:test";
import { searchGet } from "../src/helpers";

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

describe("searchGet retry/backoff", () => {
  test("retries a 429 and succeeds on the next attempt", async () => {
    instantTimers();
    const state = stubFetch([
      () => new Response('{"data":[]}', { status: 429 }),
      () => new Response('{"data":[],"totalCount":0}', { status: 200 }),
    ]);

    const result = await searchGet({ keywords: "lawyer" });
    expect(result.data).toEqual([]);
    expect(state.calls).toBe(2);
  });

  test("throws on 404 without retrying", async () => {
    const state = stubFetch([() => new Response("", { status: 404 })]);

    await expect(searchGet({ keywords: "lawyer" })).rejects.toThrow(/404/);
    expect(state.calls).toBe(1);
  });

  test("gives up after the initial attempt plus six retries on persistent 5xx", async () => {
    instantTimers();
    const state = stubFetch([() => new Response("", { status: 500 })]);

    await expect(searchGet({ keywords: "lawyer" })).rejects.toThrow(/500/);
    expect(state.calls).toBe(7);
  });
});
