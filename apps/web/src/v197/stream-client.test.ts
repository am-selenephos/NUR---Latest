import { afterEach, describe, expect, it, vi } from "vitest";

import { V197StreamClient } from "../bridge/v197StreamClient";

function result() {
  return {
    turn_event_id: "turn-1",
    response_event_id: "response-1",
    model_run_id: "run-1",
    provider: "openai",
    provider_available: true,
    provider_reason: null,
    output: {
      direct_response: "A real streamed answer.",
      observed: [],
      inferred: [],
      hypotheses: [],
      uncertainty: [],
      next_move: "Keep moving.",
      memory_candidates: [],
      source_refs: [],
    },
    verification: { verdict: "ALLOW", schema_valid: true, source_refs_valid: true },
  };
}

function response(events: Array<{ id: number; event: string; data: unknown }>): Response {
  const body = events.map(row => (
    `id: ${row.id}\nevent: ${row.event}\ndata: ${JSON.stringify(row.data)}\n\n`
  )).join("");
  return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
}

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "nur_csrf=; Max-Age=0; path=/";
});

describe("V197 semantic Talk stream", () => {
  it("forwards actual SSE deltas and resolves only on durable completion", async () => {
    document.cookie = "nur_csrf=csrf-test; path=/";
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response([
      { id: 1, event: "stream.open", data: { request_id: "request-1" } },
      { id: 2, event: "talk.accepted", data: { model_run_id: "run-1" } },
      { id: 3, event: "response.text.delta", data: { delta: "A real " } },
      { id: 4, event: "response.text.delta", data: { delta: "streamed answer." } },
      { id: 5, event: "talk.completed", data: { durable: true, result: result() } },
    ]));
    const deltas: string[] = [];
    const events: string[] = [];
    const client = new V197StreamClient();

    const completed = await client.talk(
      { request_id: "request-1", message: "Stream it", locale: "en", writing_preference: "default" },
      {
        onDelta: delta => deltas.push(delta),
        onEvent: event => events.push(event.event),
      },
    );

    expect(deltas).toEqual(["A real ", "streamed answer."]);
    expect(events).toContain("talk.accepted");
    expect(completed.model_run_id).toBe("run-1");
    expect(client.active).toBe(false);
    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/cognition/talk/stream",
      expect.objectContaining({ method: "POST", credentials: "include" }),
    );
  });

  it("forwards capability and memory mode fields in the stream request", async () => {
    document.cookie = "nur_csrf=csrf-test; path=/";
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response([
      { id: 1, event: "stream.open", data: { request_id: "request-capability" } },
      { id: 2, event: "talk.completed", data: { durable: true, result: result() } },
    ]));
    const client = new V197StreamClient();

    await client.talk({
      request_id: "request-capability",
      message: "Use this capability",
      locale: "en",
      writing_preference: "default",
      capability_id: "capability:create_draft_plan",
      memory_mode: "REVIEW",
    });

    expect(JSON.parse(String(fetch.mock.calls[0]?.[1]?.body))).toMatchObject({
      capability_id: "capability:create_draft_plan",
      memory_mode: "REVIEW",
    });
  });

  it("reconnects once with the same request and Last-Event-ID", async () => {
    document.cookie = "nur_csrf=csrf-test; path=/";
    const fetch = vi.spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(response([
        { id: 1, event: "stream.open", data: { request_id: "request-2" } },
        { id: 2, event: "talk.accepted", data: { model_run_id: "run-2" } },
      ]))
      .mockResolvedValueOnce(response([
        { id: 3, event: "response.text.delta", data: { delta: "Recovered." } },
        { id: 4, event: "talk.completed", data: { durable: true, result: result() } },
      ]));
    const client = new V197StreamClient();

    await client.talk({ request_id: "request-2", message: "Resume", locale: "en", writing_preference: "default" });

    expect(fetch).toHaveBeenCalledTimes(2);
    expect(fetch.mock.calls[1]?.[1]?.headers).toMatchObject({ "Last-Event-ID": "2" });
    expect(JSON.parse(String(fetch.mock.calls[1]?.[1]?.body))).toMatchObject({ request_id: "request-2" });
  });
});
