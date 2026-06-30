import type { Source, Connector, ChatSummary, SSEEvent, UploadResponse, MCPConnector, Project, ProjectFile, ProjectNote, ModelMode, InstructionsResponse, QueryLoopMetricsResponse, WorkbookMCPDeployment, WorkbookView, TravelIntent, TravelOffer, HotelOffer } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
const TOKEN_KEY = "datachat_user_token";
export const GENERIC_API_ERROR_MESSAGE = "Something went wrong. The error was logged for review.";
const GENERIC_THINKING_STEP = "Working on your answer";
const INTERNAL_THINKING_RE =
  /\b(?:select|with)\b[\s\S]{0,240}\b(?:from|where|join|group\s+by|order\s+by|limit)\b|\b(?:insert|update|delete|create|drop|alter)\b[\s\S]{0,160}\b(?:table|into|from|set|where)\b|\b(?:api[_-]?key|token|secret|password|credential|bearer|traceback|stack trace)\b/i;

export function getAuthToken(): string {
  if (typeof window === "undefined" || typeof localStorage?.getItem !== "function") return "";
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setAuthToken(token: string): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra || {}) };
  const token = getAuthToken();
  if (token) h["Authorization"] = `Bearer ${token}`;

  // Add admin token if present in localStorage
  if (typeof window !== "undefined" && typeof localStorage?.getItem === "function") {
    const adminToken = localStorage.getItem("datachat_admin_token");
    if (adminToken) h["x-admin-token"] = adminToken;
  }

  return h;
}

async function throwApiError(res: Response): Promise<never> {
  await res.text().catch(() => "");
  console.error("API request failed", { status: res.status, statusText: res.statusText });
  throw new Error(GENERIC_API_ERROR_MESSAGE);
}

function sanitizeStreamEvent(event: { event: string; data: any }): { event: string; data: any } {
  if (event.event !== "thinking" || typeof event.data?.step !== "string") return event;
  if (!INTERNAL_THINKING_RE.test(event.data.step)) return event;
  return { ...event, data: { ...event.data, step: GENERIC_THINKING_STEP } };
}

async function jpost<T>(path: string, body: any): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) await throwApiError(res);
  return res.json();
}

async function jget<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) await throwApiError(res);
  return res.json();
}

async function jdelete(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE", headers: authHeaders() });
  if (!res.ok) await throwApiError(res);
}

export const api = {
  health: () => jget<{ status: string }>("/health"),
  login: (email: string, password: string) => jpost<{ access_token: string; user: { id: string; email: string } }>("/auth/login", { email, password }),
  register: (email: string, password: string) => jpost<{ access_token: string; user: { id: string; email: string } }>("/auth/register", { email, password }),
  me: () => jget<{ user: { id: string; email: string } }>("/auth/me"),
  adminLogin: (password: string) => jpost<{ token: string; user_token: string; user: { id: string; email: string } }>("/admin/login", { password }),
  getAdminSession: () => jget<{ ok: boolean; role: "admin" }>("/admin/session"),
  getAdminStats: () => jget<any>("/admin/stats"),
  getHallucinations: () => jget<any[]>("/admin/hallucinations"),
  getTraces: (limit?: number) => jget<any[]>(limit ? `/admin/traces?limit=${limit}` : "/admin/traces"),
  getFeedback: (status?: string) => jget<any>(status ? `/admin/feedback?status=${encodeURIComponent(status)}` : "/admin/feedback"),
  updateFeedbackStatus: (id: string, status: string) =>
    fetch(`${BASE}/admin/feedback/${id}`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ status }),
    }).then(async (r) => {
      if (!r.ok) await throwApiError(r);
      return r.json();
    }),
  getUserAnalytics: () => jget<any>("/admin/user-analytics"),
  getQueryLoops: () => jget<QueryLoopMetricsResponse>("/admin/query-loops"),
  clearCache: () => jpost<any>("/admin/maintenance/clear-cache", {}),

  listSources: (projectId?: string | null) =>
    jget<Source[]>(projectId ? `/sources?project_id=${encodeURIComponent(projectId)}` : "/sources"),
  uploadFile: (
    file: File,
    onProgress?: (pct: number) => void,
    signal?: AbortSignal,
  ): Promise<UploadResponse> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", `${BASE}/sources/upload`);
      xhr.responseType = "json";
      const token = getAuthToken();
      if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(xhr.response);
        } else {
          console.error("Upload request failed", { status: xhr.status, statusText: xhr.statusText });
          reject(new Error(GENERIC_API_ERROR_MESSAGE));
        }
      };
      xhr.onerror = () => reject(new Error("Network error during upload"));
      xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
      if (signal) {
        signal.addEventListener("abort", () => xhr.abort());
      }
      const fd = new FormData();
      fd.append("file", file);
      xhr.send(fd);
    });
  },
  resolvePending: (upload_id: string, value: string | string[], options?: { publicBaseUrl?: string }) =>
    jpost<Source | { sources: Source[]; mcp_connector?: MCPConnector; mcp_deploy_error?: string }>("/sources/resolve_pending", {
      upload_id,
      value,
      public_base_url: options?.publicBaseUrl,
    }),
  getSourceInstructions: (sourceId: string) =>
    jget<InstructionsResponse>(`/sources/${sourceId}/instructions`),
  updateSourceInstructions: (sourceId: string, instructions: Record<string, any>) =>
    fetch(`${BASE}/sources/${sourceId}/instructions`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ instructions }),
    }).then(async (r) => {
      if (!r.ok) await throwApiError(r);
      return r.json() as Promise<InstructionsResponse>;
    }),
  applySourceClarifications: (sourceId: string, answers: Record<string, any>) =>
    jpost<InstructionsResponse>(`/sources/${sourceId}/clarifications`, { answers }),
  attachAPI: (url: string, auth: string | null, save_connector: boolean) =>
    jpost<Source>("/sources/api", { url, auth, ingest: "direct", save_connector }),
  deleteSource: (id: string) => jdelete(`/sources/${id}`),
  activateSource: (id: string) => jpost(`/sources/${id}/activate`, {}),
  previewSource: (id: string) => jget<{name:string;kind:string;rows:number;columns:string[];preview_rows:any[][];schema:any[]}>(`/sources/${id}/preview`),

  listChats: (projectId?: string | null) =>
    jget<ChatSummary[]>(projectId ? `/chats?project_id=${encodeURIComponent(projectId)}` : "/chats?project_id=none"),
  getChat: (id: string) => jget<{ id: string; title: string; messages: any[]; project_id: string | null; source_ids: string[]; sources: { id: string; name: string; kind: string; rows: number }[] }>(`/chats/${id}`),
  deleteChat: (id: string) => jdelete(`/chats/${id}`),

  listConnectors: () => jget<Connector[]>("/connectors"),
  deleteConnector: (id: string) => jdelete(`/connectors/${id}`),
  useConnector: (id: string) => jpost<Source>(`/connectors/${id}/use`, {}),

  listMCPConnectors: () => jget<MCPConnector[]>("/mcp/connectors"),
  addMCPConnector: (url: string, name?: string, options?: { scope?: "global" | "project"; project_id?: string | null }) =>
    jpost<MCPConnector>("/mcp/connectors", { url, name, ...(options || {}) }),
  updateMCPConnector: (id: string, body: { url?: string; name?: string; retry?: boolean }) =>
    fetch(`${BASE}/mcp/connectors/${id}`, {
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) await throwApiError(r);
      return r.json() as Promise<MCPConnector>;
    }),
  removeMCPConnector: (id: string) => jdelete(`/mcp/connectors/${id}`),
  attachExcelMCP: (path: string, sheet?: string) =>
    jpost<MCPConnector>("/mcp/excel", { path, sheet: sheet || null }),
  deployWorkbookCloudflare: (id: string, body: { public_base_url?: string; worker_name?: string }) =>
    jpost<WorkbookMCPDeployment>(`/mcp/connectors/${id}/cloudflare`, body),
  listWorkbookViews: (id: string) => jget<WorkbookView[]>(`/mcp/connectors/${id}/views`),
  createWorkbookView: (id: string, body: { name: string; sql: string }) =>
    jpost<WorkbookView>(`/mcp/connectors/${id}/views`, body),
  mergeWorkbookView: (id: string, body: { name: string; left_table: string; right_table: string; left_key: string; right_key: string; join_type?: string }) =>
    jpost<WorkbookView>(`/mcp/connectors/${id}/views/merge`, body),
  updateWorkbookView: (id: string, viewName: string, body: { sql: string }) =>
    fetch(`${BASE}/mcp/connectors/${id}/views/${encodeURIComponent(viewName)}`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) await throwApiError(r);
      return r.json() as Promise<WorkbookView>;
    }),
  deleteWorkbookView: (id: string, viewName: string) =>
    jdelete(`/mcp/connectors/${id}/views/${encodeURIComponent(viewName)}`),

  listProjects: () => jget<Project[]>("/projects"),
  createProject: (title: string) => jpost<Project>("/projects", { title }),
  getProject: (id: string) => jget<Project>(`/projects/${id}`),
  updateProject: (id: string, body: { title: string }) =>
    fetch(`${BASE}/projects/${id}`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) await throwApiError(r);
      return r.json() as Promise<Project>;
    }),
  deleteProject: (id: string) => jdelete(`/projects/${id}`),
  getProjectInstructions: (projectId: string) =>
    jget<InstructionsResponse>(`/projects/${projectId}/instructions`),
  updateProjectInstructions: (projectId: string, instructions: Record<string, any>) =>
    fetch(`${BASE}/projects/${projectId}/instructions`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ instructions }),
    }).then(async (r) => {
      if (!r.ok) await throwApiError(r);
      return r.json() as Promise<InstructionsResponse>;
    }),
  rebuildProjectProfile: (projectId: string) =>
    jpost<InstructionsResponse>(`/projects/${projectId}/profile/rebuild`, {}),
  addProjectFile: (projectId: string, filePath?: string, sheet?: string, sourceId?: string) =>
    jpost<ProjectFile>(`/projects/${projectId}/files`, { file_path: filePath, sheet, source_id: sourceId }),
  removeProjectFile: (projectId: string, fileId: string) =>
    jdelete(`/projects/${projectId}/files/${fileId}`),
  listProjectNotes: (projectId: string) => jget<ProjectNote[]>(`/projects/${projectId}/notes`),
  createProjectNote: (projectId: string, body: { title?: string; content: string; source_message_id?: string | null }) =>
    jpost<ProjectNote>(`/projects/${projectId}/notes`, body),
  deleteProjectNote: (projectId: string, noteId: string) =>
    jdelete(`/projects/${projectId}/notes/${noteId}`),
  listProjectMCP: (projectId: string) => jget<MCPConnector[]>(`/projects/${projectId}/mcp`),
  bindProjectMCP: (projectId: string, connectorId: string) =>
    jpost<{ ok: boolean }>(`/projects/${projectId}/mcp/${connectorId}`, {}),
  unbindProjectMCP: (projectId: string, connectorId: string) =>
    jdelete(`/projects/${projectId}/mcp/${connectorId}`),
  updateChatProject: (chatId: string, projectId: string | null) =>
    fetch(`${BASE}/chats/${chatId}/project`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ project_id: projectId }),
    }).then((r) => {
      if (!r.ok) return throwApiError(r);
      return r.json();
    }),
  postFeedback: (body: { chat_id?: string | null; message_id?: string | null; rating: number; comment?: string; category?: string }) =>
    jpost<{ ok: boolean }>("/feedback", body),
  saveTravelJourney: (body: {
    chat_id?: string | null;
    intent: TravelIntent;
    offer: TravelOffer;
    hotel_offer?: HotelOffer | null;
    status?: "saved" | "downloaded";
  }) => jpost<any>("/api/journeys", body),

  // Testing Gateway
  listTestSuites: () => jget<any[]>("/admin/testing/suites"),
  createTestSuite: (name: string) => jpost<any>("/admin/testing/suites", { name }),
  listTestQueries: (suiteId: string) => jget<any[]>(`/admin/testing/suites/${suiteId}/queries`),
  addTestQueriesBulk: (suiteId: string, queries: any[], queriesText?: string) => 
    jpost<any>("/admin/testing/queries/bulk", { suite_id: suiteId, queries, queries_text: queriesText }),
  startTestRun: (suiteId: string, options?: { source_ids?: string[]; project_id?: string | null; model_mode?: ModelMode }) =>
    jpost<any>("/admin/testing/runs", { suite_id: suiteId, ...(options || {}) }),
  createAutoTestSuite: (body: { name?: string; source_ids?: string[]; project_id?: string | null }) =>
    jpost<any>("/admin/testing/suites/auto", body),
  listTestRuns: (suiteId?: string) => jget<any[]>(suiteId ? `/admin/testing/runs?suite_id=${suiteId}` : "/admin/testing/runs"),
  listTestEvaluations: (runId: string) => jget<any[]>(`/admin/testing/runs/${runId}/evaluations`),
  gradeEvaluation: (evaluationId: string, grade: string, reason?: string) =>
    fetch(`${BASE}/admin/testing/evaluations/${evaluationId}`, {
      method: "PATCH",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ grade, reason }),
    }).then(r => r.json()),
};

export type StreamQueryBody = {
  chat_id: string | null;
  question: string;
  source_ids?: string[];
  project_id?: string | null;
  model_mode?: ModelMode;
  business_logic_enabled?: boolean;
};

export async function* streamQuery(
  body: StreamQueryBody,
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${BASE}/query`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json", Accept: "text/event-stream" }),
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    if (!res.ok) await throwApiError(res);
    throw new Error(GENERIC_API_ERROR_MESSAGE);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  // SSE block separator is two line endings; sse_starlette uses \r\n by default
  // so the on-the-wire delimiter is \r\n\r\n. The spec also allows \n\n and \r\r.
  const SEP = /\r\n\r\n|\n\n|\r\r/;
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let m: RegExpExecArray | null;
    while ((m = SEP.exec(buffer)) !== null) {
      const block = buffer.slice(0, m.index);
      buffer = buffer.slice(m.index + m[0].length);
      const ev = parseSSEBlock(block);
      if (ev) yield sanitizeStreamEvent(ev) as SSEEvent;
    }
  }
}

function parseSSEBlock(block: string): { event: string; data: any } | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  }
  if (!dataLines.length) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}
