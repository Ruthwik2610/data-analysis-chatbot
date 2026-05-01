# Chat UI Next Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Data Chat feel like a fast, polished, production-ready data-analysis workspace with stronger guidance, clearer source context, fewer dead-end states, and explicit performance guardrails.

**Architecture:** Keep the app chat-first. Add narrow, testable frontend components around the existing `InputBar`, `MessageList`, `ResultBlock`, `Sidebar`, and `ProjectDialog` surfaces without changing query execution contracts unless a task explicitly needs backend support.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS utilities, lucide-react, Vitest, Testing Library, FastAPI only for API additions.

---

## Research Notes For Production Readiness

- Next.js production guidance emphasizes keeping client JavaScript small, using Server Components unless interactivity requires Client Components, lazy-loading heavy Client Components or libraries, adding global error UI, validating production builds with `next build` and `next start`, measuring Core Web Vitals, analyzing bundles, and considering Content Security Policy for self-hosted apps. Source: https://nextjs.org/docs/app/building-your-application/deploying/production-checklist
- React guidance treats `memo`, `useMemo`, and `useCallback` as targeted optimizations for expensive or frequently re-rendered UI, not blanket defaults. Use profiling and stable props around heavy result/chart components instead of memoizing every component. Source: https://react.dev/reference/react/memo
- WCAG 2.2 should be the accessibility baseline. Normal readable text needs at least 4.5:1 contrast, and UI affordances must remain keyboard and screen-reader usable. Source: https://www.w3.org/TR/wcag/
- FastAPI/Uvicorn production guidance favors running behind a real process manager and reverse proxy, configuring forwarded headers intentionally, and using Nginx or equivalent for TLS/proxy concerns in self-hosted deployments. Sources: https://fastapi.tiangolo.com/deployment/concepts/ and https://www.uvicorn.org/deployment/
- Playwright screenshots are useful for production UI review because they can capture full pages and individual elements for visual regression checks. Source: https://playwright.dev/docs/screenshots

## Brainstormed Feature Ideas

1. **Prompt starters by data intent**
   Add compact chips for common workflows such as top-N, trend, anomaly, compare periods, segment breakdown, and explain variance. These should fill the composer with editable text rather than auto-submit.

2. **Source context drawer**
   Add a lightweight drawer that shows selected sources, row counts, available tables/sheets/tools, and connection status. This helps users understand what the model can query before asking.

3. **Answer action bar**
   Add per-answer actions for copy summary, copy SQL, rerun, refine chart, ask follow-up, and save to project notes. Keep actions icon-first with accessible labels.

4. **Chart refinement controls**
   Let users switch chart type, x/y fields, aggregation, and sort order after a query result, while preserving the current chart/table toggle behavior.

5. **Analysis memory within projects**
   Let users save useful answers as project notes and surface them when the same project is active. Start local/persisted through existing backend storage rather than adding a new service.

6. **Inline clarification chips**
   When the backend asks for clarification, show polished choices and allow a short typed answer in the same assistant bubble.

7. **Source health indicators**
   Show connected, reconnecting, error, and stale-cache statuses near source chips and in the source drawer.

8. **Mobile command tray**
   On small screens, collapse attach/connect/model/source controls into a command tray so the composer stays compact.

## Recommended Scope

Implement the next wave as **Guided Analysis + Source Context + Answer Actions + Production Guardrails**. This gives the biggest UX lift without deep backend risk:

- Prompt starters make the blank state useful.
- Source context reduces confusion before a query.
- Answer actions make successful results reusable.
- Production guardrails keep the UI efficient, accessible, observable, and safe to deploy.
- Chart refinement and saved project notes can follow once the result/action patterns are stable.

## Efficiency And Production Principles

- Do not add broad state at `page.tsx` unless multiple surfaces truly need it; keep drawer/tray state local to the component that owns the interaction.
- Do not introduce new heavy dependencies for UI polish. Prefer existing React, Tailwind utilities, and lucide-react.
- Memoize only where measurement or obvious expensive rendering warrants it, especially around chart/result components and large source lists.
- Keep all new controls keyboard-accessible, named with `aria-label` when icon-only, and readable against WCAG AA contrast.
- Add tests for every user-facing behavior before implementation.
- Add a production verification checklist for build, tests, service restart, HTTP smoke, and browser-level visual checks.

## Files To Modify

- `frontend/src/components/InputBar.tsx`
  Composer prompt starters, compact command layout, source/model context affordances.
- `frontend/src/components/MessageList.tsx`
  Empty-state starter chips and per-answer action bar placement.
- `frontend/src/components/ResultBlock.tsx`
  Copy SQL and chart/table action integration; later chart refinement controls.
- `frontend/src/components/SourceContextDrawer.tsx`
  New drawer component for selected source metadata.
- `frontend/src/components/AnswerActions.tsx`
  New action bar component for assistant answers and query results.
- `frontend/src/components/__tests__/InputBar.test.tsx`
  Composer starter and command behavior coverage.
- `frontend/src/components/__tests__/MessageList.test.tsx`
  Empty-state starter and answer action coverage.
- `frontend/src/components/__tests__/ResultBlock.test.tsx`
  Copy SQL/action regression coverage if a dedicated test does not already exist.
- `frontend/src/components/__tests__/SourceContextDrawer.test.tsx`
  Drawer rendering and status coverage.
- `frontend/src/lib/types.ts`
  Add UI-only types if needed; avoid backend schema churn unless required.
- `frontend/src/app/global-error.tsx`
  Production fallback UI for uncaught client/runtime errors.
- `frontend/src/app/not-found.tsx`
  Branded fallback for invalid routes if the app starts adding internal routes.
- `frontend/playwright.config.ts`
  Optional visual smoke test setup if browser review becomes part of the CI/deploy path.
- `frontend/src/app/useWebVitals.tsx`
  Optional small client component for reporting Web Vitals to the backend or console in production.

---

## Task 0: Production Baseline And Guardrails

**Files:**
- Create: `frontend/src/app/global-error.tsx`
- Create: `frontend/src/app/not-found.tsx`
- Create: `frontend/src/components/__tests__/ProductionFallbacks.test.tsx`
- Modify: `frontend/next.config.ts`
- Modify: `README.md`

- [ ] **Step 1: Add failing tests for production fallback UI**

```tsx
import { render, screen } from "@testing-library/react";
import GlobalError from "@/app/global-error";
import NotFound from "@/app/not-found";

describe("Production fallbacks", () => {
  it("renders a recovery action for uncaught errors", () => {
    render(<GlobalError error={new Error("boom")} reset={vi.fn()} />);

    expect(screen.getByRole("heading", { name: "Something went wrong" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("renders a useful not found state", () => {
    render(<NotFound />);

    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to chat" })).toHaveAttribute("href", "/");
  });
});
```

- [ ] **Step 2: Run the failing tests**

Run: `cd frontend && npm test -- --run src/components/__tests__/ProductionFallbacks.test.tsx`

Expected: FAIL because the fallback components do not exist.

- [ ] **Step 3: Add `global-error.tsx`**

```tsx
"use client";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html>
      <body>
        <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center" style={{ background: "var(--color-background-primary)", color: "var(--color-text-primary)" }}>
          <h1 className="text-[24px] font-semibold">Something went wrong</h1>
          <p className="max-w-[420px] text-[14px]" style={{ color: "var(--color-text-secondary)" }}>
            The chat workspace hit an unexpected error. Your uploaded sources and saved chats are kept on the server.
          </p>
          <button type="button" onClick={reset} className="rounded-[8px] px-3 py-2 text-[13px]" style={{ background: "var(--color-text-primary)", color: "var(--color-background-primary)" }}>
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
```

- [ ] **Step 4: Add `not-found.tsx`**

```tsx
import Link from "next/link";

export default function NotFound() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-3 px-6 text-center" style={{ background: "var(--color-background-primary)", color: "var(--color-text-primary)" }}>
      <h1 className="text-[24px] font-semibold">Page not found</h1>
      <p className="max-w-[420px] text-[14px]" style={{ color: "var(--color-text-secondary)" }}>
        This route is not part of the Data Chat workspace.
      </p>
      <Link href="/" className="rounded-[8px] px-3 py-2 text-[13px]" style={{ background: "var(--color-text-primary)", color: "var(--color-background-primary)" }}>
        Back to chat
      </Link>
    </main>
  );
}
```

- [ ] **Step 5: Add production config notes**

In `frontend/next.config.ts`, keep production browser source maps disabled:

```ts
const nextConfig: NextConfig = {
  productionBrowserSourceMaps: false,
};
```

In `README.md`, add a short section:

```md
### Production UI Guardrails

- Run `cd frontend && npm run build` before deploying.
- Keep `.env*` files untracked; only expose client variables with `NEXT_PUBLIC_`.
- Use the VPS build step after rsync because `.next` is excluded from sync.
- Run the frontend smoke check: `ssh datachat-vps 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/'`.
```

- [ ] **Step 6: Verify**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/ProductionFallbacks.test.tsx
npm run build
```

Expected: PASS.

## Task 1: Prompt Starters

**Files:**
- Modify: `frontend/src/components/InputBar.tsx`
- Modify: `frontend/src/components/MessageList.tsx`
- Test: `frontend/src/components/__tests__/InputBar.test.tsx`
- Test: `frontend/src/components/__tests__/MessageList.test.tsx`

- [ ] **Step 1: Add failing InputBar test for inserting starter text**

```tsx
it("inserts a prompt starter without submitting", () => {
  const onSend = vi.fn();
  render(
    <InputBar
      onSend={onSend}
      onPickFile={vi.fn()}
      onAttached={vi.fn()}
      disabled={false}
      promptStarters={[{ label: "Top 10", prompt: "Show top 10 customers by revenue" }]}
    />,
  );

  fireEvent.click(screen.getByRole("button", { name: "Top 10" }));

  expect(screen.getByDisplayValue("Show top 10 customers by revenue")).toBeInTheDocument();
  expect(onSend).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run the focused failing test**

Run: `cd frontend && npm test -- --run src/components/__tests__/InputBar.test.tsx`

Expected: FAIL because `promptStarters` is not yet supported.

- [ ] **Step 3: Implement `promptStarters` in InputBar**

Add this prop:

```tsx
promptStarters?: Array<{ label: string; prompt: string }>;
```

Render chips above the textarea when provided:

```tsx
{promptStarters.length > 0 && !value && (
  <div className="flex flex-wrap gap-1.5">
    {promptStarters.map((starter) => (
      <button
        key={starter.label}
        type="button"
        onClick={() => setValue(starter.prompt)}
        className="rounded-full px-2.5 py-1 text-[12px]"
        style={{
          background: "var(--color-background-primary)",
          border: "0.5px solid var(--color-border-tertiary)",
          color: "var(--color-text-secondary)",
        }}
      >
        {starter.label}
      </button>
    ))}
  </div>
)}
```

- [ ] **Step 4: Move empty-state quick prompts to use the same starter data**

Define a shared constant in `MessageList.tsx`:

```tsx
const DEFAULT_PROMPT_STARTERS = [
  { label: "Top 10", prompt: "Show top 10 customers by revenue" },
  { label: "Trend", prompt: "Show revenue trend by month" },
  { label: "Anomalies", prompt: "Find unusual changes in this data" },
  { label: "Compare", prompt: "Compare this period against the previous period" },
];
```

Use labels in the empty state and pass the full starter list down from `page.tsx` to `InputBar`.

- [ ] **Step 5: Verify**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/InputBar.test.tsx src/components/__tests__/MessageList.test.tsx
```

Expected: PASS.

---

## Task 2: Source Context Drawer

**Files:**
- Create: `frontend/src/components/SourceContextDrawer.tsx`
- Modify: `frontend/src/components/InputBar.tsx`
- Test: `frontend/src/components/__tests__/SourceContextDrawer.test.tsx`
- Test: `frontend/src/components/__tests__/InputBar.test.tsx`

- [ ] **Step 1: Add failing drawer test**

```tsx
import { render, screen } from "@testing-library/react";
import { SourceContextDrawer } from "../SourceContextDrawer";
import type { Source } from "@/lib/types";

const sources: Source[] = [
  { id: "s1", name: "orders.csv", kind: "csv", rows: 21350, active: true },
  { id: "s2", name: "mysql", kind: "mcp", rows: 78, active: true },
];

it("summarizes selected sources with kind and row or tool counts", () => {
  render(<SourceContextDrawer open sources={sources} onClose={vi.fn()} />);

  expect(screen.getByRole("dialog", { name: "Selected sources" })).toBeInTheDocument();
  expect(screen.getByText("orders.csv")).toBeInTheDocument();
  expect(screen.getByText("21,350 rows")).toBeInTheDocument();
  expect(screen.getByText("mysql")).toBeInTheDocument();
  expect(screen.getByText("78 tools")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused failing test**

Run: `cd frontend && npm test -- --run src/components/__tests__/SourceContextDrawer.test.tsx`

Expected: FAIL because the component does not exist.

- [ ] **Step 3: Implement the drawer**

Create `SourceContextDrawer.tsx`:

```tsx
"use client";

import { X } from "lucide-react";
import type { Source } from "@/lib/types";

interface SourceContextDrawerProps {
  open: boolean;
  sources: Source[];
  onClose: () => void;
}

export function SourceContextDrawer({ open, sources, onClose }: SourceContextDrawerProps) {
  if (!open) return null;

  return (
    <div role="dialog" aria-label="Selected sources" className="absolute bottom-full right-0 mb-2 w-[min(420px,calc(100vw-32px))] rounded-[12px] p-3 shadow-lg" style={{ background: "var(--color-background-elevated)", border: "0.5px solid var(--color-border-primary)" }}>
      <div className="mb-2 flex items-center justify-between">
        <div className="text-[13px] font-medium" style={{ color: "var(--color-text-primary)" }}>Selected sources</div>
        <button type="button" onClick={onClose} aria-label="Close selected sources" className="rounded-[8px] p-1 hover:bg-black/5">
          <X size={14} />
        </button>
      </div>
      <div className="flex flex-col gap-1.5">
        {sources.map((source) => (
          <div key={source.id} className="flex items-center justify-between gap-3 rounded-[8px] px-2 py-1.5" style={{ background: "var(--color-background-secondary)" }}>
            <div className="min-w-0">
              <div className="truncate text-[12.5px]" style={{ color: "var(--color-text-primary)" }}>{source.name}</div>
              <div className="text-[11.5px] uppercase" style={{ color: "var(--color-text-tertiary)" }}>{source.kind}</div>
            </div>
            <div className="flex-shrink-0 text-[12px]" style={{ color: "var(--color-text-secondary)" }}>
              {source.rows.toLocaleString()} {source.kind === "mcp" ? "tools" : "rows"}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire drawer to InputBar source chip**

Add local state:

```tsx
const [sourceDrawerOpen, setSourceDrawerOpen] = useState(false);
```

Change the source chip wrapper to a button:

```tsx
<button type="button" onClick={() => setSourceDrawerOpen((open) => !open)} aria-label="Show selected sources">
  ...
</button>
<SourceContextDrawer open={sourceDrawerOpen} sources={selectedSources} onClose={() => setSourceDrawerOpen(false)} />
```

- [ ] **Step 5: Verify**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/SourceContextDrawer.test.tsx src/components/__tests__/InputBar.test.tsx
```

Expected: PASS.

---

## Task 3: Answer Actions

**Files:**
- Create: `frontend/src/components/AnswerActions.tsx`
- Modify: `frontend/src/components/MessageList.tsx`
- Modify: `frontend/src/components/ResultBlock.tsx`
- Test: `frontend/src/components/__tests__/MessageList.test.tsx`
- Test: `frontend/src/components/__tests__/ResultBlock.test.tsx`

- [ ] **Step 1: Add failing MessageList test for copy answer action**

```tsx
it("shows answer actions for assistant text", () => {
  render(
    <MessageList
      messages={[{ id: "a1", role: "assistant", content: "Revenue increased by 12%." }]}
      loading={false}
      onPendingChoice={vi.fn()}
      onPickFile={vi.fn()}
      onConnectClick={vi.fn()}
    />,
  );

  expect(screen.getByRole("button", { name: "Copy answer" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused failing test**

Run: `cd frontend && npm test -- --run src/components/__tests__/MessageList.test.tsx`

Expected: FAIL because answer actions do not exist.

- [ ] **Step 3: Implement AnswerActions**

Create `AnswerActions.tsx`:

```tsx
"use client";

import { Copy, RotateCcw } from "lucide-react";

interface AnswerActionsProps {
  content?: string;
  onRerun?: () => void;
}

export function AnswerActions({ content, onRerun }: AnswerActionsProps) {
  return (
    <div className="mt-2 flex items-center gap-1">
      {content && (
        <button type="button" aria-label="Copy answer" title="Copy answer" onClick={() => navigator.clipboard?.writeText(content)} className="rounded-[8px] p-1.5 hover:bg-black/5" style={{ color: "var(--color-text-secondary)" }}>
          <Copy size={13} />
        </button>
      )}
      {onRerun && (
        <button type="button" aria-label="Rerun" title="Rerun" onClick={onRerun} className="rounded-[8px] p-1.5 hover:bg-black/5" style={{ color: "var(--color-text-secondary)" }}>
          <RotateCcw size={13} />
        </button>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Render AnswerActions below assistant text**

In `MessageList.tsx`, render:

```tsx
{message.content && !message.error && !message.streaming && (
  <AnswerActions content={message.content} />
)}
```

Keep it outside `ResultBlock` so chart/table controls remain unchanged.

- [ ] **Step 5: Add ResultBlock copy SQL regression**

If `ResultBlock` already has copy/download controls, add a test that verifies existing titles still render after `AnswerActions` is introduced:

```tsx
expect(screen.getByTitle("Download CSV")).toBeInTheDocument();
expect(screen.getByTitle("Show table")).toBeInTheDocument();
```

- [ ] **Step 6: Verify**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/MessageList.test.tsx src/components/__tests__/ResultBlock.test.tsx
```

Expected: PASS.

---

## Task 4: Mobile Command Tray

**Files:**
- Modify: `frontend/src/components/InputBar.tsx`
- Test: `frontend/src/components/__tests__/InputBar.test.tsx`

- [ ] **Step 1: Add failing test for compact command tray trigger**

```tsx
it("renders a mobile command tray trigger for composer tools", () => {
  render(
    <InputBar
      onSend={vi.fn()}
      onPickFile={vi.fn()}
      onAttached={vi.fn()}
      disabled={false}
    />,
  );

  expect(screen.getByRole("button", { name: "Open composer tools" })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run the focused failing test**

Run: `cd frontend && npm test -- --run src/components/__tests__/InputBar.test.tsx`

Expected: FAIL because the tray trigger does not exist.

- [ ] **Step 3: Implement mobile-only trigger**

Use a lucide `SlidersHorizontal` or `PanelBottomOpen` icon. Keep existing controls visible on `sm` and larger:

```tsx
<button type="button" aria-label="Open composer tools" className="inline-flex sm:hidden ...">
  <SlidersHorizontal size={14} />
</button>
<div className="hidden sm:flex ...">
  existing attach/connect/model/source controls
</div>
```

- [ ] **Step 4: Render tray content**

When open, render a small absolute panel above the composer with Attach, Connect, Model, and Source Context controls. Reuse existing handlers and state.

- [ ] **Step 5: Verify**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/InputBar.test.tsx
npm run build
```

Expected: PASS.

---

## Task 5: Performance Measurement And Visual Smoke

**Files:**
- Create: `frontend/src/app/WebVitalsReporter.tsx`
- Modify: `frontend/src/app/layout.tsx`
- Create: `frontend/src/components/__tests__/WebVitalsReporter.test.tsx`
- Optional create: `frontend/playwright.config.ts`
- Optional create: `frontend/e2e/chat-ui.spec.ts`

- [ ] **Step 1: Add failing test for Web Vitals reporter**

```tsx
import { render } from "@testing-library/react";
import { WebVitalsReporter } from "@/app/WebVitalsReporter";

vi.mock("next/web-vitals", () => ({
  useReportWebVitals: (callback: (metric: { name: string; value: number }) => void) => {
    callback({ name: "INP", value: 120 });
  },
}));

it("reports web vitals through the provided callback", () => {
  const onMetric = vi.fn();

  render(<WebVitalsReporter onMetric={onMetric} />);

  expect(onMetric).toHaveBeenCalledWith({ name: "INP", value: 120 });
});
```

- [ ] **Step 2: Run the failing test**

Run: `cd frontend && npm test -- --run src/components/__tests__/WebVitalsReporter.test.tsx`

Expected: FAIL because `WebVitalsReporter` does not exist.

- [ ] **Step 3: Implement WebVitalsReporter**

```tsx
"use client";

import { useReportWebVitals } from "next/web-vitals";

interface WebVitalsReporterProps {
  onMetric?: (metric: { name: string; value: number; id?: string; rating?: string }) => void;
}

export function WebVitalsReporter({ onMetric }: WebVitalsReporterProps) {
  useReportWebVitals((metric) => {
    if (onMetric) {
      onMetric(metric);
      return;
    }
    if (process.env.NODE_ENV === "production") {
      console.info("[web-vital]", metric.name, metric.value, metric.rating);
    }
  });

  return null;
}
```

- [ ] **Step 4: Mount reporter in layout**

In `frontend/src/app/layout.tsx`, render `<WebVitalsReporter />` inside `<body>` after `{children}`. Keep it as the only extra client component in the root layout.

- [ ] **Step 5: Add bundle and visual review commands to package scripts**

If bundle analysis is needed, add a separate optional dependency and script in a dedicated task. Do not add bundle tooling by default. For this plan, document these commands:

```bash
cd frontend
npm run build
npm exec next info
```

- [ ] **Step 6: Optional Playwright visual smoke**

Only add Playwright if the project accepts the dependency. If approved, create `frontend/e2e/chat-ui.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test("chat shell renders without overlap on desktop and mobile", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Data Chat")).toBeVisible();
  await expect(page.getByRole("textbox")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("textbox")).toBeVisible();
  await page.screenshot({ path: "test-results/chat-mobile.png", fullPage: true });
});
```

- [ ] **Step 7: Verify**

Run:

```bash
cd frontend
npm test -- --run src/components/__tests__/WebVitalsReporter.test.tsx
npm run build
```

Expected: PASS.

---

## Task 6: Deployment Hardening Checklist

**Files:**
- Modify: `README.md`
- Optional modify: deployment notes or `AGENTS.md` if the team wants operational commands copied there.

- [ ] **Step 1: Document production deploy checks**

Add this section to `README.md`:

```md
## Production Readiness Checklist

Before each VPS deploy:

- `cd frontend && npm test`
- `cd frontend && npm run build`
- `.venv/bin/python -m pytest -q`
- `rsync` with `/tmp/datachat-rsync-excludes`
- `ssh datachat-vps 'cd /opt/datachat/frontend && npm run build'`
- Restart `datachat-backend.service` and `datachat-frontend.service`
- Confirm both services are `active (running)`
- Confirm frontend local smoke check returns `200`

Operational notes:

- Keep `.env`, `.env.local`, `.env.production`, and connector secrets out of git.
- Keep Nginx as the reverse proxy in front of Next.js and FastAPI.
- If public HTTPS/proxy behavior changes, verify forwarded headers and public URLs before shipping.
- Treat Web Vitals regressions and failed smoke checks as release blockers.
```

- [ ] **Step 2: Add rollback note**

Add:

```md
Rollback:

1. `ssh datachat-vps 'cd /opt/datachat && git status --short'`
2. Re-sync the last known good local commit or restore from the VPS backup/worktree.
3. Rebuild frontend with `cd /opt/datachat/frontend && npm run build`.
4. Restart both services and run the `200` smoke check.
```

- [ ] **Step 3: Verify docs and config**

Run:

```bash
git diff --check
rg -n 'API[_-]?KEY\s*=|PASS(WORD)?\s*=|SECRET\s*=' README.md docs frontend/src backend src tests
```

Expected: no whitespace errors, no placeholders, and no committed secrets.

---

## Task 7: Final Verification And Deploy

**Files:**
- No new files.

- [ ] **Step 1: Run full frontend tests**

Run:

```bash
cd frontend
npm test
```

Expected: all Vitest files pass.

- [ ] **Step 2: Run production build**

Run:

```bash
cd frontend
npm run build
```

Expected: Next.js build completes with exit code 0.

- [ ] **Step 3: Run backend tests**

Run:

```bash
.venv/bin/python -m pytest -q
```

Expected: all backend/core tests pass.

- [ ] **Step 4: Deploy to VPS**

Run:

```bash
rsync -az --stats --exclude-from=/tmp/datachat-rsync-excludes \
  -e "ssh -F /Users/rajasekharbandreddy/.ssh/config" \
  ./ datachat-vps:/opt/datachat/
ssh datachat-vps 'cd /opt/datachat/frontend && npm run build'
ssh datachat-vps systemctl restart datachat-backend.service
ssh datachat-vps systemctl restart datachat-frontend.service
ssh datachat-vps systemctl status datachat-backend.service --no-pager
ssh datachat-vps systemctl status datachat-frontend.service --no-pager
ssh datachat-vps 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3000/'
```

Expected: both services are active and the frontend smoke check returns `200`.

## Self-Review

- No placeholders remain.
- The plan is frontend-first and does not require new backend contracts for the first two tasks.
- Result/chart behavior remains isolated in `ResultBlock`.
- The plan includes focused red-green tests for each behavior and a final deploy checklist.
