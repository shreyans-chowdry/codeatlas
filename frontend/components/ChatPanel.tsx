"use client";

import { useState, useRef, useEffect, useMemo, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Send, FileCode, Bot, Loader2, Trash2, Square, AlertTriangle } from "lucide-react";
import { api, streamChat, type ChatMessage, type Source } from "@/lib/api";
import type { OpenFileRequest } from "@/components/FileViewer";

const SUGGESTIONS = [
  "Give me a high-level overview of this codebase's architecture.",
  "Where is the main entry point and what happens on startup?",
  "How is configuration loaded?",
  "Which modules have the most dependencies, and why?",
];

// `path/to/file.py (lines 12–40)`  or  `path/to/file.py`
const CITATION_RE = /^([\w@.\-/]+\.[\w]+)(?:\s*\(lines?\s*(\d+)(?:\s*[–-]\s*(\d+))?\))?$/;

function CitationPill({
  path,
  start,
  end,
  onClick,
}: {
  path: string;
  start?: number;
  end?: number;
  onClick?: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={!onClick}
      className="inline-flex max-w-full items-center gap-1.5 px-2 py-0.5 mx-0.5 rounded-full bg-primary/15 text-primary border border-primary/30 text-xs font-medium hover:bg-primary/25 transition-colors align-middle disabled:cursor-default"
      title={onClick ? `Open ${path}` : path}
    >
      <FileCode className="w-3 h-3 shrink-0" />
      <span className="font-mono truncate min-w-0">{path.split("/").slice(-2).join("/")}</span>
      {start !== undefined && (
        <span className="opacity-70 text-[10px] shrink-0 whitespace-nowrap">
          L{start}
          {end !== undefined && end !== start ? `–${end}` : ""}
        </span>
      )}
    </button>
  );
}

/**
 * Claude is told to cite as `path (lines a–b)`; it sometimes omits the
 * backticks. Wrap bare citations of known files in backticks (outside code
 * fences) so they render as clickable pills too.
 */
function normalizeCitations(text: string, knownPaths: string[]) {
  if (!knownPaths.length) return text;
  const escaped = knownPaths
    .slice()
    .sort((a, b) => b.length - a.length)
    .map((p) => p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const re = new RegExp(`(?<![\`\\w/])(${escaped.join("|")})(\\s*\\(lines?\\s*\\d+(?:\\s*[–-]\\s*\\d+)?\\))?(?![\`\\w])`, "g");
  return text
    .split(/(```[\s\S]*?```)/g)
    .map((seg) => (seg.startsWith("```") ? seg : seg.replace(re, (m) => "`" + m.trim() + "`")))
    .join("");
}

function AssistantMarkdown({
  text,
  pathToId,
  onOpenFile,
}: {
  text: string;
  pathToId: Record<string, string>;
  onOpenFile: (r: OpenFileRequest) => void;
}) {
  const content = useMemo(() => normalizeCitations(text, Object.keys(pathToId)), [text, pathToId]);

  return (
    <div className="prose-chat text-sm leading-relaxed">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          pre: ({ children }) => (
            <pre className="my-3 p-3 rounded-lg bg-background border border-border overflow-x-auto text-[12.5px] leading-5">
              {children}
            </pre>
          ),
          code: ({ className, children }) => {
            const raw = String(children ?? "");
            const isBlock = Boolean(className) || raw.includes("\n");
            if (isBlock) return <code className="font-mono">{children}</code>;
            const m = raw.trim().match(CITATION_RE);
            if (m) {
              const path = m[1];
              const fileId = pathToId[path] ?? pathToId[path.replace(/^\.\//, "")];
              if (fileId) {
                const start = m[2] ? parseInt(m[2], 10) : undefined;
                const end = m[3] ? parseInt(m[3], 10) : start;
                return (
                  <CitationPill
                    path={path}
                    start={start}
                    end={end}
                    onClick={() => onOpenFile({ fileId, path, startLine: start, endLine: end })}
                  />
                );
              }
            }
            return <code className="font-mono text-[12.5px] px-1 py-0.5 rounded bg-muted/70 border border-border">{children}</code>;
          },
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">
              {children}
            </a>
          ),
          ul: ({ children }) => <ul className="list-disc pl-5 my-2 space-y-1">{children}</ul>,
          ol: ({ children }) => <ol className="list-decimal pl-5 my-2 space-y-1">{children}</ol>,
          p: ({ children }) => <p className="my-2 first:mt-0 last:mb-0">{children}</p>,
          h1: ({ children }) => <h3 className="text-base font-semibold mt-4 mb-2 first:mt-0">{children}</h3>,
          h2: ({ children }) => <h3 className="text-base font-semibold mt-4 mb-2 first:mt-0">{children}</h3>,
          h3: ({ children }) => <h4 className="font-semibold mt-3 mb-1.5 first:mt-0">{children}</h4>,
          table: ({ children }) => (
            <div className="overflow-x-auto my-3">
              <table className="text-xs border-collapse">{children}</table>
            </div>
          ),
          th: ({ children }) => <th className="border border-border px-2 py-1 text-left">{children}</th>,
          td: ({ children }) => <td className="border border-border px-2 py-1">{children}</td>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

function SourcesRow({ sources, onOpenFile }: { sources: Source[]; onOpenFile: (r: OpenFileRequest) => void }) {
  if (!sources.length) return null;
  return (
    <div className="mt-3 pt-3 border-t border-border">
      <div className="text-[10px] uppercase tracking-wider text-muted-foreground mb-1.5 font-semibold">
        Retrieved context ({sources.length})
      </div>
      <div className="flex flex-wrap gap-1">
        {sources.map((s, i) => (
          <CitationPill
            key={`${s.file_id}-${s.start_line}-${i}`}
            path={s.path}
            start={s.start_line}
            end={s.end_line}
            onClick={() => onOpenFile({ fileId: s.file_id, path: s.path, startLine: s.start_line, endLine: s.end_line })}
          />
        ))}
      </div>
    </div>
  );
}

export function ChatPanel({
  repoId,
  pathToId,
  onOpenFile,
}: {
  repoId: string;
  pathToId: Record<string, string>;
  onOpenFile: (r: OpenFileRequest) => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Load persisted history for this repo
  useEffect(() => {
    // Parent remounts this panel per repo (key), so state starts empty
    let cancelled = false;
    api
      .messages(repoId)
      .then((m) => !cancelled && setMessages(m))
      .catch(() => {});
    return () => {
      cancelled = true;
      abortRef.current?.abort();
    };
  }, [repoId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Immutable update of the last (assistant) message
  const updateLast = (fn: (m: ChatMessage) => ChatMessage) =>
    setMessages((prev) => {
      if (!prev.length) return prev;
      const last = prev[prev.length - 1];
      if (last.role !== "assistant") return prev;
      return [...prev.slice(0, -1), fn(last)];
    });

  const ask = async (question: string) => {
    const q = question.trim();
    if (!q || isStreaming) return;
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: q }, { role: "assistant", content: "" }]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortRef.current = controller;
    await streamChat(
      repoId,
      q,
      {
        onSources: (sources) => updateLast((m) => ({ ...m, sources })),
        onDelta: (text) => updateLast((m) => ({ ...m, content: m.content + text })),
        onError: (error) => updateLast((m) => ({ ...m, error })),
      },
      controller.signal
    );
    setIsStreaming(false);
    abortRef.current = null;
  };

  const clearChat = async () => {
    if (isStreaming) return;
    try {
      await api.clearMessages(repoId);
      setMessages([]);
    } catch {}
  };

  const renderBody = (msg: ChatMessage, isLast: boolean): ReactNode => {
    if (msg.role === "user") return <span className="whitespace-pre-wrap leading-relaxed text-sm">{msg.content}</span>;
    if (!msg.content && !msg.error && isLast && isStreaming) {
      return (
        <div className="flex items-center gap-2 text-muted-foreground h-6 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" />
          {msg.sources ? `Reading ${msg.sources.length} code excerpts…` : "Searching the codebase…"}
        </div>
      );
    }
    return (
      <>
        {msg.content && <AssistantMarkdown text={msg.content} pathToId={pathToId} onOpenFile={onOpenFile} />}
        {msg.error && (
          <div className="flex items-start gap-2 text-sm text-danger mt-1">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{msg.error}</span>
          </div>
        )}
        {msg.sources && <SourcesRow sources={msg.sources} onOpenFile={onOpenFile} />}
      </>
    );
  };

  return (
    <div className="flex flex-col h-full bg-surface border border-border rounded-2xl overflow-hidden shadow-sm">
      <div className="px-4 py-3 border-b border-border bg-muted/40 flex items-center">
        <h3 className="font-semibold text-foreground flex items-center gap-2">
          <Bot className="w-5 h-5 text-primary" />
          Code Assistant
        </h3>
        {messages.length > 0 && (
          <button
            onClick={clearChat}
            disabled={isStreaming}
            className="ml-auto flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded-md hover:bg-muted/50 disabled:opacity-40"
          >
            <Trash2 className="w-3.5 h-3.5" /> Clear chat
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-3 sm:p-4 space-y-5 sm:space-y-6">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground max-w-md mx-auto space-y-4">
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
              <Bot className="w-6 h-6 text-primary" />
            </div>
            <p className="text-sm">Ask anything about the architecture, logic, or dependencies. Answers cite the exact files and lines they come from.</p>
            <div className="flex flex-col gap-2 w-full pt-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => ask(s)}
                  className="text-left text-sm px-3 py-2 rounded-lg border border-border hover:border-primary/40 hover:bg-primary/5 text-foreground/80 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div key={idx} className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              {msg.role === "assistant" && (
                <div className="hidden sm:flex w-8 h-8 rounded-full bg-primary/15 items-center justify-center shrink-0 mt-1">
                  <Bot className="w-4 h-4 text-primary" />
                </div>
              )}
              <div
                className={`${msg.role === "user" ? "max-w-[85%]" : "max-w-full sm:max-w-[85%]"} min-w-0 rounded-2xl px-4 py-3 ${
                  msg.role === "user"
                    ? "bg-primary text-primary-foreground rounded-tr-sm"
                    : "bg-muted/50 border border-border rounded-tl-sm text-foreground"
                }`}
              >
                {renderBody(msg, idx === messages.length - 1)}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-3 sm:p-4 bg-muted/40 border-t border-border">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
          className="relative flex items-center"
        >
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about the codebase..."
            disabled={isStreaming}
            className="w-full pl-4 pr-12 py-3 rounded-xl bg-background border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all disabled:opacity-50"
          />
          {isStreaming ? (
            <button
              type="button"
              onClick={() => abortRef.current?.abort()}
              className="absolute right-2 p-2 rounded-lg bg-muted text-foreground hover:bg-muted/70 transition-colors"
              title="Stop generating"
            >
              <Square className="w-5 h-5" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!input.trim()}
              className="absolute right-2 p-2 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Send className="w-5 h-5" />
            </button>
          )}
        </form>
      </div>
    </div>
  );
}
