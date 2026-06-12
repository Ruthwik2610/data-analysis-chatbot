import { describe, expect, it } from "vitest";
import { sanitizeAssistantContent, sanitizeThinkingStep, sanitizeUserVisibleError } from "../userFacingText";

describe("user-facing text sanitizers", () => {
  it("hides SQL statements from thinking steps", () => {
    expect(sanitizeThinkingStep("Running SELECT * FROM orders WHERE token = 'secret'")).toBe("Working on your answer");
  });

  it("hides raw internal errors from users", () => {
    expect(sanitizeUserVisibleError("Traceback: SELECT * FROM users WHERE api_key = 'abc'")).toBe(
      "Something went wrong. Please try again.",
    );
  });

  it("keeps short safe errors readable", () => {
    expect(sanitizeUserVisibleError("File type is not supported")).toBe("File type is not supported");
  });

  it("removes SQL lines from assistant markdown while preserving the answer", () => {
    const content = sanitizeAssistantContent([
      "Revenue increased in May.",
      "SQL: SELECT category, revenue FROM sales WHERE token = 'secret'",
      "**Margin** also improved.",
    ].join("\n"));

    expect(content).toContain("Revenue increased in May.");
    expect(content).toContain("**Margin** also improved.");
    expect(content).not.toMatch(/select|token|sql/i);
  });
});
