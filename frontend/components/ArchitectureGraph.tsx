"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  useNodesState,
  useEdgesState,
  Node,
  Edge,
  MarkerType,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { Loader2, GitGraph } from "lucide-react";

interface GraphData {
  nodes: { id: string; path: string; language: string | null }[];
  edges: { id: string; source: string; target: string; type: string }[];
}

const nodeWidth = 250;
const nodeHeight = 50;

// Group colors based on top-level directory
const DIR_COLORS = [
  "border-blue-500 bg-blue-500/10 text-blue-300",
  "border-purple-500 bg-purple-500/10 text-purple-300",
  "border-green-500 bg-green-500/10 text-green-300",
  "border-amber-500 bg-amber-500/10 text-amber-300",
  "border-rose-500 bg-rose-500/10 text-rose-300",
  "border-cyan-500 bg-cyan-500/10 text-cyan-300",
];

const getDirColorClass = (path: string) => {
  const parts = path.split("/");
  const topDir = parts.length > 1 ? parts[0] : "root";
  let hash = 0;
  for (let i = 0; i < topDir.length; i++) {
    hash = topDir.charCodeAt(i) + ((hash << 5) - hash);
  }
  return DIR_COLORS[Math.abs(hash) % DIR_COLORS.length];
};

const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = "LR") => {
  const dagreGraph = new dagre.graphlib.Graph();
  dagreGraph.setDefaultEdgeLabel(() => ({}));
  
  const isHorizontal = direction === "LR";
  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const newNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    // We are shifting the dagre node position (anchor=center center) to the top left
    // so it matches the React Flow node anchor point (top left).
    return {
      ...node,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
    };
  });

  return { nodes: newNodes, edges };
};

export function ArchitectureGraph({ repoId }: { repoId: string }) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const [loading, setLoading] = useState(true);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  
  const [stats, setStats] = useState({ nodeCount: 0, edgeCount: 0 });

  useEffect(() => {
    async function fetchGraph() {
      try {
        const res = await fetch(`http://localhost:8000/repos/${repoId}/graph`);
        if (!res.ok) throw new Error("Failed to fetch graph");
        const data: GraphData = await res.json();
        
        setStats({ nodeCount: data.nodes.length, edgeCount: data.edges.length });

        const initialNodes: Node[] = data.nodes.map((n) => {
          const colorClass = getDirColorClass(n.path);
          const topDir = n.path.split("/").length > 1 ? n.path.split("/")[0] : "root";
          
          return {
            id: n.id,
            position: { x: 0, y: 0 },
            data: { 
              label: (
                <div className="flex flex-col items-start truncate w-full">
                  <span className="text-[10px] opacity-70 truncate max-w-full">{topDir}</span>
                  <span className="text-sm font-semibold truncate max-w-full" title={n.path}>
                    {n.path.split("/").pop()}
                  </span>
                </div>
              ),
              path: n.path,
              dirClass: colorClass
            },
            className: `w-[250px] border-2 rounded-lg p-2 ${colorClass} transition-opacity duration-300`,
          };
        });

        const initialEdges: Edge[] = data.edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          type: "smoothstep",
          markerEnd: {
            type: MarkerType.ArrowClosed,
            color: "#52525b", // zinc-600
          },
          style: { stroke: "#52525b", strokeWidth: 1.5, transition: "stroke 0.3s, opacity 0.3s" },
          animated: false,
        }));

        const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
          initialNodes,
          initialEdges,
          "LR"
        );

        setNodes(layoutedNodes);
        setEdges(layoutedEdges);
      } catch (err) {
        console.error("Failed to build graph", err);
      } finally {
        setLoading(false);
      }
    }
    fetchGraph();
  }, [repoId, setNodes, setEdges]);

  // Handle interaction (click to highlight dependencies/dependents)
  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setSelectedNodeId((prev) => (prev === node.id ? null : node.id));
  }, []);

  const onPaneClick = useCallback(() => {
    setSelectedNodeId(null);
  }, []);

  // Compute highlighted state dynamically
  const highlightedNodes = useMemo(() => {
    if (!selectedNodeId) return new Set<string>();
    const highlighted = new Set<string>();
    highlighted.add(selectedNodeId);
    edges.forEach((e) => {
      if (e.source === selectedNodeId) highlighted.add(e.target);
      if (e.target === selectedNodeId) highlighted.add(e.source);
    });
    return highlighted;
  }, [selectedNodeId, edges]);

  const styledNodes = useMemo(() => {
    if (!selectedNodeId) {
      // Reset
      return nodes.map((n) => ({ ...n, style: { opacity: 1 } }));
    }
    return nodes.map((n) => ({
      ...n,
      style: { opacity: highlightedNodes.has(n.id) ? 1 : 0.2 },
    }));
  }, [nodes, selectedNodeId, highlightedNodes]);

  const styledEdges = useMemo(() => {
    if (!selectedNodeId) {
      // Reset
      return edges.map((e) => ({
        ...e,
        style: { ...e.style, stroke: "#52525b", opacity: 1 },
        animated: false,
        markerEnd: { type: MarkerType.ArrowClosed, color: "#52525b" },
      }));
    }
    
    return edges.map((e) => {
      const isOutgoing = e.source === selectedNodeId; // The clicked file imports something
      const isIncoming = e.target === selectedNodeId; // The clicked file is imported by something

      if (isOutgoing) {
        return {
          ...e,
          style: { stroke: "#06b6d4", strokeWidth: 2, opacity: 1 }, // Cyan for outgoing
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed, color: "#06b6d4" },
        };
      } else if (isIncoming) {
        return {
          ...e,
          style: { stroke: "#f97316", strokeWidth: 2, opacity: 1 }, // Orange for incoming
          animated: true,
          markerEnd: { type: MarkerType.ArrowClosed, color: "#f97316" },
        };
      } else {
        return {
          ...e,
          style: { stroke: "#52525b", opacity: 0.1 },
          animated: false,
          markerEnd: { type: MarkerType.ArrowClosed, color: "#52525b" },
        };
      }
    });
  }, [edges, selectedNodeId]);


  if (loading) {
    return (
      <div className="w-full h-full flex items-center justify-center bg-background/50 border border-border/50 rounded-2xl">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Loader2 className="w-4 h-4 animate-spin" />
          Mapping dependencies...
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col w-full h-full bg-background/50 border border-border/50 rounded-2xl overflow-hidden backdrop-blur-xl relative group">
      {/* HUD Layer */}
      <div className="absolute top-4 left-4 z-10 bg-background/80 backdrop-blur border border-border/50 p-3 rounded-lg shadow-lg">
        <h3 className="text-sm font-semibold flex items-center gap-2 mb-2">
          <GitGraph className="w-4 h-4 text-primary" />
          Architecture Graph
        </h3>
        <div className="text-xs text-muted-foreground mb-3 flex gap-4">
          <span><strong className="text-foreground">{stats.nodeCount}</strong> files</span>
          <span><strong className="text-foreground">{stats.edgeCount}</strong> imports</span>
        </div>
        
        {/* Legend */}
        {selectedNodeId ? (
          <div className="flex flex-col gap-1 text-[10px] uppercase tracking-wider font-semibold">
            <div className="flex items-center gap-2">
              <div className="w-3 h-0.5 bg-[#f97316]" /> Imported by (dependents)
            </div>
            <div className="flex items-center gap-2">
              <div className="w-3 h-0.5 bg-[#06b6d4]" /> Imports (dependencies)
            </div>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground italic max-w-[200px]">
            Click a file to highlight its dependencies and dependents.
          </div>
        )}
      </div>

      {/* Graph Area */}
      <div className="w-full h-full flex-1">
        <ReactFlow
          nodes={styledNodes}
          edges={styledEdges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onNodeClick={onNodeClick}
          onPaneClick={onPaneClick}
          fitView
          attributionPosition="bottom-right"
          minZoom={0.1}
        >
          <Background color="#27272a" gap={16} size={1} />
          <Controls className="!bg-background !border-border !fill-foreground" />
        </ReactFlow>
      </div>
    </div>
  );
}
