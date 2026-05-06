const COMMON_SOURCE_EXTENSIONS = new Set([
  "7z",
  "csv",
  "db",
  "duckdb",
  "json",
  "parquet",
  "pdf",
  "tsv",
  "xls",
  "xlsx",
  "zip",
]);

export function displaySourceName(name?: string | null): string {
  const value = (name || "").trim();
  if (!value) return "Untitled source";
  const lastSlash = Math.max(value.lastIndexOf("/"), value.lastIndexOf("\\"));
  const dir = lastSlash >= 0 ? value.slice(0, lastSlash + 1) : "";
  const base = lastSlash >= 0 ? value.slice(lastSlash + 1) : value;
  const dot = base.lastIndexOf(".");
  if (dot <= 0 || dot === base.length - 1) return base || dir || value;
  const ext = base.slice(dot + 1).toLowerCase();
  return COMMON_SOURCE_EXTENSIONS.has(ext) ? base.slice(0, dot) : base;
}
