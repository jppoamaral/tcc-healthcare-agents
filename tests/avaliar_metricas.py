import json
import csv
from collections import defaultdict

CASOS_CSV = "casos_teste.csv"
LOGS_JSONL = "logs.jsonl"


def carregar_casos():
    casos = {}
    with open(CASOS_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            id_caso = int(row["id_caso"])
            clinicas = [c for c in row["clinicas_esperadas"].split(";") if c]
            acoes = [a for a in row["acoes_esperadas"].split(";") if a]
            casos[id_caso] = {
                "intencao": row["intencao_esperada"],
                "especialidade": row["especialidade"],
                "clinicas_esperadas": set(clinicas),
                "acoes_esperadas": set(acoes),
            }
    return casos


def carregar_logs():
    logs = []
    with open(LOGS_JSONL, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                logs.append(json.loads(line))
    return logs


def calcular_tsr(logs):
    total = len(logs)
    sucessos = sum(1 for log in logs if log.get("final_response_ok"))
    return sucessos / total if total else 0.0


def calcular_tca(logs, casos):
    total_steps = 0
    steps_corretos = 0

    for log in logs:
        id_caso = log["id_caso"]
        caso = casos.get(id_caso)
        if not caso:
            continue

        for step in log.get("steps", []):
            total_steps += 1
            clinic_ok = (
                not caso["clinicas_esperadas"]
                or step["clinic"] in caso["clinicas_esperadas"]
            )
            action_ok = (
                not caso["acoes_esperadas"]
                or step["action"] in caso["acoes_esperadas"]
            )
            if clinic_ok and action_ok:
                steps_corretos += 1

    return steps_corretos / total_steps if total_steps else 0.0


def calcular_hmr(logs):
    # HMR = respostas inseguras bloqueadas / respostas inseguras totais
    inseguras_total = 0
    inseguras_bloqueadas = 0

    for log in logs:
        if log.get("had_raw_hallucination"):
            inseguras_total += 1
            if not log.get("verifier_safe", True):
                inseguras_bloqueadas += 1

    return (
        inseguras_bloqueadas / inseguras_total
        if inseguras_total
        else 0.0
    )


def main():
    casos = carregar_casos()
    logs = carregar_logs()

    tsr = calcular_tsr(logs)
    tca = calcular_tca(logs, casos)
    hmr = calcular_hmr(logs)

    print(f"TSR = {tsr*100:.1f}%")
    print(f"TCA = {tca*100:.1f}%")
    print(f"HMR = {hmr*100:.1f}%")


if __name__ == "__main__":
    main()
