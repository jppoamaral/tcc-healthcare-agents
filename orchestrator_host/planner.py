"""
Agente Planejador — Decomposição em Grafo de Etapas
=====================================================
Responsável pela primeira fase do padrão de Coordenação Hierárquica:
receber uma consulta do usuário final e decompô-la em uma lista ordenada
de etapas executáveis (um "grafo de etapas") que o Router pode despachar
para os Agentes de Clínica federados apropriados.

Referência:
    Coordenação Hierárquica — o Orchestrator decompõe objetivos de alto
    nível em sub-tarefas antes de delegá-las, impedindo que qualquer
    agente individual tenha uma visão global dos dados do paciente
    (Preservação de Privacidade).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from openai import AzureOpenAI

# ---------------------------------------------------------------------------
# Prompts de sistema — carregados de arquivos externos em prompts/ para legibilidade.
# ---------------------------------------------------------------------------
_prompts_dir = Path(__file__).resolve().parents[1] / "prompts"

PLANNER_SYSTEM_PROMPT = (_prompts_dir / "planner.txt").read_text(encoding="utf-8")

PLANNER_COT_SYSTEM_PROMPT = (_prompts_dir / "planner_cot.txt").read_text(encoding="utf-8")


class Planner:
    """Decompõe uma consulta do usuário em um grafo de etapas executável usando Azure OpenAI."""

    def __init__(self, azure_client: AzureOpenAI, deployment: str) -> None:
        self.client = azure_client
        self.deployment = deployment

    def decompose(
        self,
        user_query: str,
        conversation_history: list[dict[str, str]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Envia a consulta do usuário ao Azure OpenAI com o prompt de sistema
        do planejador e retorna o grafo de etapas parseado.

        Args:
            user_query:           A entrada atual do usuário.
            conversation_history: Lista opcional de turnos anteriores, cada um
                                  um dict com chaves 'role' e 'content'.

        Returns:
            Uma lista de dicts de etapa, ex.:
            [{"step_id": 1, "clinic": "clinic_a", "action": "...", "parameters": {...}}]
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        ]
        if conversation_history:
            messages.extend(conversation_history)
        messages.append({"role": "user", "content": user_query})

        response = self.client.chat.completions.create(
            model=self.deployment,
            temperature=0.0,
            messages=messages,
        )

        raw = response.choices[0].message.content.strip()

        try:
            steps = json.loads(raw)
        except json.JSONDecodeError:
            # Fallback: encapsula a resposta bruta para que a execução continue
            steps = [
                {
                    "step_id": 1,
                    "clinic": "unknown",
                    "action": "raw_response",
                    "parameters": {"text": raw},
                }
            ]

        return steps

    def decompose_cot(self, user_query: str) -> dict[str, Any]:
        """
        Decomposição Chain-of-Thought — o LLM raciocina explicitamente antes
        de produzir o grafo de etapas.

        Returns:
            Um dict com 'reasoning' (list[str]) e 'steps' (list[dict]).
        """
        response = self.client.chat.completions.create(
            model=self.deployment,
            temperature=0.0,
            messages=[
                {"role": "system", "content": PLANNER_COT_SYSTEM_PROMPT},
                {"role": "user", "content": user_query},
            ],
        )

        raw = response.choices[0].message.content.strip()

        try:
            parsed = json.loads(raw)
            return {
                "reasoning": parsed.get("reasoning", []),
                "steps": parsed.get("steps", []),
            }
        except json.JSONDecodeError:
            return {
                "reasoning": ["Falha ao parsear a resposta do LLM."],
                "steps": [
                    {
                        "step_id": 1,
                        "clinic": "unknown",
                        "action": "raw_response",
                        "parameters": {"text": raw},
                    }
                ],
            }
