# Technical Blueprint — Healthcare Multi-Agent System (MAS)

> **Document Classification:** Academic Reference — TCC Ground Truth
> **Architecture Pattern:** Hierarchical Federated Orchestrator-Workers with Observer
> **Protocol:** Model Context Protocol (MCP) over HTTP / JSON-RPC 2.0
> **Version:** 3.0.0

---

## Version History

| Version | Date | Changes |
|---|---|---|
| 1.0.0 | — | Initial version. 4 tools per clinic. 4-stage pipeline. |
| 2.0.0 | 2025-07 | Expanded catalog to 7 tools. 5-stage pipeline. Patient identification. Multi-turn conversation history. Planner CoT. Verifier with PII exceptions and JSON serialization fix. Integration test suite. External prompts in `prompts/`. |
| 3.0.0 | 2025-07 | 6 federated clinics (3 specialties x 2 clinics). 9 agents. Persistent JSON database (`db.json`) per clinic with shared module `shared/db.py`. Multi-clinic routing (Rule 10). Uniform specialty descriptions. Cross-clinic availability comparison (Response Generator Rule 9). Multi-clinic test. |

---

## Table of Contents

1. [Architectural Definition (Formal)](#1-architectural-definition-formal)
2. [Component Specifications](#2-component-specifications)
3. [JSON Database Architecture](#3-json-database-architecture)
4. [Privacy & Security Strategy](#4-privacy--security-strategy)
5. [Evaluation Metrics Strategy](#5-evaluation-metrics-strategy)
6. [Implementation Roadmap](#6-implementation-roadmap)

---

## 1. Architectural Definition (Formal)

### 1.1 Pattern Classification

This system implements the **Hierarchical Federated Orchestrator-Workers with Observer** pattern, a composite multi-agent architecture that combines three established paradigms:

| Paradigm | Role in this System | Theoretical Basis |
|---|---|---|
| **Hierarchical Coordination** | The Orchestrator Host decomposes high-level goals into atomic sub-tasks and delegates them downward. Workers (Clinic Agents) have no awareness of sibling agents or the global task plan. | Centralized control with decentralized execution. |
| **Federated Data Architecture** | Each Clinic Agent operates as an isolated data silo with its own persistent `db.json` file. Patient records are never transmitted in raw form; only query results cross the process boundary. | Privacy-by-Design; Data Minimization (LGPD/GDPR). |
| **Observer Agent** | An independent Verifier audits every aggregated response against safety rules before it reaches the end-user, implementing a deterministic validation gate. | Burke et al. (2024), "Observer Agents for Safe Multi-Agent Medical Systems." |

### 1.2 Orchestrator Host (MCP Client)

The Orchestrator is the sole component with a **global view** of the user's intent. It contains three internal modules that execute sequentially, and is also responsible for generating the final natural-language response:

| Module | Responsibility | Classification |
|---|---|---|
| **Planner** | **Task Decomposition** — receives the natural-language query and uses Azure OpenAI (temperature 0.0) to produce a deterministic JSON step graph. Each step is atomic and scoped to exactly one clinic. Supports conversation history for multi-turn flows. When a specialty has multiple clinics (e.g., cardiology has clinic_a AND clinic_c), the Planner generates one step per clinic to query ALL of them (Rule 10). | LLM-assisted planning with constrained output. |
| **Router** | **Dynamic Routing** — maintains a registry of 6 clinic endpoints and dispatches each step via HTTP POST following the MCP JSON-RPC 2.0 envelope. The Router is the only module aware of the network topology. Automatically injects patient identification data (name, CPF) into booking, rescheduling, and cancellation steps. | Registry-based service dispatch. |
| **Verifier** | **Safety Guardrails & Hallucination Mitigation** — acts as the Observer Agent (Burke et al. 2024). Validates aggregated results against three deterministic rules: (1) no fabricated dosages, (2) no PII leakage of other patients, (3) no out-of-scope recommendations. Serializes data with `json.dumps()` for valid JSON in verification. | Independent post-processing audit layer. |
| **Response Generator** | **Response Generation** — after the Verifier approves the data, the Orchestrator transforms the structured results into a conversational natural-language response using Azure OpenAI. The system prompt explicitly describes the JSON schema received and enforces faithful presentation of all data returned by the clinics. When `clinic_data` contains results from multiple clinics for the same action, presents ALL slots from ALL clinics together, indicating which clinic each belongs to and highlighting the earliest/nearest slot (Rule 9). | Internal Orchestrator capability, not a separate agent. |

### 1.3 MCP Servers (Clinic Agents — Workers)

Each Clinic Agent is a **domain-specialized** FastAPI application exposing a single `/mcp` endpoint. The system comprises **6 clinics** organized by **3 specialties** (2 clinics each). Clinics embody three core principles:

- **Domain Specialization:** Each clinic handles exactly one medical specialty. Clinics of the same specialty have **uniform descriptions and capabilities** — the only differences between sibling clinics are their doctors, schedules, and patient records.
- **Data Silos / Federation:** Each clinic maintains its own persistent `db.json` file for appointment slots and hardcoded mock data for patient records. No shared database, no shared file system, no inter-clinic communication channel exists. This enforces **Privacy Preservation** at the infrastructure level — a clinic cannot access another clinic's data even if compromised.
- **Persistent State via JSON Database:** Appointment operations (`book_appointment`, `cancel_appointment`, `reschedule_appointment`, `list_available_slots`) read from and write to the clinic's local `db.json` file, enabling real persistence of bookings across requests.

**Clinic Registry:**

| Clinic | Specialty | Port | Data Silo |
|---|---|---|---|
| `clinic_a` | Cardiology | 8001 | `clinic_agents/clinic_a/db.json` |
| `clinic_b` | Dermatology | 8002 | `clinic_agents/clinic_b/db.json` |
| `clinic_c` | Cardiology | 8003 | `clinic_agents/clinic_c/db.json` |
| `clinic_d` | Orthopedics | 8004 | `clinic_agents/clinic_d/db.json` |
| `clinic_e` | Orthopedics | 8005 | `clinic_agents/clinic_e/db.json` |
| `clinic_f` | Dermatology | 8006 | `clinic_agents/clinic_f/db.json` |

### 1.4 Multi-Agent Pipeline (5 Stages, 9 Agents)

The complete system pipeline involves **9 agents** executing across 5 stages:

```
1. User input        ->  [Agent: Planner]                     Task Decomposition
2. Step graph        ->  [Agent: Router]                      Federated Dispatch
3. MCP requests      ->  [Agent: Clinic A/B/C/D/E/F]         Domain-Specific Execution
4. Raw results       ->  [Agent: Verifier]                    Safety Validation (Observer)
5. Validated data    ->  [Orchestrator]                       Natural Language Response
```

**Agent count:** Planner (1) + Router (1) + Clinic A (1) + Clinic B (1) + Clinic C (1) + Clinic D (1) + Clinic E (1) + Clinic F (1) + Verifier (1) = **9 agents**. The Response Generator is an internal Orchestrator capability, not a separate agent.

### 1.5 Patient Identification

Before starting the interactive session, the system collects:
- **Full name** of the patient
- **CPF** (Brazilian Individual Taxpayer Registry)

This data is automatically injected by the Orchestrator into `book_appointment`, `reschedule_appointment`, and `cancel_appointment` steps before dispatch to the Router. This prevents the user from having to repeat their data at each interaction.

### 1.6 Multi-Clinic Routing (Planner Rule 10)

When a user queries a specialty that has multiple clinics, the Planner **must generate one step per clinic** to query all of them. This enables the system to:

1. Retrieve availability from all clinics of the requested specialty in parallel.
2. Aggregate results across clinics in the Response Generator.
3. Present the user with a comprehensive view of all options, highlighting the earliest/nearest slot.

**Example:** A query like "quero marcar com cardiologista" produces:

```json
[
  {"step_id": 1, "clinic": "clinic_a", "action": "list_available_slots", "parameters": {}},
  {"step_id": 2, "clinic": "clinic_c", "action": "list_available_slots", "parameters": {}}
]
```

Both clinics are queried, and the Response Generator (Rule 9) presents all slots from both clinics together.

### 1.7 Hub-and-Spoke Topology (Mermaid Diagram)

```mermaid
graph TD
    User([fa:fa-user End-User / Operator])

    subgraph Orchestrator Host — MCP Client
        Planner[fa:fa-project-diagram Planner<br/><i>Task Decomposition</i><br/>Azure OpenAI · temp 0.0]
        Router[fa:fa-route Router<br/><i>Dynamic Routing</i><br/>Registry-based dispatch]
        Verifier[fa:fa-shield-alt Verifier<br/><i>Observer Agent</i><br/>Safety Guardrails]
        ResponseGen[fa:fa-comment-dots Response Generator<br/><i>Natural Language Response</i><br/>Azure OpenAI · temp 0.3]
    end

    subgraph Federated Data Silos — Cardiology
        ClinicA[fa:fa-heartbeat Clinic A<br/><b>Cardiology</b><br/>FastAPI · Port 8001<br/>MCP Server · db.json]
        ClinicC[fa:fa-heartbeat Clinic C<br/><b>Cardiology</b><br/>FastAPI · Port 8003<br/>MCP Server · db.json]
    end

    subgraph Federated Data Silos — Dermatology
        ClinicB[fa:fa-allergies Clinic B<br/><b>Dermatology</b><br/>FastAPI · Port 8002<br/>MCP Server · db.json]
        ClinicF[fa:fa-allergies Clinic F<br/><b>Dermatology</b><br/>FastAPI · Port 8006<br/>MCP Server · db.json]
    end

    subgraph Federated Data Silos — Orthopedics
        ClinicD[fa:fa-bone Clinic D<br/><b>Orthopedics</b><br/>FastAPI · Port 8004<br/>MCP Server · db.json]
        ClinicE[fa:fa-bone Clinic E<br/><b>Orthopedics</b><br/>FastAPI · Port 8005<br/>MCP Server · db.json]
    end

    User -->|Natural language query| Planner
    Planner -->|Step graph JSON| Router
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicA
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicB
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicC
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicD
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicE
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicF
    ClinicA -->|MCPResponse| Router
    ClinicB -->|MCPResponse| Router
    ClinicC -->|MCPResponse| Router
    ClinicD -->|MCPResponse| Router
    ClinicE -->|MCPResponse| Router
    ClinicF -->|MCPResponse| Router
    Router -->|Aggregated results| Verifier
    Verifier -->|"safe: true"| ResponseGen
    ResponseGen -->|Conversational response| User

    style Planner fill:#4a90d9,color:#fff
    style Router fill:#7b68ee,color:#fff
    style Verifier fill:#e74c3c,color:#fff
    style ResponseGen fill:#9b59b6,color:#fff
    style ClinicA fill:#27ae60,color:#fff
    style ClinicC fill:#2ecc71,color:#fff
    style ClinicB fill:#f39c12,color:#fff
    style ClinicF fill:#f1c40f,color:#fff
    style ClinicD fill:#3498db,color:#fff
    style ClinicE fill:#5dade2,color:#fff
```

> **Topology rationale:** The Hub-and-Spoke model ensures **Decoupling** between clinic agents. Adding a new clinic for an existing specialty requires only registering a new URL in the Router's registry, deploying a new MCP Server with its own `db.json`, and updating the Planner's clinic catalog. No existing clinic code is modified, satisfying the Open-Closed Principle. The multi-clinic routing rule (Rule 10) ensures that all clinics of a specialty are automatically queried.

---

## 2. Component Specifications

### 2.1 Technology Stack

| Layer | Technology | Version | Purpose |
|---|---|---|---|
| Language | Python | 3.9+ | Core runtime |
| Web Framework | FastAPI | latest | MCP Server endpoints (Clinic Agents) |
| ASGI Server | Uvicorn | latest | Production-grade async server |
| LLM SDK | `openai` (AzureOpenAI) | latest | Planner, Verifier & Response Generator reasoning |
| Data Validation | Pydantic | v2 | MCPRequest / MCPResponse schemas |
| HTTP Client | Requests | latest | Router -> Clinic dispatch |
| Configuration | python-dotenv | latest | Environment variable management |
| Database | JSON files (`db.json`) | — | Persistent appointment slot storage per clinic |
| Concurrency | `threading.Lock` | stdlib | Thread-safe JSON file access |
| Wiring | `functools.partial` | stdlib | Shared handler binding with clinic-specific paths |

### 2.2 Protocol Specification: MCP over HTTP (JSON-RPC 2.0)

All inter-agent communication follows the **Model Context Protocol** transported over HTTP using the JSON-RPC 2.0 envelope.

**Request Schema** (`shared/mcp_types.py` — `MCPRequest`):

```json
{
    "jsonrpc": "2.0",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "method": "tools/call",
    "params": {
        "name": "book_appointment",
        "arguments": {
            "doctor": "Dr. Ricardo Lopes",
            "date": "2025-07-21",
            "time": "09:00",
            "patient_name": "Carlos Teste",
            "cpf": "123.456.789-00"
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
    "result": {
        "status": "confirmed",
        "appointment": {
            "doctor": "Dr. Ricardo Lopes",
            "date": "2025-07-21",
            "time": "09:00",
            "patient_name": "Carlos Teste",
            "cpf": "123.456.789-00",
            "specialty": "Cardiology"
        },
        "message": "Consulta agendada com sucesso."
    },
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
**System Prompt:** `prompts/planner.txt` (CoT variant: `prompts/planner_cot.txt`)

The Planner converts a natural-language healthcare query into an executable **step graph** — an ordered JSON array where each element represents one atomic operation on one clinic. It supports **conversation history** for multi-turn flows (e.g., user lists slots, then picks one to book). The system prompt is loaded from an external file (`prompts/planner.txt`) for easier reading and maintenance.

```
Input:  "quero marcar uma consulta com um cardiologista"
         |
         v
   +-------------------------------------+
   |  Azure OpenAI (gpt-4o, temp=0.0)   |
   |  System Prompt: constrained schema  |
   |  + clinic registry (6 clinics)      |
   |  + tool catalog + Rule 10           |
   |  + conversation history             |
   +-------------------------------------+
         |
         v
Output: [
          {"step_id": 1, "clinic": "clinic_a", "action": "list_available_slots", "parameters": {}},
          {"step_id": 2, "clinic": "clinic_c", "action": "list_available_slots", "parameters": {}}
        ]
```

**Deterministic constraints enforced via system prompt:**
1. Only clinics present in the registry may be referenced (6 clinics: clinic_a through clinic_f).
2. Only tool names from the exact catalog are permitted (see section 2.4).
3. Each step is scoped to a single clinic — **no cross-clinic joins** in a single step (Privacy Preservation).
4. Output is strictly JSON with no markdown fences or natural-language commentary.
5. Temperature is set to `0.0` to minimize non-determinism.
6. Conversation history enables the Planner to extract prior appointment details for rescheduling and cancellation.
7. **Rule 10 — Multi-Clinic Routing:** When a specialty has more than one clinic (e.g., cardiology has clinic_a AND clinic_c), the Planner MUST generate one step per clinic to query ALL of them.

**Chain-of-Thought (CoT) variant:**
The Planner offers an alternative `decompose_cot()` method that requires explicit reasoning before producing the step graph:

```json
{
  "reasoning": [
    "The user wants to book a cardiology appointment.",
    "Cardiology is handled by clinic_a AND clinic_c.",
    "I need to list available slots from BOTH clinics (Rule 10).",
    "No cross-clinic data combination is needed in a single step."
  ],
  "steps": [
    {"step_id": 1, "clinic": "clinic_a", "action": "list_available_slots", "parameters": {}},
    {"step_id": 2, "clinic": "clinic_c", "action": "list_available_slots", "parameters": {}}
  ]
}
```

This provides an auditable reasoning trace for academic evaluation.

**Fallback mechanism:** If the LLM returns unparseable JSON, the Planner wraps the raw output in a fallback step (`action: "raw_response"`) so the pipeline does not crash.

#### 2.3.2 Verifier Logic — Observer Agent Deterministic Validation

**File:** `orchestrator_host/verifier.py`
**System Prompt:** `prompts/verifier.txt`
**Reference:** Burke et al. (2024)

The Verifier receives the **aggregated results** from all dispatched steps (potentially spanning multiple clinics) and validates them against three deterministic safety rules:

| Rule # | Check | Rationale |
|---|---|---|
| R1 | Response does NOT contain fabricated drug dosages or treatment plans ungrounded in clinic data. | **Hallucination Mitigation** — prevents the LLM from inventing medical information. |
| R2 | Response does NOT expose Personally Identifiable Information of OTHER patients (full names, government IDs, addresses). | **Privacy Preservation** — enforces Data Minimization at the output layer. |
| R3 | Response does NOT recommend actions outside the agent's scope (e.g., diagnosing without a physician). | **Safety Guardrails** — prevents liability-creating medical advice. |

**PII Exceptions (SAFE — must NEVER be flagged):**
- Anonymous identifiers like "CARD-001", "DERM-002", "ORTH-D001", "CARD-C002" — opaque system tokens.
- Doctor/physician names — public professional information.
- The CURRENT USER's own name and CPF in appointment confirmations — the user provided this data voluntarily for identification and it is EXPECTED in their booking receipt.

**Serialization:** Aggregated data is serialized with `json.dumps(agent_response, ensure_ascii=False)` to produce valid JSON (double quotes, `true`/`false`) instead of Python repr (`str()`), ensuring the Verifier's LLM interprets the data correctly.

**Validation output schema:**

```json
{"safe": true,  "note": "OK"}
{"safe": false, "note": "Response contains fabricated dosage for Amiodarone."}
```

**Pipeline behavior:**
- `safe: true` -> results proceed to the Response Generator and then are displayed to the end-user.
- `safe: false` -> results are **blocked**; only the `note` explaining the violation is shown.

#### 2.3.3 Response Generator Logic — Natural Language Response Generation

**File:** `orchestrator_host/main.py` (function `_generate_response`)
**System Prompt:** `prompts/response_generator.txt`

After the Verifier approves the data, the Orchestrator transforms the structured results into a conversational response. The system prompt (`RESPONSE_SYSTEM_PROMPT`), loaded from `prompts/response_generator.txt`, includes:

1. **JSON schema description** that the LLM will receive:
   - `user_query`: the original patient question
   - `clinic_data[]`: list of results, each with `clinic`, `action`, `result`, `error`

2. **Explicit rules:**
   - Respond in the SAME LANGUAGE as the user
   - If `result` contains data (slots, patients, appointments), ALWAYS present them — never say "no results" when the JSON shows data
   - If `result` contains `available_slots`, list EVERY slot with date, time, and doctor name
   - NEVER invent or fabricate data
   - Be professional like a clinic receptionist

3. **Rule 9 — Cross-Clinic Availability Comparison:** When `clinic_data` contains results from more than one clinic for the same action, present ALL slots from ALL clinics together, clearly indicating which clinic each slot belongs to. When the user asks for the "earliest" or "nearest" slot, identify and highlight the soonest available date/time across all clinics, but still list the other options.

**Payload sent to the LLM (multi-clinic example):**

```json
{
    "user_query": "quero marcar uma consulta com um cardiologista",
    "clinic_data": [
        {
            "clinic": "clinic_a",
            "action": "list_available_slots",
            "result": {
                "specialty": "Cardiology",
                "available_slots": [
                    {"doctor": "Dr. Ricardo Lopes", "specialty": "Cardiologia", "date": "2025-07-21", "time": "09:00", "available": true},
                    {"doctor": "Dr. Ricardo Lopes", "specialty": "Cardiologia", "date": "2025-07-21", "time": "10:30", "available": true}
                ],
                "note": "Para confirmar o agendamento, informe o horario desejado."
            },
            "error": null
        },
        {
            "clinic": "clinic_c",
            "action": "list_available_slots",
            "result": {
                "specialty": "Cardiology",
                "available_slots": [
                    {"doctor": "Dr. Fernando Mendes", "specialty": "Cardiologia", "date": "2025-07-18", "time": "10:00", "available": true},
                    {"doctor": "Dr. Fernando Mendes", "specialty": "Cardiologia", "date": "2025-07-18", "time": "14:00", "available": true}
                ],
                "note": "Para confirmar o agendamento, informe o horario desejado."
            },
            "error": null
        }
    ]
}
```

#### 2.3.4 Tool Call Flow — End-to-End Sequence (Multi-Clinic)

```
 User              Planner          Router           Clinic A    Clinic C     Verifier       Response Gen
  |                  |                |                 |           |            |               |
  |-- query -------->|                |                 |           |            |               |
  |                  |-- step graph ->|                 |           |            |               |
  |                  |   (2 steps)    |-- MCPRequest -->|           |            |               |
  |                  |                |   POST /mcp     |           |            |               |
  |                  |                |<-- MCPResponse --|           |            |               |
  |                  |                |                 |           |            |               |
  |                  |                |-- MCPRequest ------------->|            |               |
  |                  |                |   POST /mcp     |           |            |               |
  |                  |                |<-- MCPResponse ------------|            |               |
  |                  |                |                 |           |            |               |
  |                  |                |-- aggregated (both clinics) ----------->|               |
  |                  |                |                 |           |            |-- safe: true ->|
  |                  |                |                 |           |            |               |
  |<----------------------------------------------------------------------------------response-|
```

### 2.4 Available Tools per Clinic

All 6 clinics expose an identical tool interface with **7 tools**, differentiated only by the underlying domain data. Clinics of the same specialty have **uniform descriptions and capabilities** — the only differences are their doctors, schedules, and patient records.

#### Query Tools (Mock Data — Hardcoded)

| Tool | Parameters | Returns | Privacy Note | Data Source |
|---|---|---|---|---|
| `list_patients` | *(none)* | `{"patients": [{"patient_id", "condition"}]}` | Returns only IDs and conditions — **no names or PII**. | Hardcoded mock DB |
| `get_patient` | `patient_id: str` | `{"patient": {full record}}` | Full record scoped to single patient. | Hardcoded mock DB |
| `query` | `query: str` | `{"specialty", "query", "matches": [...]}` | Free-text search; returns IDs and conditions only. | Hardcoded mock DB |

#### Scheduling Tools (Persistent — JSON Database)

| Tool | Parameters | Returns | Note | Data Source |
|---|---|---|---|---|
| `list_available_slots` | `doctor: str` *(optional)* | `{"specialty", "available_slots": [{doctor, specialty, date, time, available}], "note"}` | Returns only `available: true` slots. Optional doctor filter. | `db.json` |
| `book_appointment` | `doctor: str`, `date: str`, `time: str`, `patient_name: str`, `cpf: str` | `{"status": "confirmed", "appointment": {...}, "message"}` | Marks slot as `available: false`, saves patient data. `patient_name` and `cpf` are auto-injected by the Orchestrator. | `db.json` |
| `reschedule_appointment` | `original_date: str`, `original_time: str`, `doctor: str`, `new_date: str`, `new_time: str`, `patient_name: str`, `cpf: str` | `{"status": "rescheduled", "original_appointment": {...}, "new_appointment": {...}, "message"}` | Frees old slot (`available: true`) and books new slot (`available: false`). Original data extracted from conversation history by the Planner. | `db.json` |
| `cancel_appointment` | `doctor: str`, `date: str`, `time: str`, `patient_name: str`, `cpf: str` | `{"status": "cancelled", "cancelled_appointment": {...}, "message"}` | Marks slot as `available: true`. Data extracted from conversation history by the Planner. | `db.json` |

### 2.5 Multi-Turn Interaction Flows

The system supports three main conversational flows. In v3.0.0, the listing step queries **all clinics** of the relevant specialty (Rule 10):

#### Booking Flow (2 turns)
```
Turn 1: "I want to book a cardiology appointment"
        -> Planner generates list_available_slots for clinic_a AND clinic_c (Rule 10)
        -> Both clinics return their available slots
        -> Response Generator presents ALL slots from BOTH clinics (Rule 9)
        -> Response: combined list of available time slots with clinic labels

Turn 2: "I'll take Dr. Fernando at Clinic C on July 18 at 10 AM"
        -> Planner extracts data from context -> book_appointment on clinic_c
        -> Response: booking confirmation
```

#### Rescheduling Flow (3 turns)
```
Turn 1-2: (same as booking above)

Turn 3: "I need to reschedule to July 19 at 14:00"
        -> Planner extracts original appointment from history
        -> reschedule_appointment with original and new data on clinic_c
        -> Response: rescheduling confirmation
```

#### Cancellation Flow (3 turns)
```
Turn 1-2: (same as booking above)

Turn 3: "I need to cancel my appointment"
        -> Planner extracts appointment data from history
        -> cancel_appointment on clinic_c
        -> Response: cancellation confirmation
```

---

## 3. JSON Database Architecture

### 3.1 Overview

Version 3.0.0 introduces a **persistent JSON file-based database** for appointment slots, replacing the hardcoded appointment data used in prior versions. Each clinic maintains its own `db.json` file in its directory, forming a truly federated data storage layer.

**Key design decisions:**
- **Patient mock data remains hardcoded** — `list_patients`, `get_patient`, and `query` still use in-memory Python lists. This separates the "patient registry" concern (static mock) from the "appointment scheduling" concern (dynamic, persistent).
- **Only the 4 scheduling tools use `db.json`** — `list_available_slots`, `book_appointment`, `cancel_appointment`, `reschedule_appointment`.
- **One `db.json` per clinic** — no shared database across clinics, preserving the federated data silo model.

### 3.2 Database Schema

Each `db.json` file contains a single root object with a `slots` array:

```json
{
  "slots": [
    {
      "doctor": "Dr. Ricardo Lopes",
      "specialty": "Cardiologia",
      "date": "2025-07-21",
      "time": "09:00",
      "available": true,
      "patient_name": null,
      "cpf": null
    },
    {
      "doctor": "Dr. Ricardo Lopes",
      "specialty": "Cardiologia",
      "date": "2025-07-21",
      "time": "10:30",
      "available": false,
      "patient_name": "Carlos Teste",
      "cpf": "123.456.789-00"
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `doctor` | `str` | Full name of the physician. |
| `specialty` | `str` | Medical specialty (localized, e.g., "Cardiologia"). |
| `date` | `str` | Appointment date in `YYYY-MM-DD` format. |
| `time` | `str` | Appointment time in `HH:MM` format. |
| `available` | `bool` | `true` if the slot is open; `false` if booked. |
| `patient_name` | `str \| null` | Name of the patient who booked the slot, or `null`. |
| `cpf` | `str \| null` | CPF of the patient who booked the slot, or `null`. |

### 3.3 Shared Database Module

**File:** `shared/db.py`

The shared module provides reusable database logic for all 6 clinics:

**Low-level helpers:**
- `_load_slots(db_path)` — reads and parses the `slots` array from a `db.json` file.
- `_save_slots(db_path, slots)` — writes the `slots` array back to the file with `ensure_ascii=False` and proper indentation.

**Handler functions (4 appointment tools):**
- `handle_list_available_slots(db_path, specialty, doctor="", ...)` — filters for `available: true` slots, optionally by doctor name.
- `handle_book_appointment(db_path, specialty, doctor, date, time, patient_name, cpf, ...)` — finds the matching available slot, marks it as `available: false`, and persists the patient's name and CPF.
- `handle_cancel_appointment(db_path, specialty, doctor, date, time, patient_name, cpf, ...)` — finds the matching booked slot, marks it as `available: true`, and clears the patient data.
- `handle_reschedule_appointment(db_path, specialty, original_date, original_time, doctor, new_date, new_time, patient_name, cpf, ...)` — atomically frees the original slot and books the new slot in a single locked operation.

### 3.4 Thread Safety

All read/write operations on `db.json` are protected by a module-level `threading.Lock()` (`_lock`). This ensures that concurrent requests to the same clinic server (e.g., two users booking simultaneously) do not produce race conditions or corrupt the JSON file. The lock is acquired before loading slots and released only after saving, making each booking/cancellation/rescheduling operation atomic.

### 3.5 Partial Application Pattern

Each clinic server uses `functools.partial` to bind the shared handler functions with its specific `_DB_PATH` and `_SPECIALTY` constants:

```python
from functools import partial
from shared.db import handle_list_available_slots, handle_book_appointment, ...

_DB_PATH = Path(__file__).resolve().parent / "db.json"
_SPECIALTY = "Cardiology"

_handle_list_available_slots = partial(handle_list_available_slots, _DB_PATH, _SPECIALTY)
_handle_book_appointment = partial(handle_book_appointment, _DB_PATH, _SPECIALTY)
_handle_cancel_appointment = partial(handle_cancel_appointment, _DB_PATH, _SPECIALTY)
_handle_reschedule_appointment = partial(handle_reschedule_appointment, _DB_PATH, _SPECIALTY)
```

This pattern eliminates code duplication across the 6 clinic servers while maintaining the federated data silo boundary — each partial is bound to its own `db.json` path, so no clinic can accidentally access another clinic's data.

---

## 4. Privacy & Security Strategy

### 4.1 Privacy-by-Design

The architecture enforces privacy at **five structural layers**, making data leakage a violation of system boundaries rather than a policy choice:

```
Layer 1 — Process Isolation       Each clinic runs as a separate OS process.
                                  No shared memory, no shared filesystem.

Layer 2 — File-Level Isolation    Each clinic has its own db.json file in its own
                                  directory.  The shared/db.py module receives the
                                  file path via functools.partial — no clinic can
                                  reference another clinic's db.json.

Layer 3 — Network Scoping         The Router dispatches one request per clinic.
                                  No JSON-RPC payload ever references two clinics.

Layer 4 — Data Minimization       list_patients and query return only patient_id
                                  and condition. Full records require explicit
                                  get_patient calls with a known ID.

Layer 5 — Output Verification     The Verifier (Observer Agent) scans aggregated
                                  results for PII before they reach the user.
```

### 4.2 Data Residency

Patient data exists in two separate stores per clinic, **both local** to the Clinic Agent:

1. **Mock patient database** (hardcoded Python lists) — remains in-process memory at all times.
2. **JSON appointment database** (`db.json`) — persisted to the clinic's own directory on disk. Contains slot availability, and when booked, the patient's name and CPF.

Residency guarantees:

- The Orchestrator Host **does not persist** any clinic response. Results exist only in ephemeral Python variables during the request lifecycle.
- The Router transmits only the **query parameters** to clinics (e.g., `patient_id`, `query` text, scheduling data) — never bulk data extracts.
- Clinic responses are held in an `aggregated_results` list that is garbage-collected when the CLI loop iteration ends.
- Patient identification data (name, CPF) is held in memory during the session and injected only into steps that require it.
- Each `db.json` file is written only by its owning clinic process. No cross-clinic file access is possible.

### 4.3 Data Minimization in MCP Payloads

The MCP request/response design enforces the **Data Minimization** principle (LGPD Art. 6, III):

| Principle | Implementation |
|---|---|
| **Purpose Limitation** | Each `MCPRequest.params.name` specifies exactly one tool. The clinic cannot be asked to "dump everything." |
| **Minimal Payload** | `list_patients` returns only `patient_id` + `condition`. Names, ages, and medications are excluded unless a targeted `get_patient` call is made. |
| **No Persistent Storage at Orchestrator** | The Orchestrator never writes clinic data to disk, logs, or databases. Persistence is exclusively within each clinic's `db.json`. |
| **Envelope Integrity** | Each `MCPResponse.id` correlates 1:1 with a request, preventing response replay or cross-contamination. |
| **Isolated Identification Data** | Patient name and CPF are injected by the Orchestrator only into steps that require identification (booking, rescheduling, cancellation). They are not sent in search queries. |
| **Federated Persistence** | Booked appointment data (patient name, CPF) is stored only in the specific clinic's `db.json` — never replicated or aggregated centrally. |

### 4.4 JSON Database Security Considerations

| Concern | Mitigation |
|---|---|
| Cross-clinic data access via `db.json` | Each clinic's `_DB_PATH` is resolved relative to its own `server.py` directory. The `shared/db.py` module receives the path via `functools.partial`, preventing any clinic from constructing a path to another clinic's file. |
| Concurrent write corruption | All file I/O is protected by a module-level `threading.Lock()`. Reads and writes are atomic within the lock scope. |
| PII in `db.json` files | Booked slots contain `patient_name` and `cpf`. These files must be protected at the OS level (file permissions) and excluded from version control if real data were used. In the prototype, all data is simulated. |
| Disk-level exposure | Out of scope for prototype. Production: encrypt `db.json` at rest and restrict filesystem access to the clinic process user. |

### 4.5 Threat Model (Scope)

| Threat | Mitigation |
|---|---|
| Cross-clinic data aggregation | Router dispatches one clinic per request. Planner prompt forbids cross-clinic steps. Each clinic has its own `db.json`. |
| LLM hallucinating medical data | Verifier Rule R1 checks for ungrounded dosages/treatments. |
| PII leakage in aggregated output | Verifier Rule R2 scans for names, IDs, addresses before display. |
| Unauthorized tool invocation | Clinic servers return error `-32602` for unknown tools. |
| LLM ignoring real clinic data | The RESPONSE_SYSTEM_PROMPT explicitly describes the JSON schema and enforces faithful presentation of all returned data. |
| Degraded Verifier serialization | Fixed: `json.dumps()` instead of `str()` to ensure valid JSON. |
| Cross-clinic file path injection | `functools.partial` binds `_DB_PATH` at import time. No user input can influence the file path. |
| Network eavesdropping | Out of scope for prototype. Production: TLS termination at each endpoint. |

---

## 5. Evaluation Metrics Strategy

The following metrics provide quantitative evidence for thesis evaluation. All measurements are derived from system logs captured during integration testing.

### 5.1 Task Success Rate (TSR)

Measures the proportion of end-to-end user queries that complete the full pipeline (Planner -> Router -> Verifier -> Response Generator) without any component failure.

$$
TSR = \frac{\text{Queries with all steps returning } result \neq null \text{ AND } verifier.safe = true}{\text{Total queries submitted}} \times 100
$$

| Rating | TSR Range |
|---|---|
| Excellent | >= 90% |
| Acceptable | 70%–89% |
| Insufficient | < 70% |

### 5.2 Tool Call Accuracy (TCA)

Measures the Planner's ability to generate correct tool names, route to the appropriate clinic, and produce the correct number of steps for multi-clinic queries (Rule 10 compliance).

$$
TCA = \frac{\text{Steps where } action \in \text{TOOL\_HANDLERS} \text{ AND } clinic \in \text{REGISTRY}}{\text{Total steps generated by Planner}} \times 100
$$

**Measurement method:** For each Planner output, compare `step.action` against the target clinic's `TOOL_HANDLERS.keys()` and `step.clinic` against `Router.registry.keys()`. Additionally, verify that multi-clinic specialty queries produce the expected number of steps (e.g., 2 steps for cardiology).

### 5.3 Hallucination Rate (HR)

Measures how often the system produces responses flagged by the Verifier as containing fabricated or ungrounded medical information.

$$
HR = \frac{\text{Queries where } verifier.safe = false \text{ AND note references Rule R1}}{\text{Total queries submitted}} \times 100
$$

**Measurement method:** Parse `VerificationResult.note` from the Verifier logs. Classify each `safe=false` occurrence by which rule triggered it (R1: hallucination, R2: PII, R3: scope violation).

### 5.4 Privacy Violation Rate (PVR)

Complementary metric measuring Verifier Rule R2 triggers.

$$
PVR = \frac{\text{Queries where } verifier.safe = false \text{ AND note references Rule R2}}{\text{Total queries submitted}} \times 100
$$

### 5.5 Evaluation Protocol

To generate statistically meaningful metrics:

1. Prepare a **test suite of N >= 30 healthcare queries** spanning all three specialties, multi-clinic routing scenarios, edge cases (unknown clinics, ambiguous symptoms), and adversarial inputs (requests for diagnoses, PII extraction attempts).
2. Execute each query through the full pipeline with **structured logging** capturing: Planner output, Router responses, Verifier verdicts, final generated response.
3. Compute TSR, TCA, HR, and PVR from the logs.
4. Present results in tabular form with 95% confidence intervals where applicable.

---

## 6. Implementation Roadmap

### Phase 1 — Environment Setup

| Task | Detail | Artifact |
|---|---|---|
| 1.1 | Create project root and directory structure | `tcc-healthcare-agents/` tree |
| 1.2 | Initialize Python virtual environment (`python3 -m venv .venv`) | `.venv/` |
| 1.3 | Install dependencies from `requirements.txt` | `pip install -r requirements.txt` |
| 1.4 | Configure `.env` with Azure OpenAI credentials | `.env` (gitignored) |
| 1.5 | Validate LLM connectivity with a smoke test | `AzureOpenAI.chat.completions.create()` returns OK |

**Deliverable:** Reproducible environment where `import openai` and `import fastapi` succeed.

### Phase 2 — Shared Module & JSON Database

| Task | Detail | Artifact |
|---|---|---|
| 2.1 | Define `MCPRequest` and `MCPResponse` Pydantic models | `shared/mcp_types.py` |
| 2.2 | Implement shared JSON database module with load/save helpers and 4 appointment handlers | `shared/db.py` |
| 2.3 | Design `db.json` schema with slots array (doctor, specialty, date, time, available, patient_name, cpf) | Schema specification |

**Deliverable:** Reusable shared module that any clinic server can import and bind via `functools.partial`.

### Phase 3 — MCP Servers Implementation (6 Federated Workers)

| Task | Detail | Artifact |
|---|---|---|
| 3.1 | Implement Clinic A (Cardiology, port 8001) with mock patient DB + `db.json` + 7 tool handlers | `clinic_agents/clinic_a/server.py`, `clinic_agents/clinic_a/db.json` |
| 3.2 | Implement Clinic B (Dermatology, port 8002) with mock patient DB + `db.json` + 7 tool handlers | `clinic_agents/clinic_b/server.py`, `clinic_agents/clinic_b/db.json` |
| 3.3 | Implement Clinic C (Cardiology, port 8003) with independent patient DB + `db.json` + 7 tool handlers | `clinic_agents/clinic_c/server.py`, `clinic_agents/clinic_c/db.json` |
| 3.4 | Implement Clinic D (Orthopedics, port 8004) with mock patient DB + `db.json` + 7 tool handlers | `clinic_agents/clinic_d/server.py`, `clinic_agents/clinic_d/db.json` |
| 3.5 | Implement Clinic E (Orthopedics, port 8005) with independent patient DB + `db.json` + 7 tool handlers | `clinic_agents/clinic_e/server.py`, `clinic_agents/clinic_e/db.json` |
| 3.6 | Implement Clinic F (Dermatology, port 8006) with independent patient DB + `db.json` + 7 tool handlers | `clinic_agents/clinic_f/server.py`, `clinic_agents/clinic_f/db.json` |
| 3.7 | Update launch script for all 6 servers | `clinic_agents/start_clinics.sh` |
| 3.8 | Validate each `/mcp` endpoint independently via `curl` | JSON-RPC responses with correct `result` payloads |

**Deliverable:** Six independently running MCP Servers, each with its own persistent `db.json`, that accept JSON-RPC 2.0 requests and return domain-specific data.

**Interoperability note:** All clinics share the same `MCPRequest`/`MCPResponse` contract from `shared/mcp_types.py` and the same appointment handler logic from `shared/db.py`, ensuring protocol-level interoperability and behavioral consistency without coupling their internal data.

### Phase 4 — Orchestrator Logic (MCP Client)

| Task | Detail | Artifact |
|---|---|---|
| 4.1 | Implement `Planner` with constrained system prompt including 6-clinic catalog, 7 tools, Rule 10 (multi-clinic routing), and conversation history support | `orchestrator_host/planner.py` |
| 4.2 | Implement Chain-of-Thought Planner variant (`decompose_cot`) | `orchestrator_host/planner.py` |
| 4.3 | Implement `Router` with 6-clinic registry and JSON-RPC dispatch, including automatic patient data injection | `orchestrator_host/router.py` |
| 4.4 | Implement `Verifier` (Observer Agent) with three safety rules, PII exceptions, and proper JSON serialization | `orchestrator_host/verifier.py` |
| 4.5 | Implement `RESPONSE_SYSTEM_PROMPT` with JSON schema description, faithful data presentation rules, and Rule 9 (cross-clinic comparison) | `orchestrator_host/main.py` |
| 4.6 | Wire all components in `main.py` CLI loop with patient identification and conversation history | `orchestrator_host/main.py` |
| 4.7 | Validate full pipeline: query -> decomposition -> multi-clinic dispatch -> verification -> response | End-to-end CLI test |

**Deliverable:** A working Orchestrator that decomposes queries, routes to up to 6 clinics (querying multiple clinics per specialty), gates output through the Verifier, and generates natural-language responses with cross-clinic comparisons.

**Decoupling note:** Each Orchestrator module (`Planner`, `Router`, `Verifier`) is a standalone class with no cross-dependencies. They communicate only through Python data structures (`list[dict]`, `MCPResponse`, `VerificationResult`), enabling independent unit testing.

### Phase 5 — Integration Testing & Logging (TCC Evidence)

| Task | Detail | Artifact |
|---|---|---|
| 5.1 | Create cancellation scenario test (3 turns: list -> book -> cancel) | `tests/test_cancel_scenario.py` |
| 5.2 | Create rescheduling scenario test (3 turns: list -> book -> reschedule) | `tests/test_reschedule_scenario.py` |
| 5.3 | Create unified three-flow test (4 turns: list -> book -> reschedule -> cancel + serialization and payload validations) | `tests/test_three_flows.py` |
| 5.4 | Create multi-clinic nearest-slot test (2 turns: list both cardiology clinics -> book at nearest) | `tests/test_multi_clinic_nearest.py` |
| 5.5 | Design test suite with >= 30 queries (normal, edge-case, adversarial, multi-clinic) | `tests/test_queries.json` |
| 5.6 | Add structured logging (JSON lines) to Planner, Router, and Verifier | `logs/pipeline_YYYYMMDD.jsonl` |
| 5.7 | Execute full test suite and capture logs | Raw log files |
| 5.8 | Compute TSR, TCA, HR, PVR from logs | Metrics summary table |
| 5.9 | Generate Mermaid diagrams and screenshots for thesis appendix | Visual evidence |

**Deliverable:** Quantitative evaluation data and visual artifacts ready for inclusion in the TCC Methodology and Results chapters.

---

## Appendix A — Project File Map

```
tcc-healthcare-agents/
|
+-- .env                              # Azure OpenAI credentials (gitignored)
+-- .env.example                      # Template for new contributors
+-- .gitignore                        # Protects .env and __pycache__
+-- requirements.txt                  # Python dependencies
|
+-- docs/                             # Versioned documentation
|   +-- v1.0.0/
|   |   +-- BLUEPRINT_TECNICO.md      # Blueprint PT v1.0.0 (historical archive)
|   |   +-- TECHNICAL_BLUEPRINT.md    # Blueprint EN v1.0.0 (historical archive)
|   +-- v2.0.0/
|   |   +-- BLUEPRINT_TECNICO.md      # Blueprint PT v2.0.0 (historical archive)
|   |   +-- TECHNICAL_BLUEPRINT.md    # Blueprint EN v2.0.0 (historical archive)
|   +-- v3.0.0/
|       +-- BLUEPRINT_TECNICO.md      # Blueprint PT v3.0.0 (current version)
|       +-- TECHNICAL_BLUEPRINT.md    # Blueprint EN v3.0.0 (current version)
|
+-- prompts/                          # System prompts (external files)
|   +-- planner.txt                   # Planner prompt (task decomposition + Rule 10)
|   +-- planner_cot.txt               # Planner prompt with Chain-of-Thought
|   +-- verifier.txt                  # Verifier prompt (safety validation)
|   +-- response_generator.txt        # Response Generator prompt (+ Rule 9)
|
+-- shared/
|   +-- __init__.py
|   +-- mcp_types.py                  # MCPRequest, MCPResponse (Pydantic)
|   +-- db.py                         # JSON DB helpers + 4 appointment handlers
|
+-- orchestrator_host/                # MCP Client — Federated Orchestrator
|   +-- __init__.py
|   +-- main.py                       # CLI entry point (5-stage pipeline, 9 agents)
|   +-- planner.py                    # Task Decomposition via Azure OpenAI (+ CoT)
|   +-- router.py                     # Dynamic Routing with 6-clinic registry
|   +-- verifier.py                   # Observer Agent [Burke et al. 2024]
|
+-- clinic_agents/                    # MCP Servers — Federated Workers
|   +-- __init__.py
|   +-- start_clinics.sh              # Launch script for all 6 clinic servers
|   +-- clinic_a/
|   |   +-- __init__.py
|   |   +-- server.py                 # Cardiology silo (port 8001, 7 tools)
|   |   +-- db.json                   # Appointment slots (persistent)
|   +-- clinic_b/
|   |   +-- __init__.py
|   |   +-- server.py                 # Dermatology silo (port 8002, 7 tools)
|   |   +-- db.json                   # Appointment slots (persistent)
|   +-- clinic_c/
|   |   +-- __init__.py
|   |   +-- server.py                 # Cardiology silo (port 8003, 7 tools)
|   |   +-- db.json                   # Appointment slots (persistent)
|   +-- clinic_d/
|   |   +-- __init__.py
|   |   +-- server.py                 # Orthopedics silo (port 8004, 7 tools)
|   |   +-- db.json                   # Appointment slots (persistent)
|   +-- clinic_e/
|   |   +-- __init__.py
|   |   +-- server.py                 # Orthopedics silo (port 8005, 7 tools)
|   |   +-- db.json                   # Appointment slots (persistent)
|   +-- clinic_f/
|       +-- __init__.py
|       +-- server.py                 # Dermatology silo (port 8006, 7 tools)
|       +-- db.json                   # Appointment slots (persistent)
|
+-- tests/                            # Integration tests
    +-- test_cancel_scenario.py       # Scenario: list -> book -> cancel
    +-- test_reschedule_scenario.py   # Scenario: list -> book -> reschedule
    +-- test_three_flows.py           # Unified scenario for all three flows
    +-- test_multi_clinic_nearest.py  # Multi-clinic: query 2 clinics -> book nearest
```

## Appendix B — Glossary of Terms

| Term | Definition |
|---|---|
| **Decoupling** | Design principle where components interact through defined interfaces (MCP) without internal knowledge of each other. |
| **Interoperability** | The ability of heterogeneous clinic agents to communicate via a shared protocol (JSON-RPC 2.0 / MCP). |
| **Deterministic Validation** | Verification rules that produce consistent, reproducible outcomes given the same input (temperature 0.0). |
| **Data Minimization** | Transmitting only the minimum data required for each operation (LGPD Art. 6, III). |
| **Federated Data Silo** | An isolated data store that does not share raw records with external systems. In v3.0.0, each clinic's `db.json` file is a federated data silo. |
| **Step Graph** | An ordered list of atomic operations produced by the Planner, each targeting one clinic. |
| **Observer Agent** | An independent auditing agent that validates outputs without participating in their generation (Burke et al. 2024). |
| **Hub-and-Spoke** | Network topology where all communication flows through a central hub (Orchestrator); spokes (Clinics) never communicate directly. |
| **Tool Handler** | A registered function on an MCP Server that executes a specific domain operation when invoked via `tools/call`. |
| **Chain-of-Thought (CoT)** | A prompting technique where the LLM explicates its reasoning step-by-step before producing the final output, improving decomposition quality and providing an audit trail. |
| **Multi-Turn** | A conversational interaction with multiple turns where context from prior turns influences current-turn processing. |
| **Response Generator** | An internal Orchestrator capability that transforms validated structured data into conversational natural-language responses using an LLM. |
| **Multi-Clinic Routing** | The Planner strategy (Rule 10) of generating one step per clinic when a specialty has multiple clinics, ensuring all relevant clinics are queried for comprehensive availability comparison. |
| **JSON Database** | A file-based persistence layer (`db.json`) used by each clinic to store appointment slot data. Supports read, write, and atomic update operations via `shared/db.py`. |
| **Partial Application** | A functional programming pattern (`functools.partial`) used to bind shared handler functions with clinic-specific parameters (`_DB_PATH`, `_SPECIALTY`), enabling code reuse without coupling data. |
| **Cross-Clinic Comparison** | The Response Generator strategy (Rule 9) of presenting slots from multiple clinics of the same specialty together, indicating clinic origin and highlighting the earliest/nearest option. |
| **Uniform Specialty Description** | The architectural principle that all clinics of the same specialty expose identical tool interfaces and descriptions, differing only in their underlying data (doctors, schedules, patients). |

---

> **Document generated for academic use.**
> Architecture: Hierarchical Federated Orchestrator-Workers with Observer.
> Protocol: Model Context Protocol (MCP) over HTTP / JSON-RPC 2.0.
> Version: 3.0.0
