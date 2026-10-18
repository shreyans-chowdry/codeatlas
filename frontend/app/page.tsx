"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { RepoIngestForm } from "@/components/RepoIngestForm";
import { FileExplorer } from "@/components/FileExplorer";
import { ChatPanel } from "@/components/ChatPanel";
import { ArchitectureGraph } from "@/components/ArchitectureGraph";
import { FileViewer, type OpenFileRequest } from "@/components/FileViewer";
import { api, type GraphData } from "@/lib/api";
import { Layers, FolderTree, Network, Plus, AlertTriangle, MessageSquare } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";

const STORAGE_KEY = "codeatlas:last-repo";

export default function Home() {
  const [repoState, setRepoState] = useState<{ id: string; name: string } | null>(null);
  const [leftPaneTab, setLeftPaneTab] = useState<"explorer" | "graph">("explorer");
  // Below the lg breakpoint only one pane is shown at a time
  const [mobileView, setMobileView] = useState<"explore" | "chat">("chat");
  // Graph results are tagged with the repo they belong to, so switching repos never shows stale data
  const [graphResult, setGraphResult] = useState<{ repoId: string; data?: GraphData; error?: string } | null>(null);
  const graph = repoState && graphResult?.repoId === repoState.id ? graphResult.data ?? null : null;
  const graphError = repoState && graphResult?.repoId === repoState.id ? graphResult.error ?? null : null;
  const [openFile, setOpenFile] = useState<OpenFileRequest | null>(null);

  // Restore the last opened repo after a refresh (if it still exists and is ready)
  useEffect(() => {
    let saved: { id: string; name: string } | null = null;
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      saved = raw ? JSON.parse(raw) : null;
    } catch {}
    if (!saved) return;
    api
      .status(saved.id)
      .then((s) => s.status === "ready" && setRepoState({ id: s.repo_id, name: s.name }))
      .catch(() => {});
  }, []);

  const selectRepo = useCallback((id: string, name: string) => {
    setRepoState({ id, name });
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ id, name }));
    } catch {}
  }, []);

  const leaveRepo = () => {
    setRepoState(null);
    setGraphResult(null);
    setOpenFile(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {}
  };

  // One graph fetch shared by the file tree, the graph view and chat citations
  useEffect(() => {
    if (!repoState) return;
    let cancelled = false;
    const id = repoState.id;
    api
      .graph(id)
      .then((data) => !cancelled && setGraphResult({ repoId: id, data }))
      .catch((e) => !cancelled && setGraphResult({ repoId: id, error: e.message }));
    return () => {
      cancelled = true;
    };
  }, [repoState]);

  const pathToId = useMemo(() => {
    const map: Record<string, string> = {};
    graph?.nodes.forEach((n) => (map[n.path] = n.id));
    return map;
  }, [graph]);

  const closeViewer = useCallback(() => setOpenFile(null), []);

  const tabClass = (active: boolean) =>
    `flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-colors ${
      active ? "bg-surface text-primary shadow-sm border border-border" : "text-muted-foreground border border-transparent hover:bg-muted/60 hover:text-foreground"
    }`;

  return (
    <main className="h-dvh bg-background text-foreground flex flex-col font-sans selection:bg-primary/25 overflow-hidden">
      {/* Header */}
      <header className="h-14 sm:h-16 border-b border-border bg-surface/80 backdrop-blur-md flex items-center gap-3 px-3 sm:px-6 shrink-0 z-20">
        <button onClick={leaveRepo} className="flex items-center gap-2.5 shrink-0 rounded-lg" title="Home">
          <div className="w-8 h-8 rounded-lg bg-primary/15 flex items-center justify-center border border-primary/30">
            <Layers className="w-4 h-4 text-primary" />
          </div>
          <h1 className="text-lg sm:text-xl font-bold tracking-tight hidden min-[400px]:block">CodeAtlas AI</h1>
        </button>

        <div className="ml-auto flex items-center gap-2 sm:gap-3 min-w-0">
          {repoState && (
            <>
              <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted/60 border border-border text-sm font-medium min-w-0">
                <span className="w-2 h-2 rounded-full bg-success shrink-0" />
                <span className="truncate">{repoState.name}</span>
                {graph && <span className="text-muted-foreground font-normal shrink-0">· {graph.nodes.length} files</span>}
              </div>
              <button
                onClick={leaveRepo}
                className="flex items-center gap-1.5 px-2.5 sm:px-3 py-1.5 rounded-lg text-sm border border-border bg-surface hover:bg-muted/60 transition-colors shrink-0"
                title="Analyze another repository"
              >
                <Plus className="w-4 h-4" />
                <span className="hidden sm:inline">New repo</span>
              </button>
            </>
          )}
          <ThemeToggle />
        </div>
      </header>

      {/* Main */}
      <div className="flex-1 flex flex-col relative overflow-hidden">
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-[1000px] h-[420px] bg-primary/[0.06] blur-[120px] rounded-full pointer-events-none" />

        {!repoState ? (
          <div className="flex-1 overflow-y-auto relative z-10">
            <div className="min-h-full flex items-center justify-center p-4 sm:p-6">
              <RepoIngestForm onReady={selectRepo} />
            </div>
          </div>
        ) : (
          <>
            {/* Phone/tablet: switch between the explorer and the chat */}
            <div className="lg:hidden flex gap-2 p-2 mx-3 mt-3 rounded-xl border border-border bg-muted/40 relative z-10">
              <button onClick={() => setMobileView("explore")} className={tabClass(mobileView === "explore")}>
                <FolderTree className="w-4 h-4" /> Explore
              </button>
              <button onClick={() => setMobileView("chat")} className={tabClass(mobileView === "chat")}>
                <MessageSquare className="w-4 h-4" /> Chat
              </button>
            </div>

            <div className="flex-1 flex p-3 sm:p-4 lg:p-6 gap-4 lg:gap-6 relative z-10 min-h-0">
              {/* Left: File tree / Graph */}
              <div
                className={`${mobileView === "explore" ? "flex" : "hidden"} lg:flex w-full lg:w-[36%] lg:min-w-[320px] lg:max-w-[520px] flex-col h-full bg-surface border border-border rounded-2xl overflow-hidden shadow-sm`}
              >
                <div className="flex p-2 gap-2 border-b border-border bg-muted/40">
                  <button onClick={() => setLeftPaneTab("explorer")} className={tabClass(leftPaneTab === "explorer")}>
                    <FolderTree className="w-4 h-4" />
                    File Tree
                  </button>
                  <button onClick={() => setLeftPaneTab("graph")} className={tabClass(leftPaneTab === "graph")}>
                    <Network className="w-4 h-4" />
                    Graph
                  </button>
                </div>

                <div className="flex-1 overflow-hidden">
                  {graphError ? (
                    <div className="p-4 text-sm text-danger flex gap-2">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" /> {graphError}
                    </div>
                  ) : leftPaneTab === "explorer" ? (
                    <FileExplorer repoName={repoState.name} graph={graph} onOpenFile={setOpenFile} />
                  ) : (
                    <ArchitectureGraph graph={graph} onOpenFile={setOpenFile} />
                  )}
                </div>
              </div>

              {/* Right: Chat */}
              <div className={`${mobileView === "chat" ? "flex" : "hidden"} lg:flex flex-1 h-full min-w-0 flex-col`}>
                <ChatPanel key={repoState.id} repoId={repoState.id} pathToId={pathToId} onOpenFile={setOpenFile} />
              </div>
            </div>
          </>
        )}
      </div>

      {repoState && openFile && (
        <FileViewer
          key={`${openFile.fileId}:${openFile.startLine ?? ""}`}
          repoId={repoState.id}
          request={openFile}
          onClose={closeViewer}
        />
      )}
    </main>
  );
}
