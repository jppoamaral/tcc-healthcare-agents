# Blueprint Tecnico — Sistema Multi-Agente para Saude (MAS)

> **Classificacao do Documento:** Referencia Academica — Ground Truth do TCC
> **Padrao Arquitetural:** Orquestrador-Trabalhadores Federado Hierarquico com Observador
> **Protocolo:** Model Context Protocol (MCP) sobre HTTP / JSON-RPC 2.0
> **Versao:** 1.0.0

---

## Sumario

1. [Definicao Arquitetural (Formal)](#1-definicao-arquitetural-formal)
2. [Especificacoes dos Componentes](#2-especificacoes-dos-componentes)
3. [Estrategia de Privacidade e Seguranca](#3-estrategia-de-privacidade-e-seguranca)
4. [Estrategia de Metricas de Avaliacao](#4-estrategia-de-metricas-de-avaliacao)
5. [Roteiro de Implementacao](#5-roteiro-de-implementacao)

---

## 1. Definicao Arquitetural (Formal)

### 1.1 Classificacao do Padrao

Este sistema implementa o padrao **Orquestrador-Trabalhadores Federado Hierarquico com Observador**, uma arquitetura multi-agente composta que combina tres paradigmas estabelecidos:

| Paradigma | Papel neste Sistema | Base Teorica |
|---|---|---|
| **Coordenacao Hierarquica** | O Orchestrator Host decompoe objetivos de alto nivel em sub-tarefas atomicas e as delega para baixo. Os Trabalhadores (Agentes Clinicos) nao possuem conhecimento sobre agentes irmãos ou sobre o plano global da tarefa. | Controle centralizado com execucao descentralizada. |
| **Arquitetura de Dados Federada** | Cada Agente Clinico opera como um silo de dados isolado. Registros de pacientes nunca sao transmitidos em forma bruta; apenas resultados de consultas cruzam a fronteira do processo. | Privacidade por Design; Minimizacao de Dados (LGPD/GDPR). |
| **Agente Observador** | Um Verificador independente audita cada resposta agregada contra regras de seguranca antes que ela chegue ao usuario final, implementando um portao de validacao deterministica. | Burke et al. (2024), "Observer Agents for Safe Multi-Agent Medical Systems." |

### 1.2 Orchestrator Host (Cliente MCP)

O Orquestrador e o unico componente com uma **visao global** da intencao do usuario. Ele contem tres modulos internos que executam sequencialmente:

| Modulo | Responsabilidade | Classificacao |
|---|---|---|
| **Planner** | **Decomposicao de Tarefas** — recebe a consulta em linguagem natural e utiliza o Azure OpenAI (temperatura 0.0) para produzir um grafo de passos JSON deterministico. Cada passo e atomico e delimitado a exatamente uma clinica. | Planejamento assistido por LLM com saida restrita. |
| **Router** | **Roteamento Dinamico** — mantem um registro de endpoints de clinicas e despacha cada passo via HTTP POST seguindo o envelope MCP JSON-RPC 2.0. O Router e o unico modulo ciente da topologia de rede. | Despacho de servico baseado em registro. |
| **Verifier** | **Barreiras de Seguranca e Mitigacao de Alucinacoes** — atua como o Agente Observador (Burke et al. 2024). Valida resultados agregados contra tres regras deterministicas: (1) sem dosagens fabricadas, (2) sem vazamento de PII, (3) sem recomendacoes fora do escopo. | Camada de auditoria pos-processamento independente. |

### 1.3 Servidores MCP (Agentes Clinicos — Trabalhadores)

Cada Agente Clinico e uma aplicacao FastAPI **especializada por dominio** que expoe um unico endpoint `/mcp`. As clinicas incorporam dois principios fundamentais:

- **Especializacao de Dominio:** A Clinica A trata de Cardiologia; a Clinica B trata de Dermatologia. Cada uma expoe apenas ferramentas relevantes ao seu dominio medico, prevenindo expansao de escopo.
- **Silos de Dados / Federacao:** Os bancos de dados de pacientes sao codificados dentro de cada processo do servidor. Nao existe banco de dados compartilhado, sistema de arquivos compartilhado ou canal de comunicacao entre clinicas. Isto garante **Preservacao de Privacidade** no nivel de infraestrutura — uma clinica nao consegue acessar os dados de outra clinica, mesmo se comprometida.

### 1.4 Topologia Hub-and-Spoke (Diagrama Mermaid)

```mermaid
graph TD
    User([fa:fa-user Usuario Final / Operador])

    subgraph Orchestrator Host — Cliente MCP
        Planner[fa:fa-project-diagram Planner<br/><i>Decomposicao de Tarefas</i><br/>Azure OpenAI · temp 0.0]
        Router[fa:fa-route Router<br/><i>Roteamento Dinamico</i><br/>Despacho baseado em registro]
        Verifier[fa:fa-shield-alt Verifier<br/><i>Agente Observador</i><br/>Barreiras de Seguranca]
    end

    subgraph Silos de Dados Federados
        ClinicA[fa:fa-heartbeat Clinica A<br/><b>Cardiologia</b><br/>FastAPI · Porta 8001<br/>Servidor MCP]
        ClinicB[fa:fa-allergies Clinica B<br/><b>Dermatologia</b><br/>FastAPI · Porta 8002<br/>Servidor MCP]
    end

    User -->|Consulta em linguagem natural| Planner
    Planner -->|Grafo de passos JSON| Router
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicA
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicB
    ClinicA -->|MCPResponse| Router
    ClinicB -->|MCPResponse| Router
    Router -->|Resultados agregados| Verifier
    Verifier -->|"safe: true / false"| User

    style Planner fill:#4a90d9,color:#fff
    style Router fill:#7b68ee,color:#fff
    style Verifier fill:#e74c3c,color:#fff
    style ClinicA fill:#27ae60,color:#fff
    style ClinicB fill:#f39c12,color:#fff
```

> **Justificativa da topologia:** O modelo Hub-and-Spoke garante **Desacoplamento** entre os agentes clinicos. Adicionar uma nova especialidade (ex.: Clinica C — Neurologia) requer apenas registrar uma nova URL no registro do Router e implantar um novo Servidor MCP. Nenhum codigo de clinica existente e modificado, satisfazendo o Principio Aberto-Fechado.

---

## 2. Especificacoes dos Componentes

### 2.1 Pilha Tecnologica

| Camada | Tecnologia | Versao | Finalidade |
|---|---|---|---|
| Linguagem | Python | 3.9+ | Runtime principal |
| Framework Web | FastAPI | mais recente | Endpoints dos Servidores MCP (Agentes Clinicos) |
| Servidor ASGI | Uvicorn | mais recente | Servidor assincrono de nivel de producao |
| SDK de LLM | `openai` (AzureOpenAI) | mais recente | Raciocinio do Planner e Verifier |
| Validacao de Dados | Pydantic | v2 | Schemas MCPRequest / MCPResponse |
| Cliente HTTP | Requests | mais recente | Despacho Router → Clinica |
| Configuracao | python-dotenv | mais recente | Gerenciamento de variaveis de ambiente |

### 2.2 Especificacao do Protocolo: MCP sobre HTTP (JSON-RPC 2.0)

Toda comunicacao inter-agente segue o **Model Context Protocol** transportado sobre HTTP utilizando o envelope JSON-RPC 2.0.

**Schema da Requisicao** (`shared/mcp_types.py` — `MCPRequest`):

```json
{
    "jsonrpc": "2.0",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "method": "tools/call",
    "params": {
        "name": "get_patient",
        "arguments": {
            "patient_id": "CARD-001"
        }
    }
}
```

| Campo | Tipo | Descricao |
|---|---|---|
| `jsonrpc` | `str` | Versao do protocolo. Sempre `"2.0"`. |
| `id` | `str` | UUID v4 gerado pelo Router. Permite correlacao requisicao-resposta. |
| `method` | `str` | Metodo MCP. Atualmente apenas `"tools/call"` e suportado. |
| `params.name` | `str` | Nome exato da ferramenta registrada no servidor clinico alvo. |
| `params.arguments` | `dict` | Parametros chave-valor encaminhados ao handler da ferramenta. |

**Schema da Resposta** (`shared/mcp_types.py` — `MCPResponse`):

```json
{
    "jsonrpc": "2.0",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "result": { "patient": { "patient_id": "CARD-001", "condition": "Hypertension" } },
    "error": null
}
```

| Campo | Tipo | Descricao |
|---|---|---|
| `id` | `str` | Espelha o `id` da requisicao para correlacao. |
| `result` | `Any \| null` | Payload de sucesso. Presente quando `error` e `null`. |
| `error` | `dict \| null` | Objeto de erro JSON-RPC com `code` e `message`. |

**Codigos de Erro Padronizados:**

| Codigo | Significado | Gatilho |
|---|---|---|
| `-32601` | Metodo nao encontrado | Metodo MCP nao suportado ou clinica desconhecida no registro |
| `-32602` | Parametros invalidos | Nome de ferramenta desconhecida no servidor clinico |
| `-32000` | Erro do servidor | Falha de rede durante o despacho HTTP |

### 2.3 Algoritmos Principais

#### 2.3.1 Logica do Planner — Decomposicao de Grafo de Passos Assistida por LLM

**Arquivo:** `orchestrator_host/planner.py`

O Planner converte uma consulta de saude em linguagem natural em um **grafo de passos** executavel — um array JSON ordenado onde cada elemento representa uma operacao atomica em uma clinica.

```
Entrada: "Listar todos os pacientes de cardiologia e verificar pacientes de dermatologia com psoriase"
           │
           ▼
     ┌─────────────────────────────────────┐
     │  Azure OpenAI (gpt-4o, temp=0.0)   │
     │  System Prompt: schema restrito     │
     │  + registro de clinicas + catalogo  │
     └─────────────────────────────────────┘
           │
           ▼
Saida:  [
          {"step_id": 1, "clinic": "clinic_a", "action": "list_patients", "parameters": {}},
          {"step_id": 2, "clinic": "clinic_b", "action": "query", "parameters": {"query": "psoriasis"}}
        ]
```

**Restricoes deterministicas aplicadas via system prompt:**
1. Apenas clinicas presentes no registro podem ser referenciadas.
2. Apenas nomes de ferramentas do catalogo exato (`list_patients`, `get_patient`, `check_medications`, `query`) sao permitidos.
3. Cada passo e delimitado a uma unica clinica — **sem joins entre clinicas** em um unico passo (Preservacao de Privacidade).
4. A saida e estritamente JSON sem blocos markdown ou comentarios em linguagem natural.
5. A temperatura e definida como `0.0` para minimizar o nao-determinismo.

**Mecanismo de fallback:** Se o LLM retornar JSON nao parseavel, o Planner encapsula a saida bruta em um passo de fallback (`action: "raw_response"`) para que o pipeline nao quebre.

#### 2.3.2 Logica do Verifier — Validacao Deterministica do Agente Observador

**Arquivo:** `orchestrator_host/verifier.py`
**Referencia:** Burke et al. (2024)

O Verifier recebe os **resultados agregados** de todos os passos despachados e os valida contra tres regras de seguranca deterministicas:

| Regra # | Verificacao | Justificativa |
|---|---|---|
| R1 | A resposta NAO contem dosagens de medicamentos fabricadas ou planos de tratamento sem fundamento nos dados clinicos. | **Mitigacao de Alucinacoes** — impede que o LLM invente informacoes medicas. |
| R2 | A resposta NAO expoe Informacoes Pessoais Identificaveis (nomes completos, documentos governamentais, enderecos). | **Preservacao de Privacidade** — aplica Minimizacao de Dados na camada de saida. |
| R3 | A resposta NAO recomenda acoes fora do escopo do agente (ex.: diagnosticar sem um medico). | **Barreiras de Seguranca** — previne aconselhamento medico que gere responsabilidade legal. |

**Schema de saida da validacao:**

```json
{"safe": true,  "note": "OK"}
{"safe": false, "note": "Resposta contem dosagem fabricada para Amiodarona."}
```

**Comportamento do pipeline:**
- `safe: true` → os resultados sao exibidos ao usuario final.
- `safe: false` → os resultados sao **bloqueados**; apenas a `note` explicando a violacao e mostrada.

#### 2.3.3 Fluxo de Chamada de Ferramentas — Sequencia Ponta a Ponta

```
 Usuario               Planner             Router              Clinica A          Verifier
  │                      │                   │                    │                  │
  │── consulta ─────────>│                   │                    │                  │
  │                      │── grafo passos ──>│                    │                  │
  │                      │                   │── MCPRequest ─────>│                  │
  │                      │                   │   POST /mcp        │                  │
  │                      │                   │   JSON-RPC 2.0     │                  │
  │                      │                   │<── MCPResponse ────│                  │
  │                      │                   │                    │                  │
  │                      │                   │── agregado ───────────────────────────>│
  │                      │                   │                    │                  │
  │<─────────────────────────────────────────── seguro/bloqueado ────────────────── │
```

### 2.4 Ferramentas Disponiveis por Clinica

Ambas as clinicas expoem uma interface de ferramentas identica, diferenciada apenas pelos dados de dominio subjacentes:

| Ferramenta | Parametros | Retorno | Nota de Privacidade |
|---|---|---|---|
| `list_patients` | *(nenhum)* | `{"patients": [{"patient_id", "condition"}]}` | Retorna apenas IDs e condicoes — **sem nomes ou PII**. |
| `get_patient` | `patient_id: str` | `{"patient": {registro completo}}` | Registro completo delimitado a um unico paciente. |
| `check_medications` | `patient_id: str` | `{"patient_id", "medications": [...]}` | Apenas lista de medicamentos. |
| `query` | `query: str` | `{"specialty", "query", "matches": [...]}` | Busca por texto livre; retorna apenas IDs e condicoes. |

---

## 3. Estrategia de Privacidade e Seguranca

### 3.1 Privacidade por Design

A arquitetura garante privacidade em **quatro camadas estruturais**, tornando o vazamento de dados uma violacao de fronteiras do sistema ao inves de uma escolha de politica:

```
Camada 1 — Isolamento de Processo    Cada clinica executa como um processo separado
                                     do sistema operacional. Sem memoria compartilhada,
                                     sem sistema de arquivos compartilhado.

Camada 2 — Escopo de Rede            O Router despacha uma requisicao por clinica.
                                     Nenhum payload JSON-RPC referencia duas clinicas.

Camada 3 — Minimizacao de Dados      list_patients e query retornam apenas patient_id
                                     e condition. Registros completos exigem chamadas
                                     explicitas de get_patient com um ID conhecido.

Camada 4 — Verificacao de Saida      O Verifier (Agente Observador) escaneia os
                                     resultados agregados em busca de PII antes que
                                     cheguem ao usuario.
```

### 3.2 Residencia de Dados

Os dados de pacientes (simulados no banco de dados codificado de cada clinica) **permanecem locais** ao processo do Agente Clinico em todos os momentos:

- O Orchestrator Host **nao persiste** nenhuma resposta clinica. Os resultados existem apenas em variaveis Python efemeras durante o ciclo de vida da requisicao.
- O Router transmite apenas os **parametros da consulta** para as clinicas (ex.: `patient_id`, texto de `query`) — nunca extracoes em massa de dados.
- As respostas das clinicas sao mantidas em uma lista `aggregated_results` que e coletada pelo garbage collector quando a iteracao do loop CLI termina.

### 3.3 Minimizacao de Dados nos Payloads MCP

O design de requisicao/resposta MCP aplica o principio de **Minimizacao de Dados** (LGPD Art. 6, III):

| Principio | Implementacao |
|---|---|
| **Limitacao de Finalidade** | Cada `MCPRequest.params.name` especifica exatamente uma ferramenta. A clinica nao pode ser solicitada a "extrair tudo." |
| **Payload Minimo** | `list_patients` retorna apenas `patient_id` + `condition`. Nomes, idades e medicamentos sao excluidos a menos que uma chamada direcionada de `get_patient` seja feita. |
| **Sem Armazenamento Persistente** | O Orquestrador nunca grava dados clinicos em disco, logs ou bancos de dados. |
| **Integridade do Envelope** | Cada `MCPResponse.id` correlaciona 1:1 com uma requisicao, prevenindo replay de resposta ou contaminacao cruzada. |

### 3.4 Modelo de Ameacas (Escopo)

| Ameaca | Mitigacao |
|---|---|
| Agregacao de dados entre clinicas | O Router despacha uma clinica por requisicao. O prompt do Planner proibe passos entre clinicas. |
| LLM alucinando dados medicos | A Regra R1 do Verifier verifica dosagens/tratamentos sem fundamento. |
| Vazamento de PII na saida agregada | A Regra R2 do Verifier escaneia nomes, IDs e enderecos antes da exibicao. |
| Invocacao de ferramenta nao autorizada | Os servidores clinicos retornam erro `-32602` para ferramentas desconhecidas. |
| Interceptacao de rede | Fora do escopo para prototipo. Producao: terminacao TLS em cada endpoint. |

---

## 4. Estrategia de Metricas de Avaliacao

As seguintes metricas fornecem evidencia quantitativa para avaliacao da tese. Todas as medicoes sao derivadas de logs do sistema capturados durante os testes de integracao.

### 4.1 Taxa de Sucesso de Tarefa (TSR)

Mede a proporcao de consultas de usuario de ponta a ponta que completam o pipeline inteiro (Planner → Router → Verifier) sem falha em nenhum componente.

$$
TSR = \frac{\text{Consultas com todos os passos retornando } result \neq null \text{ E } verifier.safe = true}{\text{Total de consultas submetidas}} \times 100
$$

| Classificacao | Faixa de TSR |
|---|---|
| Excelente | >= 90% |
| Aceitavel | 70%–89% |
| Insuficiente | < 70% |

### 4.2 Precisao de Chamada de Ferramenta (TCA)

Mede a capacidade do Planner de gerar nomes de ferramentas corretos e rotear para a clinica apropriada, isolado de falhas de rede ou do lado da clinica.

$$
TCA = \frac{\text{Passos onde } action \in \text{TOOL\_HANDLERS} \text{ E } clinic \in \text{REGISTRY}}{\text{Total de passos gerados pelo Planner}} \times 100
$$

**Metodo de medicao:** Para cada saida do Planner, comparar `step.action` contra as `TOOL_HANDLERS.keys()` da clinica alvo e `step.clinic` contra as `Router.registry.keys()`.

### 4.3 Taxa de Alucinacao (HR)

Mede com que frequencia o sistema produz respostas sinalizadas pelo Verifier como contendo informacao medica fabricada ou sem fundamento.

$$
HR = \frac{\text{Consultas onde } verifier.safe = false \text{ E a nota referencia a Regra R1}}{\text{Total de consultas submetidas}} \times 100
$$

**Metodo de medicao:** Parsear `VerificationResult.note` dos logs do Verifier. Classificar cada ocorrencia de `safe=false` pela regra que a disparou (R1: alucinacao, R2: PII, R3: violacao de escopo).

### 4.4 Taxa de Violacao de Privacidade (PVR)

Metrica complementar que mede os disparos da Regra R2 do Verifier.

$$
PVR = \frac{\text{Consultas onde } verifier.safe = false \text{ E a nota referencia a Regra R2}}{\text{Total de consultas submetidas}} \times 100
$$

### 4.5 Protocolo de Avaliacao

Para gerar metricas estatisticamente significativas:

1. Preparar um **conjunto de testes com N >= 30 consultas de saude** abrangendo ambas as especialidades, casos extremos (clinicas desconhecidas, sintomas ambiguos) e entradas adversariais (solicitacoes de diagnosticos, tentativas de extracao de PII).
2. Executar cada consulta atraves do pipeline completo com **logging estruturado** capturando: saida do Planner, respostas do Router, vereditos do Verifier.
3. Calcular TSR, TCA, HR e PVR a partir dos logs.
4. Apresentar resultados em formato tabular com intervalos de confianca de 95% quando aplicavel.

---

## 5. Roteiro de Implementacao

### Fase 1 — Configuracao do Ambiente

| Tarefa | Detalhe | Artefato |
|---|---|---|
| 1.1 | Criar raiz do projeto e estrutura de diretorios | Arvore `health_mas_tcc/` |
| 1.2 | Inicializar ambiente virtual Python (`python3 -m venv .venv`) | `.venv/` |
| 1.3 | Instalar dependencias a partir do `requirements.txt` | `pip install -r requirements.txt` |
| 1.4 | Configurar `.env` com credenciais do Azure OpenAI | `.env` (no gitignore) |
| 1.5 | Validar conectividade com o LLM via teste de fumaca | `AzureOpenAI.chat.completions.create()` retorna OK |

**Entregavel:** Ambiente reproduzivel onde `import openai` e `import fastapi` funcionam com sucesso.

### Fase 2 — Implementacao dos Servidores MCP (Trabalhadores Federados)

| Tarefa | Detalhe | Artefato |
|---|---|---|
| 2.1 | Definir modelos Pydantic `MCPRequest` e `MCPResponse` | `shared/mcp_types.py` |
| 2.2 | Implementar servidor FastAPI da Clinica A (Cardiologia) com banco de dados mock e 4 handlers de ferramentas | `clinic_agents/clinic_a/server.py` |
| 2.3 | Implementar servidor FastAPI da Clinica B (Dermatologia) com banco de dados mock e 4 handlers de ferramentas | `clinic_agents/clinic_b/server.py` |
| 2.4 | Criar script de inicializacao para ambos os servidores | `clinic_agents/start_clinics.sh` |
| 2.5 | Validar cada endpoint `/mcp` independentemente via `curl` | Respostas JSON-RPC com payloads `result` corretos |

**Entregavel:** Dois Servidores MCP executando independentemente que aceitam requisicoes JSON-RPC 2.0 e retornam dados especificos do dominio.

**Nota de Interoperabilidade:** Ambas as clinicas compartilham o mesmo contrato `MCPRequest`/`MCPResponse` de `shared/mcp_types.py`, garantindo interoperabilidade a nivel de protocolo sem acoplar suas implementacoes internas.

### Fase 3 — Logica do Orquestrador (Cliente MCP)

| Tarefa | Detalhe | Artefato |
|---|---|---|
| 3.1 | Implementar `Planner` com system prompt restrito incluindo catalogo de ferramentas | `orchestrator_host/planner.py` |
| 3.2 | Implementar `Router` com registro de clinicas e despacho JSON-RPC | `orchestrator_host/router.py` |
| 3.3 | Implementar `Verifier` (Agente Observador) com tres regras de seguranca | `orchestrator_host/verifier.py` |
| 3.4 | Conectar todos os componentes no loop CLI do `main.py` | `orchestrator_host/main.py` |
| 3.5 | Validar pipeline completo: consulta → decomposicao → despacho → verificacao → saida | Teste CLI ponta a ponta |

**Entregavel:** Um Orquestrador funcional que decompoe consultas, roteia para clinicas e filtra a saida atraves do Verifier.

**Nota de Desacoplamento:** Cada modulo do Orquestrador (`Planner`, `Router`, `Verifier`) e uma classe independente sem dependencias cruzadas. Eles se comunicam apenas atraves de estruturas de dados Python (`list[dict]`, `MCPResponse`, `VerificationResult`), possibilitando testes unitarios independentes.

### Fase 4 — Testes de Integracao e Logging (Evidencia para o TCC)

| Tarefa | Detalhe | Artefato |
|---|---|---|
| 4.1 | Projetar conjunto de testes com >= 30 consultas (normais, casos extremos, adversariais) | `tests/test_queries.json` |
| 4.2 | Adicionar logging estruturado (JSON lines) ao Planner, Router e Verifier | `logs/pipeline_YYYYMMDD.jsonl` |
| 4.3 | Executar conjunto de testes completo e capturar logs | Arquivos de log brutos |
| 4.4 | Calcular TSR, TCA, HR, PVR a partir dos logs | Tabela resumo de metricas |
| 4.5 | Gerar diagramas Mermaid e capturas de tela para apendice da tese | Evidencia visual |

**Entregavel:** Dados de avaliacao quantitativa e artefatos visuais prontos para inclusao nos capitulos de Metodologia e Resultados do TCC.

---

## Apendice A — Mapa de Arquivos do Projeto

```
tcc-healthcare-agents/
│
├── .env                              # Credenciais Azure OpenAI (no gitignore)
├── .env.example                      # Template para novos contribuidores
├── .gitignore                        # Protege .env e __pycache__
├── requirements.txt                  # Dependencias Python
├── TECHNICAL_BLUEPRINT.md            # Blueprint em ingles
├── BLUEPRINT_TECNICO.md              # Este documento
│
├── shared/
│   ├── __init__.py
│   └── mcp_types.py                  # MCPRequest, MCPResponse (Pydantic)
│
├── orchestrator_host/                # Cliente MCP — Orquestrador Federado
│   ├── __init__.py
│   ├── main.py                       # Ponto de entrada CLI (Planner → Router → Verifier)
│   ├── planner.py                    # Decomposicao de Tarefas via Azure OpenAI
│   ├── router.py                     # Roteamento Dinamico com registro de clinicas
│   └── verifier.py                   # Agente Observador [Burke et al. 2024]
│
└── clinic_agents/                    # Servidores MCP — Trabalhadores Federados
    ├── __init__.py
    ├── start_clinics.sh              # Script de inicializacao para todos os servidores
    ├── clinic_a/
    │   ├── __init__.py
    │   └── server.py                 # Silo de Cardiologia (porta 8001)
    └── clinic_b/
        ├── __init__.py
        └── server.py                 # Silo de Dermatologia (porta 8002)
```

## Apendice B — Glossario de Termos

| Termo | Definicao |
|---|---|
| **Desacoplamento** | Principio de design onde componentes interagem atraves de interfaces definidas (MCP) sem conhecimento interno um do outro. |
| **Interoperabilidade** | A capacidade de agentes clinicos heterogeneos se comunicarem via um protocolo compartilhado (JSON-RPC 2.0 / MCP). |
| **Validacao Deterministica** | Regras de verificacao que produzem resultados consistentes e reproduziveis dada a mesma entrada (temperatura 0.0). |
| **Minimizacao de Dados** | Transmitir apenas o minimo de dados necessarios para cada operacao (LGPD Art. 6, III). |
| **Silo de Dados Federado** | Um armazenamento de dados isolado que nao compartilha registros brutos com sistemas externos. |
| **Grafo de Passos** | Uma lista ordenada de operacoes atomicas produzida pelo Planner, cada uma direcionada a uma clinica. |
| **Agente Observador** | Um agente de auditoria independente que valida saidas sem participar de sua geracao (Burke et al. 2024). |
| **Hub-and-Spoke** | Topologia de rede onde toda comunicacao flui atraves de um hub central (Orquestrador); os spokes (Clinicas) nunca se comunicam diretamente. |
| **Handler de Ferramenta** | Uma funcao registrada em um Servidor MCP que executa uma operacao de dominio especifica quando invocada via `tools/call`. |

---

> **Documento gerado para uso academico.**
> Arquitetura: Orquestrador-Trabalhadores Federado Hierarquico com Observador.
> Protocolo: Model Context Protocol (MCP) sobre HTTP / JSON-RPC 2.0.
