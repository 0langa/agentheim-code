import type {
  CoderSessionMessageRequest,
  ContextValidateRequest,
  ContextValidationResult,
  DiscoveredModel,
  FileBrowsePage,
  ManagementAccountTestResult,
  ManagementModelBinding,
  ManagementProfile,
  ManagementProviderAccount,
  ProviderTemplate,
  Session,
} from "./types";

const DEFAULT_API_BASE = "/api";
let resolvedApiBase: Promise<string> | null = null;

function isDesktopRuntime(): boolean {
  return window.location.protocol === "tauri:" || window.location.hostname === "tauri.localhost";
}

function newRequestId(): string {
  return crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeApiBase(base: string): string {
  return `${base.replace(/\/+$/, "")}/api`;
}

async function getApiBase(): Promise<string> {
  if (resolvedApiBase) return resolvedApiBase;

  resolvedApiBase = (async () => {
    if (!isDesktopRuntime()) {
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

export function isDesktopApp(): boolean {
  return isDesktopRuntime();
}

export async function pickDesktopWorkspace(): Promise<string | null> {
  if (!isDesktopRuntime()) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string | null>("desktop_pick_workspace");
}

export async function getDesktopBackendLaunchError(): Promise<string | null> {
  if (!isDesktopRuntime()) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  return invoke<string | null>("backend_launch_error");
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

function extractApiErrorMessage(raw: string): string {
  try {
    const parsed = JSON.parse(raw) as {
      detail?:
        | string
        | { message?: string; code?: string }
        | Array<{ msg?: string; loc?: Array<string | number> }>;
      message?: string;
      error?: string;
    };
    const detail = parsed.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    if (Array.isArray(detail) && detail.length > 0) {
      const first = detail[0];
      if (typeof first?.msg === "string" && first.msg.trim()) {
        const location = Array.isArray(first.loc) && first.loc.length > 0
          ? ` (${first.loc.join(".")})`
          : "";
        return `${first.msg}${location}`;
      }
    }
    if (detail && typeof detail === "object" && !Array.isArray(detail)) {
      const code = typeof detail.code === "string" ? detail.code : "";
      const message = typeof detail.message === "string" ? detail.message : "";
      if (message) return code ? `${message} (${code})` : message;
    }
    if (typeof parsed.message === "string" && parsed.message.trim()) return parsed.message;
    if (typeof parsed.error === "string" && parsed.error.trim()) return parsed.error;
  } catch {
    // Fall back to raw body text below.
  }
  return raw;
}

async function fetchWithRetry(url: string, init: RequestInit): Promise<Response> {
  const isSafe = !init.method || init.method === "GET" || init.method === "HEAD";
  // Also retry idempotent mutations (PATCH config, POST cancel) on transient failures
  const isIdempotent = isSafe || init.method === "POST" && url.endsWith("/cancel");
  const retries = isSafe ? 2 : isIdempotent ? 1 : 0;
  for (let attempt = 0; attempt <= retries; attempt++) {
    let response: Response;
    try {
      response = await fetch(url, init);
    } catch (error) {
      if (attempt === retries) {
        throw error;
      }
      const delay = Math.min(300 * 2 ** attempt, 2000);
      await new Promise((r) => setTimeout(r, delay));
      continue;
    }
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

function withWorkspaceRoot(path: string, workspaceRoot?: string | null): string {
  if (!workspaceRoot || workspaceRoot === ".") return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}workspace_root=${encodeURIComponent(workspaceRoot)}`;
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
    throw new ApiError(
      response.status,
      extractApiErrorMessage(text),
      response.headers.get("x-request-id") ?? requestId,
    );
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
  workspaceRoot?: string | null,
): Promise<void> {
  const apiBase = await getApiBase();
  const body = JSON.stringify({
    prompt,
    context_files: contextFiles,
    use_context_bundle: true,
  } satisfies CoderSessionMessageRequest);
  const response = await fetch(
    `${apiBase}${withWorkspaceRoot(`/coder/sessions/${sessionId}/messages/stream`, workspaceRoot)}`,
    {
      method: "POST",
      headers: mergeHeaders({ body }, newRequestId()),
      body,
      signal,
    },
  );
  if (!response.ok) {
    const text = await response.text();
    throw new ApiError(response.status, extractApiErrorMessage(text));
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

export async function cancelSession(
  sessionId: string,
  workspaceRoot?: string | null,
): Promise<Session> {
  return api<Session>(withWorkspaceRoot(`/coder/sessions/${sessionId}/cancel`, workspaceRoot), {
    method: "POST",
  });
}

export async function validateContext(
  sessionId: string,
  paths: string[],
  workspaceRoot?: string | null,
): Promise<ContextValidationResult> {
  return api<ContextValidationResult>(
    withWorkspaceRoot(`/coder/sessions/${sessionId}/context/validate`, workspaceRoot),
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

// Provider management API

export async function listManagementProfiles() {
  return api<{ configured: boolean; default_profile?: string; profiles: ManagementProfile[] }>(
    "/provider-management/profiles",
  );
}

export async function getManagementProfile(profileName: string) {
  return api<{ ok: boolean; profile: ManagementProfile }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}`,
  );
}

export async function createManagementProfile(name: string, setAsDefault = false) {
  return api<{ ok: boolean; profile: { name: string } }>("/provider-management/profiles", {
    method: "POST",
    body: JSON.stringify({ name, set_as_default: setAsDefault }),
  });
}

export async function deleteManagementProfile(name: string) {
  return api<{ ok: boolean }>(`/provider-management/profiles/${encodeURIComponent(name)}`, {
    method: "DELETE",
  });
}

export async function duplicateManagementProfile(source: string, target: string) {
  return api<{ ok: boolean; profile: { name: string } }>(
    `/provider-management/profiles/${encodeURIComponent(source)}/duplicate`,
    {
      method: "POST",
      body: JSON.stringify({ target_name: target }),
    },
  );
}

export async function setDefaultManagementProfile(name: string) {
  return api<{ ok: boolean }>(
    `/provider-management/profiles/${encodeURIComponent(name)}/set-default`,
    { method: "POST" },
  );
}

export async function exportManagementProfile(name: string) {
  return api<{ ok: boolean; data: unknown }>(
    `/provider-management/profiles/${encodeURIComponent(name)}/export`,
  );
}

export async function importManagementProfile(data: unknown, name?: string) {
  return api<{ ok: boolean; profile: { name: string } }>("/provider-management/profiles/import", {
    method: "POST",
    body: JSON.stringify({ data, name }),
  });
}

export async function addManagementAccount(profileName: string, account: unknown) {
  return api<{ ok: boolean; account: ManagementProviderAccount }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/accounts`,
    { method: "POST", body: JSON.stringify(account) },
  );
}

export async function updateManagementAccount(
  profileName: string,
  accountId: string,
  updates: unknown,
) {
  return api<{ ok: boolean; account: ManagementProviderAccount }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/accounts/${encodeURIComponent(accountId)}`,
    { method: "PATCH", body: JSON.stringify(updates) },
  );
}

export async function deleteManagementAccount(
  profileName: string,
  accountId: string,
  cascade = false,
) {
  return api<{ ok: boolean }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/accounts/${encodeURIComponent(accountId)}?cascade=${cascade}`,
    { method: "DELETE" },
  );
}

export async function testManagementAccount(profileName: string, accountId: string, modelId?: string) {
  return api<{ ok: boolean; result: ManagementAccountTestResult }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/accounts/${encodeURIComponent(accountId)}/test`,
    { method: "POST", body: JSON.stringify({ model_id: modelId }) },
  );
}

export async function testDraftManagementAccount(
  account: ManagementProviderAccount,
  options?: {
    secretValue?: string;
    modelId?: string;
    profileName?: string;
    existingAccountId?: string;
  },
) {
  return api<{ ok: boolean; result: ManagementAccountTestResult }>(
    "/provider-management/accounts/test-draft",
    {
      method: "POST",
      body: JSON.stringify({
        account,
        secret_value: options?.secretValue,
        model_id: options?.modelId,
        profile_name: options?.profileName,
        existing_account_id: options?.existingAccountId,
      }),
    },
  );
}

export async function rotateManagementSecret(
  profileName: string,
  accountId: string,
  secretName: string,
  secretValue: string,
) {
  return api<{ ok: boolean }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/accounts/${encodeURIComponent(accountId)}/rotate-secret`,
    { method: "POST", body: JSON.stringify({ secret_name: secretName, secret_value: secretValue }) },
  );
}

export async function discoverManagementModels(profileName: string, accountId: string) {
  return api<{
    ok: boolean;
    supported: boolean;
    discovery_mode: string;
    models: DiscoveredModel[];
  }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/accounts/${encodeURIComponent(accountId)}/discover-models`,
    { method: "POST" },
  );
}

export async function addManagementModel(profileName: string, model: unknown) {
  return api<{ ok: boolean; model: ManagementModelBinding }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/models`,
    { method: "POST", body: JSON.stringify(model) },
  );
}

export async function updateManagementModel(
  profileName: string,
  modelId: string,
  updates: unknown,
) {
  return api<{ ok: boolean; model: ManagementModelBinding }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/models/${encodeURIComponent(modelId)}`,
    { method: "PATCH", body: JSON.stringify(updates) },
  );
}

export async function deleteManagementModel(profileName: string, modelId: string) {
  return api<{ ok: boolean }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/models/${encodeURIComponent(modelId)}`,
    { method: "DELETE" },
  );
}

export async function setDefaultManagementModel(profileName: string, modelId: string) {
  return api<{ ok: boolean; model: ManagementModelBinding }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/models/${encodeURIComponent(modelId)}/set-default`,
    { method: "POST" },
  );
}

export async function importDiscoveredManagementModels(
  profileName: string,
  accountId: string,
  models: DiscoveredModel[],
) {
  return api<{ ok: boolean; models: ManagementModelBinding[] }>(
    `/provider-management/profiles/${encodeURIComponent(profileName)}/models/import-discovered`,
    { method: "POST", body: JSON.stringify({ account_id: accountId, models }) },
  );
}

export async function getManagementTemplates() {
  return api<ProviderTemplate[]>("/provider-management/templates");
}

