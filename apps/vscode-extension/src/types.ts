export interface Position { line: number; byte_column: number }
export interface Finding {
  rule_id: string; title: string; severity: string; path: string; language: string | null;
  start: Position | null; end: Position | null; evidence: string; explanation: string;
  affected_paths?: string[];
}
export interface GraphNode {
  id: string; path: string; directory: string; language: string | null;
  status: string; cst?: { nodes: number; diagnostics: unknown[] };
}
export interface GraphEdge { id: string; source: string; target: string; kind: string; specifier: string | null }
export interface GraphReference { id: string; source: string; status: string; specifier: string | null }
export interface GraphSnapshot {
  root: string; nodes: GraphNode[]; edges: GraphEdge[]; references: GraphReference[];
  directories: { path: string; parent: string | null; direct_files: string[] }[];
  issues: unknown[];
}
export interface AnalysisResult {
  request_id: string | number; workspace_id: string; version: number; status: string;
  baseline?: { kind: 'git'; ref: string; commit: string } | { kind: 'directory'; path: string } | null;
  coverage: Record<string, string>;
  findings: Finding[];
  issues: unknown[];
  changes: { added: string[]; modified: string[]; removed: string[]; renamed: { from_path: string; to_path: string }[] };
  metrics: { files: number; parsed_files: number; reused_files: number; re_resolved_files: number; findings: number };
}
