"""
Test: Multi-clinic nearest slot — "quero o horario mais perto"
===============================================================
Validates that the Orchestrator can:
  1. Query BOTH cardiology clinics (A and C) in parallel
  2. Aggregate slots from multiple clinics
  3. Identify the nearest available slot across clinics
  4. Book the appointment at the correct clinic

Clinic A earliest slot: 2025-07-21 09:00 (Dr. Ricardo Lopes)
Clinic C earliest slot: 2025-07-18 10:00 (Dr. Fernando Mendes)  ← nearest

The test runs real MCP servers (ports 8001, 8002, 8003).
Planner/Verifier LLM calls are NOT used — steps are hardcoded.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Ensure project root is importable
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from orchestrator_host.router import Router

# ---------------------------------------------------------------------------
# Patient info
# ---------------------------------------------------------------------------
PATIENT_INFO = {"name": "Carlos Teste", "cpf": "123.456.789-00"}


# ---------------------------------------------------------------------------
# Helper: start / stop clinic servers
# ---------------------------------------------------------------------------

def _start_servers() -> list[subprocess.Popen]:
    """Start clinic_a (8001), clinic_b (8002) and clinic_c (8003)."""
    servers = []
    for module, port in [
        ("clinic_agents.clinic_a.server:app", 8001),
        ("clinic_agents.clinic_b.server:app", 8002),
        ("clinic_agents.clinic_c.server:app", 8003),
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
# Pipeline helpers
# ---------------------------------------------------------------------------

def _run_turn(
    router: Router,
    planner_steps: list[dict[str, Any]],
    patient_info: dict[str, str],
) -> list[dict[str, Any]]:
    """Execute steps through the Router and collect aggregated results."""
    aggregated: list[dict[str, Any]] = []
    for step in planner_steps:
        action = step.get("action", "?")
        if action in ("book_appointment", "reschedule_appointment", "cancel_appointment"):
            step.setdefault("parameters", {})
            step["parameters"]["patient_name"] = patient_info["name"]
            step["parameters"]["cpf"] = patient_info["cpf"]

        response = router.dispatch(step)
        if response.error:
            aggregated.append({"step": step, "error": response.error})
        else:
            aggregated.append({"step": step, "result": response.result})
    return aggregated


def _find_nearest_slot(aggregated_results: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find the earliest slot across all clinic results."""
    nearest = None
    nearest_clinic = None
    for item in aggregated_results:
        result = item.get("result", {})
        clinic = item["step"].get("clinic", "?")
        for slot in result.get("available_slots", []):
            key = (slot["date"], slot["time"])
            if nearest is None or key < (nearest["date"], nearest["time"]):
                nearest = slot
                nearest_clinic = clinic
    if nearest:
        return {**nearest, "clinic": nearest_clinic}
    return None


# ======================================================================== #
#  TEST
# ======================================================================== #

def main() -> None:
    print("=" * 65)
    print("  TEST: Multi-clinic nearest slot")
    print("  Clinic A (Cardiology, port 8001) earliest: 2025-07-21 09:00")
    print("  Clinic C (Cardiology, port 8003) earliest: 2025-07-18 10:00")
    print("=" * 65)
    print()

    print("[setup] Starting clinic MCP servers (8001, 8002, 8003) ...")
    servers = _start_servers()
    try:
        _wait_for_servers([8001, 8002, 8003])
        print("[setup] All servers are up.\n")

        router = Router()
        passed = 0
        total = 5

        # ============================================================== #
        # TURN 1 — Query BOTH cardiology clinics for available slots
        # (This is what the Planner should generate for a cardiology query)
        # ============================================================== #
        print("-" * 65)
        print("TURN 1: \"quero marcar uma consulta com um cardiologista\"")
        print("  Planner should generate 2 steps (clinic_a + clinic_c)")
        print("-" * 65)

        steps_t1 = [
            {
                "step_id": 1,
                "clinic": "clinic_a",
                "action": "list_available_slots",
                "parameters": {},
            },
            {
                "step_id": 2,
                "clinic": "clinic_c",
                "action": "list_available_slots",
                "parameters": {},
            },
        ]

        results_t1 = _run_turn(router, steps_t1, PATIENT_INFO)

        # --- Check 1: Clinic A responded with slots ---
        r1_a = results_t1[0]
        slots_a = r1_a.get("result", {}).get("available_slots", [])
        ok1 = "result" in r1_a and len(slots_a) > 0
        print(f"  CHECK 1 — Clinic A responded with {len(slots_a)} slots: {'PASS' if ok1 else 'FAIL'}")
        if ok1:
            passed += 1

        # --- Check 2: Clinic C responded with slots ---
        r1_c = results_t1[1]
        slots_c = r1_c.get("result", {}).get("available_slots", [])
        ok2 = "result" in r1_c and len(slots_c) > 0
        print(f"  CHECK 2 — Clinic C responded with {len(slots_c)} slots: {'PASS' if ok2 else 'FAIL'}")
        if ok2:
            passed += 1

        # --- Check 3: Nearest slot is from Clinic C (2025-07-18) ---
        nearest = _find_nearest_slot(results_t1)
        ok3 = (
            nearest is not None
            and nearest["clinic"] == "clinic_c"
            and nearest["date"] == "2025-07-18"
        )
        print(f"  CHECK 3 — Nearest slot across both clinics:")
        if nearest:
            print(f"    {nearest['doctor']}, {nearest['date']} {nearest['time']} ({nearest['clinic']})")
        print(f"    Expected: clinic_c, 2025-07-18: {'PASS' if ok3 else 'FAIL'}")
        if ok3:
            passed += 1
        print()

        # ============================================================== #
        # TURN 2 — "quero o horario mais perto"
        # The system should book at Clinic C (the nearest slot)
        # ============================================================== #
        print("-" * 65)
        print("TURN 2: \"quero o horario mais perto\"")
        print("  Should book at Clinic C: Dr. Fernando Mendes, 2025-07-18 10:00")
        print("-" * 65)

        steps_t2 = [
            {
                "step_id": 1,
                "clinic": "clinic_c",
                "action": "book_appointment",
                "parameters": {
                    "doctor": "Dr. Fernando Mendes",
                    "date": "2025-07-18",
                    "time": "10:00",
                },
            }
        ]

        results_t2 = _run_turn(router, steps_t2, PATIENT_INFO)
        r2 = results_t2[0]

        ok4 = (
            "result" in r2
            and r2["result"].get("status") == "confirmed"
            and r2["result"]["appointment"]["doctor"] == "Dr. Fernando Mendes"
            and r2["result"]["appointment"]["date"] == "2025-07-18"
            and r2["result"]["appointment"]["time"] == "10:00"
            and r2["result"]["appointment"]["patient_name"] == PATIENT_INFO["name"]
        )
        print(f"  CHECK 4 — Booking at Clinic C confirmed: {'PASS' if ok4 else 'FAIL'}")
        if ok4:
            appt = r2["result"]["appointment"]
            print(f"    {appt['doctor']}, {appt['date']} {appt['time']}")
            print(f"    Patient: {appt['patient_name']} (CPF: {appt['cpf']})")
            passed += 1
        print()

        # ============================================================== #
        # CHECK 5 — Response payload aggregates both clinics correctly
        # ============================================================== #
        print("-" * 65)
        print("CHECK 5: Response payload contains data from both clinics")
        print("-" * 65)

        payload = json.dumps(
            {
                "user_query": "quero marcar uma consulta com um cardiologista",
                "clinic_data": [
                    {
                        "clinic": item["step"].get("clinic", "?"),
                        "action": item["step"].get("action", "?"),
                        "result": item.get("result"),
                        "error": item.get("error"),
                    }
                    for item in results_t1
                ],
            },
            ensure_ascii=False,
        )
        data = json.loads(payload)
        clinics_in_payload = [entry["clinic"] for entry in data["clinic_data"]]
        ok5 = "clinic_a" in clinics_in_payload and "clinic_c" in clinics_in_payload
        print(f"  Clinics in payload: {clinics_in_payload}")
        total_slots = sum(
            len(entry.get("result", {}).get("available_slots", []))
            for entry in data["clinic_data"]
        )
        print(f"  Total slots across clinics: {total_slots}")
        print(f"  Both clinics present: {'PASS' if ok5 else 'FAIL'}")
        if ok5:
            passed += 1
        print()

        # ============================================================== #
        # SUMMARY
        # ============================================================== #
        print("=" * 65)
        print(f"  RESULT: {passed}/{total} checks passed", end="")
        if passed == total:
            print("  ALL PASSED")
        else:
            print("  SOME FAILED")
        print("=" * 65)

        sys.exit(0 if passed == total else 1)

    finally:
        print("\n[teardown] Stopping clinic servers ...")
        _stop_servers(servers)
        print("[teardown] Done.")


if __name__ == "__main__":
    main()
