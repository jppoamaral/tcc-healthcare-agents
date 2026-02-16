"""
Banco de dados simples baseado em arquivo JSON para horários de consulta.
=========================================================================
Cada clínica mantém seu próprio ``db.json`` — este módulo fornece
helpers de leitura/escrita e os quatro handlers relacionados a consultas
(listar, agendar, cancelar, reagendar) para que todos os servidores
reutilizem a mesma lógica.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()


# ------------------------------------------------------------------
# Helpers de baixo nível
# ------------------------------------------------------------------

def _load_slots(db_path: Path) -> list[dict[str, Any]]:
    with open(db_path, encoding="utf-8") as f:
        return json.load(f)["slots"]


def _save_slots(db_path: Path, slots: list[dict[str, Any]]) -> None:
    with open(db_path, "w", encoding="utf-8") as f:
        json.dump({"slots": slots}, f, ensure_ascii=False, indent=2)
        f.write("\n")


# ------------------------------------------------------------------
# Handlers — chamados via functools.partial de cada servidor
# ------------------------------------------------------------------

def handle_list_available_slots(
    db_path: Path,
    specialty: str,
    doctor: str = "",
    **_kw: Any,
) -> dict[str, Any]:
    with _lock:
        slots = _load_slots(db_path)
    available = [
        {"doctor": s["doctor"], "specialty": s["specialty"],
         "date": s["date"], "time": s["time"], "available": True}
        for s in slots if s["available"]
    ]
    if doctor:
        dl = doctor.lower()
        available = [s for s in available if dl in s["doctor"].lower()]
    return {
        "specialty": specialty,
        "available_slots": available,
        "note": "Para confirmar o agendamento, informe o horario desejado.",
    }


def handle_book_appointment(
    db_path: Path,
    specialty: str,
    doctor: str = "",
    date: str = "",
    time: str = "",
    patient_name: str = "",
    cpf: str = "",
    **_kw: Any,
) -> dict[str, Any]:
    if not doctor or not date or not time:
        return {"error": "Campos obrigatórios ausentes: doctor, date, time"}
    if not patient_name or not cpf:
        return {"error": "Identificação do paciente ausente: patient_name, cpf"}

    with _lock:
        slots = _load_slots(db_path)
        for s in slots:
            if (s["doctor"].lower() == doctor.lower()
                    and s["date"] == date
                    and s["time"] == time
                    and s["available"]):
                s["available"] = False
                s["patient_name"] = patient_name
                s["cpf"] = cpf
                _save_slots(db_path, slots)
                return {
                    "status": "confirmed",
                    "appointment": {
                        "doctor": s["doctor"], "date": date, "time": time,
                        "patient_name": patient_name, "cpf": cpf,
                        "specialty": specialty,
                    },
                    "message": "Consulta agendada com sucesso.",
                }
    return {"error": f"Horário indisponível: {doctor} em {date} às {time}"}


def handle_cancel_appointment(
    db_path: Path,
    specialty: str,
    doctor: str = "",
    date: str = "",
    time: str = "",
    patient_name: str = "",
    cpf: str = "",
    **_kw: Any,
) -> dict[str, Any]:
    if not doctor or not date or not time:
        return {"error": "Campos obrigatórios ausentes: doctor, date, time"}
    if not patient_name or not cpf:
        return {"error": "Identificação do paciente ausente: patient_name, cpf"}

    with _lock:
        slots = _load_slots(db_path)
        for s in slots:
            if (s["doctor"].lower() == doctor.lower()
                    and s["date"] == date
                    and s["time"] == time
                    and not s["available"]):
                s["available"] = True
                s["patient_name"] = None
                s["cpf"] = None
                _save_slots(db_path, slots)
                return {
                    "status": "cancelled",
                    "cancelled_appointment": {
                        "doctor": s["doctor"], "date": date, "time": time,
                        "patient_name": patient_name, "cpf": cpf,
                        "specialty": specialty,
                    },
                    "message": "Consulta cancelada com sucesso.",
                }
    return {"error": f"Consulta não encontrada: {doctor} em {date} às {time}"}


def handle_reschedule_appointment(
    db_path: Path,
    specialty: str,
    original_date: str = "",
    original_time: str = "",
    doctor: str = "",
    new_date: str = "",
    new_time: str = "",
    patient_name: str = "",
    cpf: str = "",
    **_kw: Any,
) -> dict[str, Any]:
    if not original_date or not original_time or not doctor:
        return {"error": "Campos obrigatórios ausentes: original_date, original_time, doctor"}
    if not new_date or not new_time:
        return {"error": "Campos obrigatórios ausentes: new_date, new_time"}
    if not patient_name or not cpf:
        return {"error": "Identificação do paciente ausente: patient_name, cpf"}

    with _lock:
        slots = _load_slots(db_path)
        orig = new = None
        for s in slots:
            if (s["doctor"].lower() == doctor.lower()
                    and s["date"] == original_date
                    and s["time"] == original_time
                    and not s["available"]):
                orig = s
            if (s["doctor"].lower() == doctor.lower()
                    and s["date"] == new_date
                    and s["time"] == new_time
                    and s["available"]):
                new = s

        if not orig:
            return {"error": f"Consulta original não encontrada: {doctor} em {original_date} às {original_time}"}
        if not new:
            return {"error": f"Novo horário indisponível: {doctor} em {new_date} às {new_time}"}

        orig["available"] = True
        orig["patient_name"] = None
        orig["cpf"] = None
        new["available"] = False
        new["patient_name"] = patient_name
        new["cpf"] = cpf
        _save_slots(db_path, slots)

        return {
            "status": "rescheduled",
            "original_appointment": {
                "doctor": doctor, "date": original_date, "time": original_time,
            },
            "new_appointment": {
                "doctor": new["doctor"], "date": new_date, "time": new_time,
                "patient_name": patient_name, "cpf": cpf,
                "specialty": specialty,
            },
            "message": "Consulta reagendada com sucesso.",
        }
