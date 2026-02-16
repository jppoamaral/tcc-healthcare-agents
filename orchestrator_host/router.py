"""
Agente Router — Despacho Federado
====================================
Mantém um registro de endpoints dos Agentes de Clínica e despacha etapas
individuais do grafo de etapas do Planejador para o Servidor MCP correto
via chamadas HTTP JSON-RPC.

Notas de arquitetura:
    Coordenação Hierárquica — o Router é o único componente que conhece
    a topologia de rede; os Agentes de Clínica não sabem da existência
    uns dos outros, reforçando a fronteira federada.

    Preservação de Privacidade — cada requisição é direcionada a uma única
    clínica. Nenhum dado de paciente entre clínicas transita pelo Router
    em um único payload.
"""

from __future__ import annotations

import uuid
from typing import Any

import requests

from shared.mcp_types import MCPRequest, MCPResponse


# ---------------------------------------------------------------------------
# Registro padrão de clínicas — mapeia nomes lógicos para endpoints MCP.
# Em produção, estes viriam de uma camada de service-discovery ou variáveis de ambiente.
# ---------------------------------------------------------------------------
DEFAULT_REGISTRY: dict[str, str] = {
    "clinic_a": "http://localhost:8001/mcp",
    "clinic_b": "http://localhost:8002/mcp",
    "clinic_c": "http://localhost:8003/mcp",
    "clinic_d": "http://localhost:8004/mcp",
    "clinic_e": "http://localhost:8005/mcp",
    "clinic_f": "http://localhost:8006/mcp",
}


class Router:
    """
    Despacha etapas do grafo para o Agente de Clínica federado apropriado
    usando o protocolo MCP JSON-RPC sobre HTTP.
    """

    def __init__(self, registry: dict[str, str] | None = None) -> None:
        self.registry = registry or DEFAULT_REGISTRY

    def dispatch(self, step: dict[str, Any]) -> MCPResponse:
        """
        Envia uma única etapa para o endpoint MCP da clínica alvo.

        Args:
            step: Um dict com pelo menos 'clinic', 'action' e 'parameters'.

        Returns:
            Um MCPResponse parseado da resposta JSON-RPC da clínica.

        Raises:
            ValueError: Se a clínica alvo não estiver no registro.
            requests.RequestException: Em falhas de rede.
        """
        clinic_id = step.get("clinic", "unknown")
        url = self.registry.get(clinic_id)

        if url is None:
            return MCPResponse(
                id="error",
                error={
                    "code": -32601,
                    "message": f"Clínica '{clinic_id}' não encontrada no registro",
                },
            )

        # Constrói uma requisição MCP / JSON-RPC 2.0 padrão
        mcp_request = MCPRequest(
            id=str(uuid.uuid4()),
            method="tools/call",
            params={
                "name": step.get("action", ""),
                "arguments": step.get("parameters", {}),
            },
        )

        try:
            http_response = requests.post(
                url,
                json=mcp_request.model_dump(),
                headers={"Content-Type": "application/json"},
                timeout=30,
            )
            http_response.raise_for_status()
            return MCPResponse(**http_response.json())

        except requests.RequestException as exc:
            return MCPResponse(
                id=mcp_request.id,
                error={
                    "code": -32000,
                    "message": f"Erro de rede ao contactar {clinic_id}: {exc}",
                },
            )
