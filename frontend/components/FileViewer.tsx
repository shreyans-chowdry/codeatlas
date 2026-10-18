"use client";

import { useEffect, useRef, useState } from "react";
import { X, FileCode2, Loader2, Copy, Check } from "lucide-react";
import { api } from "@/lib/api";

export interface OpenFileRequest {
  fileId: string;
  path?: string;
  startLine?: number;
  endLine?: number;
}

export function FileViewer({
  repoId,
  request,
  onClose,
}: {
  repoId: string;
  request: OpenFileRequest;
  onClose: () => void;
}) {
  const [file, setFile] = useState<{ path: string; language: string | null; content: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const highlightRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Parent remounts this component (key) per file, so no state reset is needed here
    let cancelled = false;
    api
      .file(repoId, request.fileId)
      .then((f) => !cancelled && setFile(f))
      .catch((e) => !cancelled && setError(e.message));
    return () => {
      cancelled = true;
    };
  }, [repoId, request.fileId]);

  // Scroll the cited range into view once the file renders
  useEffect(() => {
    if (file && highlightRef.current) {
      highlightRef.current.scrollIntoView({ block: "center" });
    }
  }, [file, request.startLine]);

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const lines = file ? file.content.split("\n") : [];
  const start = request.startLine ?? -1;
  const end = request.endLine ?? start;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 dark:bg-black/60 backdrop-blur-sm p-2 sm:p-4" onClick={onClose}>
      <div
        className="w-full max-w-5xl h-[92dvh] sm:h-[85vh] flex flex-col rounded-2xl border border-border bg-background shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-muted/40">
          <FileCode2 className="w-4 h-4 text-primary shrink-0" />
          <span className="font-mono text-sm truncate">{file?.path || request.path || "Loading…"}</span>
          {start > 0 && (
            <span className="text-xs text-muted-foreground shrink-0">
              lines {start}–{end}
            </span>
          )}
          <div className="ml-auto flex items-center gap-1">
            {file && (
              <button
                onClick={() => {
                  navigator.clipboard?.writeText(file.content).then(() => {
                    setCopied(true);
                    setTimeout(() => setCopied(false), 1500);
                  });
                }}
                className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground"
                title="Copy file"
              >
                {copied ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
              </button>
            )}
            <button onClick={onClose} className="p-2 rounded-lg hover:bg-muted text-muted-foreground hover:text-foreground" title="Close (Esc)">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto font-mono text-[13px] leading-6">
          {error ? (
            <div className="p-6 text-danger text-sm">{error}</div>
          ) : !file ? (
            <div className="h-full flex items-center justify-center text-muted-foreground gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading file…
            </div>
          ) : file.content === "" ? (
            <div className="p-6 text-muted-foreground text-sm">
              No stored content for this file. Re-ingest the repository to enable the file viewer.
            </div>
          ) : (
            <div className="min-w-max py-2">
              {lines.map((line, i) => {
                const n = i + 1;
                const hit = n >= start && n <= end;
                return (
                  <div
                    key={n}
                    ref={n === start ? highlightRef : undefined}
                    className={`flex ${hit ? "bg-primary/15 border-l-2 border-primary" : "border-l-2 border-transparent"}`}
                  >
                    <span className="w-14 shrink-0 text-right pr-4 select-none text-muted-foreground/60">{n}</span>
                    <span className="whitespace-pre pr-6">{line || " "}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
