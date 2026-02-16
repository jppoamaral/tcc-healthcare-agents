"""
Clínica F — Servidor MCP de Dermatologia
===========================================
Silo de dados federado de dermatologia expondo ferramentas MCP.
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
    title="Clínica F — Dermatologia (Servidor MCP)",
    description="Silo de dados federado de dermatologia expondo ferramentas MCP.",
    version="0.1.0",
)

_DB_PATH = Path(__file__).resolve().parent / "db.json"
_SPECIALTY = "Dermatology"

# ---------------------------------------------------------------------------
# Banco de Dados Mock de Dermatologia
# ---------------------------------------------------------------------------
DERMATOLOGY_DB: list[dict[str, Any]] = [
    {
        "patient_id": "DERM-F001",
        "name": "Juliana Prado",
        "age": 33,
        "condition": "Melasma",
        "last_treatment": "Chemical peel — glycolic acid 30%",
        "next_appointment": "2025-08-10",
    },
    {
        "patient_id": "DERM-F002",
        "name": "Eduardo Fonseca",
        "age": 55,
        "condition": "Basal Cell Carcinoma — Nose",
        "last_biopsy": "Confirmed BCC, nodular type",
        "next_appointment": "2025-07-22",
    },
    {
        "patient_id": "DERM-F003",
        "name": "Camila Rezende",
        "age": 27,
        "condition": "Contact Dermatitis — Nickel Allergy",
        "last_patch_test": "Positive for nickel sulfate",
        "next_appointment": "2025-09-05",
    },
]

# ---------------------------------------------------------------------------
# Handlers de ferramentas
# ---------------------------------------------------------------------------

def _handle_list_patients(**_kwargs: Any) -> dict[str, Any]:
    return {
        "patients": [
            {"patient_id": p["patient_id"], "condition": p["condition"]}
            for p in DERMATOLOGY_DB
        ]
    }


def _handle_get_patient(patient_id: str = "", **_kwargs: Any) -> dict[str, Any]:
    for patient in DERMATOLOGY_DB:
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
    uvicorn.run(app, host="0.0.0.0", port=8006)
