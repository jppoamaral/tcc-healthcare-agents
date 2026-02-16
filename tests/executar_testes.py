"""
Executor de casos de teste — roda cada caso do CSV pelo pipeline real
(Planner → Router → Verifier → Geração de Resposta) e grava os
resultados em logs.jsonl para avaliação pelo avaliar_metricas.py.

Pré-requisito: as clínicas devem estar rodando (start_all_clinics.sh).
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

_project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_project_root))

from orchestrator_host.main import build_azure_client, _generate_response
from orchestrator_host.planner import Planner
from orchestrator_host.router import Router
from orchestrator_host.verifier import Verifier

CASOS_CSV = Path(__file__).resolve().parent / "casos_teste.csv"
LOGS_JSONL = Path(__file__).resolve().parent / "logs.jsonl"

# Palavras-chave que indicam risco de privacidade na consulta do usuário
_PRIVACY_KEYWORDS = [
    "cpf", "dados pessoais", "prontuário", "prontuarios",
    "pacientes cadastrados", "endereço", "telefone",
    "nomes dos pacientes", "dados dos pacientes",
]


def normalize(name: str) -> str:
    """Remove underscores para bater com a convenção do CSV.

    clinic_a → clinica, list_available_slots → listavailableslots
    """
    return name.replace("_", "")


def main() -> None:
    print("=" * 65)
    print("  Executor de Testes — Pipeline Real")
    print("=" * 65)

    client, deployment = build_azure_client()
    planner = Planner(azure_client=client, deployment=deployment)
    router = Router()
    verifier = Verifier(azure_client=client, deployment=deployment)

    # Carrega os casos de teste
    cases: list[dict[str, str]] = []
    with open(CASOS_CSV, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            cases.append(row)

    print(f"\n  {len(cases)} casos de teste carregados.\n")

    logs: list[dict] = []

    for case in cases:
        id_caso = int(case["id_caso"])
        texto = case["texto_usuario"]
        intencao = case["intencao_esperada"]

        print(f"\n{'─' * 65}")
        print(f"  Caso #{id_caso:02d} | {intencao}")
        print(f"  Query: {texto}")

        # ── AGENTE 1: PLANEJADOR ──────────────────────────────────────
        try:
            steps = planner.decompose(texto)
        except Exception as exc:
            print(f"  [ERRO] Planner falhou: {exc}")
            logs.append({
                "id_caso": id_caso,
                "final_response_ok": False,
                "steps": [],
                "had_raw_hallucination": False,
                "verifier_safe": True,
            })
            continue

        print(f"  Planner → {len(steps)} etapa(s)")

        # Verifica se é greeting / fora de escopo
        is_greeting = (
            not steps
            or (len(steps) == 1 and steps[0].get("action") == "greeting")
            or (len(steps) == 1 and steps[0].get("action") == "raw_response")
        )

        if is_greeting:
            msg = ""
            if steps:
                params = steps[0].get("parameters", {})
                msg = params.get("message", params.get("text", ""))
            print(f"  → Greeting/Fora de escopo: {msg[:100]}")
            logs.append({
                "id_caso": id_caso,
                "final_response_ok": True,
                "steps": [],
                "had_raw_hallucination": False,
                "verifier_safe": True,
            })
            time.sleep(0.5)
            continue

        # ── AGENTE 2: ROUTER → CLÍNICAS ──────────────────────────────
        aggregated: list[dict] = []
        step_log: list[dict] = []

        for step in steps:
            clinic = step.get("clinic", "unknown")
            action = step.get("action", "unknown")

            response = router.dispatch(step)

            if response.error:
                print(f"    {clinic}/{action} → ERRO: {response.error.get('message', '?')}")
                aggregated.append({"step": step, "error": response.error})
            else:
                print(f"    {clinic}/{action} → OK")
                aggregated.append({"step": step, "result": response.result})

            step_log.append({
                "clinic": normalize(clinic),
                "action": normalize(action),
            })

        # Detecta risco de alucinação/privacidade nos dados brutos
        has_privacy_action = any(
            s.get("action") in ("list_patients", "get_patient")
            for s in steps
        )
        has_privacy_query = any(
            kw in texto.lower() for kw in _PRIVACY_KEYWORDS
        )
        had_raw_hallucination = has_privacy_action or has_privacy_query

        # ── AGENTE 3: VERIFICADOR ────────────────────────────────────
        try:
            verdict = verifier.verify(texto, aggregated)
        except Exception as exc:
            print(f"  [ERRO] Verifier falhou: {exc}")
            verdict_safe = True
            verdict_note = f"Erro: {exc}"
        else:
            verdict_safe = verdict.safe
            verdict_note = verdict.note

        print(f"  Verifier → safe={verdict_safe} | {verdict_note}")

        # ── GERAÇÃO DE RESPOSTA ──────────────────────────────────────
        if verdict_safe:
            try:
                answer = _generate_response(
                    client, deployment, texto, aggregated,
                )
                final_ok = True
                print(f"  Resposta: {answer[:120]}...")
            except Exception as exc:
                final_ok = False
                print(f"  [ERRO] Geração falhou: {exc}")
        else:
            final_ok = False
            print(f"  BLOQUEADO pelo verificador.")

        logs.append({
            "id_caso": id_caso,
            "final_response_ok": final_ok,
            "steps": step_log,
            "had_raw_hallucination": had_raw_hallucination,
            "verifier_safe": verdict_safe,
        })

        # Pequena pausa para não estourar rate limit do Azure
        time.sleep(0.5)

    # Grava logs
    with open(LOGS_JSONL, "w", encoding="utf-8") as f:
        for log in logs:
            f.write(json.dumps(log, ensure_ascii=False) + "\n")

    print(f"\n{'=' * 65}")
    print(f"  {len(logs)} logs gravados em {LOGS_JSONL.name}")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()
