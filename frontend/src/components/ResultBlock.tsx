"use client";

import { ChevronDown, Download, Table as TableIcon, BarChart3 } from "lucide-react";
import { useMemo, useRef, useState, type RefObject } from "react";
import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";
import * as XLSX from "xlsx";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ResultPayload } from "@/lib/types";

interface ResultBlockProps {
  result: ResultPayload;
  narrative?: string | null;
}

type DisplayViz = Exclude<ResultPayload["viz"], "chart">;

const PALETTE = [
  "#6366f1", "#10b981", "#f59e0b", "#ef4444", "#0ea5e9",
  "#8b5cf6", "#84cc16", "#ec4899", "#f97316", "#14b8a6",
];

const AXIS_COLOR = "var(--color-text-tertiary)";
const GRID_COLOR = "var(--color-border-tertiary)";
const JPEG_EXPORT_TYPE = "image/jpeg";
const JPEG_EXPORT_EXTENSION = "jpg";
const JPEG_EXPORT_QUALITY = 0.95;
const JPEG_EXPORT_SCALE = 3;
const IMAGE_EXPORT_PADDING = 32;
const IMAGE_EXPORT_HEADER_HEIGHT = 76;
const IMAGE_EXPORT_MIN_CHART_WIDTH = 960;
const IMAGE_EXPORT_MIN_CHART_HEIGHT = 320;
const DEFAULT_IMAGE_EXPORT_BACKGROUND = "#ffffff";
const DEFAULT_IMAGE_EXPORT_TEXT = "#0f172a";
const DEFAULT_IMAGE_EXPORT_MUTED_TEXT = "#64748b";
const DEFAULT_IMAGE_EXPORT_GRID = "#e2e8f0";
const DEFAULT_IMAGE_EXPORT_AXIS = "#cbd5e1";
const PDF_MARGIN = 40;
const PDF_BODY_FONT_SIZE = 10.5;
const PDF_SECTION_GAP = 18;
const PDF_LINE_HEIGHT = 15;
const PDF_MUTED_TEXT = [100, 116, 139] as const;
const PDF_PRIMARY_TEXT = [15, 23, 42] as const;
const PDF_BLUE = [37, 99, 235] as const;
const PDF_INTERNAL_DETAIL_RE = /^(source|sources|model|metric|grouped by|filters|display|sql|query|provider|elapsed|tool|trace|request id)\s*:/i;

function normalizeViz(viz: ResultPayload["viz"]): DisplayViz {
  return viz === "chart" ? "bar" : viz;
}

export function ResultBlock({ result, narrative }: ResultBlockProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const [chartType, setChartType] = useState<DisplayViz>(normalizeViz(result.viz));
  const refinedResult = useMemo(() => ({ ...result, viz: chartType }), [result, chartType]);
  const shape = useMemo(() => analyze(refinedResult), [refinedResult]);
  // BI default: a time × category breakdown is most readable as a crosstab — long-format tables of 50+ rows are unreadable.
  const defaultToTable = shape.kind === "bar" && !!shape.crosstab && shape.crosstab.colsArePeriod;
  const [showTable, setShowTable] = useState(defaultToTable);
  const hasChart = shape.kind !== "table" && shape.kind !== "card";
  const hasChartControls = result.viz !== "card" && result.rows.length > 0 && shape.kind !== "table";
  const canExportChartImage = !showTable && chartType !== "table" && hasChart && result.view_type !== "timetable";

  if (shape.kind === "card" && result.view_type !== "timetable") {
    return <ScalarMetric shape={shape} />;
  }

  return (
    <div
      className="mt-2 fade-in glass"
      style={{
        borderRadius: 22,
        padding: 20,
        boxShadow: "var(--shadow-xl)",
      }}
    >
      <div className="flex items-start justify-between mb-4">
        <div className="flex flex-col gap-1.5">
          <div className="text-[10px] font-bold uppercase tracking-[0.2em]" style={{ color: "var(--color-text-tertiary)" }}>
            {result.title} · {result.row_count.toLocaleString()} rows
          </div>
        </div>
        <div className="flex items-center gap-2 mt-1">
          {hasChartControls && result.view_type !== "timetable" && (
            <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-secondary border border-tertiary">
              <span className="text-[9px] font-bold uppercase tracking-widest text-tertiary ml-1">Viz</span>
              <select
                aria-label="Chart type"
                value={chartType}
                onChange={(e) => {
                  setShowTable(false);
                  setChartType(e.target.value as DisplayViz);
                }}
                className="bg-transparent text-[10px] font-bold text-primary outline-none cursor-pointer pr-1"
              >
                <option value="bar" className="bg-secondary">Bar</option>
                <option value="line" className="bg-secondary">Line</option>
                <option value="pie" className="bg-secondary">Pie</option>
                <option value="table" className="bg-secondary">Table</option>
              </select>
            </div>
          )}
          <div className="h-4 w-[1px] bg-tertiary mx-1" />
          <ExportMenu
            canExportImage={canExportChartImage}
            onCsv={() => downloadCsv(result)}
            onXlsx={() => downloadXlsx(result)}
            onPdf={() => downloadPdf(refinedResult, { chartRef, narrative, includeChart: canExportChartImage })}
            onJpeg={() => downloadVisibleImage(refinedResult, chartRef)}
          />
          {hasChartControls && result.view_type !== "timetable" && (
            <IconBtn
              onClick={() => setShowTable((s) => !s)}
              title={showTable ? "Show chart" : "Show table"}
              icon={showTable ? <BarChart3 size={12} strokeWidth={2} /> : <TableIcon size={12} strokeWidth={2} />}
              label={showTable ? "Chart" : "Table"}
              active={showTable}
            />
          )}
        </div>
      </div>

      {result.view_type === "timetable" ? (
        <TimetableGrid result={result} />
      ) : (
        <div ref={chartRef}>
          {!showTable && chartType !== "table" && shape.kind === "bar" && <BarViz shape={shape} />}
          {!showTable && chartType !== "table" && shape.kind === "pie" && <PieViz shape={shape} />}
          {!showTable && chartType !== "table" && shape.kind === "line" && <LineViz shape={shape} />}
          {(showTable || chartType === "table" || shape.kind === "table") && (
            shape.kind === "bar" && shape.crosstab
              ? <CrosstabTable data={shape.crosstab} />
              : <DataTable result={result} />
          )}
        </div>
      )}

    </div>
  );
}

function IconBtn({ onClick, title, icon, label, active }: { onClick: () => void; title: string; icon: React.ReactNode; label: string; active?: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={`flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest px-3 py-1.5 rounded-lg transition-all border ${active ? 'bg-blue-600 text-white border-blue-500 shadow-lg shadow-blue-500/20' : 'bg-secondary text-secondary border-tertiary hover:bg-tertiary hover:text-primary'}`}
    >
      {icon}
      {label}
    </button>
  );
}

function ExportMenu({
  canExportImage,
  onCsv,
  onXlsx,
  onPdf,
  onJpeg,
}: {
  canExportImage: boolean;
  onCsv: () => void;
  onXlsx: () => void;
  onPdf: () => void;
  onJpeg: () => void;
}) {
  const [open, setOpen] = useState(false);
  const run = (handler: () => void) => {
    setOpen(false);
    handler();
  };

  return (
    <div
      className="relative"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
          setOpen(false);
        }
      }}
    >
      <button
        type="button"
        title="Export result"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest px-3 py-1.5 rounded-lg transition-all border bg-secondary text-secondary border-tertiary hover:bg-tertiary hover:text-primary"
      >
        <Download size={12} strokeWidth={2} />
        Export
        <ChevronDown size={12} strokeWidth={2} />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute right-0 top-[calc(100%+6px)] z-30 min-w-[132px] overflow-hidden rounded-lg border border-tertiary bg-primary py-1 shadow-xl"
        >
          <ExportMenuItem label="CSV" onClick={() => run(onCsv)} />
          <ExportMenuItem label="XLSX" onClick={() => run(onXlsx)} />
          <ExportMenuItem label="PDF" onClick={() => run(onPdf)} />
          {canExportImage && <ExportMenuItem label="JPEG" onClick={() => run(onJpeg)} />}
        </div>
      )}
    </div>
  );
}

function ExportMenuItem({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      role="menuitem"
      onMouseDown={(event) => event.preventDefault()}
      onClick={onClick}
      className="block w-full px-3 py-2 text-left text-[11px] font-bold uppercase tracking-widest text-secondary transition-colors hover:bg-secondary hover:text-primary"
    >
      {label}
    </button>
  );
}

interface CrosstabData {
  rowKey: string;
  colKey: string;
  valueKey: string;
  rowLabels: string[];
  colLabels: string[];
  cells: Map<string, Map<string, number>>;
  colsArePeriod: boolean;
}

type Shape =
  | { kind: "table" }
  | { kind: "card"; label: string; value: any; sublabel?: string }
  | { kind: "line"; data: Array<Record<string, any>>; xKey: string; xIsPeriod: boolean; series: string[] }
  | { kind: "pie"; data: Array<{ name: string; value: number }>; valueKey: string }
  | {
      kind: "bar";
      data: Array<Record<string, any>>;
      xKey: string;
      xIsPeriod: boolean;
      series: string[];
      stacked: boolean;
      crosstab?: CrosstabData;
    };

function analyze(result: ResultPayload): Shape {
  const { viz, columns, rows } = result;
  if (rows.length === 0) return { kind: "table" };

  if (viz === "card" || (rows.length === 1 && columns.length <= 3)) {
    if (columns.length === 1) {
      return { kind: "card", label: columns[0], value: rows[0][0] };
    }
    const valueCol = columns[columns.length - 1];
    const valueIdx = columns.length - 1;
    if (columns.length === 2) {
      return { kind: "card", label: valueCol, value: rows[0][valueIdx], sublabel: String(rows[0][0] ?? "") };
    }
    return { kind: "card", label: valueCol, value: rows[0][valueIdx], sublabel: columns.slice(0, -1).map((c, i) => `${c}: ${rows[0][i]}`).join(" · ") };
  }

  if (rows.length === 1 && columns.length > 3) return { kind: "table" };

  // Identify columns by dtype heuristic
  const numericIdx: number[] = [];
  const dimIdx: number[] = [];
  for (let i = 0; i < columns.length; i++) {
    if (rows.every((r) => r[i] === null || r[i] === undefined || isNumeric(r[i]))) numericIdx.push(i);
    else dimIdx.push(i);
  }
  const valueIdx = numericIdx[numericIdx.length - 1] ?? columns.length - 1;
  const valueKey = columns[valueIdx];

  if (viz === "pie" && dimIdx.length >= 1) {
    const labelIdx = dimIdx[0];
    const data = rows.slice(0, 12).map((r) => ({ name: String(r[labelIdx] ?? "—"), value: Number(r[valueIdx]) || 0 }));
    return { kind: "pie", data, valueKey };
  }

  // Pure time series: exactly one time-like dim + numeric series, no other string dims.
  // Only render this as a line when line was requested; explicit bar and pie requests
  // should stay visually faithful to the selected chart type.
  const periodLikeIdx = columns.findIndex((c, i) => isPeriodColumn(c, rows.map((r) => r[i])));
  const otherStringDims = columns.filter((c, i) => i !== periodLikeIdx && !rows.every((r) => r[i] === null || r[i] === undefined || isNumeric(r[i])));
  const isPureTimeSeries = periodLikeIdx >= 0 && otherStringDims.length === 0;
  if (viz === "line" && isPureTimeSeries) {
    const xKey = periodLikeIdx >= 0 ? columns[periodLikeIdx] : columns[0];
    const xIdx = columns.indexOf(xKey);
    const numericIdx: number[] = [];
    for (let i = 0; i < columns.length; i++) {
      if (i === xIdx) continue;
      if (rows.some((r) => isNumeric(r[i]))) numericIdx.push(i);
    }
    const series = numericIdx.map((i) => columns[i]);
    const data = rows.map((r) => {
      const o: Record<string, any> = { [xKey]: r[xIdx] };
      for (const i of numericIdx) o[columns[i]] = Number(r[i]);
      return o;
    });
    return { kind: "line", data, xKey, xIsPeriod: isPeriodColumn(xKey, rows.map((r) => r[xIdx])), series: series.slice(0, 5) };
  }

  // 2-dim stacked bar: pivot col0 (x) × col1 (series) → numeric
  if (dimIdx.length >= 2 && numericIdx.length >= 1) {
    // BI convention: when one dim is time, time goes on COLUMNS of the crosstab and X-axis of the bar.
    const periodDimIdx = dimIdx.find((i) => isPeriodColumn(columns[i], rows.map((r) => r[i])));
    const xIdx = periodDimIdx ?? dimIdx[0];
    const seriesIdx = dimIdx.find((i) => i !== xIdx) ?? dimIdx[1];
    const xKey = columns[xIdx];
    const seriesKey = columns[seriesIdx];

    const buckets = new Map<string, Record<string, any>>();
    const seriesSet = new Set<string>();
    const cells = new Map<string, Map<string, number>>();
    const colSet = new Set<string>();
    for (const r of rows) {
      const x = String(r[xIdx] ?? "—");
      const s = String(r[seriesIdx] ?? "—");
      const v = Number(r[valueIdx]);
      if (!Number.isFinite(v)) continue;
      seriesSet.add(s);
      colSet.add(x);
      if (!buckets.has(x)) buckets.set(x, { [xKey]: x });
      const bucket = buckets.get(x)!;
      bucket[s] = (bucket[s] || 0) + v;
      if (!cells.has(s)) cells.set(s, new Map());
      const row = cells.get(s)!;
      row.set(x, (row.get(x) || 0) + v);
    }
    const data = Array.from(buckets.values()).slice(0, 20);
    const series = Array.from(seriesSet).slice(0, 8);
    const xIsPeriod = periodDimIdx !== undefined;
    const colLabels = xIsPeriod
      ? Array.from(colSet).sort()
      : Array.from(colSet);
    const rowLabels = Array.from(cells.keys()).sort((a, b) => {
      const sa = Array.from(cells.get(a)!.values()).reduce((s, n) => s + n, 0);
      const sb = Array.from(cells.get(b)!.values()).reduce((s, n) => s + n, 0);
      return sb - sa;
    });
    const crosstab: CrosstabData = {
      rowKey: seriesKey,
      colKey: xKey,
      valueKey,
      rowLabels,
      colLabels,
      cells,
      colsArePeriod: xIsPeriod,
    };
    return { kind: "bar", data, xKey, xIsPeriod, series, stacked: true, crosstab };
  }

  // Simple bar
  const xIdx = dimIdx[0] ?? 0;
  const xKey = columns[xIdx];
  const data = rows.slice(0, 20).map((r) => ({ [xKey]: String(r[xIdx] ?? "—"), [valueKey]: Number(r[valueIdx]) || 0 }));
  return { kind: "bar", data, xKey, xIsPeriod: isPeriodColumn(xKey, rows.map((r) => r[xIdx])), series: [valueKey], stacked: false };
}

function ScalarMetric({ shape }: { shape: Extract<Shape, { kind: "card" }> }) {
  return (
    <div className="mt-2 flex flex-col items-start gap-0.5 py-1.5">
      <div className="text-[12px] font-medium" style={{ color: "var(--color-text-secondary)" }}>
        {prettyLabel(shape.label)}
      </div>
      <div className="text-[20px] font-semibold tabular-nums leading-tight" style={{ color: "var(--color-text-primary)" }}>
        {formatCell(shape.value)}
      </div>
      {shape.sublabel && (
        <div className="text-[12px]" style={{ color: "var(--color-text-tertiary)" }}>
          {shape.sublabel}
        </div>
      )}
    </div>
  );
}

function BarViz({ shape }: { shape: Extract<Shape, { kind: "bar" }> }) {
  const height = Math.min(360, 60 + shape.data.length * 22);
  const yTickFormatter = shape.xIsPeriod ? formatPeriod : undefined;
  return (
    <div aria-label="Bar chart" style={{ width: "100%", height }}>
      <ResponsiveContainer>
        <BarChart data={shape.data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} horizontal={false} />
          <XAxis type="number" tick={{ fill: AXIS_COLOR, fontSize: 11 }} tickFormatter={formatNumber} stroke={GRID_COLOR} />
          <YAxis type="category" dataKey={shape.xKey} tick={{ fill: AXIS_COLOR, fontSize: 11 }} tickFormatter={yTickFormatter} width={120} stroke={GRID_COLOR} />
          <Tooltip content={<ChartTooltip labelFormatter={yTickFormatter} />} cursor={{ fill: "rgba(0,0,0,0.04)" }} />
          {shape.stacked && shape.series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" />}
          {shape.series.map((key, i) => (
            <Bar
              key={key}
              dataKey={key}
              stackId={shape.stacked ? "a" : undefined}
              fill={PALETTE[i % PALETTE.length]}
              radius={shape.stacked ? 0 : [0, 4, 4, 0]}
            >
              {!shape.stacked &&
                shape.data.map((_, idx) => <Cell key={idx} fill={PALETTE[idx % PALETTE.length]} />)}
            </Bar>
          ))}
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function PieViz({ shape }: { shape: Extract<Shape, { kind: "pie" }> }) {
  const total = shape.data.reduce((s, d) => s + (d.value || 0), 0) || 1;
  return (
    <div aria-label="Pie chart" style={{ width: "100%", height: 280 }}>
      <ResponsiveContainer>
        <PieChart margin={{ top: 0, right: 0, left: 0, bottom: 0 }}>
          <Pie
            data={shape.data}
            dataKey="value"
            nameKey="name"
            cx="40%"
            cy="50%"
            innerRadius={50}
            outerRadius={95}
            paddingAngle={2}
            stroke="var(--color-background-secondary)"
            strokeWidth={1.5}
            label={({ percent }) => `${((percent ?? 0) * 100).toFixed(0)}%`}
            labelLine={false}
          >
            {shape.data.map((_, i) => (
              <Cell key={i} fill={PALETTE[i % PALETTE.length]} />
            ))}
          </Pie>
          <Tooltip content={<ChartTooltip totalForPct={total} />} />
          <Legend
            layout="vertical"
            align="right"
            verticalAlign="middle"
            iconType="circle"
            wrapperStyle={{ fontSize: 11, color: "var(--color-text-secondary)" }}
          />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}

function LineViz({ shape }: { shape: Extract<Shape, { kind: "line" }> }) {
  const xTickFormatter = shape.xIsPeriod ? formatPeriod : undefined;
  return (
    <div aria-label="Line chart" style={{ width: "100%", height: 240 }}>
      <ResponsiveContainer>
        <LineChart data={shape.data} margin={{ top: 8, right: 16, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke={GRID_COLOR} />
          <XAxis dataKey={shape.xKey} tick={{ fill: AXIS_COLOR, fontSize: 11 }} tickFormatter={xTickFormatter} stroke={GRID_COLOR} />
          <YAxis tick={{ fill: AXIS_COLOR, fontSize: 11 }} tickFormatter={formatNumber} stroke={GRID_COLOR} width={50} />
          <Tooltip content={<ChartTooltip labelFormatter={xTickFormatter} />} />
          {shape.series.length > 1 && <Legend wrapperStyle={{ fontSize: 11 }} iconType="circle" />}
          {shape.series.map((key, i) => (
            <Line
              key={key}
              type="monotone"
              dataKey={key}
              stroke={PALETTE[i % PALETTE.length]}
              strokeWidth={2}
              dot={{ r: 2, fill: PALETTE[i % PALETTE.length] }}
              activeDot={{ r: 4 }}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function ChartTooltip({ active, payload, label, totalForPct, labelFormatter }: any) {
  if (!active || !payload?.length) return null;
  const displayLabel = label !== undefined ? (labelFormatter ? labelFormatter(label) : String(label)) : null;
  return (
    <div
      style={{
        background: "var(--color-background-primary)",
        border: "0.5px solid var(--color-border-secondary)",
        borderRadius: 8,
        padding: "6px 10px",
        fontSize: 11,
        boxShadow: "0 4px 12px rgba(0,0,0,0.08)",
        color: "var(--color-text-primary)",
      }}
    >
      {displayLabel && (
        <div style={{ color: "var(--color-text-tertiary)", marginBottom: 3 }}>{displayLabel}</div>
      )}
      {payload.map((p: any, i: number) => {
        const v = Number(p.value);
        const pct = totalForPct ? ` (${((v / totalForPct) * 100).toFixed(1)}%)` : "";
        return (
          <div key={i} className="flex items-center gap-1.5">
            <span style={{ width: 7, height: 7, borderRadius: 99, background: p.color || p.fill }} />
            <span style={{ color: "var(--color-text-secondary)" }}>{p.name}</span>
            <span className="tabular-nums" style={{ marginLeft: "auto" }}>
              {formatNumber(v)}{pct}
            </span>
          </div>
        );
      })}
    </div>
  );
}

function DataTable({ result }: { result: ResultPayload }) {
  const [filter, setFilter] = useState("");
  const periodColIdx = useMemo(
    () => result.columns.map((c, i) => (isPeriodColumn(c, result.rows.map((r) => r[i])) ? i : -1)).filter((i) => i >= 0),
    [result.columns, result.rows],
  );
  
  const filteredRows = useMemo(() => {
    if (!filter) return result.rows.slice(0, 50);
    const lowFilter = filter.toLowerCase();
    return result.rows.filter(row => 
      row.some(cell => String(cell ?? "").toLowerCase().includes(lowFilter))
    ).slice(0, 50);
  }, [filter, result.rows]);

  const isPeriodCol = (j: number) => periodColIdx.includes(j);
  return (
    <div className="overflow-x-auto rounded-xl border border-secondary bg-primary">
      {result.rows.length > 10 && (
        <div className="flex items-center justify-between px-4 py-2 border-b border-tertiary bg-secondary">
          <input 
            value={filter} 
            onChange={e => setFilter(e.target.value)}
            placeholder="Search result set..."
            className="w-full text-xs bg-transparent outline-none text-primary placeholder:text-tertiary"
          />
          {filter && (
            <span className="text-[9px] font-bold uppercase tracking-widest ml-2 whitespace-nowrap text-tertiary">
              {filteredRows.length} / {result.rows.length} matches
            </span>
          )}
        </div>
      )}
      <table className="w-full border-collapse text-[12px]">
        <thead>
          <tr>
            {result.columns.map((c) => (
              <th
                key={c}
                className="text-left py-2.5 px-4 font-bold uppercase tracking-wider text-[10px] bg-secondary"
                style={{
                  color: "var(--color-text-tertiary)",
                  borderBottom: "1px solid var(--color-border-tertiary)",
                }}
              >
                {prettyLabel(c)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {filteredRows.map((row, i) => (
            <tr
              key={i}
              className="hover:bg-tertiary transition-colors"
              style={{ background: i % 2 === 1 ? "var(--color-background-secondary)" : "transparent" }}
            >
              {row.map((v, j) => (
                <td
                  key={j}
                  className="py-2 px-4 tabular-nums text-secondary"
                  style={{
                    borderBottom: i === filteredRows.length - 1 ? "none" : "1px solid var(--color-border-tertiary)",
                  }}
                >
                  {isPeriodCol(j) ? formatPeriod(v) : formatCell(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TimetableGrid({ result }: { result: ResultPayload }) {
  return (
    <div className="mt-1 mb-3">
      <div className="flex items-center gap-2 mb-3">
        <span
          className="px-1.5 py-0.5 rounded-[4px] text-[10px] font-bold uppercase tracking-wider"
          style={{
            background: "rgba(99, 102, 241, 0.1)",
            color: "#6366f1",
            border: "0.5px solid rgba(99, 102, 241, 0.2)",
          }}
        >
          Education View
        </span>
        <span className="text-[11px]" style={{ color: "var(--color-text-tertiary)" }}>
          Timetable Format
        </span>
      </div>
      <DataTable result={result} />
    </div>
  );
}

const _PERIOD_NAME_RE = /^(period|date|datetime|month|quarter|year|_at|timestamp|delivery|created_at|updated_at)$/i;
const _ISO_PREFIX_RE = /^\d{4}-\d{2}-\d{2}/;
const _MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function isPeriodColumn(name: string, samples: any[]): boolean {
  if (_PERIOD_NAME_RE.test(name)) return true;
  for (const s of samples) {
    if (s == null) continue;
    if (typeof s === "string" && _ISO_PREFIX_RE.test(s)) return true;
    return false;
  }
  return false;
}

function formatPeriod(value: any): string {
  if (value == null) return "—";
  const s = String(value);
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return s;
  const month = _MONTHS[parseInt(m[2], 10) - 1];
  if (!month) return s;
  // If full year span is single year, show "Mon DD"; else "Mon YYYY". Default safer: "Mon YYYY".
  return `${month} ${m[1]}`;
}

function CrosstabTable({ data }: { data: CrosstabData }) {
  const totalsCol = data.rowLabels.map((r) => {
    const row = data.cells.get(r);
    if (!row) return 0;
    let s = 0;
    for (const v of row.values()) s += v;
    return s;
  });
  const totalsRow = data.colLabels.map((c) => {
    let s = 0;
    for (const r of data.rowLabels) {
      const row = data.cells.get(r);
      if (row?.has(c)) s += row.get(c) || 0;
    }
    return s;
  });
  const grandTotal = totalsRow.reduce((s, n) => s + n, 0);

  return (
    <div className="overflow-x-auto">
      <table className="border-collapse text-[12px]" style={{ minWidth: "100%" }}>
        <thead>
          <tr>
            <th
              className="text-left py-1.5 px-2 font-medium sticky left-0"
              style={{
                color: "var(--color-text-tertiary)",
                background: "var(--color-background-secondary)",
                borderBottom: "0.5px solid var(--color-border-tertiary)",
              }}
            >
              {prettyLabel(data.rowKey)}
            </th>
            {data.colLabels.map((c) => (
              <th
                key={c}
                className="text-right py-1.5 px-2 font-medium tabular-nums whitespace-nowrap"
                style={{
                  color: "var(--color-text-tertiary)",
                  borderBottom: "0.5px solid var(--color-border-tertiary)",
                }}
              >
                {data.colsArePeriod ? formatPeriod(c) : c}
              </th>
            ))}
            <th
              className="text-right py-1.5 px-2 font-medium tabular-nums"
              style={{
                color: "var(--color-text-tertiary)",
                borderBottom: "0.5px solid var(--color-border-tertiary)",
                borderLeft: "0.5px solid var(--color-border-tertiary)",
              }}
            >
              Total
            </th>
          </tr>
        </thead>
        <tbody>
          {data.rowLabels.map((r, i) => {
            const row = data.cells.get(r);
            return (
              <tr key={r} style={{ background: i % 2 === 1 ? "var(--color-background-primary)" : "transparent" }}>
                <td
                  className="py-[5px] px-2 font-medium whitespace-nowrap sticky left-0"
                  style={{
                    color: "var(--color-text-primary)",
                    background: i % 2 === 1 ? "var(--color-background-primary)" : "var(--color-background-secondary)",
                    borderBottom: "0.5px solid var(--color-border-tertiary)",
                  }}
                >
                  {r}
                </td>
                {data.colLabels.map((c) => (
                  <td
                    key={c}
                    className="py-[5px] px-2 text-right tabular-nums"
                    style={{
                      color: "var(--color-text-primary)",
                      borderBottom: "0.5px solid var(--color-border-tertiary)",
                    }}
                  >
                    {row?.has(c) ? formatNumber(row.get(c) || 0) : "—"}
                  </td>
                ))}
                <td
                  className="py-[5px] px-2 text-right tabular-nums font-medium"
                  style={{
                    color: "var(--color-text-primary)",
                    borderBottom: "0.5px solid var(--color-border-tertiary)",
                    borderLeft: "0.5px solid var(--color-border-tertiary)",
                  }}
                >
                  {formatNumber(totalsCol[i])}
                </td>
              </tr>
            );
          })}
          <tr style={{ borderTop: "0.5px solid var(--color-border-secondary)" }}>
            <td
              className="py-[5px] px-2 font-medium sticky left-0"
              style={{
                color: "var(--color-text-secondary)",
                background: "var(--color-background-secondary)",
                borderTop: "0.5px solid var(--color-border-secondary)",
              }}
            >
              Total
            </td>
            {data.colLabels.map((c, j) => (
              <td
                key={c}
                className="py-[5px] px-2 text-right tabular-nums font-medium"
                style={{
                  color: "var(--color-text-secondary)",
                  borderTop: "0.5px solid var(--color-border-secondary)",
                }}
              >
                {formatNumber(totalsRow[j])}
              </td>
            ))}
            <td
              className="py-[5px] px-2 text-right tabular-nums font-medium"
              style={{
                color: "var(--color-text-primary)",
                borderTop: "0.5px solid var(--color-border-secondary)",
                borderLeft: "0.5px solid var(--color-border-tertiary)",
              }}
            >
              {formatNumber(grandTotal)}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function isNumeric(v: any): boolean {
  if (v === null || v === undefined || v === "") return false;
  const n = Number(v);
  return Number.isFinite(n) && typeof v !== "boolean";
}

function prettyLabel(s: string): string {
  return s.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
}

function formatNumber(v: number): string {
  if (!Number.isFinite(v)) return "—";
  if (Math.abs(v) < 1 && v !== 0) return v.toFixed(3);
  return v.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

function formatCell(v: any): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") return formatNumber(v);
  if (typeof v === "string" && isNumeric(v)) return formatNumber(Number(v));
  return String(v);
}

function downloadCsv(result: ResultPayload) {
  const header = result.columns.join(",");
  const lines = result.rows.map((r) =>
    r.map((v) => (v == null ? "" : /[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v))).join(","),
  );
  const blob = new Blob([[header, ...lines].join("\n")], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${result.title.replace(/\s+/g, "_").toLowerCase()}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function downloadXlsx(result: ResultPayload) {
  const ws = XLSX.utils.aoa_to_sheet([result.columns, ...result.rows]);
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(wb, ws, "Result");
  XLSX.writeFile(wb, `${result.title.replace(/\s+/g, "_").toLowerCase()}.xlsx`);
}

function safeFilename(title: string, extension: string): string {
  const base = title
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80) || "result";
  return `${base}.${extension}`;
}

function downloadBlob(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function downloadPdf(
  result: ResultPayload,
  options: {
    chartRef?: RefObject<HTMLDivElement | null>;
    includeChart?: boolean;
    narrative?: string | null;
  } = {},
) {
  const doc = new jsPDF({ orientation: "portrait", unit: "pt", format: "a4" });
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const contentWidth = pageWidth - PDF_MARGIN * 2;
  let y = PDF_MARGIN;

  doc.setFont("helvetica", "bold");
  doc.setFontSize(19);
  doc.setTextColor(...PDF_PRIMARY_TEXT);
  y = addPdfLines(doc, result.title || "Result", PDF_MARGIN, y, contentWidth, 24);

  doc.setFont("helvetica", "normal");
  doc.setFontSize(9);
  doc.setTextColor(...PDF_MUTED_TEXT);
  doc.text(`${result.row_count.toLocaleString()} rows · ${new Date().toLocaleDateString()}`, PDF_MARGIN, y + 3);
  y += 26;

  const narrative = cleanNarrative(options.narrative);
  if (narrative) {
    y = addPdfSection(doc, "Analysis", y, pageHeight);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(PDF_BODY_FONT_SIZE);
    doc.setTextColor(...PDF_PRIMARY_TEXT);
    y = addPdfParagraphs(doc, narrative, PDF_MARGIN, y, contentWidth, pageHeight);
  }

  const chartImage = options.includeChart ? await chartImageDataUrl(options.chartRef) : null;
  if (chartImage) {
    y = addPdfSection(doc, "Graph", y + 4, pageHeight);
    const imageProps = doc.getImageProperties(chartImage);
    const imageRatio = imageProps.height / imageProps.width;
    const imageWidth = contentWidth;
    const imageHeight = Math.min(imageWidth * imageRatio, pageHeight - PDF_MARGIN * 2);
    if (y + imageHeight > pageHeight - PDF_MARGIN) {
      doc.addPage();
      y = PDF_MARGIN;
    }
    doc.addImage(chartImage, "JPEG", PDF_MARGIN, y, imageWidth, imageHeight);
  } else if (result.columns.length > 0) {
    y = addPdfSection(doc, "Data", y + 4, pageHeight);
    autoTable(doc, {
      startY: y,
      head: [result.columns.map(prettyLabel)],
      body: result.rows.slice(0, 500).map((row) => result.columns.map((_, i) => formatCell(row[i]))),
      theme: "grid",
      headStyles: { fillColor: [...PDF_BLUE], textColor: 255 },
      alternateRowStyles: { fillColor: [248, 250, 252] },
      styles: { fontSize: 8, cellPadding: 4, textColor: [...PDF_PRIMARY_TEXT] },
      margin: { left: PDF_MARGIN, right: PDF_MARGIN },
    });
  }

  doc.save(safeFilename(result.title, "pdf"));
}

function addPdfSection(doc: jsPDF, label: string, y: number, pageHeight: number) {
  if (y + PDF_SECTION_GAP > pageHeight - PDF_MARGIN) {
    doc.addPage();
    y = PDF_MARGIN;
  }
  doc.setFont("helvetica", "bold");
  doc.setFontSize(10);
  doc.setTextColor(...PDF_BLUE);
  doc.text(label.toUpperCase(), PDF_MARGIN, y + 12);
  return y + 26;
}

function addPdfLines(doc: jsPDF, text: string, x: number, y: number, width: number, lineHeight: number) {
  const lines = doc.splitTextToSize(text, width);
  doc.text(lines, x, y);
  return y + lines.length * lineHeight;
}

function addPdfParagraphs(doc: jsPDF, text: string, x: number, y: number, width: number, pageHeight: number) {
  const paragraphs = text
    .split(/\n{2,}/)
    .map((paragraph) => paragraph.trim())
    .filter(Boolean);

  for (const paragraph of paragraphs) {
    const lines = doc.splitTextToSize(paragraph, width);
    for (const line of lines) {
      if (y > pageHeight - PDF_MARGIN) {
        doc.addPage();
        y = PDF_MARGIN;
      }
      doc.text(line, x, y);
      y += PDF_LINE_HEIGHT;
    }
    y += 8;
  }
  return y + 2;
}

function cleanNarrative(text?: string | null) {
  if (!text) return "";
  return text
    .replace(/```[\s\S]*?```/g, "")
    .split("\n")
    .filter((line) => {
      const trimmed = line.trim();
      if (!trimmed) return true;
      if (PDF_INTERNAL_DETAIL_RE.test(trimmed)) return false;
      if (/^\|.*\|$/.test(trimmed)) return false;
      if (/^[-:| ]+$/.test(trimmed)) return false;
      return true;
    })
    .map((line) => line
      .replace(/^#{1,6}\s+/g, "")
      .replace(/^[-*]\s+/g, "• ")
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/\*([^*]+)\*/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
      .trim())
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

async function chartImageDataUrl(chartRef?: RefObject<HTMLDivElement | null>) {
  const svg = chartRef?.current?.querySelector("svg");
  if (!svg) return null;
  const { source, width, height } = serializeVisibleSvg(svg);
  const svgBlob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);
  try {
    const image = await loadImage(url);
    const canvas = renderChartCanvas(image, width, height);
    return canvas?.toDataURL(JPEG_EXPORT_TYPE, JPEG_EXPORT_QUALITY) || null;
  } finally {
    URL.revokeObjectURL(url);
  }
}

function loadImage(src: string) {
  return new Promise<HTMLImageElement>((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("Unable to render chart image."));
    img.src = src;
  });
}

function renderChartCanvas(image: CanvasImageSource, sourceWidth: number, sourceHeight: number) {
  const width = Math.max(Math.ceil(sourceWidth), IMAGE_EXPORT_MIN_CHART_WIDTH);
  const height = Math.max(Math.ceil(sourceHeight * (width / sourceWidth)), IMAGE_EXPORT_MIN_CHART_HEIGHT);
  const canvas = document.createElement("canvas");
  canvas.width = width * JPEG_EXPORT_SCALE;
  canvas.height = height * JPEG_EXPORT_SCALE;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.scale(JPEG_EXPORT_SCALE, JPEG_EXPORT_SCALE);
  ctx.fillStyle = imageExportBackground();
  ctx.fillRect(0, 0, width, height);
  ctx.drawImage(image, 0, 0, width, height);
  return canvas;
}

function downloadVisibleImage(result: ResultPayload, chartRef: RefObject<HTMLDivElement | null>) {
  const svg = chartRef.current?.querySelector("svg");
  if (!svg) return;
  const { source, width, height } = serializeVisibleSvg(svg);
  const svgBlob = new Blob([source], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(svgBlob);
  const image = new Image();

  image.onload = () => {
    drawImageExport(result, image, width, height, () => URL.revokeObjectURL(url));
  };
  image.onerror = () => URL.revokeObjectURL(url);
  image.src = url;
}

function serializeVisibleSvg(svg: SVGSVGElement) {
  const box = svg.getBoundingClientRect();
  const width = Math.max(Math.ceil(box.width || svg.clientWidth || IMAGE_EXPORT_MIN_CHART_WIDTH), IMAGE_EXPORT_MIN_CHART_WIDTH);
  const height = Math.max(Math.ceil(box.height || svg.clientHeight || IMAGE_EXPORT_MIN_CHART_HEIGHT), IMAGE_EXPORT_MIN_CHART_HEIGHT);
  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  if (!clone.getAttribute("viewBox")) {
    clone.setAttribute("viewBox", `0 0 ${width} ${height}`);
  }
  inlineSvgPaint(svg, clone);
  normalizeExportSvgColors(clone);
  return {
    source: new XMLSerializer().serializeToString(clone),
    width,
    height,
  };
}

function inlineSvgPaint(source: Element, target: Element) {
  const sourceNodes = [source, ...Array.from(source.querySelectorAll("*"))];
  const targetNodes = [target, ...Array.from(target.querySelectorAll("*"))];
  sourceNodes.forEach((sourceNode, index) => {
    const targetNode = targetNodes[index];
    if (!(sourceNode instanceof SVGElement) || !(targetNode instanceof SVGElement)) return;
    const computed = window.getComputedStyle(sourceNode);
    copyResolvedSvgAttribute(sourceNode, targetNode, computed, "fill");
    copyResolvedSvgAttribute(sourceNode, targetNode, computed, "stroke");
    copyResolvedSvgAttribute(sourceNode, targetNode, computed, "color");
    ["font-size", "font-family", "font-weight", "opacity", "stroke-width"].forEach((prop) => {
      const value = computed.getPropertyValue(prop);
      if (value) targetNode.style.setProperty(prop, value);
    });
  });
}

function normalizeExportSvgColors(svg: SVGSVGElement) {
  svg.style.background = DEFAULT_IMAGE_EXPORT_BACKGROUND;
  svg.querySelectorAll("text, tspan").forEach((node) => {
    if (!(node instanceof SVGElement)) return;
    node.setAttribute("fill", DEFAULT_IMAGE_EXPORT_MUTED_TEXT);
    node.style.fill = DEFAULT_IMAGE_EXPORT_MUTED_TEXT;
    node.style.color = DEFAULT_IMAGE_EXPORT_MUTED_TEXT;
  });
  svg.querySelectorAll(".recharts-cartesian-grid line").forEach((node) => {
    if (!(node instanceof SVGElement)) return;
    node.setAttribute("stroke", DEFAULT_IMAGE_EXPORT_GRID);
    node.style.stroke = DEFAULT_IMAGE_EXPORT_GRID;
  });
  svg.querySelectorAll(".recharts-cartesian-axis-line, .recharts-cartesian-axis-tick-line").forEach((node) => {
    if (!(node instanceof SVGElement)) return;
    node.setAttribute("stroke", DEFAULT_IMAGE_EXPORT_AXIS);
    node.style.stroke = DEFAULT_IMAGE_EXPORT_AXIS;
  });
  svg.querySelectorAll(".recharts-pie-sector path").forEach((node) => {
    if (!(node instanceof SVGElement)) return;
    node.setAttribute("stroke", DEFAULT_IMAGE_EXPORT_BACKGROUND);
    node.style.stroke = DEFAULT_IMAGE_EXPORT_BACKGROUND;
  });
}

function copyResolvedSvgAttribute(sourceNode: SVGElement, targetNode: SVGElement, computed: CSSStyleDeclaration, attr: "fill" | "stroke" | "color") {
  const raw = sourceNode.getAttribute(attr);
  if (!raw) return;
  if (raw === "none" || raw.startsWith("url(")) {
    targetNode.setAttribute(attr, raw);
    return;
  }
  const value = computed.getPropertyValue(attr).trim();
  if (value) targetNode.setAttribute(attr, value);
}

function drawImageExport(result: ResultPayload, image: CanvasImageSource, sourceWidth: number, sourceHeight: number, cleanup?: () => void) {
  const chartWidth = Math.max(Math.ceil(sourceWidth), IMAGE_EXPORT_MIN_CHART_WIDTH);
  const chartHeight = Math.max(Math.ceil(sourceHeight * (chartWidth / sourceWidth)), IMAGE_EXPORT_MIN_CHART_HEIGHT);
  const logicalWidth = chartWidth + IMAGE_EXPORT_PADDING * 2;
  const logicalHeight = chartHeight + IMAGE_EXPORT_HEADER_HEIGHT + IMAGE_EXPORT_PADDING * 2;
  const canvas = document.createElement("canvas");
  canvas.width = logicalWidth * JPEG_EXPORT_SCALE;
  canvas.height = logicalHeight * JPEG_EXPORT_SCALE;
  const ctx = canvas.getContext("2d");
  if (!ctx) {
    cleanup?.();
    return;
  }

  ctx.scale(JPEG_EXPORT_SCALE, JPEG_EXPORT_SCALE);
  ctx.fillStyle = imageExportBackground();
  ctx.fillRect(0, 0, logicalWidth, logicalHeight);
  drawExportHeader(ctx, result, logicalWidth);
  ctx.drawImage(image, IMAGE_EXPORT_PADDING, IMAGE_EXPORT_PADDING + IMAGE_EXPORT_HEADER_HEIGHT, chartWidth, chartHeight);
  canvas.toBlob((blob) => {
    cleanup?.();
    if (blob) downloadBlob(safeFilename(result.title, JPEG_EXPORT_EXTENSION), blob);
  }, JPEG_EXPORT_TYPE, JPEG_EXPORT_QUALITY);
}

function drawExportHeader(ctx: CanvasRenderingContext2D, result: ResultPayload, width: number) {
  const maxTextWidth = width - IMAGE_EXPORT_PADDING * 2;
  ctx.fillStyle = imageExportTextColor();
  ctx.font = "700 24px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.fillText(fitCanvasText(ctx, result.title || "Result", maxTextWidth), IMAGE_EXPORT_PADDING, IMAGE_EXPORT_PADDING + 24);
  ctx.fillStyle = imageExportMutedTextColor();
  ctx.font = "500 13px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
  ctx.fillText(`${result.row_count.toLocaleString()} rows`, IMAGE_EXPORT_PADDING, IMAGE_EXPORT_PADDING + 48);
}

function fitCanvasText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number) {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let clipped = text;
  while (clipped.length > 1 && ctx.measureText(`${clipped}...`).width > maxWidth) {
    clipped = clipped.slice(0, -1);
  }
  return `${clipped}...`;
}

function imageExportBackground() {
  return DEFAULT_IMAGE_EXPORT_BACKGROUND;
}

function imageExportTextColor() {
  return DEFAULT_IMAGE_EXPORT_TEXT;
}

function imageExportMutedTextColor() {
  return DEFAULT_IMAGE_EXPORT_MUTED_TEXT;
}
