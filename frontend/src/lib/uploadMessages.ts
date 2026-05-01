import type { UploadResponse } from "./types";

export function formatArchiveSkippedNote(skipped: NonNullable<UploadResponse["skipped"]> = []): string {
  if (!skipped.length) {
    return "";
  }
  const visible = skipped.slice(0, 3).map((item) => `${item.file_name}: ${item.error}`);
  const remaining = skipped.length - visible.length;
  const details = remaining > 0 ? `${visible.join("; ")}; ${remaining} more` : visible.join("; ");
  return ` ${skipped.length} PDF${skipped.length === 1 ? " was" : "s were"} skipped: ${details}.`;
}
