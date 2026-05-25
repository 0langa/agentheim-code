import React, { useDeferredValue, useEffect, useRef, useState } from "react";
import { FileText, Folder, Copy, Eye, Plus } from "lucide-react";
import { api, browseFiles } from "../api";
import type { FileEntry } from "../types";

const BATCH_SIZE = 100;

interface WorkspaceExplorerProps {
  workspaceRoot?: string;
  changedFiles?: string[];
  onAttach?: (path: string) => void;
}

export function WorkspaceExplorer({ workspaceRoot, changedFiles = [], onAttach }: WorkspaceExplorerProps) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const [preview, setPreview] = useState<{ path: string; content: string } | null>(null);
  const [nextOffset, setNextOffset] = useState<number | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const requestSequence = useRef(0);

  const loadPage = async (offset: number, append: boolean) => {
    if (!workspaceRoot) return;
    const requestId = requestSequence.current + 1;
    requestSequence.current = requestId;
    setIsLoading(true);
    setLoadError(null);
    try {
      const data = await browseFiles(deferredQuery, offset, BATCH_SIZE);
      if (requestSequence.current !== requestId) return;
      setFiles((current) => (append ? [...current, ...data.items] : data.items));
      setNextOffset(data.next_offset ?? null);
      setHasMore(data.has_more);
    } catch (err) {
      if (requestSequence.current !== requestId) return;
      setLoadError(err instanceof Error ? err.message : "Unable to load workspace files.");
      if (!append) {
        setFiles([]);
        setNextOffset(null);
        setHasMore(false);
      }
    } finally {
      if (requestSequence.current === requestId) {
        setIsLoading(false);
      }
    }
  };

  useEffect(() => {
    if (!workspaceRoot) return;
    void loadPage(0, false);
  }, [workspaceRoot, deferredQuery]);

  const isChanged = (path: string) => changedFiles.includes(path);

  const copyPath = (path: string) => {
    navigator.clipboard.writeText(path).catch(() => {});
  };

  const openPreview = async (path: string) => {
    try {
      const text = await api<string>(`/coder/files/preview?path=${encodeURIComponent(path)}`);
      setPreview({ path, content: text });
    } catch {
      setPreview({ path, content: "Unable to preview file." });
    }
  };

  return (
    <div className="panel-list">
      <div style={{ padding: "8px 12px", borderBottom: "1px solid var(--border)" }}>
        <input
          type="text"
          placeholder="Search files..."
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
          }}
          style={{ width: "100%", fontSize: "13px" }}
        />
      </div>
      <div style={{ padding: "4px 12px", fontSize: "11px", color: "var(--muted)" }}>
        {deferredQuery
          ? `${files.length} matching ${files.length === 1 ? "entry" : "entries"} loaded`
          : `${files.length} ${files.length === 1 ? "entry" : "entries"} loaded`}
      </div>
      {isLoading && (
        <div style={{ padding: "4px 12px", fontSize: "11px", color: "var(--accent)" }}>
          Loading files…
        </div>
      )}
      {loadError && (
        <div style={{ padding: "4px 12px", fontSize: "11px", color: "var(--error)" }}>
          {loadError}
        </div>
      )}
      {preview ? (
        <div style={{ padding: 8 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
            <strong style={{ fontSize: "12px" }}>{preview.path}</strong>
            <button type="button" onClick={() => setPreview(null)} style={{ marginLeft: "auto", fontSize: "11px" }}>
              Close
            </button>
          </div>
          <pre style={{ maxHeight: 300, overflow: "auto", fontSize: "11px" }}>{preview.content}</pre>
        </div>
      ) : (
        <div style={{ display: "grid" }}>
          {files.map((file) => (
            <div
              key={file.path}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 6,
                padding: "4px 12px",
                fontSize: "12px",
                borderBottom: "1px solid var(--border-subtle)",
              }}
            >
              {file.type === "directory" ? <Folder size={14} /> : <FileText size={14} />}
              <span style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                {file.path}
              </span>
              {isChanged(file.path) && (
                <span
                  className="badge"
                  style={{ background: "color-mix(in srgb, var(--accent) 25%, transparent)" }}
                >
                  changed
                </span>
              )}
              {file.type === "file" && (
                <>
                  <button type="button" aria-label={`Preview ${file.path}`} onClick={() => openPreview(file.path)}>
                    <Eye size={12} />
                  </button>
                  <button type="button" aria-label={`Copy ${file.path}`} onClick={() => copyPath(file.path)}>
                    <Copy size={12} />
                  </button>
                  {onAttach && (
                    <button type="button" aria-label={`Attach ${file.path}`} onClick={() => onAttach(file.path)}>
                      <Plus size={12} />
                    </button>
                  )}
                </>
              )}
            </div>
          ))}
          {!isLoading && files.length === 0 && (
            <div style={{ padding: "8px 12px", fontSize: "12px", color: "var(--muted)" }}>
              {deferredQuery ? "No files match this search yet." : "No files found in this workspace yet."}
            </div>
          )}
          {hasMore && nextOffset !== null && (
            <button
              type="button"
              onClick={() => void loadPage(nextOffset, true)}
              disabled={isLoading}
              style={{ padding: "8px 12px", fontSize: "12px", margin: "4px 12px" }}
            >
              Load next {BATCH_SIZE}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
