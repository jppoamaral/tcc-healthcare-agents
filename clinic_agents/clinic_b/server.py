"""
Clínica B — Servidor MCP de Dermatologia
===========================================
Aplicação FastAPI que expõe um único endpoint /mcp seguindo a convenção
JSON-RPC 2.0 / Model Context Protocol (MCP).

Notas de arquitetura:
    Preservação de Privacidade — este servidor opera como um silo de dados
    federado isolado. Registros de pacientes nunca saem deste processo;
    apenas resultados de consultas são retornados ao Orchestrator.

    Coordenação Hierárquica — este Agente de Clínica é um "Trabalhador"
    que responde apenas a requisições despachadas pelo Router do
    Orchestrator. Ele não tem conhecimento de outras clínicas ou do
    plano global de tarefas.
"""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path
from typing import Any

from fastapi import FastAPI

# ---------------------------------------------------------------------------
# Garante que o pacote compartilhado é importável ao executar este arquivo diretamente.
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from shared.mcp_types import MCPRequest, MCPResponse  # noqa: E402
from shared.db import (                                # noqa: E402
    handle_list_available_slots,
    handle_book_appointment,
    handle_cancel_appointment,
    handle_reschedule_appointment,
)

app = FastAPI(
    title="Clínica B — Dermatologia (Servidor MCP)",
    description="Silo de dados federado de dermatologia expondo ferramentas MCP.",
    version="0.1.0",
)

_DB_PATH = Path(__file__).resolve().parent / "db.json"
_SPECIALTY = "Dermatology"

# ---------------------------------------------------------------------------
# Banco de Dados Mock de Dermatologia (simula um silo de dados federado)
# ---------------------------------------------------------------------------
DERMATOLOGY_DB: list[dict[str, Any]] = [
    {
        "patient_id": "DERM-001",
        "name": "Carlos Mendes",
        "age": 34,
        "condition": "Atopic Dermatitis",
        "affected_area": "Arms and neck",
        "next_appointment": "2025-07-28",
    },
    {
        "patient_id": "DERM-002",
        "name": "Fernanda Lima",
        "age": 29,
        "condition": "Psoriasis (plaque type)",
        "affected_area": "Scalp and elbows",
        "next_appointment": "2025-08-10",
    },
    {
        "patient_id": "DERM-003",
        "name": "Roberto Alves",
        "age": 71,
        "condition": "Suspected melanoma — pending biopsy",
        "affected_area": "Left forearm, 8 mm lesion",
        "biopsy_scheduled": "2025-07-18",
        "next_appointment": "2025-07-25",
    },
]


# ---------------------------------------------------------------------------
# Handlers de ferramentas
# ---------------------------------------------------------------------------

def _handle_list_patients(**_kwargs: Any) -> dict[str, Any]:
    """Retorna um resumo de todos os pacientes (Privacidade: apenas IDs e condições)."""
    return {
        "patients": [
            {"patient_id": p["patient_id"], "condition": p["condition"]}
            for p in DERMATOLOGY_DB
        ]
    }


def _handle_get_patient(patient_id: str = "", **_kwargs: Any) -> dict[str, Any]:
    """Retorna o registro completo de um único paciente."""
    for patient in DERMATOLOGY_DB:
        if patient["patient_id"] == patient_id:
            return {"patient": patient}
    return {"error": f"Paciente '{patient_id}' não encontrado"}


_handle_list_available_slots = partial(handle_list_available_slots, _DB_PATH, _SPECIALTY)
_handle_book_appointment = partial(handle_book_appointment, _DB_PATH, _SPECIALTY)
_handle_cancel_appointment = partial(handle_cancel_appointment, _DB_PATH, _SPECIALTY)
_handle_reschedule_appointment = partial(handle_reschedule_appointment, _DB_PATH, _SPECIALTY)


def _handle_query(query: str = "", **_kwargs: Any) -> dict[str, Any]:
    """Busca em texto livre em todos os registros de dermatologia."""
    query_lower = query.lower()
    matches = [
        {"patient_id": p["patient_id"], "condition": p["condition"]}
        for p in DERMATOLOGY_DB
        if query_lower in str(p).lower()
    ]
    return {"specialty": "Dermatology", "query": query, "matches": matches}


TOOL_HANDLERS = {
    "list_patients": _handle_list_patients,
    "get_patient": _handle_get_patient,
    "query": _handle_query,
    "list_available_slots": _handle_list_available_slots,
    "book_appointment": _handle_book_appointment,
    "reschedule_appointment": _handle_reschedule_appointment,
    "cancel_appointment": _handle_cancel_appointment,
}


# ---------------------------------------------------------------------------
# Endpoint MCP
# ---------------------------------------------------------------------------

@app.post("/mcp", response_model=MCPResponse)
async def mcp_endpoint(request: MCPRequest) -> MCPResponse:
    """
    Ponto de entrada JSON-RPC 2.0 / MCP.
    """
    if request.method != "tools/call":
        return MCPResponse(
            id=request.id,
            error={
                "code": -32601,
                "message": f"Método '{request.method}' não suportado. Use 'tools/call'.",
            },
        )

    tool_name = request.params.get("name", "")
    arguments = request.params.get("arguments", {})

    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return MCPResponse(
            id=request.id,
            error={
                "code": -32602,
                "message": (
                    f"Ferramenta desconhecida '{tool_name}'. "
                    f"Disponíveis: {list(TOOL_HANDLERS.keys())}"
                ),
            },
        )

    result = handler(**arguments)
    return MCPResponse(id=request.id, result=result)


# ---------------------------------------------------------------------------
# Execução direta
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8002)
