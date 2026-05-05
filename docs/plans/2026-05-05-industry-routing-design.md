# Intelligent Industry Routing Design

## Overview
To provide tailored functionality and user experiences for different industries (e.g., Education, Sales, Logistics) without polluting a single monolithic codebase, we are moving to a **Sub-Agent Swarm** architecture. This system automatically classifies incoming data and routes user queries to specialized domain agents capable of rendering bespoke UI components.

## 1. Architecture and Routing Flow
- **Upfront Profiling:** When a dataset is ingested (e.g., an Excel file is uploaded or an MCP bridge is connected), a lightweight **Profiler Meta-Agent** runs in the background. It analyzes the column names, data types, and a small row sample.
- **Domain Tagging:** The Profiler classifies the dataset into an `industry_domain` (e.g., `Education`, `Retail`, `Financial`, `Logistics`, or `Generic`) and saves this tag to the project's metadata in the database.
- **Expert Handoff:** Upon receiving a user query, the backend inspects the active project's `industry_domain`. Instead of executing a monolithic agent, it dynamically delegates the task to the appropriate sub-agent (e.g., `EducationAgent`).
- **Specialized Context:** The sub-agent operates with an industry-specific system prompt, specialized Python formatters, and unique constraints optimized for its domain.

## 2. Data Flow, Extensibility & UI
- **The Agent Registry:** A new `src/agents/` directory will house the `AgentRegistry`. Adding a new industry requires only creating a new file (e.g., `retail_agent.py`) that implements a standard `DomainAgent` base class.
- **Specialized Tools:** Each domain sub-agent can inject custom, domain-specific tools (e.g., `generate_pnl_statement` for Finance or `pivot_timetable` for Education) into its execution loop.
- **UI Signaling:** When a sub-agent completes a task, it attaches a specific `view_type` to the final SSE result payload (e.g., `view: "timetable"`, `view: "pipeline_board"`).
- **Dynamic Frontend Rendering:** The React frontend’s `ResultBlock` acts as a component router. It reads the `view_type` and maps it to bespoke, highly-styled React components, falling back to a standard `DataTable` if a custom component isn't available.

## 3. Fallbacks, Cross-Domain Queries, & Testing
- **Graceful Fallbacks:** If the Profiler Agent cannot confidently classify a dataset, it defaults to a `GenericAgent`, which mirrors the current baseline functionality.
- **UI Degradation:** If a sub-agent requests a highly specific view (e.g., `view: "3d_supply_chain"`) but the corresponding React component is not yet deployed, the frontend gracefully degrades to render the data using the standard `DataTable` or `BarViz`.
- **Cross-Domain Queries:** For questions spanning multiple datasets from different domains, the `MultiSourceAgent` takes over. It delegates data-fetching to individual domain sub-agents, aggregates the results, and presents them using a generic view.
- **Testing Strategy:** The existing `pytest` setup will be expanded with mock schemas to ensure the Profiler accurately categorizes datasets and that each sub-agent outputs the correct `view_type` payload.
