# Technical Blueprint — Healthcare Multi-Agent System (MAS)

> **Document Classification:** Academic Reference — TCC Ground Truth
> **Architecture Pattern:** Hierarchical Federated Orchestrator-Workers with Observer
> **Protocol:** Model Context Protocol (MCP) over HTTP / JSON-RPC 2.0
> **Version:** 1.0.0

---

## Table of Contents

1. [Architectural Definition (Formal)](#1-architectural-definition-formal)
2. [Component Specifications](#2-component-specifications)
3. [Privacy & Security Strategy](#3-privacy--security-strategy)
4. [Evaluation Metrics Strategy](#4-evaluation-metrics-strategy)
5. [Implementation Roadmap](#5-implementation-roadmap)

---

## 1. Architectural Definition (Formal)

### 1.1 Pattern Classification

This system implements the **Hierarchical Federated Orchestrator-Workers with Observer** pattern, a composite multi-agent architecture that combines three established paradigms:

| Paradigm | Role in this System | Theoretical Basis |
|---|---|---|
| **Hierarchical Coordination** | The Orchestrator Host decomposes high-level goals into atomic sub-tasks and delegates them downward. Workers (Clinic Agents) have no awareness of sibling agents or the global task plan. | Centralized control with decentralized execution. |
| **Federated Data Architecture** | Each Clinic Agent operates as an isolated data silo. Patient records are never transmitted in raw form; only query results cross the process boundary. | Privacy-by-Design; Data Minimization (LGPD/GDPR). |
| **Observer Agent** | An independent Verifier audits every aggregated response against safety rules before it reaches the end-user, implementing a deterministic validation gate. | Burke et al. (2024), "Observer Agents for Safe Multi-Agent Medical Systems." |

### 1.2 Orchestrator Host (MCP Client)

The Orchestrator is the sole component with a **global view** of the user's intent. It contains three internal modules that execute sequentially:

| Module | Responsibility | Classification |
|---|---|---|
| **Planner** | **Task Decomposition** — receives the natural-language query and uses Azure OpenAI (temperature 0.0) to produce a deterministic JSON step graph. Each step is atomic and scoped to exactly one clinic. | LLM-assisted planning with constrained output. |
| **Router** | **Dynamic Routing** — maintains a registry of clinic endpoints and dispatches each step via HTTP POST following the MCP JSON-RPC 2.0 envelope. The Router is the only module aware of the network topology. | Registry-based service dispatch. |
| **Verifier** | **Safety Guardrails & Hallucination Mitigation** — acts as the Observer Agent (Burke et al. 2024). Validates aggregated results against three deterministic rules: (1) no fabricated dosages, (2) no PII leakage, (3) no out-of-scope recommendations. | Independent post-processing audit layer. |

### 1.3 MCP Servers (Clinic Agents — Workers)

Each Clinic Agent is a **domain-specialized** FastAPI application exposing a single `/mcp` endpoint. Clinics embody two core principles:

- **Domain Specialization:** Clinic A handles Cardiology; Clinic B handles Dermatology. Each exposes only tools relevant to its medical domain, preventing scope creep.
- **Data Silos / Federation:** Patient databases are hardcoded within each server process. No shared database, no shared file system, no inter-clinic communication channel exists. This enforces **Privacy Preservation** at the infrastructure level — a clinic cannot access another clinic's data even if compromised.

### 1.4 Hub-and-Spoke Topology (Mermaid Diagram)

```mermaid
graph TD
    User([fa:fa-user End-User / Operator])

    subgraph Orchestrator Host — MCP Client
        Planner[fa:fa-project-diagram Planner<br/><i>Task Decomposition</i><br/>Azure OpenAI · temp 0.0]
        Router[fa:fa-route Router<br/><i>Dynamic Routing</i><br/>Registry-based dispatch]
        Verifier[fa:fa-shield-alt Verifier<br/><i>Observer Agent</i><br/>Safety Guardrails]
    end

    subgraph Federated Data Silos
        ClinicA[fa:fa-heartbeat Clinic A<br/><b>Cardiology</b><br/>FastAPI · Port 8001<br/>MCP Server]
        ClinicB[fa:fa-allergies Clinic B<br/><b>Dermatology</b><br/>FastAPI · Port 8002<br/>MCP Server]
    end

    User -->|Natural language query| Planner
    Planner -->|Step graph JSON| Router
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicA
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicB
    ClinicA -->|MCPResponse| Router
    ClinicB -->|MCPResponse| Router
    Router -->|Aggregated results| Verifier
    Verifier -->|"safe: true / false"| User

    style Planner fill:#4a90d9,color:#fff
    style Router fill:#7b68ee,color:#fff
    style Verifier fill:#e74c3c,color:#fff
    style ClinicA fill:#27ae60,color:#fff
    style ClinicB fill:#f39c12,color:#fff
```

> **Topology rationale:** The Hub-and-Spoke model ensures **Decoupling** between clinic agents. Adding a new specialty (e.g., Clinic C — Neurology) requires only registering a new URL in the Router's registry and deploying a new MCP Server. No existing clinic code is modified, satisfying the Open-Closed Principle.

---

## 2. Component Specifications

### 2.1 Technology Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.9+ | Core runtime |
| Web Framework | FastAPI | latest | MCP Server endpoints (Clinic Agents) |
| ASGI Server | Uvicorn | latest | Production-grade async server |
| LLM SDK | `openai` (AzureOpenAI) | latest | Planner & Verifier reasoning |
| Data Validation | Pydantic | v2 | MCPRequest / MCPResponse schemas |
| HTTP Client | Requests | latest | Router → Clinic dispatch |
| Configuration | python-dotenv | latest | Environment variable management |

### 2.2 Protocol Specification: MCP over HTTP (JSON-RPC 2.0)

All inter-agent communication follows the **Model Context Protocol** transported over HTTP using the JSON-RPC 2.0 envelope.

**Request Schema** (`shared/mcp_types.py` — `MCPRequest`):

```json
{
    "jsonrpc": "2.0",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "method": "tools/call",
    "params": {
        "name": "get_patient",
        "arguments": {
            "patient_id": "CARD-001"
        }
    }
}
```

| Field | Type | Description |
|---|---|---|
| `jsonrpc` | `str` | Protocol version. Always `"2.0"`. |
| `id` | `str` | UUID v4 generated by the Router. Enables request-response correlation. |
| `method` | `str` | MCP method. Currently only `"tools/call"` is supported. |
| `params.name` | `str` | Exact tool name registered on the target clinic server. |
| `params.arguments` | `dict` | Key-value parameters forwarded to the tool handler. |

**Response Schema** (`shared/mcp_types.py` — `MCPResponse`):

```json
{
    "jsonrpc": "2.0",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "result": { "patient": { "patient_id": "CARD-001", "condition": "Hypertension" } },
    "error": null
}
```

| Field | Type | Description |
|---|---|---|
| `id` | `str` | Mirrors the request `id` for correlation. |
| `result` | `Any \| null` | Successful payload. Present when `error` is `null`. |
| `error` | `dict \| null` | JSON-RPC error object with `code` and `message`. |

**Standardized Error Codes:**

| Code | Meaning | Trigger |
|---|---|---|
| `-32601` | Method not found | Unsupported MCP method or unknown clinic in registry |
| `-32602` | Invalid params | Unknown tool name on the clinic server |
| `-32000` | Server error | Network failure during HTTP dispatch |

### 2.3 Key Algorithms

#### 2.3.1 Planner Logic — LLM-Assisted Step-Graph Decomposition

**File:** `orchestrator_host/planner.py`

The Planner converts a natural-language healthcare query into an executable **step graph** — an ordered JSON array where each element represents one atomic operation on one clinic.

```
Input:  "List all cardiology patients and check dermatology patients with psoriasis"
         │
         ▼
   ┌─────────────────────────────────────┐
   │  Azure OpenAI (gpt-4o, temp=0.0)   │
   │  System Prompt: constrained schema  │
   │  + clinic registry + tool catalog   │
   └─────────────────────────────────────┘
         │
         ▼
Output: [
          {"step_id": 1, "clinic": "clinic_a", "action": "list_patients", "parameters": {}},
          {"step_id": 2, "clinic": "clinic_b", "action": "query", "parameters": {"query": "psoriasis"}}
        ]
```

**Deterministic constraints enforced via system prompt:**
1. Only clinics present in the registry may be referenced.
2. Only tool names from the exact catalog (`list_patients`, `get_patient`, `check_medications`, `query`) are permitted.
3. Each step is scoped to a single clinic — **no cross-clinic joins** in a single step (Privacy Preservation).
4. Output is strictly JSON with no markdown fences or natural-language commentary.
5. Temperature is set to `0.0` to minimize non-determinism.

**Fallback mechanism:** If the LLM returns unparseable JSON, the Planner wraps the raw output in a fallback step (`action: "raw_response"`) so the pipeline does not crash.

#### 2.3.2 Verifier Logic — Observer Agent Deterministic Validation

**File:** `orchestrator_host/verifier.py`
**Reference:** Burke et al. (2024)

The Verifier receives the **aggregated results** from all dispatched steps and validates them against three deterministic safety rules:

| Rule # | Check | Rationale |
|---|---|---|
| R1 | Response does NOT contain fabricated drug dosages or treatment plans ungrounded in clinic data. | **Hallucination Mitigation** — prevents the LLM from inventing medical information. |
| R2 | Response does NOT expose Personally Identifiable Information (full names, government IDs, addresses). | **Privacy Preservation** — enforces Data Minimization at the output layer. |
| R3 | Response does NOT recommend actions outside the agent's scope (e.g., diagnosing without a physician). | **Safety Guardrails** — prevents liability-creating medical advice. |

**Validation output schema:**

```json
{"safe": true,  "note": "OK"}
{"safe": false, "note": "Response contains fabricated dosage for Amiodarone."}
```

**Pipeline behavior:**
- `safe: true` → results are displayed to the end-user.
- `safe: false` → results are **blocked**; only the `note` explaining the violation is shown.

#### 2.3.3 Tool Call Flow — End-to-End Sequence

```
 User                  Planner             Router              Clinic A           Verifier
  │                      │                   │                    │                  │
  │── query ────────────>│                   │                    │                  │
  │                      │── step graph ────>│                    │                  │
  │                      │                   │── MCPRequest ─────>│                  │
  │                      │                   │   POST /mcp        │                  │
  │                      │                   │   JSON-RPC 2.0     │                  │
  │                      │                   │<── MCPResponse ────│                  │
  │                      │                   │                    │                  │
  │                      │                   │── aggregated ─────────────────────────>│
  │                      │                   │                    │                  │
  │<─────────────────────────────────────────── safe/blocked ─────────────────────── │
```

### 2.4 Available Tools per Clinic

Both clinics expose an identical tool interface, differentiated only by the underlying domain data:

| Tool | Parameters | Returns | Privacy Note |
|---|---|---|---|
| `list_patients` | *(none)* | `{"patients": [{"patient_id", "condition"}]}` | Returns only IDs and conditions — **no names or PII**. |
| `get_patient` | `patient_id: str` | `{"patient": {full record}}` | Full record scoped to single patient. |
| `check_medications` | `patient_id: str` | `{"patient_id", "medications": [...]}` | Medication list only. |
| `query` | `query: str` | `{"specialty", "query", "matches": [...]}` | Free-text search; returns IDs and conditions only. |

---

## 3. Privacy & Security Strategy

### 3.1 Privacy-by-Design

The architecture enforces privacy at **four structural layers**, making data leakage a violation of system boundaries rather than a policy choice:

```
Layer 1 — Process Isolation       Each clinic runs as a separate OS process.
                                  No shared memory, no shared filesystem.

Layer 2 — Network Scoping         The Router dispatches one request per clinic.
                                  No JSON-RPC payload ever references two clinics.

Layer 3 — Data Minimization       list_patients and query return only patient_id
                                  and condition. Full records require explicit
                                  get_patient calls with a known ID.

Layer 4 — Output Verification     The Verifier (Observer Agent) scans aggregated
                                  results for PII before they reach the user.
```

### 3.2 Data Residency

Patient data (simulated in each clinic's hardcoded database) **remains local** to the Clinic Agent process at all times:

- The Orchestrator Host **does not persist** any clinic response. Results exist only in ephemeral Python variables during the request lifecycle.
- The Router transmits only the **query parameters** to clinics (e.g., `patient_id`, `query` text) — never bulk data extracts.
- Clinic responses are held in an `aggregated_results` list that is garbage-collected when the CLI loop iteration ends.

### 3.3 Data Minimization in MCP Payloads

The MCP request/response design enforces the **Data Minimization** principle (LGPD Art. 6, III):

| Principle | Implementation |
|---|---|
| **Purpose Limitation** | Each `MCPRequest.params.name` specifies exactly one tool. The clinic cannot be asked to "dump everything." |
| **Minimal Payload** | `list_patients` returns only `patient_id` + `condition`. Names, ages, and medications are excluded unless a targeted `get_patient` call is made. |
| **No Persistent Storage** | The Orchestrator never writes clinic data to disk, logs, or databases. |
| **Envelope Integrity** | Each `MCPResponse.id` correlates 1:1 with a request, preventing response replay or cross-contamination. |

### 3.4 Threat Model (Scope)

| Threat | Mitigation |
|---|---|
| Cross-clinic data aggregation | Router dispatches one clinic per request. Planner prompt forbids cross-clinic steps. |
| LLM hallucinating medical data | Verifier Rule R1 checks for ungrounded dosages/treatments. |
| PII leakage in aggregated output | Verifier Rule R2 scans for names, IDs, addresses before display. |
| Unauthorized tool invocation | Clinic servers return error `-32602` for unknown tools. |
| Network eavesdropping | Out of scope for prototype. Production: TLS termination at each endpoint. |

---

## 4. Evaluation Metrics Strategy

The following metrics provide quantitative evidence for thesis evaluation. All measurements are derived from system logs captured during integration testing.

### 4.1 Task Success Rate (TSR)

Measures the proportion of end-to-end user queries that complete the full pipeline (Planner → Router → Verifier) without any component failure.

$$
TSR = \frac{\text{Queries with all steps returning } result \neq null \text{ AND } verifier.safe = true}{\text{Total queries submitted}} \times 100
$$

| Rating | TSR Range |
|---|---|
| Excellent | >= 90% |
| Acceptable | 70%–89% |
| Insufficient | < 70% |

### 4.2 Tool Call Accuracy (TCA)

Measures the Planner's ability to generate correct tool names and route to the appropriate clinic, isolated from network or clinic-side failures.

$$
TCA = \frac{\text{Steps where } action \in \text{TOOL\_HANDLERS} \text{ AND } clinic \in \text{REGISTRY}}{\text{Total steps generated by Planner}} \times 100
$$

**Measurement method:** For each Planner output, compare `step.action` against the target clinic's `TOOL_HANDLERS.keys()` and `step.clinic` against `Router.registry.keys()`.

### 4.3 Hallucination Rate (HR)

Measures how often the system produces responses flagged by the Verifier as containing fabricated or ungrounded medical information.

$$
HR = \frac{\text{Queries where } verifier.safe = false \text{ AND note references Rule R1}}{\text{Total queries submitted}} \times 100
$$

**Measurement method:** Parse `VerificationResult.note` from the Verifier logs. Classify each `safe=false` occurrence by which rule triggered it (R1: hallucination, R2: PII, R3: scope violation).

### 4.4 Privacy Violation Rate (PVR)

Complementary metric measuring Verifier Rule R2 triggers.

$$
PVR = \frac{\text{Queries where } verifier.safe = false \text{ AND note references Rule R2}}{\text{Total queries submitted}} \times 100
$$

### 4.5 Evaluation Protocol

To generate statistically meaningful metrics:

1. Prepare a **test suite of N >= 30 healthcare queries** spanning both specialties, edge cases (unknown clinics, ambiguous symptoms), and adversarial inputs (requests for diagnoses, PII extraction attempts).
2. Execute each query through the full pipeline with **structured logging** capturing: Planner output, Router responses, Verifier verdicts.
3. Compute TSR, TCA, HR, and PVR from the logs.
4. Present results in tabular form with 95% confidence intervals where applicable.

---

## 5. Implementation Roadmap

### Phase 1 — Environment Setup

| Task | Detail | Artifact |
|---|---|---|
| 1.1 | Create project root and directory structure | `health_mas_tcc/` tree |
| 1.2 | Initialize Python virtual environment (`python3 -m venv .venv`) | `.venv/` |
| 1.3 | Install dependencies from `requirements.txt` | `pip install -r requirements.txt` |
| 1.4 | Configure `.env` with Azure OpenAI credentials | `.env` (gitignored) |
| 1.5 | Validate LLM connectivity with a smoke test | `AzureOpenAI.chat.completions.create()` returns OK |

**Deliverable:** Reproducible environment where `import openai` and `import fastapi` succeed.

### Phase 2 — MCP Servers Implementation (Federated Workers)

| Task | Detail | Artifact |
|---|---|---|
| 2.1 | Define `MCPRequest` and `MCPResponse` Pydantic models | `shared/mcp_types.py` |
| 2.2 | Implement Clinic A (Cardiology) FastAPI server with mock database and 4 tool handlers | `clinic_agents/clinic_a/server.py` |
| 2.3 | Implement Clinic B (Dermatology) FastAPI server with mock database and 4 tool handlers | `clinic_agents/clinic_b/server.py` |
| 2.4 | Create launch script for both servers | `clinic_agents/start_clinics.sh` |
| 2.5 | Validate each `/mcp` endpoint independently via `curl` | JSON-RPC responses with correct `result` payloads |

**Deliverable:** Two independently running MCP Servers that accept JSON-RPC 2.0 requests and return domain-specific data.

**Interoperability note:** Both clinics share the same `MCPRequest`/`MCPResponse` contract from `shared/mcp_types.py`, ensuring protocol-level interoperability without coupling their internal implementations.

### Phase 3 — Orchestrator Logic (MCP Client)

| Task | Detail | Artifact |
|---|---|---|
| 3.1 | Implement `Planner` with constrained system prompt including tool catalog | `orchestrator_host/planner.py` |
| 3.2 | Implement `Router` with clinic registry and JSON-RPC dispatch | `orchestrator_host/router.py` |
| 3.3 | Implement `Verifier` (Observer Agent) with three safety rules | `orchestrator_host/verifier.py` |
| 3.4 | Wire all components in `main.py` CLI loop | `orchestrator_host/main.py` |
| 3.5 | Validate full pipeline: query → decomposition → dispatch → verification → output | End-to-end CLI test |

**Deliverable:** A working Orchestrator that decomposes queries, routes to clinics, and gates output through the Verifier.

**Decoupling note:** Each Orchestrator module (`Planner`, `Router`, `Verifier`) is a standalone class with no cross-dependencies. They communicate only through Python data structures (`list[dict]`, `MCPResponse`, `VerificationResult`), enabling independent unit testing.

### Phase 4 — Integration Testing & Logging (TCC Evidence)

| Task | Detail | Artifact |
|---|---|---|
| 4.1 | Design test suite with >= 30 queries (normal, edge-case, adversarial) | `tests/test_queries.json` |
| 4.2 | Add structured logging (JSON lines) to Planner, Router, and Verifier | `logs/pipeline_YYYYMMDD.jsonl` |
| 4.3 | Execute full test suite and capture logs | Raw log files |
| 4.4 | Compute TSR, TCA, HR, PVR from logs | Metrics summary table |
| 4.5 | Generate Mermaid diagrams and screenshots for thesis appendix | Visual evidence |

**Deliverable:** Quantitative evaluation data and visual artifacts ready for inclusion in the TCC Methodology and Results chapters.

---

## Appendix A — Project File Map

```
tcc-healthcare-agents/
│
├── .env                              # Azure OpenAI credentials (gitignored)
├── .env.example                      # Template for new contributors
├── .gitignore                        # Protects .env and __pycache__
├── requirements.txt                  # Python dependencies
├── TECHNICAL_BLUEPRINT.md            # This document
│
├── shared/
│   ├── __init__.py
│   └── mcp_types.py                  # MCPRequest, MCPResponse (Pydantic)
│
├── orchestrator_host/                # MCP Client — Federated Orchestrator
│   ├── __init__.py
│   ├── main.py                       # CLI entry point (Planner → Router → Verifier)
│   ├── planner.py                    # Task Decomposition via Azure OpenAI
│   ├── router.py                     # Dynamic Routing with clinic registry
│   └── verifier.py                   # Observer Agent [Burke et al. 2024]
│
└── clinic_agents/                    # MCP Servers — Federated Workers
    ├── __init__.py
    ├── start_clinics.sh              # Launch script for all clinic servers
    ├── clinic_a/
    │   ├── __init__.py
    │   └── server.py                 # Cardiology silo (port 8001)
    └── clinic_b/
        ├── __init__.py
        └── server.py                 # Dermatology silo (port 8002)
```

## Appendix B — Glossary of Terms

| Term | Definition |
|---|---|
| **Decoupling** | Design principle where components interact through defined interfaces (MCP) without internal knowledge of each other. |
| **Interoperability** | The ability of heterogeneous clinic agents to communicate via a shared protocol (JSON-RPC 2.0 / MCP). |
| **Deterministic Validation** | Verification rules that produce consistent, reproducible outcomes given the same input (temperature 0.0). |
| **Data Minimization** | Transmitting only the minimum data required for each operation (LGPD Art. 6, III). |
| **Federated Data Silo** | An isolated data store that does not share raw records with external systems. |
| **Step Graph** | An ordered list of atomic operations produced by the Planner, each targeting one clinic. |
| **Observer Agent** | An independent auditing agent that validates outputs without participating in their generation (Burke et al. 2024). |
| **Hub-and-Spoke** | Network topology where all communication flows through a central hub (Orchestrator); spokes (Clinics) never communicate directly. |
| **Tool Handler** | A registered function on an MCP Server that executes a specific domain operation when invoked via `tools/call`. |

---

> **Document generated for academic use.**
> Architecture: Hierarchical Federated Orchestrator-Workers with Observer.
> Protocol: Model Context Protocol (MCP) over HTTP / JSON-RPC 2.0.
