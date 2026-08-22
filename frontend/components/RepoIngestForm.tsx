"use client";

import { useState, useEffect } from "react";
import { Loader2, GitBranch, ArrowRight } from "lucide-react";

interface RepoIngestFormProps {
  onReady: (repoId: string, repoName: string) => void;
}

export function RepoIngestForm({ onReady }: RepoIngestFormProps) {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<"idle" | "pending" | "ingesting" | "ready" | "failed">("idle");
  const [repoId, setRepoId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Poll for status once repoId is set
  useEffect(() => {
    if (!repoId || status === "ready" || status === "failed") return;

    const interval = setInterval(async () => {
      try {
        const res = await fetch(`http://localhost:8000/repos/${repoId}/status`);
        if (!res.ok) throw new Error("Failed to fetch status");
        const data = await res.json();
        
        setStatus(data.status);
        if (data.status === "ready") {
          clearInterval(interval);
          onReady(repoId, data.name);
        } else if (data.status === "failed") {
          clearInterval(interval);
          setError("Repository ingestion failed. Ensure it is a public repository.");
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [repoId, status, onReady]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!url) return;

    setStatus("pending");
    setError(null);
    try {
      const res = await fetch("http://localhost:8000/repos", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ github_url: url }),
      });
      
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || "Failed to submit repository");
      }
      
      const data = await res.json();
      setRepoId(data.repo_id);
    } catch (err: any) {
      setStatus("failed");
      setError(err.message);
    }
  };

  return (
    <div className="w-full max-w-md p-8 rounded-2xl bg-muted/30 border border-border/50 backdrop-blur-xl shadow-2xl transition-all">
      <div className="mb-8 text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
          <GitBranch className="w-8 h-8 text-primary" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight text-foreground mb-2">Ingest Repository</h2>
        <p className="text-sm text-muted-foreground">
          Enter a public GitHub URL to map its architecture and enable natural language exploration.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <input
            type="url"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/user/repo"
            required
            disabled={status !== "idle" && status !== "failed"}
            className="w-full px-4 py-3 rounded-xl bg-background border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all disabled:opacity-50"
          />
        </div>

        {error && (
          <div className="p-3 text-sm rounded-lg bg-red-500/10 text-red-500 border border-red-500/20">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={status !== "idle" && status !== "failed"}
          className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-primary text-primary-foreground font-medium hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background transition-all disabled:opacity-70 disabled:cursor-not-allowed"
        >
          {status === "idle" || status === "failed" ? (
            <>
              Start Ingestion
              <ArrowRight className="w-4 h-4" />
            </>
          ) : (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              {status === "pending" && "Initializing..."}
              {status === "ingesting" && "Mapping repository..."}
              {status === "ready" && "Ready!"}
            </>
          )}
        </button>
      </form>
    </div>
  );
}
