"use client";

import { useEffect, useState } from "react";
import { Folder, FolderOpen, FileCode2, ChevronRight, ChevronDown } from "lucide-react";

interface FileNode {
  id: string;
  path: string;
  language: string | null;
}

// Tree structure for rendering
interface TreeNode {
  name: string;
  type: "file" | "dir";
  language?: string | null;
  children?: Record<string, TreeNode>;
}

// Map languages to aesthetic Tailwind colors
const LANGUAGE_COLORS: Record<string, string> = {
  python: "bg-green-500/20 text-green-400 border-green-500/30",
  typescript: "bg-blue-500/20 text-blue-400 border-blue-500/30",
  javascript: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
  go: "bg-cyan-500/20 text-cyan-400 border-cyan-500/30",
  rust: "bg-orange-500/20 text-orange-400 border-orange-500/30",
  java: "bg-red-500/20 text-red-400 border-red-500/30",
};

function getLanguageColor(lang: string | null | undefined) {
  if (!lang) return "bg-muted text-muted-foreground border-border";
  return LANGUAGE_COLORS[lang.toLowerCase()] || "bg-purple-500/20 text-purple-400 border-purple-500/30";
}

// Recursive component to render a tree node
function TreeView({ node, pathPrefix = "" }: { node: TreeNode; pathPrefix?: string }) {
  const [isOpen, setIsOpen] = useState(true);

  if (node.type === "file") {
    return (
      <div className="flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-muted/50 text-sm group transition-colors">
        <FileCode2 className="w-4 h-4 text-muted-foreground shrink-0" />
        <span className="text-foreground/90 truncate flex-1">{node.name}</span>
        {node.language && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wider font-medium ${getLanguageColor(node.language)}`}>
            {node.language}
          </span>
        )}
      </div>
    );
  }

  // Directory
  const childrenList = Object.values(node.children || {}).sort((a, b) => {
    // Directories first
    if (a.type !== b.type) return a.type === "dir" ? -1 : 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="flex flex-col">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-1.5 py-1.5 px-2 rounded-md hover:bg-muted/50 text-sm text-foreground/90 transition-colors w-full text-left"
      >
        {isOpen ? <ChevronDown className="w-3.5 h-3.5 text-muted-foreground" /> : <ChevronRight className="w-3.5 h-3.5 text-muted-foreground" />}
        {isOpen ? <FolderOpen className="w-4 h-4 text-blue-400 shrink-0" /> : <Folder className="w-4 h-4 text-blue-400 shrink-0" />}
        <span className="font-medium truncate">{node.name}</span>
      </button>
      
      {isOpen && childrenList.length > 0 && (
        <div className="ml-3 pl-2 border-l border-border/50 flex flex-col gap-0.5">
          {childrenList.map((child) => (
            <TreeView key={`${pathPrefix}/${child.name}`} node={child} pathPrefix={`${pathPrefix}/${node.name}`} />
          ))}
        </div>
      )}
    </div>
  );
}

export function FileExplorer({ repoId, repoName }: { repoId: string; repoName: string }) {
  const [tree, setTree] = useState<TreeNode | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchGraph() {
      try {
        const res = await fetch(`http://localhost:8000/repos/${repoId}/graph`);
        if (!res.ok) throw new Error("Failed to fetch graph");
        const data = await res.json();
        
        // Build tree
        const root: TreeNode = { name: repoName, type: "dir", children: {} };
        
        data.nodes.forEach((file: FileNode) => {
          const parts = file.path.split("/");
          let current = root;
          
          for (let i = 0; i < parts.length; i++) {
            const part = parts[i];
            const isFile = i === parts.length - 1;
            
            if (!current.children) current.children = {};
            
            if (!current.children[part]) {
              current.children[part] = {
                name: part,
                type: isFile ? "file" : "dir",
                language: isFile ? file.language : undefined,
                children: isFile ? undefined : {},
              };
            }
            current = current.children[part];
          }
        });
        
        setTree(root);
      } catch (err) {
        console.error("Failed to build file tree", err);
      } finally {
        setLoading(false);
      }
    }
    fetchGraph();
  }, [repoId, repoName]);

  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center text-muted-foreground">
        Loading architecture...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-background/50 border border-border/50 rounded-2xl overflow-hidden backdrop-blur-xl">
      <div className="p-4 border-b border-border/50 bg-muted/20">
        <h3 className="font-semibold text-foreground flex items-center gap-2">
          <Folder className="w-4 h-4 text-primary" />
          Project Architecture
        </h3>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {tree && <TreeView node={tree} />}
      </div>
    </div>
  );
}
