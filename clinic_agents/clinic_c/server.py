"""
Clínica C — Servidor MCP de Cardiologia
==========================================
Silo de dados federado de cardiologia expondo ferramentas MCP.
Clínica independente com seus próprios médicos, agendas e registros de pacientes.
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
    title="Clínica C — Cardiologia (Servidor MCP)",
    description="Silo de dados federado de cardiologia expondo ferramentas MCP.",
    version="0.1.0",
)

_DB_PATH = Path(__file__).resolve().parent / "db.json"
_SPECIALTY = "Cardiology"

# ---------------------------------------------------------------------------
# Banco de Dados Mock de Cardiologia (simula um silo de dados federado)
# Pacientes diferentes da Clínica A — completamente independente.
# ---------------------------------------------------------------------------
CARDIOLOGY_DB: list[dict[str, Any]] = [
    {
        "patient_id": "CARD-C001",
        "name": "Roberto Almeida",
        "age": 58,
        "condition": "Coronary Artery Disease",
        "last_catheterization": "2025-03-10",
        "next_appointment": "2025-08-20",
    },
    {
        "patient_id": "CARD-C002",
        "name": "Teresa Monteiro",
        "age": 70,
        "condition": "Aortic Stenosis",
        "last_echo": "Valve area 0.9 cm2",
        "next_appointment": "2025-07-25",
    },
    {
        "patient_id": "CARD-C003",
        "name": "Paulo Nascimento",
        "age": 42,
        "condition": "Hypertrophic Cardiomyopathy",
        "last_mri": "Septal thickness 18mm",
        "next_appointment": "2025-09-10",
    },
]


# ---------------------------------------------------------------------------
# Handlers de ferramentas — cada ação que o Orchestrator pode requisitar.
# ---------------------------------------------------------------------------

def _handle_list_patients(**_kwargs: Any) -> dict[str, Any]:
    """Retorna um resumo de todos os pacientes (Privacidade: apenas IDs e condições)."""
    return {
        "patients": [
            {"patient_id": p["patient_id"], "condition": p["condition"]}
            for p in CARDIOLOGY_DB
        ]
    }


def _handle_get_patient(patient_id: str = "", **_kwargs: Any) -> dict[str, Any]:
    """Retorna o registro completo de um único paciente."""
    for patient in CARDIOLOGY_DB:
        if patient["patient_id"] == patient_id:
            return {"patient": patient}
    return {"error": f"Paciente '{patient_id}' não encontrado"}


_handle_list_available_slots = partial(handle_list_available_slots, _DB_PATH, _SPECIALTY)
_handle_book_appointment = partial(handle_book_appointment, _DB_PATH, _SPECIALTY)
_handle_cancel_appointment = partial(handle_cancel_appointment, _DB_PATH, _SPECIALTY)
_handle_reschedule_appointment = partial(handle_reschedule_appointment, _DB_PATH, _SPECIALTY)


def _handle_query(query: str = "", **_kwargs: Any) -> dict[str, Any]:
    """Busca em texto livre em todos os registros de cardiologia."""
    query_lower = query.lower()
    matches = [
        {"patient_id": p["patient_id"], "condition": p["condition"]}
        for p in CARDIOLOGY_DB
        if query_lower in str(p).lower()
    ]
    return {"specialty": "Cardiology", "query": query, "matches": matches}


# Registro de ferramentas disponíveis
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

    Espera method="tools/call" com params.name identificando a ferramenta
    e params.arguments contendo os argumentos nomeados da ferramenta.
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

    uvicorn.run(app, host="0.0.0.0", port=8003)
