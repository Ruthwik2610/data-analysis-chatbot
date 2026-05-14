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

export interface SourceMeta {
  id: string;
  name: string;
  kind: string;
  rows: number;
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
  view_type?: string;
}

export type PendingResolver =
  | "sheet_pick_mode"
  | "sheet_pick"
  | "table_pick"
  | "ingest_pick"
  | "source_clarification"
  | "connect_url"
  | "clarify_text"
  | "source_pick";

export interface Pending {
  resolver: PendingResolver;
  options: { label: string; value: string }[];
  args: Record<string, any>;
  hint?: string;
  multiSelect?: boolean;
}

export interface ModelFallbackNotice {
  kind: "model_fallback";
  from: string;
  to: string;
  reason: string;
}

export interface TravelIntent {
  origin: string | null;
  destination: string | null;
  departure_date: string | null;
  return_date: string | null;
  passengers: number;
  cabin_class: string;
  traveler_tier: string;
  budget_limit_usd: number;
  check_in_date: string | null;
  check_out_date: string | null;
  rooms: number;
  guests: number;
  wants_flights: boolean;
  wants_hotels: boolean;
}

export interface HotelOffer {
  hotel_id: string;
  name: string;
  address: string;
  star_rating: number | null;
  review_score: number | null;
  photo_url: string;
  price_per_night: number;
  total_price: number;
  currency: string;
  check_in_date: string;
  check_out_date: string;
  rooms: number;
  guests: number;
  redirect_url: string;
  policy_compliant: boolean;
  policy_violation_reason: string | null;
  score: number;
}

export interface TravelOffer {
  offer_id: string;
  airline: string;
  airline_iata: string;
  origin: string;
  destination: string;
  departure_at: string;
  arrival_at: string;
  duration_minutes: number;
  stops: number;
  cabin_class: string;
  price_usd: number;
  currency: string;
  policy_compliant: boolean;
  policy_violation_reason: string | null;
  booking_redirect_url: string;
  expires_at: string | null;
  return_slice?: {
    origin: string;
    destination: string;
    departure_at: string;
    arrival_at: string;
    duration_minutes: number;
    stops: number;
    airline: string;
    airline_iata: string;
  } | null;
  score: number;
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
      travel_intent?: TravelIntent;
      travel_offers?: TravelOffer[];
      hotel_offers?: HotelOffer[];
    };

export type SSEEvent =
  | { event: "meta"; data: { chat_id: string; source: { id: string | null; name: string; kind: string; rows: number } } }
  | { event: "thinking"; data: { step: string } }
  | { event: "result"; data: ResultPayload }
  | { event: "text"; data: { delta: string } }
  | { event: "clarify"; data: { content: string; message_id: string } }
  | { event: "error"; data: { message: string; detail?: string } }
  | { event: "notice"; data: ModelFallbackNotice }
  | { event: "travel_result"; data: { text: string; travel_intent: TravelIntent; travel_offers: TravelOffer[]; hotel_offers: HotelOffer[] } }
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
  cloudflare?: WorkbookMCPDeployment | null;
}

export interface WorkbookMCPDeployment {
  connector_id: string;
  worker_name: string;
  worker_url: string;
  created_at: number;
  updated_at: number;
}

export interface WorkbookView {
  id: string;
  connector_id?: string;
  name: string;
  sql: string;
  columns: string[];
  row_count: number;
  created_at?: number;
  updated_at?: number;
}

export interface QueryLoopMetricsResponse {
  summary: {
    total_queries: number;
    high_loop_queries: number;
    avg_tool_calls: number;
    avg_rounds: number;
    total_tool_errors: number;
  };
  queries: Array<{
    id: string;
    question: string;
    route: string;
    round_count: number;
    tool_call_count: number;
    tool_error_count: number;
    thinking_event_count: number;
    created_at: number;
    chat_id?: string | null;
    chat_title?: string | null;
    project_name?: string | null;
    trace_id?: string | null;
  }>;
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
    multi_select?: boolean;
  };
  mcp_connector?: MCPConnector;
  mcp_deploy_error?: string;
  clarifications?: SourceClarification[];
}
