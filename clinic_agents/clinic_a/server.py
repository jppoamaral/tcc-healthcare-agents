"""
Clínica A — Servidor MCP de Cardiologia
==========================================
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
    title="Clínica A — Cardiologia (Servidor MCP)",
    description="Silo de dados federado de cardiologia expondo ferramentas MCP.",
    version="0.1.0",
)

_DB_PATH = Path(__file__).resolve().parent / "db.json"
_SPECIALTY = "Cardiology"

# ---------------------------------------------------------------------------
# Banco de Dados Mock de Cardiologia (simula um silo de dados federado)
# Em produção seria conectado a um prontuário eletrônico real (EHR / FHIR).
# ---------------------------------------------------------------------------
CARDIOLOGY_DB: list[dict[str, Any]] = [
    {
        "patient_id": "CARD-001",
        "name": "Maria Silva",
        "age": 62,
        "condition": "Hypertension",
        "last_bp": "150/95 mmHg",
        "next_appointment": "2025-08-15",
    },
    {
        "patient_id": "CARD-002",
        "name": "João Pereira",
        "age": 45,
        "condition": "Arrhythmia",
        "last_ecg": "Atrial fibrillation detected",
        "next_appointment": "2025-07-20",
    },
    {
        "patient_id": "CARD-003",
        "name": "Ana Costa",
        "age": 55,
        "condition": "Heart Failure — NYHA Class II",
        "ejection_fraction": "38%",
        "next_appointment": "2025-09-01",
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

    uvicorn.run(app, host="0.0.0.0", port=8001)
