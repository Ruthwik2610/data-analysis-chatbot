import type { Source, Connector, ChatSummary, SSEEvent, UploadResponse, MCPConnector, Project, ProjectFile } from "./types";

const BASE = process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const h: Record<string, string> = { ...(extra || {}) };
  if (API_KEY) h["Authorization"] = `Bearer ${API_KEY}`;
  return h;
}

async function jpost<T>(path: string, body: any): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error((await res.text()) || `${res.status}`);
  return res.json();
}

async function jget<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

async function jdelete(path: string): Promise<void> {
  const res = await fetch(`${BASE}${path}`, { method: "DELETE", headers: authHeaders() });
  if (!res.ok) throw new Error(`${res.status}`);
}

export const api = {
  health: () => jget<{ status: string }>("/health"),

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
      if (API_KEY) xhr.setRequestHeader("Authorization", `Bearer ${API_KEY}`);
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable && onProgress) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          resolve(xhr.response);
        } else {
          const detail = xhr.response?.detail || xhr.statusText || `${xhr.status}`;
          reject(new Error(typeof detail === "string" ? detail : JSON.stringify(detail)));
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
  resolvePending: (upload_id: string, value: string) =>
    jpost<Source>("/sources/resolve_pending", { upload_id, value }),
  attachAPI: (url: string, auth: string | null, save_connector: boolean) =>
    jpost<Source>("/sources/api", { url, auth, ingest: "direct", save_connector }),
  deleteSource: (id: string) => jdelete(`/sources/${id}`),
  activateSource: (id: string) => jpost(`/sources/${id}/activate`, {}),

  listChats: () => jget<ChatSummary[]>("/chats"),
  getChat: (id: string) => jget<{ id: string; title: string; messages: any[]; project_id: string | null }>(`/chats/${id}`),
  deleteChat: (id: string) => jdelete(`/chats/${id}`),

  listConnectors: () => jget<Connector[]>("/connectors"),
  deleteConnector: (id: string) => jdelete(`/connectors/${id}`),
  useConnector: (id: string) => jpost<Source>(`/connectors/${id}/use`, {}),

  listMCPConnectors: () => jget<MCPConnector[]>("/mcp/connectors"),
  addMCPConnector: (url: string, name?: string, options?: { scope?: "global" | "project"; project_id?: string | null }) =>
    jpost<MCPConnector>("/mcp/connectors", { url, name, ...(options || {}) }),
  updateMCPConnector: (id: string, body: { url?: string; name?: string }) =>
    fetch(`${BASE}/mcp/connectors/${id}`, {
      method: "PUT",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    }).then(async (r) => {
      if (!r.ok) throw new Error((await r.text()) || `${r.status}`);
      return r.json() as Promise<MCPConnector>;
    }),
  removeMCPConnector: (id: string) => jdelete(`/mcp/connectors/${id}`),
  attachExcelMCP: (path: string, sheet?: string) =>
    jpost<MCPConnector>("/mcp/excel", { path, sheet: sheet || null }),

  listProjects: () => jget<Project[]>("/projects"),
  createProject: (title: string) => jpost<Project>("/projects", { title }),
  getProject: (id: string) => jget<Project>(`/projects/${id}`),
  deleteProject: (id: string) => jdelete(`/projects/${id}`),
  addProjectFile: (projectId: string, filePath?: string, sheet?: string, sourceId?: string) =>
    jpost<ProjectFile>(`/projects/${projectId}/files`, { file_path: filePath, sheet, source_id: sourceId }),
  removeProjectFile: (projectId: string, fileId: string) =>
    jdelete(`/projects/${projectId}/files/${fileId}`),
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
      if (!r.ok) throw new Error(`${r.status}`);
      return r.json();
    }),
};

export async function* streamQuery(
  body: { chat_id: string | null; question: string; source_ids?: string[]; project_id?: string | null },
  signal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${BASE}/query`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json", Accept: "text/event-stream" }),
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const err = await res.text().catch(() => "");
    throw new Error(err || `${res.status}`);
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
      if (ev) yield ev as SSEEvent;
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
