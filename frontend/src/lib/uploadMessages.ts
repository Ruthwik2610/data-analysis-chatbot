import type { MCPConnector, Source, UploadResponse } from "./types";
import { displaySourceName } from "./displayNames";

export function formatArchiveSkippedNote(skipped: NonNullable<UploadResponse["skipped"]> = []): string {
  if (!skipped.length) {
    return "";
  }
  const visible = skipped.slice(0, 3).map((item) => `${displaySourceName(item.file_name)}: ${item.error}`);
  const remaining = skipped.length - visible.length;
  const details = remaining > 0 ? `${visible.join("; ")}; ${remaining} more` : visible.join("; ");
  return ` ${skipped.length} PDF${skipped.length === 1 ? " was" : "s were"} skipped: ${details}.`;
}

export function formatWorkbookMCPConnectedMessage(sources: Source[], connector?: MCPConnector, deployError?: string): string {
  const loaded = `Loaded ${sources.length} sheets: ${sources.map((source) => `**${displaySourceName(source.name)}**`).join(", ")}.`;
  if (!connector) {
    return `${loaded} Ask me anything about them.`;
  }
  const workerUrl = connector.cloudflare?.worker_url;
  if (workerUrl) {
    return `${loaded}\n\nAuto MCP is connected to this chat.\n\nMCP URL: ${workerUrl}`;
  }
  if (deployError) {
    return `${loaded}\n\nAuto MCP is connected locally, but the public MCP URL could not be created: ${deployError}`;
  }
  return `${loaded}\n\nAuto MCP is connected to this chat.`;
}
