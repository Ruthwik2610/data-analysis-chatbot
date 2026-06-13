import type { Message, ResultPayload } from "@/lib/types";

export interface ArtifactItem {
  id: string;
  messageId: string;
  result: ResultPayload;
  index: number;
  count: number;
}

export function shouldUseArtifact(result: ResultPayload): boolean {
  return result.viz === "bar" || result.viz === "line" || result.viz === "pie" || result.viz === "chart";
}

export function artifactItems(messages: Message[]): ArtifactItem[] {
  const items: ArtifactItem[] = [];
  for (const message of messages) {
    if (message.role !== "assistant" || message.streaming) continue;
    const resultArtifacts = (message.artifacts || []).filter(shouldUseArtifact);
    if (resultArtifacts.length <= 1) continue;

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
