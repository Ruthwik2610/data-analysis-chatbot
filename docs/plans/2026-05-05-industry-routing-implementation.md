# Intelligent Industry Routing Implementation Plan

> **For Gemini:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform the monolithic data agent into a specialized "swarm" of industry experts that provide tailored tools, prompts, and UI components based on the uploaded data.

**Architecture:** A lightweight `ProfilerAgent` classifies datasets upon ingestion (or first query). Queries are then routed to domain-specific sub-agents (e.g., `EducationAgent`) that return both data and a `view_type` signal to the frontend for specialized rendering.

**Tech Stack:** Python (FastAPI, DuckDB), React (TypeScript), LLM (DeepSeek/Gemini for reasoning).

---

## Phase 0: What was Implemented (Foundation)

These tasks were completed in the previous turns to prepare the system for intelligent routing.

### Task 1: DSML Leakage Prevention
**Status:** DONE
- **Files:** `backend/server.py`
- **Logic:** Implemented real-time chunk filtering to prevent `<｜｜DSML` tags from appearing in the UI stream. Added `_sanitize_assistant_text` to clean persisted messages.

### Task 2: SQL Header Sanitization
**Status:** DONE
- **Files:** `backend/server.py`, `tests/test_output_sanitizer.py`
- **Logic:** Implemented `_clean_column_name` to strip raw SQL functions (e.g., `MAX(CASE...)`) from table headers, providing a clean "Education Timetable" look.

### Task 3: Routing Safeguards
**Status:** DONE
- **Files:** `backend/server.py`, `src/prompting.py`
- **Logic:** Updated the `query` endpoint and intent prompts to explicitly prevent local table queries from falling back to unrelated MCP agents (fixing the `rapidai` hallucination bug).

---

## Phase 1: The Domain Agent Swarm (To be Implemented)

### Task 4: Define Domain Agent Registry
**Goal:** Create a plug-and-play directory for industry experts.

**Files:**
- Create: `src/agents/__init__.py`
- Create: `src/agents/base.py`
- Create: `src/agents/education.py`
- Modify: `backend/server.py`

**Step 1: Create the Base Domain Agent class**
```python
class DomainAgent:
    def __init__(self, domain: str):
        self.domain = domain
    def get_system_prompt(self) -> str: ...
    def get_tools(self) -> list[dict]: ...
```

**Step 2: Implement `EducationAgent`**
Define specialized prompts for timetables and scheduling.

**Step 3: Commit**
`git add src/agents/ && git commit -m "feat: add domain agent registry and education agent"`

### Task 5: Implement Profiler Agent
**Goal:** Automatically classify datasets into domains.

**Files:**
- Modify: `src/project_intelligence.py`
- Test: `tests/test_profiler.py`

**Step 1: Write a failing test for classification**
Upload a timetable CSV and expect `domain == "education"`.

**Step 2: Implement `ProfilerAgent.classify_source(source)`**
Use the LLM to inspect columns (e.g., `class`, `period`, `teacher`) and return a domain tag.

**Step 3: Update database schema**
Modify `storage.py` or the project metadata to persist the `industry_domain` tag.

**Step 4: Commit**
`git add src/project_intelligence.py && git commit -m "feat: implement data profiler agent"`

### Task 6: Dynamic UI View Routing
**Goal:** Enable the frontend to render different components based on the agent's signal.

**Files:**
- Modify: `backend/server.py`
- Modify: `frontend/src/components/ResultBlock.tsx`

**Step 1: Update result payload in Backend**
Include `view_type: "timetable"` in the result payload when the `EducationAgent` is active.

**Step 2: Update `ResultBlock.tsx`**
```tsx
if (result.view_type === "timetable") {
  return <TimetableGrid data={result} />;
}
```

**Step 3: Commit**
`git add backend/server.py frontend/src/components/ResultBlock.tsx && git commit -m "feat: add frontend view routing"`

---

## Phase 2: Refinement & Validation

### Task 7: E2E Verification
**Goal:** Ensure a timetable question now results in a "Timetable" view without any manual configuration.

**Steps:**
1. Upload a scheduling file.
2. Ask "What is the schedule for Teacher X?".
3. Verify the `ResultBlock` detects the `view_type` and renders accordingly.
4. Run all tests: `pytest`.
