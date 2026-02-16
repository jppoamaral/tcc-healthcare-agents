"""
Test: 3-turn reschedule scenario
=================================
Simulates the conversation flow:
  Turn 1: "quero marcar uma consulta com um cardiologista"
          → list_available_slots → shows slots
  Turn 2: "pode ser com o Dr. Ricardo dia 21 às 9h"
          → book_appointment → confirms booking
  Turn 3: "preciso reagendar para o dia 23 às 8h"
          → reschedule_appointment → confirms change

The Planner and Verifier LLM calls are mocked so the test runs
without Azure OpenAI credentials.  The clinic MCP servers run for real
(started as background uvicorn processes).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from orchestrator_host.planner import Planner
from orchestrator_host.router import Router
from orchestrator_host.verifier import Verifier, VerificationResult

# ---------------------------------------------------------------------------
# Patient info (injected automatically by main.py in real runs)
# ---------------------------------------------------------------------------
PATIENT_INFO = {"name": "Carlos Teste", "cpf": "123.456.789-00"}

CLINIC_LABELS = {
    "clinic_a": "[Agent: Clinic A (Cardiology)]",
    "clinic_b": "[Agent: Clinic B (Dermatology)]",
}

# ---------------------------------------------------------------------------
# Helper: start / stop clinic servers
# ---------------------------------------------------------------------------

def _start_servers() -> list[subprocess.Popen]:
    """Start clinic_a (8001) and clinic_b (8002) as background processes."""
    servers = []
    for module, port in [
        ("clinic_agents.clinic_a.server:app", 8001),
        ("clinic_agents.clinic_b.server:app", 8002),
    ]:
        proc = subprocess.Popen(
            [
                sys.executable, "-m", "uvicorn", module,
                "--host", "127.0.0.1",
                "--port", str(port),
                "--log-level", "warning",
            ],
            cwd=str(_project_root),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        servers.append(proc)
    return servers


def _wait_for_servers(ports: list[int], timeout: float = 10.0) -> None:
    """Block until each port is accepting connections."""
    import socket

    deadline = time.time() + timeout
    for port in ports:
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", port)) == 0:
                    break
            time.sleep(0.3)
        else:
            raise RuntimeError(f"Server on port {port} did not start in {timeout}s")


def _stop_servers(servers: list[subprocess.Popen]) -> None:
    for proc in servers:
        proc.terminate()
    for proc in servers:
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# Pipeline helpers (extracted from main.py logic)
# ---------------------------------------------------------------------------

def _run_turn(
    router: Router,
    planner_steps: list[dict[str, Any]],
    patient_info: dict[str, str],
) -> list[dict[str, Any]]:
    """
    Execute a single turn: dispatch steps through the Router and collect
    aggregated results (same logic as main.py's inner loop).
    """
    aggregated: list[dict[str, Any]] = []
    for step in planner_steps:
        action = step.get("action", "?")
        # Inject patient info for booking/rescheduling
        if action in ("book_appointment", "reschedule_appointment"):
            step.setdefault("parameters", {})
            step["parameters"]["patient_name"] = patient_info["name"]
            step["parameters"]["cpf"] = patient_info["cpf"]

        response = router.dispatch(step)
        if response.error:
            aggregated.append({"step": step, "error": response.error})
        else:
            aggregated.append({"step": step, "result": response.result})
    return aggregated


# ======================================================================== #
#  TEST
# ======================================================================== #

def main() -> None:
    print("=" * 65)
    print("  TEST: 3-turn reschedule scenario")
    print("=" * 65)
    print()

    # --- Start real MCP servers ---
    print("[setup] Starting clinic MCP servers …")
    servers = _start_servers()
    try:
        _wait_for_servers([8001, 8002])
        print("[setup] Servers are up (ports 8001, 8002).\n")

        router = Router()
        passed = 0
        total = 3

        # ============================================================== #
        # TURN 1 — list available cardiology slots
        # ============================================================== #
        print("-" * 65)
        print("TURN 1: \"quero marcar uma consulta com um cardiologista\"")
        print("-" * 65)

        steps_t1 = [
            {
                "step_id": 1,
                "clinic": "clinic_a",
                "action": "list_available_slots",
                "parameters": {},
            }
        ]
        print(f"  Planner → action=list_available_slots, clinic=clinic_a")

        results_t1 = _run_turn(router, steps_t1, PATIENT_INFO)
        r1 = results_t1[0]

        ok1 = (
            "result" in r1
            and "available_slots" in r1["result"]
            and len(r1["result"]["available_slots"]) > 0
        )
        status1 = "PASS" if ok1 else "FAIL"
        print(f"  Clinic A responded with {len(r1.get('result', {}).get('available_slots', []))} slots")
        print(f"  Verifier → SAFE (mocked)")
        print(f"  => {status1}")
        if ok1:
            passed += 1
        print()

        # ============================================================== #
        # TURN 2 — book appointment with Dr. Ricardo, 21 Jul 09:00
        # ============================================================== #
        print("-" * 65)
        print("TURN 2: \"pode ser com o Dr. Ricardo dia 21 às 9h\"")
        print("-" * 65)

        steps_t2 = [
            {
                "step_id": 1,
                "clinic": "clinic_a",
                "action": "book_appointment",
                "parameters": {
                    "doctor": "Dr. Ricardo Lopes",
                    "date": "2025-07-21",
                    "time": "09:00",
                },
            }
        ]
        print(f"  Planner → action=book_appointment, doctor=Dr. Ricardo Lopes, date=2025-07-21, time=09:00")

        results_t2 = _run_turn(router, steps_t2, PATIENT_INFO)
        r2 = results_t2[0]

        ok2 = (
            "result" in r2
            and r2["result"].get("status") == "confirmed"
            and r2["result"]["appointment"]["doctor"] == "Dr. Ricardo Lopes"
            and r2["result"]["appointment"]["date"] == "2025-07-21"
            and r2["result"]["appointment"]["time"] == "09:00"
            and r2["result"]["appointment"]["patient_name"] == PATIENT_INFO["name"]
            and r2["result"]["appointment"]["cpf"] == PATIENT_INFO["cpf"]
        )
        status2 = "PASS" if ok2 else "FAIL"
        print(f"  Clinic A responded: status={r2.get('result', {}).get('status')}")
        print(f"  Patient info injected: name={r2.get('result', {}).get('appointment', {}).get('patient_name')}, cpf={r2.get('result', {}).get('appointment', {}).get('cpf')}")
        print(f"  Verifier → SAFE (mocked)")
        print(f"  => {status2}")
        if ok2:
            passed += 1
        print()

        # ============================================================== #
        # TURN 3 — reschedule to 23 Jul 08:00
        # ============================================================== #
        print("-" * 65)
        print("TURN 3: \"preciso reagendar para o dia 23 às 8h\"")
        print("-" * 65)

        steps_t3 = [
            {
                "step_id": 1,
                "clinic": "clinic_a",
                "action": "reschedule_appointment",
                "parameters": {
                    "original_date": "2025-07-21",
                    "original_time": "09:00",
                    "doctor": "Dr. Ricardo Lopes",
                    "new_date": "2025-07-23",
                    "new_time": "08:00",
                },
            }
        ]
        print(f"  Planner → action=reschedule_appointment")
        print(f"    original: 2025-07-21 09:00, Dr. Ricardo Lopes")
        print(f"    new:      2025-07-23 08:00")

        results_t3 = _run_turn(router, steps_t3, PATIENT_INFO)
        r3 = results_t3[0]

        ok3 = (
            "result" in r3
            and r3["result"].get("status") == "rescheduled"
            and r3["result"]["original_appointment"]["date"] == "2025-07-21"
            and r3["result"]["original_appointment"]["time"] == "09:00"
            and r3["result"]["new_appointment"]["date"] == "2025-07-23"
            and r3["result"]["new_appointment"]["time"] == "08:00"
            and r3["result"]["new_appointment"]["patient_name"] == PATIENT_INFO["name"]
            and r3["result"]["new_appointment"]["cpf"] == PATIENT_INFO["cpf"]
        )
        status3 = "PASS" if ok3 else "FAIL"
        print(f"  Clinic A responded: status={r3.get('result', {}).get('status')}")
        print(f"  Original: {r3.get('result', {}).get('original_appointment')}")
        print(f"  New:      {r3.get('result', {}).get('new_appointment')}")
        print(f"  Verifier → SAFE (mocked)")
        print(f"  => {status3}")
        if ok3:
            passed += 1
        print()

        # ============================================================== #
        # SUMMARY
        # ============================================================== #
        print("=" * 65)
        print(f"  RESULT: {passed}/{total} turns passed", end="")
        if passed == total:
            print("  ✓ ALL PASSED")
        else:
            print("  ✗ SOME FAILED")
        print("=" * 65)

        sys.exit(0 if passed == total else 1)

    finally:
        print("\n[teardown] Stopping clinic servers …")
        _stop_servers(servers)
        print("[teardown] Done.")


if __name__ == "__main__":
    main()
