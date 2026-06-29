"use client";

import type { ReactNode } from "react";
import { CheckCircle2, Database, Eye, Plug, RefreshCw, Table2, Trash2, X } from "lucide-react";
import { displaySourceName } from "@/lib/displayNames";
import type { Connector, MCPConnector, Source } from "@/lib/types";

interface SourcePreviewData {
  name: string;
  kind: string;
  rows: number;
  columns: string[];
  preview_rows: any[][];
  schema: any[];
}

interface SourcesPanelProps {
  open: boolean;
  sources: Source[];
  selectedSourceIds: string[];
  selectedSourceId: string | null;
  sourcePreviewData: SourcePreviewData | null;
  sourcePreviewLoading: boolean;
  mcpConnectors?: MCPConnector[];
  apiConnectors?: Connector[];
  usingConnectorId?: string | null;
  onOpenSource: (sourceId: string) => void;
  onToggleSource: (sourceId: string) => void;
  onDeleteSource: (sourceId: string) => void;
  onUseConnector?: (connectorId: string) => void;
  onDeleteConnector?: (connectorId: string) => void;
  onRetryMCPConnector?: (connectorId: string) => void;
  retryingMcpConnectorId?: string | null;
  onCloseSourcePreview: () => void;
  onClose: () => void;
}

export function SourcesPanel({
  open,
  sources,
  selectedSourceIds,
  selectedSourceId,
  sourcePreviewData,
  sourcePreviewLoading,
  mcpConnectors = [],
  apiConnectors = [],
  usingConnectorId = null,
  onOpenSource,
  onToggleSource,
  onDeleteSource,
  onUseConnector,
  onDeleteConnector,
  onRetryMCPConnector,
  retryingMcpConnectorId = null,
  onCloseSourcePreview,
  onClose,
}: SourcesPanelProps) {
  const showSourcePreview = selectedSourceId ? selectedSourceIds.includes(selectedSourceId) : false;
  const selectedCount = selectedSourceIds.filter((id) => sources.some((source) => source.id === id)).length;
  const mcpSources = sources.filter((source) => source.kind === "mcp");
  const apiSources = sources.filter((source) => source.kind === "api");
  const fileSources = sources.filter((source) => source.kind !== "mcp" && source.kind !== "api");
  const attachedApiNames = new Set(apiSources.map((source) => source.name));
  const representedMcpIds = new Set(
    mcpSources.map((source) => source.id.startsWith("mcp:") ? source.id.slice(4) : source.id),
  );
  const unavailableMcpConnectors = mcpConnectors.filter((connector) => !representedMcpIds.has(connector.id));
  const savedApiConnectors = apiConnectors.filter((connector) => connector.kind === "api" && !attachedApiNames.has(connector.label));
  const apiCount = apiSources.length + savedApiConnectors.length;
  const availableSummary = `${fileSources.length} files · ${apiCount} APIs · ${mcpSources.length} MCP`;

  if (!open) return null;

  return (
    <aside
      className="fixed inset-y-0 right-0 z-50 flex h-full min-h-0 w-[min(92vw,460px)] flex-shrink-0 animate-in slide-in-from-right-2 flex-col border-l shadow-2xl duration-300 xl:static xl:z-auto xl:w-[460px] xl:shadow-none"
      style={{
        background: "var(--color-background-primary)",
        borderColor: "var(--color-border-tertiary)",
      }}
      aria-label="Sources panel"
    >
      <div
        className="flex items-center justify-between gap-3 px-4 py-3.5"
        style={{
          borderBottom: "1px solid var(--color-border-tertiary)",
          background: "var(--glass-background)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
        }}
      >
        <div className="flex min-w-0 items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-[10px]" style={{ background: "var(--color-background-info)", color: "var(--color-text-info)" }}>
            <Database size={16} strokeWidth={1.8} />
          </div>
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold" style={{ color: "var(--color-text-primary)" }}>Sources</div>
            <div className="text-[11px]" style={{ color: "var(--color-text-tertiary)" }}>
              {selectedCount} active · {availableSummary}
            </div>
          </div>
        </div>
        <button
          type="button"
          aria-label="Close sources panel"
          onClick={onClose}
          className="flex h-8 w-8 items-center justify-center rounded-full"
          style={{ color: "var(--color-text-tertiary)" }}
        >
          <X size={15} strokeWidth={1.8} />
        </button>
      </div>

      <div className="px-4 py-3" style={{ borderBottom: "1px solid var(--color-border-tertiary)" }}>
        {sources.length === 0 && mcpConnectors.length === 0 && savedApiConnectors.length === 0 ? (
          <div className="rounded-[14px] border px-4 py-5 text-[13px]" style={{ borderColor: "var(--color-border-secondary)", color: "var(--color-text-tertiary)" }}>
            Uploaded and connected sources will appear here.
          </div>
        ) : (
          <div className="space-y-4">
            {(mcpSources.length > 0 || unavailableMcpConnectors.length > 0) && (
              <div className="space-y-2">
                <SectionLabel>MCP bridges</SectionLabel>
                {mcpSources.map((source) => (
                  <SourceRow
                    key={source.id}
                    source={source}
                    selected={selectedSourceIds.includes(source.id)}
                    previewing={source.id === selectedSourceId}
                    onOpen={onOpenSource}
                    onToggle={onToggleSource}
                    onDelete={onDeleteSource}
                  />
                ))}
                {unavailableMcpConnectors.map((connector) => (
                  <MCPConnectorRow
                    key={connector.id}
                    connector={connector}
                    retrying={retryingMcpConnectorId === connector.id}
                    onRetry={onRetryMCPConnector}
                  />
                ))}
              </div>
            )}

            {(apiSources.length > 0 || savedApiConnectors.length > 0) && (
              <div className="space-y-2">
                <SectionLabel>API sources</SectionLabel>
                {apiSources.map((source) => (
                  <SourceRow
                    key={source.id}
                    source={source}
                    selected={selectedSourceIds.includes(source.id)}
                    previewing={source.id === selectedSourceId}
                    onOpen={onOpenSource}
                    onToggle={onToggleSource}
                    onDelete={onDeleteSource}
                  />
                ))}
                {savedApiConnectors.map((connector) => (
                  <APIConnectorRow
                    key={connector.id}
                    connector={connector}
                    loading={usingConnectorId === connector.id}
                    onUse={onUseConnector}
                    onDelete={onDeleteConnector}
                  />
                ))}
              </div>
            )}

            {fileSources.length > 0 && (
              <div className="space-y-2">
                <SectionLabel>File sources</SectionLabel>
                {fileSources.map((source) => (
                  <SourceRow
                    key={source.id}
                    source={source}
                    selected={selectedSourceIds.includes(source.id)}
                    previewing={source.id === selectedSourceId}
                    onOpen={onOpenSource}
                    onToggle={onToggleSource}
                    onDelete={onDeleteSource}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-4 py-4 scrollbar-thin">
        {showSourcePreview ? (
          <SourcePreviewContent data={sourcePreviewData} loading={sourcePreviewLoading} onClose={onCloseSourcePreview} />
        ) : (
          <div className="rounded-[14px] border px-4 py-5 text-[13px]" style={{ borderColor: "var(--color-border-secondary)", color: "var(--color-text-tertiary)" }}>
            Select a source, then use the eye button to preview its rows.
          </div>
        )}
      </div>
    </aside>
  );
}

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div className="text-[10.5px] font-bold uppercase" style={{ color: "var(--color-text-tertiary)", letterSpacing: "0.08em" }}>
      {children}
    </div>
  );
}

function MCPConnectorRow({
  connector,
  retrying,
  onRetry,
}: {
  connector: MCPConnector;
  retrying: boolean;
  onRetry?: (connectorId: string) => void;
}) {
  const statusColor =
    connector.status === "connected"
      ? "var(--color-text-success)"
      : connector.status === "connecting"
        ? "var(--color-text-warning)"
        : "#ef4444";
  const tools = connector.tools?.length ?? 0;
  const detail =
    connector.status === "connected"
      ? `${tools.toLocaleString()} tools`
      : connector.status === "connecting"
        ? "Connecting"
        : "Needs reconnect";
  const retryDisabled = !onRetry || retrying || connector.status === "connecting";

  return (
    <div
      className="flex items-start gap-2 rounded-[10px] border px-2 py-2"
      style={{
        background: "var(--color-background-secondary)",
        borderColor: "var(--color-border-tertiary)",
      }}
    >
      <span
        aria-label={`${connector.name} ${connector.status}`}
        className="mt-1.5 h-[7px] w-[7px] flex-shrink-0 rounded-full"
        style={{ background: statusColor }}
      />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12px] font-semibold" style={{ color: "var(--color-text-primary)" }}>
          {connector.name}
        </div>
        <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px]" style={{ color: "var(--color-text-tertiary)" }}>
          <span className="uppercase">MCP</span>
          <span>·</span>
          <span style={{ color: statusColor }}>{connector.status}</span>
          <span>·</span>
          <span>{detail}</span>
        </div>
      </div>
      {connector.status === "error" && (
        <button
          type="button"
          aria-label={`Retry MCP bridge ${connector.name}`}
          disabled={retryDisabled}
          onClick={() => onRetry?.(connector.id)}
          className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[8px]"
          style={{
            color: "var(--color-text-tertiary)",
            opacity: retryDisabled ? 0.45 : 1,
          }}
          title="Retry"
        >
          <RefreshCw size={13} strokeWidth={1.7} />
        </button>
      )}
    </div>
  );
}

function APIConnectorRow({
  connector,
  loading,
  onUse,
  onDelete,
}: {
  connector: Connector;
  loading: boolean;
  onUse?: (connectorId: string) => void;
  onDelete?: (connectorId: string) => void;
}) {
  return (
    <div
      className="flex items-center gap-2 rounded-[10px] border px-2 py-2"
      style={{
        background: "var(--color-background-secondary)",
        borderColor: "var(--color-border-tertiary)",
      }}
    >
      <Plug size={14} strokeWidth={1.7} style={{ color: "var(--color-text-info)" }} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12px] font-semibold" style={{ color: "var(--color-text-primary)" }}>
          {connector.label}
        </div>
        <div className="mt-0.5 text-[10.5px] uppercase" style={{ color: "var(--color-text-tertiary)" }}>
          Saved API
        </div>
      </div>
      <button
        type="button"
        aria-label={`Use API source ${connector.label}`}
        disabled={!onUse || loading}
        onClick={() => onUse?.(connector.id)}
        className="flex h-7 flex-shrink-0 items-center rounded-[8px] px-2 text-[11px] font-semibold"
        style={{
          background: "var(--color-background-primary)",
          border: "0.5px solid var(--color-border-secondary)",
          color: "var(--color-text-secondary)",
          opacity: loading ? 0.6 : 1,
        }}
      >
        {loading ? "..." : "Use"}
      </button>
      <button
        type="button"
        aria-label={`Delete saved API source ${connector.label}`}
        disabled={!onDelete}
        onClick={() => onDelete?.(connector.id)}
        className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[8px]"
        style={{ color: "var(--color-text-tertiary)", opacity: onDelete ? 1 : 0.45 }}
      >
        <Trash2 size={13} strokeWidth={1.7} />
      </button>
    </div>
  );
}

function SourceRow({
  source,
  selected,
  previewing,
  onOpen,
  onToggle,
  onDelete,
}: {
  source: Source;
  selected: boolean;
  previewing: boolean;
  onOpen: (sourceId: string) => void;
  onToggle: (sourceId: string) => void;
  onDelete: (sourceId: string) => void;
}) {
  const name = displaySourceName(source.name);
  const detail = source.kind === "mcp" ? `${source.rows.toLocaleString()} tools` : `${source.rows.toLocaleString()} rows`;
  const canPreview = source.kind !== "mcp";
  const canDelete = source.kind !== "mcp" || source.id.startsWith("mcp:");

  return (
    <div
      className="flex items-center gap-2 rounded-[10px] border px-2 py-2"
      style={{
        background: previewing ? "var(--color-background-info)" : "var(--color-background-secondary)",
        borderColor: previewing ? "var(--color-border-info)" : "var(--color-border-tertiary)",
      }}
    >
      <button
        type="button"
        aria-label={`Toggle source ${name}`}
        onClick={() => onToggle(source.id)}
        className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full"
        style={{ color: selected ? "var(--color-text-success)" : "var(--color-text-tertiary)" }}
      >
        {selected ? (
          <CheckCircle2 aria-label={`Source selected ${name}`} role="img" size={15} strokeWidth={2.2} />
        ) : (
          <span aria-hidden className="h-[13px] w-[13px] rounded-full" style={{ border: "1px solid var(--color-border-secondary)" }} />
        )}
      </button>
      <button
        type="button"
        aria-label={`Preview source ${name}`}
        disabled={!selected || !canPreview}
        onClick={() => {
          if (selected && canPreview) onOpen(source.id);
        }}
        className="min-w-0 flex-1 text-left"
        style={{ color: "var(--color-text-secondary)", opacity: selected ? 1 : 0.72 }}
      >
        <div className="truncate text-[12px] font-semibold" style={{ color: "var(--color-text-primary)" }}>{name}</div>
        <div className="mt-0.5 flex items-center gap-1.5 text-[10.5px]" style={{ color: "var(--color-text-tertiary)" }}>
          <span className="uppercase">{source.kind}</span>
          <span>·</span>
          <span>{detail}</span>
        </div>
      </button>
      <button
        type="button"
        aria-label={`Open source preview ${name}`}
        disabled={!selected || !canPreview}
        onClick={() => {
          if (selected && canPreview) onOpen(source.id);
        }}
        className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[8px]"
        style={{ color: "var(--color-text-tertiary)", opacity: selected ? 1 : 0.45 }}
      >
        <Eye size={13} strokeWidth={1.7} />
      </button>
      {canDelete && (
        <button
          type="button"
          aria-label={`Delete source ${name}`}
          onClick={() => onDelete(source.id)}
          className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-[8px]"
          style={{ color: "var(--color-text-tertiary)" }}
        >
          <Trash2 size={13} strokeWidth={1.7} />
        </button>
      )}
    </div>
  );
}

function SourcePreviewContent({ data, loading, onClose }: { data: SourcePreviewData | null; loading: boolean; onClose: () => void }) {
  if (loading || !data) {
    return (
      <div className="space-y-3">
        {[100, 80, 90, 70, 85].map((width, index) => (
          <div key={index} className="skeleton" style={{ width: `${width}%`, height: 16, borderRadius: 4 }} />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-[14px] font-medium" style={{ color: "var(--color-text-primary)" }}>Source Preview</h2>
          <button
            type="button"
            aria-label="Close source preview"
            onClick={onClose}
            className="flex h-7 w-7 items-center justify-center rounded-full"
            style={{ color: "var(--color-text-tertiary)" }}
          >
            <X size={14} strokeWidth={1.8} />
          </button>
        </div>
        <h3 className="mt-4 text-[13px] font-medium" style={{ color: "var(--color-text-primary)" }}>
          {data.name}
        </h3>
        <div className="mt-2 flex items-center gap-2">
          <span
            style={{
              fontSize: 9,
              fontWeight: 700,
              textTransform: "uppercase",
              letterSpacing: "0.05em",
              padding: "2px 6px",
              borderRadius: 4,
              background: "var(--color-background-secondary)",
              color: "var(--color-text-secondary)",
              border: "0.5px solid var(--color-border-tertiary)",
            }}
          >
            {data.kind}
          </span>
          <span className="text-[11px]" style={{ color: "var(--color-text-tertiary)" }}>
            {data.rows.toLocaleString()} rows
          </span>
          <span className="text-[11px]" style={{ color: "var(--color-text-tertiary)" }}>
            · {data.columns.length} columns
          </span>
        </div>
      </div>

      {data.schema.length > 0 && (
        <div>
          <h4 className="mb-3 text-[11.5px] font-medium uppercase tracking-wider" style={{ color: "var(--color-text-secondary)" }}>
            Schema
          </h4>
          <div className="flex flex-wrap gap-1.5">
            {data.schema.map((col: any, index: number) => (
              <div
                key={`${col.name}-${index}`}
                className="flex items-center gap-1.5 rounded px-2 py-1 text-[11px]"
                style={{ background: "var(--color-background-secondary)", border: "0.5px solid var(--color-border-tertiary)" }}
              >
                <span style={{ color: "var(--color-text-primary)", fontWeight: 500 }}>{col.name}</span>
                <span style={{ color: "var(--color-text-tertiary)" }}>{col.type}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <h4 className="mb-3 flex items-center gap-1.5 text-[11.5px] font-medium uppercase tracking-wider" style={{ color: "var(--color-text-secondary)" }}>
          <Table2 size={13} />
          Preview (First {data.preview_rows.length} rows)
        </h4>
        <div className="overflow-x-auto rounded-[8px]" style={{ border: "0.5px solid var(--color-border-tertiary)" }}>
          <table className="w-full min-w-[500px] border-collapse text-left">
            <thead>
              <tr>
                {data.columns.map((column) => (
                  <th
                    key={column}
                    className="whitespace-nowrap px-3 py-2 text-[11px] font-medium"
                    style={{
                      background: "var(--color-background-secondary)",
                      color: "var(--color-text-secondary)",
                      borderBottom: "0.5px solid var(--color-border-tertiary)",
                    }}
                  >
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {data.preview_rows.map((row, rowIndex) => (
                <tr key={rowIndex}>
                  {row.map((cell, cellIndex) => (
                    <td
                      key={cellIndex}
                      className="max-w-[150px] truncate whitespace-nowrap px-3 py-1.5 text-[11px]"
                      style={{
                        color: "var(--color-text-primary)",
                        borderBottom: rowIndex < data.preview_rows.length - 1 ? "0.5px solid var(--color-border-tertiary)" : "none",
                      }}
                      title={String(cell)}
                    >
                      {String(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
