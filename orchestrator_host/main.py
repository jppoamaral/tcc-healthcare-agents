"""
Orchestrator Host — Ponto de Entrada Principal
================================================
O Cliente MCP que coordena todo o sistema multi-agente Federado
Orquestrador-Trabalhadores para saúde.

Pipeline Multi-Agente (5 agentes):
    1. Entrada do usuário →  [Agente: Planejador]     Decomposição de Tarefas
    2. Grafo de etapas    →  [Agente: Router]          Despacho Federado
    3. Requisições MCP    →  [Agente: Clínica A/B/...] Execução Específica do Domínio
    4. Resultados brutos  →  [Agente: Verificador]     Validação de Segurança (Observador)
    5. Validado           →  [Orchestrator]            Resposta em Linguagem Natural

Notas de arquitetura:
    Coordenação Hierárquica — o Orchestrator está no topo da hierarquia
    e é o único componente com visão global da tarefa. As clínicas
    individuais (trabalhadores) veem apenas suas próprias sub-tarefas.

    Preservação de Privacidade — dados brutos de pacientes nunca são
    agregados fora da clínica que os possui. O Orchestrator vê apenas
    *resultados* de consultas, que são auditados pelo Verificador antes
    de chegar ao usuário.

    Geração de Resposta — após o Verificador aprovar os dados agregados,
    o próprio Orchestrator transforma os resultados estruturados em uma
    resposta conversacional em linguagem natural usando Azure OpenAI.
    Isso faz parte da responsabilidade de coordenação do Orchestrator,
    não é um agente separado, mantendo o sistema dentro do padrão
    arquitetural estabelecido.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AzureOpenAI

# ---------------------------------------------------------------------------
# Garante que a raiz do projeto está no sys.path para `shared` ser importável.
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from orchestrator_host.planner import Planner          # noqa: E402
from orchestrator_host.router import Router            # noqa: E402
from orchestrator_host.verifier import Verifier        # noqa: E402


# ---------------------------------------------------------------------------
# Rótulos dos agentes — torna o Sistema Multi-Agente visível no CLI
# ---------------------------------------------------------------------------
AGENT_ORCHESTRATOR = "[Agente: Orchestrator]"
AGENT_PLANNER      = "[Agente: Planejador]"
AGENT_ROUTER       = "[Agente: Router]"
AGENT_CLINIC_A     = "[Agente: Clínica A (Cardiologia)]"
AGENT_CLINIC_B     = "[Agente: Clínica B (Dermatologia)]"
AGENT_CLINIC_C     = "[Agente: Clínica C (Cardiologia)]"
AGENT_CLINIC_D     = "[Agente: Clínica D (Ortopedia)]"
AGENT_CLINIC_E     = "[Agente: Clínica E (Ortopedia)]"
AGENT_CLINIC_F     = "[Agente: Clínica F (Dermatologia)]"
AGENT_VERIFIER     = "[Agente: Verificador (Observador)]"

CLINIC_LABELS = {
    "clinic_a": AGENT_CLINIC_A,
    "clinic_b": AGENT_CLINIC_B,
    "clinic_c": AGENT_CLINIC_C,
    "clinic_d": AGENT_CLINIC_D,
    "clinic_e": AGENT_CLINIC_E,
    "clinic_f": AGENT_CLINIC_F,
}

# ---------------------------------------------------------------------------
# Prompt de geração de resposta — usado pelo Orchestrator para converter
# dados estruturados das clínicas em linguagem natural conversacional.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Prompt de sistema — carregado de arquivo externo em prompts/ para legibilidade.
# ---------------------------------------------------------------------------
RESPONSE_SYSTEM_PROMPT = (
    _project_root / "prompts" / "response_generator.txt"
).read_text(encoding="utf-8")


def _generate_response(
    client: AzureOpenAI,
    deployment: str,
    user_query: str,
    aggregated_results: list[dict[str, Any]],
) -> str:
    """
    Geração de resposta do Orchestrator — transforma dados validados das
    clínicas em uma resposta conversacional em linguagem natural.

    Esta é uma capacidade interna do Orchestrator, não um agente separado.
    """
    payload = json.dumps(
        {
            "user_query": user_query,
            "clinic_data": [
                {
                    "clinic": item["step"].get("clinic", "?"),
                    "action": item["step"].get("action", "?"),
                    "result": item.get("result"),
                    "error": item.get("error"),
                }
                for item in aggregated_results
            ],
        },
        ensure_ascii=False,
    )

    response = client.chat.completions.create(
        model=deployment,
        temperature=0.3,
        messages=[
            {"role": "system", "content": RESPONSE_SYSTEM_PROMPT},
            {"role": "user", "content": payload},
        ],
    )

    return response.choices[0].message.content.strip()


def _collect_patient_info() -> dict[str, str]:
    """
    Coleta a identificação do paciente antes de iniciar a sessão.

    Retorna um dict com as chaves 'name' e 'cpf'.
    """
    print("-" * 65)
    print("  Identificação do Paciente")
    print("  Por favor, informe seus dados antes de prosseguir.")
    print("-" * 65)
    print()

    # --- Nome ---
    while True:
        name = input("  Nome completo: ").strip()
        if name:
            break
        print("  Por favor, informe seu nome.\n")

    # --- CPF ---
    while True:
        cpf = input("  CPF: ").strip()
        if cpf:
            break
        print("  Por favor, informe seu CPF.\n")

    print()
    print(f"  Paciente identificado: {name} (CPF: {cpf})")
    print()
    return {"name": name, "cpf": cpf}


def build_azure_client() -> tuple[AzureOpenAI, str]:
    """
    Inicializa o cliente AzureOpenAI a partir de variáveis de ambiente.
    """
    dotenv_path = _project_root / ".env"
    load_dotenv(dotenv_path=dotenv_path)

    api_key = os.getenv("AZURE_OPENAI_KEY", "")
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o")

    if not api_key or not endpoint:
        print(
            "ERRO: AZURE_OPENAI_KEY e AZURE_OPENAI_ENDPOINT devem estar "
            "definidos no arquivo .env."
        )
        sys.exit(1)

    client = AzureOpenAI(
        api_key=api_key,
        api_version="2024-06-01",
        azure_endpoint=endpoint,
    )
    return client, deployment


def main() -> None:
    """Executa o loop interativo do CLI."""

    print("=" * 65)
    print("  Health MAS — Sistema Multi-Agente para Saúde")
    print("  Arquitetura: Orquestrador-Trabalhadores Federado com Observador")
    print("  Protocolo: MCP sobre HTTP / JSON-RPC 2.0")
    print("=" * 65)
    print()

    # --- Inicializa os agentes ---
    client, deployment = build_azure_client()

    planner  = Planner(azure_client=client, deployment=deployment)
    router   = Router()
    verifier = Verifier(azure_client=client, deployment=deployment)

    print(f"{AGENT_ORCHESTRATOR} Sistema inicializado — 9 agentes:")
    print(f"  1. {AGENT_PLANNER}      — Decomposição de Tarefas (Azure OpenAI)")
    print(f"  2. {AGENT_ROUTER}       — Despacho Federado (HTTP/JSON-RPC)")
    print(f"  3. {AGENT_CLINIC_A} — Servidor MCP Cardiologia (porta 8001)")
    print(f"  4. {AGENT_CLINIC_B} — Servidor MCP Dermatologia (porta 8002)")
    print(f"  5. {AGENT_CLINIC_C} — Servidor MCP Cardiologia (porta 8003)")
    print(f"  6. {AGENT_CLINIC_D} — Servidor MCP Ortopedia (porta 8004)")
    print(f"  7. {AGENT_CLINIC_E} — Servidor MCP Ortopedia (porta 8005)")
    print(f"  8. {AGENT_CLINIC_F} — Servidor MCP Dermatologia (porta 8006)")
    print(f"  9. {AGENT_VERIFIER} — Guardrails de Segurança")
    print()
    print(f"{AGENT_ORCHESTRATOR} O Orchestrator coordena todos os agentes e")
    print(f"  gera a resposta final em linguagem natural.")
    print()

    # --- Identificação do paciente (obrigatória antes das interações com clínicas) ---
    patient_info = _collect_patient_info()

    print(f"{AGENT_ORCHESTRATOR} Bem-vindo(a), {patient_info['name']}!")
    print()
    print("Digite sua consulta de saúde (ou 'sair' para encerrar).")
    print()

    # Histórico da conversa — dá ao Planejador contexto para consultas de acompanhamento
    conversation_history: list[dict[str, str]] = []

    while True:
        try:
            user_input = input("Você > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAté logo!")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit", "q", "sair"}:
            print("Até logo!")
            break

        # ==============================================================
        # AGENTE 1: PLANEJADOR — Decomposição de Tarefas
        # ==============================================================
        print(f"\n{AGENT_PLANNER} Analisando consulta e decompondo em tarefas...")
        steps = planner.decompose(user_input, conversation_history)
        print(f"{AGENT_PLANNER} {len(steps)} tarefa(s) gerada(s).")

        # Trata consultas não relacionadas a saúde (saudações, fora de escopo)
        if not steps:
            print(f"\n{AGENT_ORCHESTRATOR} Este é um sistema de saúde. "
                  "Pergunte sobre cardiologia, dermatologia ou ortopedia!")
            print()
            continue

        if len(steps) == 1 and steps[0].get("action") == "greeting":
            message = steps[0].get("parameters", {}).get("message", "")
            print(f"\n{AGENT_ORCHESTRATOR} {message}")
            print()
            continue

        # ==============================================================
        # AGENTE 2: ROUTER — Despacho Federado para Agentes de Clínica
        # ==============================================================
        aggregated_results: list[dict] = []
        for step in steps:
            clinic = step.get("clinic", "?")
            action = step.get("action", "?")
            clinic_label = CLINIC_LABELS.get(clinic, f"[Agente: {clinic}]")

            # Injeta dados do paciente em etapas de agendamento automaticamente
            if action in ("book_appointment", "reschedule_appointment", "cancel_appointment"):
                step.setdefault("parameters", {})
                step["parameters"]["patient_name"] = patient_info["name"]
                step["parameters"]["cpf"] = patient_info["cpf"]

            print(f"{AGENT_ROUTER} Despachando '{action}' → {clinic_label}")

            # ==============================================================
            # AGENTE 3: AGENTE DE CLÍNICA — Servidor MCP Específico do Domínio
            # ==============================================================
            response = router.dispatch(step)

            if response.error:
                print(f"{clinic_label} Erro: {response.error['message']}")
                aggregated_results.append({"step": step, "error": response.error})
            else:
                print(f"{clinic_label} Respondeu com sucesso.")
                aggregated_results.append({"step": step, "result": response.result})

        # ==============================================================
        # AGENTE 4: VERIFICADOR — Agente Observador [Burke et al. 2024]
        # ==============================================================
        print(f"\n{AGENT_VERIFIER} Validando segurança da resposta...")
        verdict = verifier.verify(user_input, aggregated_results)

        if not verdict.safe:
            print(f"{AGENT_VERIFIER} BLOQUEADO — {verdict.note}")
            print(f"{AGENT_ORCHESTRATOR} A resposta foi bloqueada pelo "
                  "verificador de segurança.")
            print()
            continue

        print(f"{AGENT_VERIFIER} Resposta é SEGURA.")

        # ==============================================================
        # ORCHESTRATOR — Geração de Resposta em Linguagem Natural
        # ==============================================================
        print(f"{AGENT_ORCHESTRATOR} Gerando resposta em linguagem natural...\n")
        answer = _generate_response(client, deployment, user_input, aggregated_results)
        print(f"Assistente > {answer}")
        print()

        # Salva este turno no histórico da conversa para contexto de acompanhamento
        conversation_history.append({"role": "user", "content": user_input})
        conversation_history.append({"role": "assistant", "content": answer})


if __name__ == "__main__":
    main()
