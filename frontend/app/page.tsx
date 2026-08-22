"use client";

import { useState } from "react";
import { RepoIngestForm } from "@/components/RepoIngestForm";
import { FileExplorer } from "@/components/FileExplorer";
import { ChatPanel } from "@/components/ChatPanel";
import { ArchitectureGraph } from "@/components/ArchitectureGraph";
import { Layers, FolderTree, Network } from "lucide-react";

export default function Home() {
  const [repoState, setRepoState] = useState<{ id: string; name: string } | null>(null);
  const [leftPaneTab, setLeftPaneTab] = useState<"explorer" | "graph">("explorer");

  return (
    <main className="min-h-screen bg-background text-foreground flex flex-col font-sans selection:bg-primary/30">
      
      {/* Top Navigation / Header */}
      <header className="h-16 border-b border-border/50 bg-background/80 backdrop-blur-md flex items-center px-6 shrink-0 sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-primary/20 flex items-center justify-center border border-primary/30 shadow-sm">
            <Layers className="w-4 h-4 text-primary" />
          </div>
          <h1 className="text-xl font-bold tracking-tight bg-gradient-to-br from-foreground to-foreground/70 bg-clip-text text-transparent">
            CodeAtlas AI
          </h1>
        </div>
        {repoState && (
          <div className="ml-auto flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted/30 border border-border/50 text-sm font-medium">
            <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
            {repoState.name}
          </div>
        )}
      </header>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col relative overflow-hidden">
        {/* Subtle Background Glow */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-[1000px] h-[500px] bg-primary/5 blur-[120px] rounded-full pointer-events-none" />

        {!repoState ? (
          // Uninitialized State: Centered Form
          <div className="flex-1 flex items-center justify-center p-6 relative z-10">
            <RepoIngestForm 
              onReady={(id, name) => setRepoState({ id, name })} 
            />
          </div>
        ) : (
          // Ready State: Split Pane Dashboard
          <div className="flex-1 flex p-6 gap-6 relative z-10 h-[calc(100vh-4rem)]">
            
            {/* Left Pane: Tabbed File Explorer / Architecture Graph */}
            <div className="w-1/3 min-w-[300px] flex flex-col h-full bg-background/50 border border-border/50 rounded-2xl overflow-hidden backdrop-blur-xl">
              
              {/* Tab Switcher */}
              <div className="flex p-2 gap-2 border-b border-border/50 bg-muted/20">
                <button
                  onClick={() => setLeftPaneTab("explorer")}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                    leftPaneTab === "explorer"
                      ? "bg-background text-primary shadow-sm border border-border/50"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                  }`}
                >
                  <FolderTree className="w-4 h-4" />
                  File Tree
                </button>
                <button
                  onClick={() => setLeftPaneTab("graph")}
                  className={`flex-1 flex items-center justify-center gap-2 py-2 px-3 rounded-lg text-sm font-medium transition-all ${
                    leftPaneTab === "graph"
                      ? "bg-background text-primary shadow-sm border border-border/50"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                  }`}
                >
                  <Network className="w-4 h-4" />
                  Graph
                </button>
              </div>

              {/* Tab Content */}
              <div className="flex-1 overflow-hidden">
                {leftPaneTab === "explorer" ? (
                  <FileExplorer repoId={repoState.id} repoName={repoState.name} />
                ) : (
                  <ArchitectureGraph repoId={repoState.id} />
                )}
              </div>
            </div>

            {/* Right Pane: Chat */}
            <div className="flex-1 h-full min-w-0">
              <ChatPanel repoId={repoState.id} />
            </div>
          </div>
        )}
      </div>
      
    </main>
  );
}
