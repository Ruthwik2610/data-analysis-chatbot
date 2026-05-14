import { displaySourceName } from "./displayNames";
import type { Pending } from "./types";

interface SheetQuestionArgs {
  fileName: string;
  uploadId: string;
  sheets: string[];
}

export function buildSheetModeQuestion({ fileName, uploadId, sheets }: SheetQuestionArgs): { content: string; pending: Pending } {
  return {
    content: `Got **${displaySourceName(fileName)}**. It has ${sheets.length} sheets — which one should I open as the source?`,
    pending: {
      resolver: "sheet_pick",
      hint: "Pick a sheet",
      options: sheets.map((sheet) => ({ label: sheet, value: sheet })),
      args: { upload_id: uploadId },
    },
  };
}

export function buildCustomSheetQuestion({ fileName, uploadId, sheets }: SheetQuestionArgs): { content: string; pending: Pending } {
  return {
    content: `Which sheets from **${displaySourceName(fileName)}** should I load?`,
    pending: {
      resolver: "sheet_pick",
      hint: "Pick sheets",
      options: sheets.map((sheet) => ({ label: sheet, value: sheet })),
      args: { upload_id: uploadId },
      multiSelect: true,
    },
  };
}
