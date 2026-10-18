"use client";

import { useMemo, useState } from "react";
import { Folder, FolderOpen, FileCode2, ChevronRight, ChevronDown, Search } from "lucide-react";
import type { GraphData } from "@/lib/api";
import type { OpenFileRequest } from "@/components/FileViewer";

// Tree structure for rendering
interface TreeNode {
  name: string;
  type: "file" | "dir";
  id?: string;
  path?: string;
  language?: string | null;
  children?: Record<string, TreeNode>;
}

// Map languages to aesthetic Tailwind colors
const LANGUAGE_COLORS: Record<string, string> = {
  python: "bg-green-500/10 text-green-700 border-green-600/25 dark:bg-green-500/15 dark:text-green-400 dark:border-green-500/30",
  typescript: "bg-blue-500/10 text-blue-700 border-blue-600/25 dark:bg-blue-500/15 dark:text-blue-400 dark:border-blue-500/30",
  javascript: "bg-yellow-500/15 text-yellow-800 border-yellow-600/30 dark:bg-yellow-500/15 dark:text-yellow-400 dark:border-yellow-500/30",
  go: "bg-cyan-500/10 text-cyan-700 border-cyan-600/25 dark:bg-cyan-500/15 dark:text-cyan-400 dark:border-cyan-500/30",
  rust: "bg-orange-500/10 text-orange-700 border-orange-600/25 dark:bg-orange-500/15 dark:text-orange-400 dark:border-orange-500/30",
  java: "bg-red-500/10 text-red-700 border-red-600/25 dark:bg-red-500/15 dark:text-red-400 dark:border-red-500/30",
};

function getLanguageColor(lang: string | null | undefined) {
  if (!lang) return "bg-muted text-muted-foreground border-border";
  return (
    LANGUAGE_COLORS[lang.toLowerCase()] ||
    "bg-purple-500/10 text-purple-700 border-purple-600/25 dark:bg-purple-500/15 dark:text-purple-400 dark:border-purple-500/30"
  );
}

// Recursive component to render a tree node
function TreeView({
  node,
  pathPrefix = "",
  onOpenFile,
  defaultOpen = true,
}: {
  node: TreeNode;
  pathPrefix?: string;
  onOpenFile: (r: OpenFileRequest) => void;
  defaultOpen?: boolean;
}) {
  const [isOpen, setIsOpen] = useState(defaultOpen);

  if (node.type === "file") {
    return (
      <button
        onClick={() => node.id && onOpenFile({ fileId: node.id, path: node.path })}
        className="flex items-center gap-2 py-1.5 px-2 rounded-md hover:bg-muted/50 text-sm group transition-colors w-full text-left"
        title={node.path}
      >
        <FileCode2 className="w-4 h-4 text-muted-foreground shrink-0" />
        <span className="text-foreground/90 truncate flex-1">{node.name}</span>
        {node.language && (
          <span className={`text-[10px] px-1.5 py-0.5 rounded border uppercase tracking-wider font-medium ${getLanguageColor(node.language)}`}>
            {node.language}
          </span>
        )}
      </button>
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
        {isOpen ? <FolderOpen className="w-4 h-4 text-primary shrink-0" /> : <Folder className="w-4 h-4 text-primary shrink-0" />}
        <span className="font-medium truncate">{node.name}</span>
      </button>
      
      {isOpen && childrenList.length > 0 && (
        <div className="ml-3 pl-2 border-l border-border flex flex-col gap-0.5">
          {childrenList.map((child) => (
            <TreeView
              key={`${pathPrefix}/${child.name}`}
              node={child}
              pathPrefix={`${pathPrefix}/${node.name}`}
              onOpenFile={onOpenFile}
              defaultOpen={defaultOpen}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function buildTree(repoName: string, files: GraphData["nodes"]): TreeNode {
  const root: TreeNode = { name: repoName, type: "dir", children: {} };
  files.forEach((file) => {
    const parts = file.path.split("/");
    let current = root;
    parts.forEach((part, i) => {
      const isFile = i === parts.length - 1;
      if (!current.children) current.children = {};
      if (!current.children[part]) {
        current.children[part] = {
          name: part,
          type: isFile ? "file" : "dir",
          id: isFile ? file.id : undefined,
          path: isFile ? file.path : undefined,
          language: isFile ? file.language : undefined,
          children: isFile ? undefined : {},
        };
      }
      current = current.children[part];
    });
  });
  return root;
}

export function FileExplorer({
  repoName,
  graph,
  onOpenFile,
}: {
  repoName: string;
  graph: GraphData | null;
  onOpenFile: (r: OpenFileRequest) => void;
}) {
  const [filter, setFilter] = useState("");

  const tree = useMemo(() => {
    if (!graph) return null;
    const q = filter.trim().toLowerCase();
    const files = q ? graph.nodes.filter((n) => n.path.toLowerCase().includes(q)) : graph.nodes;
    return buildTree(repoName, files);
  }, [graph, repoName, filter]);

  if (!graph) {
    return (
      <div className="w-full h-full flex items-center justify-center text-muted-foreground text-sm">
        Loading files...
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="p-3 border-b border-border">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={`Filter ${graph.nodes.length} files…`}
            className="w-full pl-8 pr-3 py-1.5 text-sm rounded-lg bg-background border border-border focus:outline-none focus:ring-2 focus:ring-primary/40"
          />
        </div>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {tree && <TreeView key={filter} node={tree} onOpenFile={onOpenFile} />}
        {graph.nodes.length === 0 && (
          <p className="text-sm text-muted-foreground p-2">No supported source files were found in this repository.</p>
        )}
      </div>
    </div>
  );
}
