"use client";

import { useState, useRef, useEffect, Fragment } from "react";
import { Send, FileCode, Bot, User, Loader2 } from "lucide-react";

interface Message {
  role: "user" | "assistant";
  content: string;
}

// Helper to parse and render citations as pill badges
function renderTextWithCitations(text: string) {
  // Regex to match "### filepath (lines X-Y)"
  // Example: ### auth/middleware.py (lines 12-40)
  const citationRegex = /###\s+([^\s()]+)\s+\(lines\s+([0-9–-]+)\)/g;
  
  const parts = [];
  let lastIndex = 0;
  let match;

  while ((match = citationRegex.exec(text)) !== null) {
    // Push the text before the match
    if (match.index > lastIndex) {
      parts.push(text.slice(lastIndex, match.index));
    }

    const filePath = match[1];
    const lines = match[2];

    parts.push(
      <span
        key={match.index}
        className="inline-flex items-center gap-1.5 px-2 py-0.5 mx-1 rounded-full bg-primary/20 text-primary border border-primary/30 text-xs font-medium cursor-pointer hover:bg-primary/30 transition-colors align-middle"
        title={`Click to view ${filePath}`}
      >
        <FileCode className="w-3 h-3" />
        {filePath} <span className="opacity-70 text-[10px]">({lines})</span>
      </span>
    );

    lastIndex = citationRegex.lastIndex;
  }

  // Push remaining text
  if (lastIndex < text.length) {
    parts.push(text.slice(lastIndex));
  }

  return (
    <span className="whitespace-pre-wrap leading-relaxed">
      {parts.map((part, i) => (
        <Fragment key={i}>{part}</Fragment>
      ))}
    </span>
  );
}

export function ChatPanel({ repoId }: { repoId: string }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isStreaming]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isStreaming) return;

    const userMessage = input.trim();
    setInput("");
    setMessages((prev) => [...prev, { role: "user", content: userMessage }, { role: "assistant", content: "" }]);
    setIsStreaming(true);

    try {
      const res = await fetch(`http://localhost:8000/repos/${repoId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: userMessage }),
      });

      if (!res.body) throw new Error("No response body");

      const reader = res.body.getReader();
      const decoder = new TextDecoder("utf-8");
      
      let done = false;
      
      while (!done) {
        const { value, done: readerDone } = await reader.read();
        if (value) {
          const chunk = decoder.decode(value, { stream: true });
          // SSE chunks arrive as "data: {json}\n\n"
          const lines = chunk.split("\n");
          for (const line of lines) {
            if (line.startsWith("data: ")) {
              const dataStr = line.slice(6);
              try {
                const data = JSON.parse(dataStr);
                if (data.type === "delta" && data.text) {
                  setMessages((prev) => {
                    const newMessages = [...prev];
                    const lastMessage = newMessages[newMessages.length - 1];
                    if (lastMessage.role === "assistant") {
                      lastMessage.content += data.text;
                    }
                    return newMessages;
                  });
                } else if (data.type === "done") {
                  done = true;
                } else if (data.type === "error") {
                  console.error("Stream error:", data.message);
                  done = true;
                }
              } catch (e) {
                // Incomplete JSON chunk, wait for next chunk (edge case for simple parsing)
              }
            }
          }
        }
        if (readerDone) done = true;
      }
    } catch (err) {
      console.error("Chat error:", err);
    } finally {
      setIsStreaming(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-background/50 border border-border/50 rounded-2xl overflow-hidden backdrop-blur-xl">
      <div className="p-4 border-b border-border/50 bg-muted/20">
        <h3 className="font-semibold text-foreground flex items-center gap-2">
          <Bot className="w-5 h-5 text-primary" />
          Code Assistant
        </h3>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center text-muted-foreground max-w-sm mx-auto space-y-4">
            <div className="w-12 h-12 rounded-full bg-primary/10 flex items-center justify-center">
              <Bot className="w-6 h-6 text-primary" />
            </div>
            <p>I have analyzed the repository graph and code embeddings. Ask me anything about the architecture, logic, or dependencies!</p>
          </div>
        ) : (
          messages.map((msg, idx) => (
            <div key={idx} className={`flex gap-4 ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
              {msg.role === "assistant" && (
                <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center shrink-0 mt-1">
                  <Bot className="w-4 h-4 text-primary" />
                </div>
              )}
              <div
                className={`max-w-[80%] rounded-2xl p-4 ${
                  msg.role === "user" 
                    ? "bg-primary text-primary-foreground rounded-tr-sm" 
                    : "bg-muted/50 border border-border/50 rounded-tl-sm text-foreground"
                }`}
              >
                {msg.role === "assistant" && !msg.content && isStreaming ? (
                  <div className="flex items-center gap-2 text-muted-foreground h-6">
                    <Loader2 className="w-4 h-4 animate-spin" /> Thinking...
                  </div>
                ) : (
                  renderTextWithCitations(msg.content)
                )}
              </div>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 bg-muted/20 border-t border-border/50">
        <form onSubmit={handleSubmit} className="relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask about the codebase..."
            disabled={isStreaming}
            className="w-full pl-4 pr-12 py-3 rounded-xl bg-background border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={!input.trim() || isStreaming}
            className="absolute right-2 p-2 rounded-lg bg-primary/10 text-primary hover:bg-primary/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Send className="w-5 h-5" />
          </button>
        </form>
      </div>
    </div>
  );
}
