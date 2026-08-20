import { V197ApiError, type V197TalkResult } from "./v197ApiClient";

export interface V197TalkStreamPayload {
  request_id: string;
  message: string;
  orbit_id?: string | null;
  locale: string;
  writing_preference: string;
  mode?: string;
  capability_id?: string | null;
  memory_mode?: "EPHEMERAL" | "REVIEW";
}

export interface V197StreamEvent {
  id: number;
  event: string;
  data: Record<string, unknown>;
}

export interface V197TalkStreamHooks {
  onEvent?: (event: V197StreamEvent) => void;
  onDelta?: (delta: string) => void;
}

const STREAM_IDLE_TIMEOUT_MS = 65_000;

function cookie(name: string): string | null {
  const prefix = `${name}=`;
  const row = document.cookie.split(";").map(value => value.trim()).find(value => value.startsWith(prefix));
  return row ? decodeURIComponent(row.slice(prefix.length)) : null;
}

function errorDetail(body: string, fallback: string): string {
  try {
    const parsed = JSON.parse(body) as { detail?: unknown };
    return parsed.detail ? String(parsed.detail) : fallback;
  } catch {
    return fallback;
  }
}

async function readWithIdleTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): Promise<ReadableStreamReadResult<Uint8Array>> {
  let timeout = 0;
  try {
    return await Promise.race([
      reader.read(),
      new Promise<never>((_, reject) => {
        timeout = window.setTimeout(
          () => reject(new V197ApiError("The live Talk stream stopped responding.", 0)),
          STREAM_IDLE_TIMEOUT_MS,
        );
      }),
    ]);
  } finally {
    window.clearTimeout(timeout);
  }
}

function parseEvent(block: string): V197StreamEvent | null {
  if (!block || block.startsWith(":")) return null;
  let id = 0;
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    const separator = line.indexOf(":");
    const field = separator < 0 ? line : line.slice(0, separator);
    const value = separator < 0 ? "" : line.slice(separator + 1).replace(/^ /, "");
    if (field === "id") id = Number.parseInt(value, 10) || 0;
    else if (field === "event") event = value;
    else if (field === "data") data.push(value);
  }
  let payload: Record<string, unknown> = {};
  if (data.length) {
    try {
      payload = JSON.parse(data.join("\n")) as Record<string, unknown>;
    } catch {
      throw new V197ApiError("NUR received a malformed live Talk event.", 0);
    }
  }
  return { id, event, data: payload };
}

export class V197StreamClient {
  private controller: AbortController | null = null;
  private currentRequestId: string | null = null;

  get active(): boolean {
    return this.controller !== null;
  }

  async talk(
    payload: V197TalkStreamPayload,
    hooks: V197TalkStreamHooks = {},
    signal?: AbortSignal,
  ): Promise<V197TalkResult> {
    if (this.active) throw new V197ApiError("NUR is already answering this Talk turn.", 409);
    const csrf = cookie("nur_csrf");
    if (!csrf) throw new V197ApiError("The local session is missing its CSRF token.", 401);
    const controller = new AbortController();
    this.controller = controller;
    this.currentRequestId = payload.request_id;
    const abortFromCaller = () => controller.abort();
    signal?.addEventListener("abort", abortFromCaller, { once: true });

    let lastEventId = 0;
    try {
      for (let connection = 0; connection < 2; connection += 1) {
        const response = await fetch("/api/v1/cognition/talk/stream", {
          method: "POST",
          credentials: "include",
          signal: controller.signal,
          headers: {
            accept: "text/event-stream",
            "content-type": "application/json",
            "X-CSRF-Token": csrf,
            ...(lastEventId ? { "Last-Event-ID": String(lastEventId) } : {}),
          },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          const raw = await response.text();
          throw new V197ApiError(errorDetail(raw, `Talk stream returned ${response.status}.`), response.status);
        }
        if (!response.body) throw new V197ApiError("NUR Talk streaming is unavailable in this browser.", 0);

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        try {
          while (true) {
            const { value, done } = await readWithIdleTimeout(reader);
            buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
            let boundary = buffer.indexOf("\n\n");
            while (boundary >= 0) {
              const block = buffer.slice(0, boundary);
              buffer = buffer.slice(boundary + 2);
              boundary = buffer.indexOf("\n\n");
              const streamEvent = parseEvent(block);
              if (!streamEvent) continue;
              lastEventId = Math.max(lastEventId, streamEvent.id);
              hooks.onEvent?.(streamEvent);
              if (streamEvent.event === "response.text.delta") {
                const delta = streamEvent.data.delta;
                if (typeof delta === "string" && delta) hooks.onDelta?.(delta);
              }
              if (streamEvent.event === "talk.completed") {
                return streamEvent.data.result as unknown as V197TalkResult;
              }
              if (["talk.error", "talk.conflict", "talk.cancelled"].includes(streamEvent.event)) {
                // The backend publishes the honest reason under `message` (with a
                // machine `code`, e.g. "provider_disabled"); older code read the
                // wrong `detail` key and lost it, leaving a generic notice.
                const message = streamEvent.data.message ?? streamEvent.data.detail;
                const code = typeof streamEvent.data.code === "string" ? streamEvent.data.code : null;
                throw new V197ApiError(
                  typeof message === "string" && message
                    ? message
                    : streamEvent.event === "talk.cancelled"
                      ? "The Talk turn was cancelled."
                      : "The Talk stream failed closed.",
                  streamEvent.event === "talk.conflict" ? 409 : 0,
                  code,
                );
              }
            }
            if (done) break;
          }
        } finally {
          reader.releaseLock();
        }
        if (connection === 0 && !controller.signal.aborted) continue;
        throw new V197ApiError("The Talk stream ended before a durable response arrived.", 0);
      }
      throw new V197ApiError("The Talk stream could not be resumed.", 0);
    } catch (error) {
      if (error instanceof V197ApiError) throw error;
      if (controller.signal.aborted) throw new V197ApiError("The Talk turn was cancelled.", 0);
      throw new V197ApiError("NUR lost the live Talk connection before completion.", 0);
    } finally {
      signal?.removeEventListener("abort", abortFromCaller);
      if (this.controller === controller) this.controller = null;
      if (this.currentRequestId === payload.request_id) this.currentRequestId = null;
    }
  }

  async cancel(): Promise<boolean> {
    const requestId = this.currentRequestId;
    const csrf = cookie("nur_csrf");
    this.controller?.abort();
    if (!requestId || !csrf) return false;
    const response = await fetch(`/api/v1/cognition/talk-runs/${encodeURIComponent(requestId)}/cancel`, {
      method: "POST",
      credentials: "include",
      headers: { accept: "application/json", "X-CSRF-Token": csrf },
    });
    return response.ok;
  }
}
