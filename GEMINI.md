# Data Analysis Chatbot - Engineering Mandates

## 🏗️ Architecture: Observability & Quality
- **Tracing**: Every LLM interaction MUST be instrumented with OpenTelemetry.
  - Parent span: `query` in `backend/server.py`.
  - Child spans: `classify_intent`, `build_query_plan`, `summarize_answer` in `LLMRouter`.
  - Agentic spans: `agent_loop`, `agent_round_X`.
  - Judge spans: `faithfulness_judge`, `benchmark_judge`.
- **Trace Propagation**: Background tasks (Evaluators) MUST inherit the parent trace context via `attach/detach` to ensure nested diagnostic trees in Arize Phoenix.
- **Auto-Grading**: All benchmark runs in the 'Testing Gateway' MUST trigger the AI-Judge for automated correctness and faithfulness scoring.

## 🎨 UI/UX: High-Fidelity Standards
- **Aesthetic**: Modern 'Glassmorphism' using the `.glass` utility (`backdrop-blur`, semi-transparent backgrounds).
- **Flow**: Chat interactions MUST follow a 'bottom-up' anchored flow (`justify-end` in `MessageList`).
- **Control Center**: The Admin area is a unified, tabbed 'Control Center' (Insights, Observability, Testing Gateway).
- **Branding**: Use `LayoutGrid` for Admin links and maintain a professional 'Grade-A' typography (0.2em tracking for labels).

## 🚀 Operations: VPS Stability (4GB RAM)
- **Observability**: Use **Arize Phoenix Cloud** (OTLP export) to avoid RAM overhead on the VPS.
- **Monitoring**: Always display VPS Infrastructure Health (CPU, RAM, Disk) in the Insights dashboard.
- **Maintenance**: Safe cache management via the `/admin/maintenance/clear-cache` endpoint.
- **Deployment**: Rebuild the frontend (`npm run build`) on the VPS after every `rsync` sync to ensure production optimizations.

## 🧪 Testing & Verification
- **Regression**: Any change to intent parsing or SQL generation MUST be verified with a benchmark run in the Testing Gateway.
- **Unit Tests**:
  - Backend: `tests/test_observability.py`
  - Frontend: `frontend/src/components/__tests__/AdminDashboard.test.tsx`, `ObservabilityDashboard.test.tsx`
