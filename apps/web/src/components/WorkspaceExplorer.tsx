import React, { useEffect, useState } from "react";
import { FileText, Folder, Copy, Eye, Plus } from "lucide-react";
import { api } from "../api";
import type { FileEntry } from "../types";

interface WorkspaceExplorerProps {
  workspaceRoot?: string;
  changedFiles?: string[];
  onAttach?: (path: string) => void;
}

export function WorkspaceExplorer({ workspaceRoot, changedFiles = [], onAttach }: WorkspaceExplorerProps) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [query, setQuery] = useState("");
  const [preview, setPreview] = useState<{ path: string; content: string } | null>(null);

  useEffect(() => {
    if (!workspaceRoot) return;
    api<FileEntry[]>("/coder/files")
      .then(setFiles)
      .catch(() => setFiles([]));
  }, [workspaceRoot]);

  const filtered = files.filter((f) =>
    f.path.toLowerCase().includes(query.toLowerCase())
  );

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
          onChange={(e) => setQuery(e.target.value)}
          style={{ width: "100%", fontSize: "13px" }}
        />
      </div>
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
          {filtered.map((file) => (
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
        </div>
      )}
    </div>
  );
}
