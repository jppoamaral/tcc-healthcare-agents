"""
Agente Verificador — Observador de Segurança e Conformidade
=============================================================
Atua como o Agente Observador descrito em Burke et al. (2024): recebe
toda resposta produzida pelo pipeline multi-agente e a valida contra
um conjunto configurável de regras de segurança *antes* de exibi-la
ao usuário final.

Notas de arquitetura:
    Coordenação Hierárquica — o Verificador é o portão final no pipeline
    do orquestrador; nenhuma saída de clínica chega ao usuário sem
    validação independente.

    Preservação de Privacidade — o Verificador verifica que nenhuma
    Informação Pessoal Identificável (PII) vaza através de respostas
    agregadas.

Referência:
    Burke, T. et al. (2024). "Observer Agents for Safe Multi-Agent
    Medical Systems" — propõe uma camada de verificação independente que
    audita saídas de agentes para dosagens alucinadas, interações
    medicamentosas contraindicadas e exposição de PII.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AzureOpenAI

# ---------------------------------------------------------------------------
# Prompt de sistema — carregado de arquivo externo em prompts/ para legibilidade.
# ---------------------------------------------------------------------------
_prompts_dir = Path(__file__).resolve().parents[1] / "prompts"

VERIFIER_SYSTEM_PROMPT = (_prompts_dir / "verifier.txt").read_text(encoding="utf-8")


@dataclass
class VerificationResult:
    """Resultado da verificação de segurança."""

    safe: bool
    note: str


class Verifier:
    """
    Agente Observador [Burke et al. 2024] — valida respostas agregadas das
    clínicas contra regras de segurança e privacidade usando Azure OpenAI.
    """

    def __init__(self, azure_client: AzureOpenAI, deployment: str) -> None:
        self.client = azure_client
        self.deployment = deployment

    def verify(
        self, user_query: str, agent_response: Any
    ) -> VerificationResult:
        """
        Valida a agent_response contra regras de segurança.

        Args:
            user_query:     A entrada original do usuário.
            agent_response: A resposta agregada de todas as etapas das clínicas.

        Returns:
            Um VerificationResult indicando se a resposta é segura.
        """
        import json

        payload = json.dumps(
            {
                "user_query": user_query,
                "agent_response": json.dumps(agent_response, ensure_ascii=False),
            },
            ensure_ascii=False,
        )

        response = self.client.chat.completions.create(
            model=self.deployment,
            temperature=0.0,
            messages=[
                {"role": "system", "content": VERIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": payload},
            ],
        )

        raw = response.choices[0].message.content.strip()

        try:
            data = json.loads(raw)
            return VerificationResult(
                safe=bool(data.get("safe", False)),
                note=data.get("note", "Nenhuma nota fornecida"),
            )
        except json.JSONDecodeError:
            return VerificationResult(
                safe=False,
                note=f"Verificador retornou não-JSON: {raw}",
            )
