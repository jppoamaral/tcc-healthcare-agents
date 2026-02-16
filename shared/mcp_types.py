"""
Definições de Tipos MCP JSON-RPC
=================================
Tipos de mensagem padronizados para a camada de comunicação do Model Context
Protocol (MCP) entre o Orchestrator Host (cliente) e os Agentes de Clínica
(servidores).

Nota de arquitetura — Preservação de Privacidade:
    Cada mensagem é autocontida para que os servidores das clínicas nunca
    precisem compartilhar dados brutos de pacientes entre si. O orquestrador
    encaminha requisições discretas e apenas agrega resultados anonimizados.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class MCPRequest(BaseModel):
    """
    Envelope de requisição JSON-RPC 2.0 usado pelo Orchestrator para invocar
    uma ferramenta/recurso em um Agente de Clínica remoto (Servidor MCP).
    """

    jsonrpc: str = Field(default="2.0", description="Versão do protocolo JSON-RPC")
    id: str = Field(..., description="Identificador único desta requisição")
    method: str = Field(
        ...,
        description="Método MCP a invocar (ex.: 'tools/call', 'resources/read')",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Parâmetros específicos do método",
    )


class MCPResponse(BaseModel):
    """
    Envelope de resposta JSON-RPC 2.0 retornado por um Agente de Clínica.
    Exatamente um entre `result` ou `error` estará presente.
    """

    jsonrpc: str = Field(default="2.0", description="Versão do protocolo JSON-RPC")
    id: str = Field(..., description="Deve corresponder ao id da requisição")
    result: Optional[Any] = Field(
        default=None,
        description="Payload do resultado bem-sucedido",
    )
    error: Optional[dict[str, Any]] = Field(
        default=None,
        description="Objeto de erro com código, mensagem e dados opcionais",
    )
