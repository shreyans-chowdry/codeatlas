"use client";

import { useState, useEffect, useCallback } from "react";
import { Loader2, GitBranch, ArrowRight, AlertTriangle, CheckCircle2, Trash2, Clock, RotateCw } from "lucide-react";
import { api, API_URL, type Health, type RepoInfo, type RepoStatus } from "@/lib/api";

interface RepoIngestFormProps {
  onReady: (repoId: string, repoName: string) => void;
}

const EXAMPLES = ["pallets/itsdangerous", "encode/starlette", "tiangolo/typer"];

const STATUS_LABEL: Record<RepoStatus, string> = {
  pending: "Queued…",
  ingesting: "Cloning, chunking & embedding…",
  ready: "Ready",
  failed: "Failed",
};

function HealthBanner({ health, error }: { health: Health | null; error: string | null }) {
  if (error) {
    return (
      <div className="p-3 text-sm rounded-lg bg-danger/10 text-danger border border-danger/25 flex gap-2">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
        <span>
          Backend not reachable at <code className="font-mono">{API_URL}</code>. Start it with{" "}
          <code className="font-mono">uvicorn backend.main:app --reload</code>.
        </span>
      </div>
    );
  }
  if (!health) return null;
  const missing: string[] = [];
  if (!health.database) missing.push(`database (${health.database_error ?? "check DATABASE_URL"})`);
  if (!health.voyage_key_set) missing.push("VOYAGE_API_KEY");
  if (!health.anthropic_key_set) missing.push("ANTHROPIC_API_KEY");
  if (!missing.length) return null;
  return (
    <div className="p-3 text-sm rounded-lg bg-warning/10 text-warning border border-warning/25 flex gap-2">
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
      <span>
        Backend is running but not fully configured. Missing: <strong>{missing.join(", ")}</strong>. Add them to{" "}
        <code className="font-mono">.env</code> and restart the backend.
      </span>
    </div>
  );
}

export function RepoIngestForm({ onReady }: RepoIngestFormProps) {
  const [url, setUrl] = useState("");
  const [status, setStatus] = useState<"idle" | RepoStatus>("idle");
  const [repoId, setRepoId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [recent, setRecent] = useState<RepoInfo[]>([]);

  const loadRecent = useCallback(() => {
    api.listRepos().then(setRecent).catch(() => {});
  }, []);

  useEffect(() => {
    api
      .health()
      .then((h) => {
        setHealth(h);
        setHealthError(null);
      })
      .catch((e) => setHealthError(e.message));
    loadRecent();
  }, [loadRecent]);

  // Poll for status once repoId is set
  useEffect(() => {
    if (!repoId || status === "ready" || status === "failed" || status === "idle") return;

    const interval = setInterval(async () => {
      try {
        const data = await api.status(repoId);
        setStatus(data.status);
        if (data.status === "ready") {
          clearInterval(interval);
          onReady(repoId, data.name);
        } else if (data.status === "failed") {
          clearInterval(interval);
          setError(data.error || "Repository ingestion failed. Ensure it is a public repository.");
          loadRecent();
        }
      } catch (err) {
        console.error("Polling error:", err);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [repoId, status, onReady, loadRecent]);

  const submit = async (githubUrl: string, force = false) => {
    if (!githubUrl) return;
    setStatus("pending");
    setError(null);
    try {
      const data = await api.createRepo(githubUrl, force);
      if (data.status === "ready") {
        const info = await api.status(data.repo_id);
        onReady(data.repo_id, info.name);
        return;
      }
      setRepoId(data.repo_id);
      setStatus(data.status);
    } catch (err) {
      setStatus("failed");
      setError((err as Error).message);
    }
  };

  const busy = status === "pending" || status === "ingesting" || status === "ready";

  return (
    <div className="w-full max-w-lg space-y-4">
      <div className="p-6 sm:p-8 rounded-2xl bg-surface border border-border shadow-xl shadow-black/5 dark:shadow-black/40">
        <div className="mb-8 text-center">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-primary/10 mb-4">
            <GitBranch className="w-8 h-8 text-primary" />
          </div>
          <h2 className="text-2xl font-bold tracking-tight text-foreground mb-2">Ingest Repository</h2>
          <p className="text-sm text-muted-foreground">
            Enter a public GitHub URL to map its architecture and enable natural language exploration.
          </p>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            submit(url);
          }}
          className="space-y-4"
        >
          <HealthBanner health={health} error={healthError} />

          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://github.com/user/repo"
            required
            disabled={busy}
            className="w-full px-4 py-3 rounded-xl bg-background border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition-all disabled:opacity-50"
          />

          {error && (
            <div className="p-3 text-sm rounded-lg bg-danger/10 text-danger border border-danger/25 break-words">{error}</div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-xl bg-primary text-primary-foreground font-medium hover:bg-primary/90 focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background transition-all disabled:opacity-70 disabled:cursor-not-allowed"
          >
            {!busy ? (
              <>
                Start Ingestion
                <ArrowRight className="w-4 h-4" />
              </>
            ) : (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {STATUS_LABEL[status as RepoStatus]}
              </>
            )}
          </button>
          {busy && (
            <p className="text-xs text-center text-muted-foreground">
              Small repos take ~10–30s. Large ones can take a few minutes.
            </p>
          )}
          {!busy && (
            <div className="flex flex-wrap items-center justify-center gap-1.5 pt-1 text-xs text-muted-foreground">
              <span>Try:</span>
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => setUrl(`https://github.com/${ex}`)}
                  className="px-2 py-1 rounded-md border border-border bg-background hover:border-primary/40 hover:text-foreground font-mono transition-colors"
                >
                  {ex}
                </button>
              ))}
            </div>
          )}
        </form>
      </div>

      {recent.length > 0 && (
        <div className="p-3 sm:p-4 rounded-2xl bg-surface border border-border shadow-sm">
          <h3 className="text-xs uppercase tracking-wider font-semibold text-muted-foreground mb-2 px-1">Indexed repositories</h3>
          <ul className="space-y-1">
            {recent.map((r) => (
              <li key={r.repo_id} className="flex items-center gap-2 group">
                <button
                  disabled={r.status !== "ready" || busy}
                  onClick={() => onReady(r.repo_id, r.name)}
                  className="flex-1 flex items-center gap-2 px-2 py-2 rounded-lg text-sm text-left hover:bg-muted/50 disabled:hover:bg-transparent disabled:cursor-default min-w-0"
                  title={r.error || r.github_url}
                >
                  {r.status === "ready" ? (
                    <CheckCircle2 className="w-4 h-4 text-success shrink-0" />
                  ) : r.status === "failed" ? (
                    <AlertTriangle className="w-4 h-4 text-danger shrink-0" />
                  ) : (
                    <Clock className="w-4 h-4 text-warning shrink-0" />
                  )}
                  <span className="font-medium truncate">{r.name}</span>
                  <span className="text-xs text-muted-foreground shrink-0">
                    {r.status === "ready" ? `${r.file_count} files` : STATUS_LABEL[r.status]}
                  </span>
                </button>
                <button
                  onClick={() => submit(r.github_url, true)}
                  disabled={busy}
                  className="p-1.5 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/50 sm:opacity-0 sm:group-hover:opacity-100 focus-visible:opacity-100 disabled:opacity-30"
                  title="Re-ingest (pull latest code)"
                >
                  <RotateCw className="w-3.5 h-3.5" />
                </button>
                <button
                  onClick={async () => {
                    await api.deleteRepo(r.repo_id).catch(() => {});
                    loadRecent();
                  }}
                  disabled={busy}
                  className="p-1.5 rounded-md text-muted-foreground hover:text-danger hover:bg-muted/50 sm:opacity-0 sm:group-hover:opacity-100 focus-visible:opacity-100 disabled:opacity-30"
                  title="Delete index"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
