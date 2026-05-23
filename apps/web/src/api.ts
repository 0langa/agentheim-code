const API_BASE = "/api";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE}${path}`;
  const response = await fetch(url, {
    headers: { "content-type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  return response.json() as Promise<T>;
}

export interface StreamHandlers {
  onStart?: () => void;
  onToken?: (token: string) => void;
  onActivity?: (event: unknown) => void;
  onDone?: (payload: unknown) => void;
  onError?: (error: string) => void;
}

function dispatchSseBlock(block: string, handlers: StreamHandlers): void {
  const lines = block.split("\n").filter(Boolean);
  const event = lines
    .find((line) => line.startsWith("event:"))
    ?.slice("event:".length)
    .trim();
  const data = lines
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trim())
    .join("\n");
  const payload = data ? JSON.parse(data) : {};

  if (event === "start") handlers.onStart?.();
  if (event === "token") handlers.onToken?.(String(payload.token ?? ""));
  if (event === "activity") handlers.onActivity?.(payload.event);
  if (event === "done") handlers.onDone?.(payload);
  if (event === "error") handlers.onError?.(String(payload.error ?? "Stream failed"));
}

export async function streamSessionMessage(
  sessionId: string,
  prompt: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(
    `${API_BASE}/coder/sessions/${sessionId}/messages/stream`,
    {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ prompt }),
      signal,
    },
  );
  if (!response.ok) {
    throw new ApiError(response.status, await response.text());
  }
  if (!response.body) {
    throw new Error("Streaming response is not readable");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value ?? new Uint8Array(), { stream: !done });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      if (block.trim()) dispatchSseBlock(block, handlers);
    }
    if (done) break;
  }

  if (buffer.trim()) dispatchSseBlock(buffer, handlers);
}
