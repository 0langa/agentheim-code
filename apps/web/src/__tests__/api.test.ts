import { describe, expect, it, vi } from "vitest";

import { api, streamSessionMessage, validateContext } from "../api";

function streamFromText(text: string): ReadableStream<Uint8Array> {
  return new ReadableStream({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(text));
      controller.close();
    },
  });
}

describe("streamSessionMessage", () => {
  it("dispatches token and done events from an SSE response", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(
          streamFromText(
            [
              'event: token\ndata: {"token":"hello "}',
              'event: token\ndata: {"token":"world"}',
              'event: done\ndata: {"session_id":"sess-1"}',
              "",
            ].join("\n\n"),
          ),
          { status: 200, headers: { "content-type": "text/event-stream" } },
        ),
      );
    const onToken = vi.fn();
    const onDone = vi.fn();

    await streamSessionMessage("sess-1", "hi", { onToken, onDone });

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/coder/sessions/sess-1/messages/stream",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ prompt: "hi", context_files: [], use_context_bundle: true }),
      }),
    );
    expect(onToken).toHaveBeenNthCalledWith(1, "hello ");
    expect(onToken).toHaveBeenNthCalledWith(2, "world");
    expect(onDone).toHaveBeenCalledWith({ session_id: "sess-1" });

    fetchMock.mockRestore();
  });

  it("sends selected context files with streamed prompts", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(streamFromText('event: done\ndata: {"session_id":"sess-1"}\n\n'), {
        status: 200,
        headers: { "content-type": "text/event-stream" },
      }),
    );

    await streamSessionMessage("sess-1", "hi", {}, undefined, ["src/app.py"]);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/coder/sessions/sess-1/messages/stream",
      expect.objectContaining({
        body: JSON.stringify({ prompt: "hi", context_files: ["src/app.py"], use_context_bundle: true }),
      }),
    );

    fetchMock.mockRestore();
  });

  it("generates a fresh request id for each streamed prompt", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(streamFromText('event: done\ndata: {"session_id":"sess-1"}\n\n'), {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(streamFromText('event: done\ndata: {"session_id":"sess-2"}\n\n'), {
          status: 200,
          headers: { "content-type": "text/event-stream" },
        }),
      );

    await streamSessionMessage("sess-1", "hi", {});
    await streamSessionMessage("sess-2", "again", {});

    const firstHeaders = new Headers(fetchMock.mock.calls[0]?.[1]?.headers as HeadersInit);
    const secondHeaders = new Headers(fetchMock.mock.calls[1]?.[1]?.headers as HeadersInit);

    expect(firstHeaders.get("x-request-id")).toBeTruthy();
    expect(secondHeaders.get("x-request-id")).toBeTruthy();
    expect(secondHeaders.get("x-request-id")).not.toBe(firstHeaders.get("x-request-id"));

    fetchMock.mockRestore();
  });
});

describe("api", () => {
  it("generates a fresh request id for each request", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "content-type": "application/json" },
        }),
      );

    await api<{ ok: boolean }>("/config");
    await api<{ ok: boolean }>("/config");

    const firstHeaders = new Headers(fetchMock.mock.calls[0]?.[1]?.headers as HeadersInit);
    const secondHeaders = new Headers(fetchMock.mock.calls[1]?.[1]?.headers as HeadersInit);

    expect(firstHeaders.get("x-request-id")).toBeTruthy();
    expect(secondHeaders.get("x-request-id")).toBeTruthy();
    expect(secondHeaders.get("x-request-id")).not.toBe(firstHeaders.get("x-request-id"));

    fetchMock.mockRestore();
  });

  it("preserves request id headers when custom headers are provided", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      new Response(
        JSON.stringify({ items: [], errors: [], total_token_estimate: 0 }),
        {
          status: 200,
          headers: { "content-type": "application/json" },
        },
      ),
    );

    await validateContext("sess-1", ["src/app.py"]);

    const headers = new Headers(fetchMock.mock.calls[0]?.[1]?.headers as HeadersInit);
    expect(headers.get("content-type")).toBe("application/json");
    expect(headers.get("x-request-id")).toBeTruthy();

    fetchMock.mockRestore();
  });
});
