#!/usr/bin/env bash
# ===========================================================================
# start_all_clinics.sh — Inicia TODAS as 6 Clínicas (servidores MCP)
# ===========================================================================
# Diferente do start_clinics.sh (que inicia apenas A e B para testes rápidos),
# este script inicia todas as 6 clínicas para cenários completos de
# roteamento multi-clínica.
#
# Arquitetura: Coordenação Hierárquica
#   O Orchestrator Host se conecta a estes servidores via HTTP JSON-RPC.
#   As clínicas nunca se comunicam entre si — apenas com o Orchestrator.
# ===========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Iniciando TODAS as 6 Clínicas Federadas ==="
echo "Raiz do projeto: $PROJECT_ROOT"
echo ""

# Garante que o pacote compartilhado pode ser importado
export PYTHONPATH="$PROJECT_ROOT:${PYTHONPATH:-}"

echo "[Clínica A] Cardiologia   → http://localhost:8001/mcp"
python3 "$SCRIPT_DIR/clinic_a/server.py" &
PID_A=$!

echo "[Clínica B] Dermatologia  → http://localhost:8002/mcp"
python3 "$SCRIPT_DIR/clinic_b/server.py" &
PID_B=$!

echo "[Clínica C] Cardiologia   → http://localhost:8003/mcp"
python3 "$SCRIPT_DIR/clinic_c/server.py" &
PID_C=$!

echo "[Clínica D] Ortopedia     → http://localhost:8004/mcp"
python3 "$SCRIPT_DIR/clinic_d/server.py" &
PID_D=$!

echo "[Clínica E] Ortopedia     → http://localhost:8005/mcp"
python3 "$SCRIPT_DIR/clinic_e/server.py" &
PID_E=$!

echo "[Clínica F] Dermatologia  → http://localhost:8006/mcp"
python3 "$SCRIPT_DIR/clinic_f/server.py" &
PID_F=$!

echo ""
echo "=== Todas as 6 clínicas iniciadas ==="
echo "  Clínica A PID: $PID_A"
echo "  Clínica B PID: $PID_B"
echo "  Clínica C PID: $PID_C"
echo "  Clínica D PID: $PID_D"
echo "  Clínica E PID: $PID_E"
echo "  Clínica F PID: $PID_F"
echo ""
echo "Pressione Ctrl+C para parar todos os servidores."

# Intercepta SIGINT/SIGTERM para encerrar todos os servidores de forma limpa
cleanup() {
    echo ""
    echo "Encerrando servidores das clínicas..."
    kill "$PID_A" "$PID_B" "$PID_C" "$PID_D" "$PID_E" "$PID_F" 2>/dev/null || true
    wait "$PID_A" "$PID_B" "$PID_C" "$PID_D" "$PID_E" "$PID_F" 2>/dev/null || true
    echo "Todos os servidores foram encerrados."
}
trap cleanup SIGINT SIGTERM

# Aguarda os processos em background
wait
