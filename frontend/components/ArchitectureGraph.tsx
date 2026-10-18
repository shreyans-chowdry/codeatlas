"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import { ReactFlow, Controls, Background, useNodesState, useEdgesState, Node, Edge, MarkerType } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { Loader2, GitGraph } from "lucide-react";
import type { GraphData } from "@/lib/api";
import type { OpenFileRequest } from "@/components/FileViewer";
import { useTheme, type ResolvedTheme } from "@/lib/theme";

const NODE_W = 220;
const NODE_H = 52;

// Per-directory accent colors, tuned for each theme. Inline styles are used because
// React Flow's own (unlayered) node CSS would override Tailwind utility classes.
const PALETTE: Record<ResolvedTheme, { border: string; background: string; color: string }[]> = {
  dark: [
    { border: "#3b82f6", background: "rgba(59,130,246,0.12)", color: "#bfdbfe" },
    { border: "#a855f7", background: "rgba(168,85,247,0.12)", color: "#e9d5ff" },
    { border: "#22c55e", background: "rgba(34,197,94,0.12)", color: "#bbf7d0" },
    { border: "#f59e0b", background: "rgba(245,158,11,0.12)", color: "#fde68a" },
    { border: "#f43f5e", background: "rgba(244,63,94,0.12)", color: "#fecdd3" },
    { border: "#06b6d4", background: "rgba(6,182,212,0.12)", color: "#a5f3fc" },
  ],
  light: [
    { border: "#3b82f6", background: "#eff6ff", color: "#1e3a8a" },
    { border: "#a855f7", background: "#faf5ff", color: "#581c87" },
    { border: "#22c55e", background: "#f0fdf4", color: "#14532d" },
    { border: "#f59e0b", background: "#fffbeb", color: "#78350f" },
    { border: "#f43f5e", background: "#fff1f2", color: "#881337" },
    { border: "#06b6d4", background: "#ecfeff", color: "#164e63" },
  ],
};

const EDGE = {
  dark: { idle: "#52525b", grid: "#27272a", out: "#22d3ee", in: "#fb923c" },
  light: { idle: "#a1a1aa", grid: "#dcdce1", out: "#0891b2", in: "#ea580c" },
};

function dirIndex(path: string) {
  const parts = path.split("/");
  const topDir = parts.length > 1 ? parts[0] : "root";
  let hash = 0;
  for (let i = 0; i < topDir.length; i++) hash = topDir.charCodeAt(i) + ((hash << 5) - hash);
  return Math.abs(hash) % PALETTE.dark.length;
}

/**
 * Connected files are laid out top-to-bottom with dagre (the pane is tall and
 * narrow). Files with no internal imports are packed into a grid underneath,
 * instead of one very long row.
 */
function layout(nodes: Node[], edges: Edge[]): Node[] {
  const connected = new Set<string>();
  edges.forEach((e) => {
    connected.add(e.source);
    connected.add(e.target);
  });

  const g = new dagre.graphlib.Graph();
  g.setDefaultEdgeLabel(() => ({}));
  g.setGraph({ rankdir: "TB", nodesep: 24, ranksep: 70, marginx: 10, marginy: 10 });
  nodes.filter((n) => connected.has(n.id)).forEach((n) => g.setNode(n.id, { width: NODE_W, height: NODE_H }));
  edges.forEach((e) => g.setEdge(e.source, e.target));
  dagre.layout(g);

  let maxY = 0;
  let minX = Infinity;
  let maxX = 0;
  const positioned = new Map<string, { x: number; y: number }>();
  nodes.forEach((n) => {
    if (!connected.has(n.id)) return;
    const p = g.node(n.id);
    const pos = { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 };
    positioned.set(n.id, pos);
    maxY = Math.max(maxY, pos.y + NODE_H);
    minX = Math.min(minX, pos.x);
    maxX = Math.max(maxX, pos.x + NODE_W);
  });
  if (!positioned.size) {
    minX = 0;
    maxX = NODE_W * 3;
  }

  const isolated = nodes.filter((n) => !connected.has(n.id));
  const cols = Math.max(2, Math.min(3, Math.floor((maxX - minX + 24) / (NODE_W + 24)) || 2));
  const startY = positioned.size ? maxY + 90 : 0;
  isolated.forEach((n, i) => {
    positioned.set(n.id, {
      x: minX + (i % cols) * (NODE_W + 24),
      y: startY + Math.floor(i / cols) * (NODE_H + 20),
    });
  });

  return nodes.map((n) => ({ ...n, position: positioned.get(n.id)! }));
}

export function ArchitectureGraph({
  graph,
  onOpenFile,
}: {
  graph: GraphData | null;
  onOpenFile: (r: OpenFileRequest) => void;
}) {
  const { resolved: theme } = useTheme();
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  const stats = { nodeCount: graph?.nodes.length ?? 0, edgeCount: graph?.edges.length ?? 0 };

  useEffect(() => {
    if (!graph) return;

    const baseNodes: Node[] = graph.nodes.map((n) => {
      const parts = n.path.split("/");
      const parent = parts.length > 1 ? parts.slice(-3, -1).join("/") : "root";
      return {
        id: n.id,
        position: { x: 0, y: 0 },
        data: {
          label: (
            <div className="flex flex-col items-start w-full min-w-0 text-left" title={n.path}>
              <span className="text-[10px] opacity-70 truncate max-w-full leading-tight">{parent}</span>
              <span className="text-[13px] font-semibold truncate max-w-full leading-snug">{parts[parts.length - 1]}</span>
            </div>
          ),
          path: n.path,
          dir: dirIndex(n.path),
        },
      };
    });

    const baseEdges: Edge[] = graph.edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      type: "default",
    }));

    setNodes(layout(baseNodes, baseEdges));
    setEdges(baseEdges);
  }, [graph, setNodes, setEdges]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId((prev) => (prev === node.id ? null : node.id));
  }, []);

  const onNodeDoubleClick = useCallback(
    (_: React.MouseEvent, node: Node) => onOpenFile({ fileId: node.id, path: (node.data as { path?: string }).path }),
    [onOpenFile]
  );

  const onPaneClick = useCallback(() => setSelectedNodeId(null), []);

  const highlighted = useMemo(() => {
    const set = new Set<string>();
    if (!selectedNodeId) return set;
    set.add(selectedNodeId);
    edges.forEach((e) => {
      if (e.source === selectedNodeId) set.add(e.target);
      if (e.target === selectedNodeId) set.add(e.source);
    });
    return set;
  }, [selectedNodeId, edges]);

  const styledNodes = useMemo(
    () =>
      nodes.map((n) => {
        const c = PALETTE[theme][(n.data as { dir: number }).dir];
        const dim = selectedNodeId !== null && !highlighted.has(n.id);
        const selected = n.id === selectedNodeId;
        return {
          ...n,
          style: {
            width: NODE_W,
            height: NODE_H,
            border: `${selected ? 2 : 1.5}px solid ${c.border}`,
            background: c.background,
            color: c.color,
            borderRadius: 10,
            padding: "7px 10px",
            opacity: dim ? 0.18 : 1,
            boxShadow: selected ? `0 0 0 4px ${c.border}33` : "none",
            transition: "opacity 0.25s, box-shadow 0.25s",
          },
        };
      }),
    [nodes, theme, selectedNodeId, highlighted]
  );

  const styledEdges = useMemo(() => {
    const p = EDGE[theme];
    return edges.map((e) => {
      let color = p.idle;
      let opacity = 1;
      let width = 1.25;
      let animated = false;
      if (selectedNodeId) {
        if (e.source === selectedNodeId) [color, width, animated] = [p.out, 2, true];
        else if (e.target === selectedNodeId) [color, width, animated] = [p.in, 2, true];
        else opacity = 0.08;
      }
      return {
        ...e,
        animated,
        style: { stroke: color, strokeWidth: width, opacity, transition: "opacity 0.25s" },
        markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
      };
    });
  }, [edges, selectedNodeId, theme]);

  if (!graph) {
    return (
      <div className="w-full h-full flex items-center justify-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        Mapping dependencies...
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full h-full overflow-hidden relative">
      {/* HUD */}
      <div className="absolute top-3 left-3 z-10 bg-surface/95 border border-border p-3 rounded-xl shadow-sm max-w-[240px]">
        <h3 className="text-sm font-semibold flex items-center gap-2 mb-1.5">
          <GitGraph className="w-4 h-4 text-primary" />
          Architecture Graph
        </h3>
        <div className="text-xs text-muted-foreground mb-2 flex gap-3">
          <span>
            <strong className="text-foreground">{stats.nodeCount}</strong> files
          </span>
          <span>
            <strong className="text-foreground">{stats.edgeCount}</strong> imports
          </span>
        </div>
        {selectedNodeId ? (
          <div className="flex flex-col gap-1 text-[11px] text-muted-foreground">
            <div className="flex items-center gap-2">
              <span className="w-4 h-0.5 rounded" style={{ background: EDGE[theme].in }} /> Imported by (dependents)
            </div>
            <div className="flex items-center gap-2">
              <span className="w-4 h-0.5 rounded" style={{ background: EDGE[theme].out }} /> Imports (dependencies)
            </div>
          </div>
        ) : (
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Click a file to trace its imports. Double-click to open it.
          </p>
        )}
      </div>

      {stats.nodeCount === 0 ? (
        <div className="flex-1 flex items-center justify-center text-sm text-muted-foreground p-6 text-center">
          No source files to graph.
        </div>
      ) : (
        <div className="w-full h-full flex-1">
          <ReactFlow
            nodes={styledNodes}
            edges={styledEdges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={onNodeClick}
            onNodeDoubleClick={onNodeDoubleClick}
            onPaneClick={onPaneClick}
            zoomOnDoubleClick={false}
            nodesConnectable={false}
            colorMode={theme}
            fitView
            fitViewOptions={{ padding: 0.12, maxZoom: 1, minZoom: 0.5 }}
            minZoom={0.1}
            attributionPosition="bottom-right"
          >
            <Background color={EDGE[theme].grid} gap={18} size={1} />
            <Controls showInteractive={false} position="bottom-left" />
          </ReactFlow>
        </div>
      )}
    </div>
  );
}
