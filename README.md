# tcc-healthcare-agents

Sistema multi-agente para saude usando o Model Context Protocol (MCP).
Trabalho de Conclusao de Curso -- arquitetura distribuida com privacidade por design.

## Arquitetura

**Padrao:** Orquestrador-Trabalhadores Federado Hierarquico com Observador (Burke et al. 2024)

- **9 agentes:** Planner, Router, 6 Clinicas, Verifier (Observador)
- **6 clinicas** em 3 especialidades (Cardiologia, Dermatologia, Ortopedia -- 2 clinicas cada)
- **Protocolo:** MCP sobre HTTP / JSON-RPC 2.0
- **Privacidade:** silos de dados federados com isolamento de processo

```
Entrada do Usuario
       |
   [Planner]        decomposicao em passos atomicos
       |
   [Router]         despacho HTTP para clinicas
       |
 [Clinica A..F]     execucao de dominio (MCP servers)
       |
   [Verifier]       validacao de seguranca (Observador)
       |
 [Orquestrador]     geracao de resposta em linguagem natural
       |
Resposta ao Usuario
```

## Requisitos

- Python 3.9+
- Conta Azure OpenAI (com deployment GPT-4o)

## Instalacao

```bash
# 1. Clonar o repositorio
git clone https://github.com/<seu-usuario>/tcc-healthcare-agents.git
cd tcc-healthcare-agents

# 2. Criar ambiente virtual
python3 -m venv .venv
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar credenciais
cp .env.example .env
# Editar .env com suas credenciais Azure OpenAI
```

## Uso

**Terminal 1 -- Iniciar as 6 clinicas:**

```bash
bash clinic_agents/start_all_clinics.sh
```

**Terminal 2 -- Rodar o orquestrador:**

```bash
python3 orchestrator_host/main.py
```

O sistema solicita nome e CPF do paciente e entra em modo interativo.
Digite `sair` ou `quit` para encerrar.

## Testes

Requer que todas as clinicas estejam rodando (Terminal 1).

```bash
# Executar os 30 casos de teste
python3 tests/executar_testes.py

# Avaliar metricas
python3 tests/avaliar_metricas.py
```

## Metricas Baseline

| Metrica | Valor | Descricao |
|---------|-------|-----------|
| TSR     | 86.7% | Task Success Rate (26/30 casos) |
| TCA     | 100.0%| Tool Call Accuracy |
| HMR     | 0.0%  | Hallucination Mitigation Rate (nenhuma detectada) |

## Estrutura do Projeto

```
tcc-healthcare-agents/
|-- orchestrator_host/          # MCP Client -- Orquestrador central
|   |-- main.py                 #   entrada CLI, pipeline de 5 estagios
|   |-- planner.py              #   decomposicao de tarefas via LLM
|   |-- router.py               #   despacho HTTP para clinicas
|   +-- verifier.py             #   agente observador (seguranca)
|
|-- clinic_agents/              # MCP Servers -- 6 clinicas federadas
|   |-- start_all_clinics.sh    #   script para iniciar todas
|   |-- clinic_a/               #   Cardiologia  (porta 8001)
|   |-- clinic_b/               #   Dermatologia (porta 8002)
|   |-- clinic_c/               #   Cardiologia  (porta 8003)
|   |-- clinic_d/               #   Ortopedia    (porta 8004)
|   |-- clinic_e/               #   Ortopedia    (porta 8005)
|   +-- clinic_f/               #   Dermatologia (porta 8006)
|
|-- shared/                     # Codigo compartilhado
|   |-- mcp_types.py            #   MCPRequest, MCPResponse (Pydantic)
|   +-- db.py                   #   helpers JSON DB + handlers de agendamento
|
|-- prompts/                    # Prompts de sistema para LLM
|   |-- planner.txt             #   10 regras de decomposicao
|   |-- planner_cot.txt         #   variante Chain-of-Thought
|   |-- verifier.txt            #   3 regras de seguranca
|   +-- response_generator.txt  #   geracao de resposta (Regra 9)
|
|-- tests/                      # Testes e avaliacao
|   |-- casos_teste.csv         #   30 casos (9 categorias)
|   |-- executar_testes.py      #   executor batch
|   |-- avaliar_metricas.py     #   avaliador TSR/TCA/HMR
|   +-- logs.jsonl              #   log estruturado de execucao
|
|-- docs/v4.0.0/                # Blueprints (versao atual)
|   |-- BLUEPRINT_TECNICO.md    #   blueprint em portugues
|   +-- TECHNICAL_BLUEPRINT.md  #   blueprint em ingles
|
|-- .env.example                # Template de configuracao
|-- .gitignore                  # Protege .env e __pycache__
+-- requirements.txt            # Dependencias Python
```

## Documentacao

Os blueprints tecnicos completos estao em [`docs/v4.0.0/`](docs/v4.0.0/):

- [Blueprint Tecnico (PT)](docs/v4.0.0/BLUEPRINT_TECNICO.md)
- [Technical Blueprint (EN)](docs/v4.0.0/TECHNICAL_BLUEPRINT.md)

## Subida Manual do Codigo (GitHub)

Passo a passo para subir o projeto pela primeira vez:

```bash
# 1. Criar repositorio no GitHub
#    - Va em https://github.com/new
#    - Nome: tcc-healthcare-agents
#    - NAO marque "Add a README", ".gitignore" ou "License"
#    - Clique em "Create repository"

# 2. Inicializar git localmente
cd /caminho/para/tcc-healthcare-agents
git init

# 3. Adicionar todos os arquivos
#    NOTA: .env ja esta no .gitignore, entao e seguro usar git add .
git add .

# 4. Criar o commit inicial
git commit -m "initial commit"

# 5. Configurar o remote
git remote add origin https://github.com/<seu-usuario>/tcc-healthcare-agents.git

# 6. Renomear branch para main
git branch -M main

# 7. Enviar para o GitHub
git push -u origin main
```

> **Importante:** Nunca commite o arquivo `.env` com suas credenciais.
> O `.gitignore` ja esta configurado para ignora-lo.
