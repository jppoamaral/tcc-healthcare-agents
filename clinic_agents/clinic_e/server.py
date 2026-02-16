"""
Clínica E — Servidor MCP de Ortopedia
========================================
Silo de dados federado de ortopedia expondo ferramentas MCP.
Clínica independente com seus próprios médicos, agendas e registros de pacientes.
"""

from __future__ import annotations

import sys
from functools import partial
from pathlib import Path
from typing import Any

from fastapi import FastAPI

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
    title="Clínica E — Ortopedia (Servidor MCP)",
    description="Silo de dados federado de ortopedia expondo ferramentas MCP.",
    version="0.1.0",
)

_DB_PATH = Path(__file__).resolve().parent / "db.json"
_SPECIALTY = "Orthopedics"

# ---------------------------------------------------------------------------
# Banco de Dados Mock de Ortopedia
# ---------------------------------------------------------------------------
ORTHOPEDICS_DB: list[dict[str, Any]] = [
    {
        "patient_id": "ORTH-E001",
        "name": "Claudia Ferraz",
        "age": 52,
        "condition": "Herniated Disc — L4-L5",
        "last_mri": "Posterolateral herniation with nerve compression",
        "next_appointment": "2025-08-01",
    },
    {
        "patient_id": "ORTH-E002",
        "name": "Diego Barbosa",
        "age": 11,
        "condition": "Scoliosis — Adolescent Idiopathic",
        "last_xray": "Cobb angle 28 degrees",
        "next_appointment": "2025-07-30",
    },
    {
        "patient_id": "ORTH-E003",
        "name": "Mariana Teixeira",
        "age": 45,
        "condition": "Carpal Tunnel Syndrome",
        "last_emg": "Moderate median nerve compression",
        "next_appointment": "2025-08-18",
    },
]

# ---------------------------------------------------------------------------
# Handlers de ferramentas
# ---------------------------------------------------------------------------

def _handle_list_patients(**_kwargs: Any) -> dict[str, Any]:
    return {
        "patients": [
            {"patient_id": p["patient_id"], "condition": p["condition"]}
            for p in ORTHOPEDICS_DB
        ]
    }


def _handle_get_patient(patient_id: str = "", **_kwargs: Any) -> dict[str, Any]:
    for patient in ORTHOPEDICS_DB:
        if patient["patient_id"] == patient_id:
            return {"patient": patient}
    return {"error": f"Paciente '{patient_id}' não encontrado"}


_handle_list_available_slots = partial(handle_list_available_slots, _DB_PATH, _SPECIALTY)
_handle_book_appointment = partial(handle_book_appointment, _DB_PATH, _SPECIALTY)
_handle_cancel_appointment = partial(handle_cancel_appointment, _DB_PATH, _SPECIALTY)
_handle_reschedule_appointment = partial(handle_reschedule_appointment, _DB_PATH, _SPECIALTY)


def _handle_query(query: str = "", **_kwargs: Any) -> dict[str, Any]:
    query_lower = query.lower()
    matches = [
        {"patient_id": p["patient_id"], "condition": p["condition"]}
        for p in ORTHOPEDICS_DB
        if query_lower in str(p).lower()
    ]
    return {"specialty": "Orthopedics", "query": query, "matches": matches}


TOOL_HANDLERS = {
    "list_patients": _handle_list_patients,
    "get_patient": _handle_get_patient,
    "query": _handle_query,
    "list_available_slots": _handle_list_available_slots,
    "book_appointment": _handle_book_appointment,
    "reschedule_appointment": _handle_reschedule_appointment,
    "cancel_appointment": _handle_cancel_appointment,
}


@app.post("/mcp", response_model=MCPResponse)
async def mcp_endpoint(request: MCPRequest) -> MCPResponse:
    if request.method != "tools/call":
        return MCPResponse(id=request.id, error={"code": -32601, "message": f"Método '{request.method}' não suportado. Use 'tools/call'."})
    tool_name = request.params.get("name", "")
    arguments = request.params.get("arguments", {})
    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        return MCPResponse(id=request.id, error={"code": -32602, "message": f"Ferramenta desconhecida '{tool_name}'. Disponíveis: {list(TOOL_HANDLERS.keys())}"})
    result = handler(**arguments)
    return MCPResponse(id=request.id, result=result)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
