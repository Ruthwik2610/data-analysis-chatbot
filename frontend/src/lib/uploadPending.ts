import { displaySourceName } from "./displayNames";
import type { Pending } from "./types";

interface SheetQuestionArgs {
  fileName: string;
  uploadId: string;
  sheets: string[];
}

export function buildSheetModeQuestion({ fileName, uploadId, sheets }: SheetQuestionArgs): { content: string; pending: Pending } {
  return {
    content: `Got **${displaySourceName(fileName)}**. It has ${sheets.length} sheets. Load all sheets or choose specific sheets?`,
    pending: {
      resolver: "sheet_pick_mode",
      hint: "Choose sheet mode",
      options: [
        { label: "All sheets", value: "all_sheets" },
        { label: "Custom sheets", value: "custom_sheets" },
      ],
      args: { upload_id: uploadId, file_name: fileName, sheets },
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
