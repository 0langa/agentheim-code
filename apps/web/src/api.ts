import type {
  CoderSessionMessageRequest,
  ContextValidateRequest,
  ContextValidationResult,
  FileBrowsePage,
  Session,
} from "./types";

const DEFAULT_API_BASE = "/api";
let resolvedApiBase: Promise<string> | null = null;

function newRequestId(): string {
  return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeApiBase(base: string): string {
  return `${base.replace(/\/+$/, "")}/api`;
}

async function getApiBase(): Promise<string> {
  if (resolvedApiBase) return resolvedApiBase;

  resolvedApiBase = (async () => {
    if (
      window.location.protocol !== "tauri:" &&
      window.location.hostname !== "tauri.localhost"
    ) {
      return DEFAULT_API_BASE;
    }

    try {
      const { invoke } = await import("@tauri-apps/api/core");
      const backendUrl = await invoke<string | null>("backend_url");
      if (backendUrl) return normalizeApiBase(backendUrl);
    } catch {
      // Fall through to the local default when a backend is already running on
      // the standard port.
    }

    return "http://127.0.0.1:8765/api";
  })();

  return resolvedApiBase;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public requestId: string = "",
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
  const isSafe = !init.method || init.method === "GET" || init.method === "HEAD";
  // Also retry idempotent mutations (PATCH config, POST cancel) on transient failures
  const isIdempotent = isSafe || init.method === "POST" && url.endsWith("/cancel");
  const retries = isSafe ? 2 : isIdempotent ? 1 : 0;
  for (let attempt = 0; attempt <= retries; attempt++) {
    const response = await fetch(url, init);
    if (response.ok) {
      return response;
    }
    const isRetryable =
      response.status === 429 ||
      response.status === 503 ||
      response.status >= 500;
    if (!isRetryable || attempt === retries) {
      return response;
    }
    const delay = Math.min(300 * 2 ** attempt, 2000);
    await new Promise((r) => setTimeout(r, delay));
  }
  // Unreachable, but satisfies TypeScript
  return fetch(url, init);
}

function mergeHeaders(init?: RequestInit, requestId?: string): Headers {
  const headers = new Headers(init?.headers);
  if (!headers.has("content-type") && init?.body !== undefined) {
    headers.set("content-type", "application/json");
  }
  if (requestId) {
    headers.set("x-request-id", requestId);
  }
  return headers;
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${await getApiBase()}${path}`;
  const requestId = newRequestId();
  const response = await fetchWithRetry(url, {
    ...init,
    headers: mergeHeaders(init, requestId),
  });
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, text, response.headers.get("x-request-id") ?? requestId);
  }
  return response.json() as Promise<T>;
}

export interface StreamHandlers {
  onStart?: () => void;
  onToken?: (token: string) => void;
  onActivity?: (event: unknown) => void;
  onDone?: (payload: unknown) => void;
  onError?: (error: string, structuredError?: unknown) => void;
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
  if (event === "error") {
    const structured = (payload as Record<string, unknown>)?.structured_error;
    handlers.onError?.(String(payload.error ?? "Stream failed"), structured);
  }
}

export async function streamSessionMessage(
  sessionId: string,
  prompt: string,
  handlers: StreamHandlers,
  signal?: AbortSignal,
  contextFiles: string[] = [],
): Promise<void> {
  const apiBase = await getApiBase();
  const response = await fetch(
    `${apiBase}/coder/sessions/${sessionId}/messages/stream`,
    {
      method: "POST",
      headers: mergeHeaders(undefined, newRequestId()),
      body: JSON.stringify({
        prompt,
        context_files: contextFiles,
        use_context_bundle: true,
      } satisfies CoderSessionMessageRequest),
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

export async function cancelSession(sessionId: string): Promise<Session> {
  return api<Session>(`/coder/sessions/${sessionId}/cancel`, { method: "POST" });
}

export async function validateContext(
  sessionId: string,
  paths: string[],
): Promise<ContextValidationResult> {
  return api<ContextValidationResult>(
    `/coder/sessions/${sessionId}/context/validate`,
    {
      method: "POST",
      body: JSON.stringify({ paths } satisfies ContextValidateRequest),
    },
  );
}

export async function browseFiles(
  query = "",
  offset = 0,
  limit = 100,
): Promise<FileBrowsePage> {
  const params = new URLSearchParams({
    q: query,
    offset: String(offset),
    limit: String(limit),
  });
  return api<FileBrowsePage>(`/coder/files/browser?${params.toString()}`);
}
