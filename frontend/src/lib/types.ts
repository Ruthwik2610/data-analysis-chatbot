export type SourceKind = "csv" | "xlsx" | "duckdb" | "api" | "json" | "pdf" | "mcp" | "multi";
export type ModelMode = "flash" | "pro";

export interface Source {
  id: string;
  name: string;
  kind: SourceKind;
  rows: number;
  active: boolean;
  loaded?: boolean;
  clarifications?: SourceClarification[];
}

export interface Connector {
  id: string;
  kind: "api" | "mcp";
  label: string;
  config: Record<string, any>;
}

export interface ChatSummary {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  project_id?: string | null;
}

export interface ProjectFile {
  id: string;
  project_id: string;
  file_path: string | null;
  source_id: string | null;
  source_name?: string | null;
  sheet_name: string | null;
  created_at: number;
}

export interface Project {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  files: ProjectFile[];
}

export interface ProjectNote {
  id: string;
  project_id: string;
  title: string;
  content: string;
  source_message_id?: string | null;
  created_at: number;
}

export interface SourceClarification {
  id: string;
  question: string;
  options: { label: string; value: string }[];
}

export interface InstructionsResponse {
  source_id?: string;
  project_id?: string;
  instructions: Record<string, any>;
  updated_at?: number;
}

export interface ResultPayload {
  title: string;
  viz: "bar" | "line" | "pie" | "card" | "table";
  elapsed_ms: number;
  sql: string;
  how: string;
  columns: string[];
  rows: any[][];
  row_count: number;
  truncated: boolean;
}

export type PendingResolver =
  | "sheet_pick"
  | "table_pick"
  | "ingest_pick"
  | "source_clarification"
  | "connect_url"
  | "clarify_text";

export interface Pending {
  resolver: PendingResolver;
  options: { label: string; value: string }[];
  args: Record<string, any>;
  hint?: string;
}

export interface ModelFallbackNotice {
  kind: "model_fallback";
  from: string;
  to: string;
  reason: string;
}

export type Message =
  | { id: string; role: "user"; content: string; created_at?: number }
  | {
      id: string;
      role: "assistant";
      content: string;
      created_at?: number;
      streaming?: boolean;
      thinking?: string | null;
      progress?: number | null;
      source?: { id: string | null; name: string; kind: string; rows: number };
      result?: ResultPayload;
      error?: boolean;
      pending?: Pending;
      resolved?: boolean;
      notice?: ModelFallbackNotice | null;
    };

export type SSEEvent =
  | { event: "meta"; data: { chat_id: string; source: { id: string | null; name: string; kind: string; rows: number } } }
  | { event: "thinking"; data: { step: string } }
  | { event: "result"; data: ResultPayload }
  | { event: "text"; data: { delta: string } }
  | { event: "clarify"; data: { content: string; message_id: string } }
  | { event: "error"; data: { message: string; detail?: string } }
  | { event: "notice"; data: ModelFallbackNotice }
  | { event: "done"; data: { message_id?: string; chat_id: string } };

export type MCPStatus = "connecting" | "connected" | "error";

export interface MCPConnector {
  id: string;
  name: string;
  url: string | null;
  status: MCPStatus;
  tools: { name: string; description?: string; input_schema?: any }[];
  last_error?: string | null;
  is_excel?: boolean;
  description?: string | null;
  generated_description?: string | null;
  description_status?: "metadata" | "generated" | string;
  scope?: "global" | "project" | string;
  project_ids?: string[];
}

export interface UploadResponse {
  // Either a finished source...
  id?: string;
  name?: string;
  kind?: SourceKind;
  rows?: number;
  active?: boolean;
  // ...or several finished sources from an archive...
  sources?: Source[];
  skipped?: { file_name: string; error: string }[];
  // ...or a pending decision
  pending?: {
    kind: "sheet_pick" | "table_pick" | "ingest_pick";
    upload_id: string;
    file_name: string;
    sheets?: string[];
    tables?: string[];
    size_mb?: number;
  };
  clarifications?: SourceClarification[];
}
