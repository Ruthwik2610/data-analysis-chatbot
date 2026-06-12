import type { Message, ResultPayload } from "@/lib/types";

export interface ArtifactItem {
  id: string;
  messageId: string;
  result: ResultPayload;
  index: number;
  count: number;
}

export function shouldUseArtifact(result: ResultPayload): boolean {
  if (result.view_type === "timetable") return true;
  if (result.viz !== "card") return true;
  return result.row_count > 8 || result.columns.length > 4;
}

export function artifactItems(messages: Message[]): ArtifactItem[] {
  const items: ArtifactItem[] = [];
  for (const message of messages) {
    if (message.role !== "assistant" || message.streaming) continue;
    const explicitArtifacts = (message.artifacts || []).filter(shouldUseArtifact);
    const resultArtifacts = explicitArtifacts.length > 0
      ? explicitArtifacts
      : message.result && shouldUseArtifact(message.result)
        ? [message.result]
        : [];

    resultArtifacts.forEach((result, index) => {
      items.push({
        id: `${message.id}:artifact:${index}`,
        messageId: message.id,
        result,
        index,
        count: resultArtifacts.length,
      });
    });
  }
  return items;
}
