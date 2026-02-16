#!/usr/bin/env bash
# ===========================================================================
# start_clinics.sh — Inicia os servidores MCP das Clínicas A e B
# ===========================================================================
# Cada clínica roda como um processo independente (simulando silos de dados
# federados com isolamento de rede completo em um deploy real).
#
# Arquitetura: Coordenação Hierárquica
#   O Orchestrator Host se conecta a estes servidores via HTTP JSON-RPC.
#   As clínicas nunca se comunicam entre si — apenas com o Orchestrator.
# ===========================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== Iniciando Agentes de Clínicas Federadas (A e B) ==="
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

echo ""
echo "=== Todas as clínicas iniciadas ==="
echo "  Clínica A PID: $PID_A"
echo "  Clínica B PID: $PID_B"
echo ""
echo "Pressione Ctrl+C para parar todos os servidores."

# Intercepta SIGINT/SIGTERM para encerrar ambos os servidores de forma limpa
cleanup() {
    echo ""
    echo "Encerrando servidores das clínicas..."
    kill "$PID_A" "$PID_B" 2>/dev/null || true
    wait "$PID_A" "$PID_B" 2>/dev/null || true
    echo "Todos os servidores foram encerrados."
}
trap cleanup SIGINT SIGTERM

# Aguarda os processos em background
wait
