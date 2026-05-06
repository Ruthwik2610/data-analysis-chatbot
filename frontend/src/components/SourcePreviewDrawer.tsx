import { X, Table2 } from "lucide-react";

interface SourcePreviewDrawerProps {
  open: boolean;
  onClose: () => void;
  data: {
    name: string;
    kind: string;
    rows: number;
    columns: string[];
    preview_rows: any[][];
    schema: any[];
  } | null;
  loading: boolean;
}

export function SourcePreviewDrawer({ open, onClose, data, loading }: SourcePreviewDrawerProps) {
  if (!open) return null;

  return (
    <div
      className="fixed inset-y-0 right-0 z-50 flex flex-col shadow-xl transition-transform transform translate-x-0"
      style={{
        width: 480,
        background: "var(--color-background-primary)",
        borderLeft: "0.5px solid var(--color-border-secondary)",
      }}
    >
      <div
        className="flex items-center justify-between px-5 py-4"
        style={{ borderBottom: "0.5px solid var(--color-border-tertiary)" }}
      >
        <div className="flex items-center gap-2">
          <h2 className="text-[14px] font-medium" style={{ color: "var(--color-text-primary)" }}>
            Source Preview
          </h2>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded transition-colors"
          style={{ color: "var(--color-text-secondary)" }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "var(--color-background-secondary)")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          <X size={16} strokeWidth={1.5} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin p-5 space-y-6">
        {loading || !data ? (
          <div className="space-y-3">
            {[100, 80, 90, 70, 85].map((w, i) => (
              <div
                key={i}
                className="skeleton"
                style={{ width: `${w}%`, height: 16, borderRadius: 4 }}
              />
            ))}
          </div>
        ) : (
          <>
            <div>
              <h3 className="text-[13px] font-medium mb-1" style={{ color: "var(--color-text-primary)" }}>
                {data.name}
              </h3>
              <div className="flex items-center gap-2 mt-2">
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

            {data.schema && data.schema.length > 0 && (
              <div>
                <h4 className="text-[11.5px] font-medium mb-3 uppercase tracking-wider" style={{ color: "var(--color-text-secondary)" }}>
                  Schema
                </h4>
                <div className="flex flex-wrap gap-1.5">
                  {data.schema.map((col: any, idx: number) => (
                    <div
                      key={idx}
                      className="flex items-center gap-1.5 text-[11px] px-2 py-1 rounded"
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
              <h4 className="text-[11.5px] font-medium mb-3 flex items-center gap-1.5 uppercase tracking-wider" style={{ color: "var(--color-text-secondary)" }}>
                <Table2 size={13} />
                Preview (First {data.preview_rows.length} rows)
              </h4>
              <div
                className="overflow-x-auto rounded-[8px]"
                style={{ border: "0.5px solid var(--color-border-tertiary)" }}
              >
                <table className="w-full text-left border-collapse min-w-[500px]">
                  <thead>
                    <tr>
                      {data.columns.map((col) => (
                        <th
                          key={col}
                          className="px-3 py-2 text-[11px] font-medium whitespace-nowrap"
                          style={{
                            background: "var(--color-background-secondary)",
                            color: "var(--color-text-secondary)",
                            borderBottom: "0.5px solid var(--color-border-tertiary)",
                          }}
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.preview_rows.map((row, rIdx) => (
                      <tr key={rIdx}>
                        {row.map((cell, cIdx) => (
                          <td
                            key={cIdx}
                            className="px-3 py-1.5 text-[11px] whitespace-nowrap truncate max-w-[150px]"
                            style={{
                              color: "var(--color-text-primary)",
                              borderBottom: rIdx < data.preview_rows.length - 1 ? "0.5px solid var(--color-border-tertiary)" : "none",
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
          </>
        )}
      </div>
    </div>
  );
}
