import { describe, expect, it, vi } from "vitest";

import { streamSessionMessage } from "../api";

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
        body: JSON.stringify({ prompt: "hi", context_files: [] }),
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
        body: JSON.stringify({ prompt: "hi", context_files: ["src/app.py"] }),
      }),
    );

    fetchMock.mockRestore();
  });
});
