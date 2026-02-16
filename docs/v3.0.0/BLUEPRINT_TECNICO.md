# Blueprint Tecnico — Sistema Multi-Agente para Saude (MAS)

> **Classificacao do Documento:** Referencia Academica — Ground Truth do TCC
> **Padrao Arquitetural:** Orquestrador-Trabalhadores Federado Hierarquico com Observador
> **Protocolo:** Model Context Protocol (MCP) sobre HTTP / JSON-RPC 2.0
> **Versao:** 3.0.0

---

## Historico de Versoes

| Versao | Data | Alteracoes |
|---|---|---|
| 1.0.0 | — | Versao inicial. 4 ferramentas por clinica. Pipeline de 4 etapas. |
| 2.0.0 | 2025-07 | Catalogo expandido para 7 ferramentas. Pipeline de 5 etapas. Identificacao do paciente. Historico de conversacao. Planner CoT. Verifier com excecoes PII e JSON. Suite de testes. Prompts externos em `prompts/`. |
| 3.0.0 | 2025-07 | 6 clinicas federadas (3 especialidades x 2 clinicas). 9 agentes. Banco de dados JSON persistente (`db.json`) por clinica com modulo compartilhado `shared/db.py`. Roteamento multi-clinica (Regra 10). Descricoes uniformes por especialidade. Comparacao de disponibilidade entre clinicas (Regra 9 do Response Generator). Teste multi-clinica. |

---

## Sumario

1. [Definicao Arquitetural (Formal)](#1-definicao-arquitetural-formal)
2. [Especificacoes dos Componentes](#2-especificacoes-dos-componentes)
3. [Arquitetura do Banco de Dados JSON](#3-arquitetura-do-banco-de-dados-json)
4. [Estrategia de Privacidade e Seguranca](#4-estrategia-de-privacidade-e-seguranca)
5. [Estrategia de Metricas de Avaliacao](#5-estrategia-de-metricas-de-avaliacao)
6. [Roteiro de Implementacao](#6-roteiro-de-implementacao)

---

## 1. Definicao Arquitetural (Formal)

### 1.1 Classificacao do Padrao

Este sistema implementa o padrao **Orquestrador-Trabalhadores Federado Hierarquico com Observador**, uma arquitetura multi-agente composta que combina tres paradigmas estabelecidos:

| Paradigma | Papel neste Sistema | Base Teorica |
|---|---|---|
| **Coordenacao Hierarquica** | O Orchestrator Host decompoe objetivos de alto nivel em sub-tarefas atomicas e as delega para baixo. Os Trabalhadores (Agentes Clinicos) nao possuem conhecimento sobre agentes irmaos ou sobre o plano global da tarefa. | Controle centralizado com execucao descentralizada. |
| **Arquitetura de Dados Federada** | Cada Agente Clinico opera como um silo de dados isolado. Registros de pacientes nunca sao transmitidos em forma bruta; apenas resultados de consultas cruzam a fronteira do processo. Cada clinica possui seu proprio arquivo `db.json` para persistencia de agendamentos. | Privacidade por Design; Minimizacao de Dados (LGPD/GDPR). |
| **Agente Observador** | Um Verificador independente audita cada resposta agregada contra regras de seguranca antes que ela chegue ao usuario final, implementando um portao de validacao deterministica. | Burke et al. (2024), "Observer Agents for Safe Multi-Agent Medical Systems." |

### 1.2 Orchestrator Host (Cliente MCP)

O Orquestrador e o unico componente com uma **visao global** da intencao do usuario. Ele contem tres modulos internos que executam sequencialmente, alem de ser responsavel pela geracao da resposta final em linguagem natural:

| Modulo | Responsabilidade | Classificacao |
|---|---|---|
| **Planner** | **Decomposicao de Tarefas** — recebe a consulta em linguagem natural e utiliza o Azure OpenAI (temperatura 0.0) para produzir um grafo de passos JSON deterministico. Cada passo e atomico e delimitado a exatamente uma clinica. Suporta historico de conversacao para fluxos multi-turn. Quando uma especialidade possui multiplas clinicas, gera um passo por clinica (Regra 10). | Planejamento assistido por LLM com saida restrita. |
| **Router** | **Roteamento Dinamico** — mantem um registro de endpoints de 6 clinicas e despacha cada passo via HTTP POST seguindo o envelope MCP JSON-RPC 2.0. O Router e o unico modulo ciente da topologia de rede. Injeta automaticamente dados de identificacao do paciente (nome, CPF) em passos de agendamento, reagendamento e cancelamento. | Despacho de servico baseado em registro. |
| **Verifier** | **Barreiras de Seguranca e Mitigacao de Alucinacoes** — atua como o Agente Observador (Burke et al. 2024). Valida resultados agregados contra tres regras deterministicas: (1) sem dosagens fabricadas, (2) sem vazamento de PII de outros pacientes, (3) sem recomendacoes fora do escopo. Serializa os dados com `json.dumps()` para garantir JSON valido na verificacao. | Camada de auditoria pos-processamento independente. |
| **Response Generator** | **Geracao de Resposta** — apos o Verifier aprovar os dados, o Orquestrador transforma os resultados estruturados em uma resposta conversacional em linguagem natural usando Azure OpenAI. O prompt do sistema descreve explicitamente o schema JSON recebido e obriga a apresentacao fiel de todos os dados retornados pelas clinicas. Quando multiplas clinicas respondem para a mesma acao, apresenta TODOS os resultados indicando a clinica de origem e destaca o horario mais proximo (Regra 9). | Capacidade interna do Orquestrador, nao um agente separado. |

### 1.3 Servidores MCP (Agentes Clinicos — Trabalhadores)

Cada Agente Clinico e uma aplicacao FastAPI **especializada por dominio** que expoe um unico endpoint `/mcp`. O sistema contem **6 clinicas** organizadas por **3 especialidades** (2 clinicas por especialidade). As clinicas incorporam tres principios fundamentais:

- **Especializacao de Dominio:** Clinicas da mesma especialidade possuem descricoes e capacidades identicas (mesmas 7 ferramentas, mesma interface). A unica diferenca entre clinicas de mesma especialidade sao os medicos, horarios e pacientes.
- **Silos de Dados / Federacao:** Cada clinica mantem seu proprio arquivo `db.json` para agendamentos e seu proprio banco de dados mock para pacientes. Nao existe banco de dados compartilhado, sistema de arquivos compartilhado ou canal de comunicacao entre clinicas. Isto garante **Preservacao de Privacidade** no nivel de infraestrutura — uma clinica nao consegue acessar os dados de outra clinica, mesmo se comprometida.
- **Persistencia Local via JSON:** As 4 ferramentas de agendamento (`list_available_slots`, `book_appointment`, `cancel_appointment`, `reschedule_appointment`) leem e gravam no arquivo `db.json` local da clinica, com protecao thread-safe via `threading.Lock()`. As 3 ferramentas de consulta (`list_patients`, `get_patient`, `query`) continuam usando dados mock codificados em memoria.

| Clinica | Especialidade | Porta | Identificador |
|---|---|---|---|
| Clinica A | Cardiologia | 8001 | `clinic_a` |
| Clinica B | Dermatologia | 8002 | `clinic_b` |
| Clinica C | Cardiologia | 8003 | `clinic_c` |
| Clinica D | Ortopedia | 8004 | `clinic_d` |
| Clinica E | Ortopedia | 8005 | `clinic_e` |
| Clinica F | Dermatologia | 8006 | `clinic_f` |

### 1.4 Pipeline Multi-Agente (5 Etapas, 9 Agentes)

O pipeline completo do sistema envolve **9 agentes** executando sequencialmente:

```
1. Entrada do usuario  →  [Agente: Planner]                  Decomposicao de Tarefas
2. Grafo de passos     →  [Agente: Router]                    Despacho Federado
3. Requisicoes MCP     →  [Agentes: Clinica A/B/C/D/E/F]     Execucao Especifica do Dominio
4. Resultados brutos   →  [Agente: Verifier]                  Validacao de Seguranca (Observador)
5. Dados validados     →  [Orquestrador]                      Resposta em Linguagem Natural
```

Os 9 agentes sao: **Planner**, **Router**, **Clinica A**, **Clinica B**, **Clinica C**, **Clinica D**, **Clinica E**, **Clinica F** e **Verifier**.

### 1.5 Roteamento Multi-Clinica

Quando o usuario solicita uma acao relacionada a uma especialidade que possui mais de uma clinica (ex.: Cardiologia tem `clinic_a` e `clinic_c`), o Planner **DEVE** gerar um passo para **cada** clinica dessa especialidade. Isso permite que o sistema:

1. Consulte todas as clinicas da especialidade em paralelo.
2. Agregue os resultados de multiplas clinicas.
3. Compare disponibilidade entre clinicas.
4. Identifique e destaque o horario mais proximo/conveniente.

**Exemplo — Roteamento Multi-Clinica para Cardiologia:**

```json
[
  {"step_id": 1, "clinic": "clinic_a", "action": "list_available_slots", "parameters": {}},
  {"step_id": 2, "clinic": "clinic_c", "action": "list_available_slots", "parameters": {}}
]
```

Esta regra (Regra 10 do Planner) garante que o paciente tenha visibilidade completa de todos os horarios disponiveis em sua especialidade, independentemente de qual clinica os oferece.

### 1.6 Identificacao do Paciente

Antes de iniciar a sessao interativa, o sistema coleta:
- **Nome completo** do paciente
- **CPF** (Cadastro de Pessoa Fisica)

Esses dados sao injetados automaticamente pelo Orquestrador nos passos de `book_appointment`, `reschedule_appointment` e `cancel_appointment` antes do despacho ao Router. Isso evita que o usuario precise repetir seus dados a cada interacao.

### 1.7 Topologia Hub-and-Spoke (Diagrama Mermaid)

```mermaid
graph TD
    User([fa:fa-user Usuario Final / Operador])

    subgraph Orchestrator Host — Cliente MCP
        Planner[fa:fa-project-diagram Planner<br/><i>Decomposicao de Tarefas</i><br/>Azure OpenAI · temp 0.0]
        Router[fa:fa-route Router<br/><i>Roteamento Dinamico</i><br/>Despacho baseado em registro]
        Verifier[fa:fa-shield-alt Verifier<br/><i>Agente Observador</i><br/>Barreiras de Seguranca]
        ResponseGen[fa:fa-comment-dots Response Generator<br/><i>Resposta em Linguagem Natural</i><br/>Azure OpenAI · temp 0.3]
    end

    subgraph Silos de Dados Federados — Cardiologia
        ClinicA[fa:fa-heartbeat Clinica A<br/><b>Cardiologia</b><br/>FastAPI · Porta 8001<br/>Servidor MCP + db.json]
        ClinicC[fa:fa-heartbeat Clinica C<br/><b>Cardiologia</b><br/>FastAPI · Porta 8003<br/>Servidor MCP + db.json]
    end

    subgraph Silos de Dados Federados — Dermatologia
        ClinicB[fa:fa-allergies Clinica B<br/><b>Dermatologia</b><br/>FastAPI · Porta 8002<br/>Servidor MCP + db.json]
        ClinicF[fa:fa-allergies Clinica F<br/><b>Dermatologia</b><br/>FastAPI · Porta 8006<br/>Servidor MCP + db.json]
    end

    subgraph Silos de Dados Federados — Ortopedia
        ClinicD[fa:fa-bone Clinica D<br/><b>Ortopedia</b><br/>FastAPI · Porta 8004<br/>Servidor MCP + db.json]
        ClinicE[fa:fa-bone Clinica E<br/><b>Ortopedia</b><br/>FastAPI · Porta 8005<br/>Servidor MCP + db.json]
    end

    User -->|Consulta em linguagem natural| Planner
    Planner -->|Grafo de passos JSON| Router
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicA
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicB
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicC
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicD
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicE
    Router -->|"HTTP POST /mcp<br/>JSON-RPC 2.0"| ClinicF
    ClinicA -->|MCPResponse| Router
    ClinicB -->|MCPResponse| Router
    ClinicC -->|MCPResponse| Router
    ClinicD -->|MCPResponse| Router
    ClinicE -->|MCPResponse| Router
    ClinicF -->|MCPResponse| Router
    Router -->|Resultados agregados| Verifier
    Verifier -->|"safe: true"| ResponseGen
    ResponseGen -->|Resposta conversacional| User

    style Planner fill:#4a90d9,color:#fff
    style Router fill:#7b68ee,color:#fff
    style Verifier fill:#e74c3c,color:#fff
    style ResponseGen fill:#9b59b6,color:#fff
    style ClinicA fill:#27ae60,color:#fff
    style ClinicC fill:#2ecc71,color:#fff
    style ClinicB fill:#f39c12,color:#fff
    style ClinicF fill:#f1c40f,color:#000
    style ClinicD fill:#3498db,color:#fff
    style ClinicE fill:#5dade2,color:#fff
```

> **Justificativa da topologia:** O modelo Hub-and-Spoke garante **Desacoplamento** entre os agentes clinicos. Adicionar uma nova clinica de qualquer especialidade requer apenas registrar uma nova URL no registro do Router e implantar um novo Servidor MCP. Nenhum codigo de clinica existente e modificado, satisfazendo o Principio Aberto-Fechado. A presenca de multiplas clinicas por especialidade habilita **roteamento multi-clinica** e **comparacao de disponibilidade**, permitindo ao paciente encontrar o horario mais conveniente entre todas as clinicas de sua especialidade.

---

## 2. Especificacoes dos Componentes

### 2.1 Pilha Tecnologica

| Camada | Tecnologia | Versao | Finalidade |
|---|---|---|---|
| Linguagem | Python | 3.9+ | Runtime principal |
| Framework Web | FastAPI | mais recente | Endpoints dos Servidores MCP (Agentes Clinicos) |
| Servidor ASGI | Uvicorn | mais recente | Servidor assincrono de nivel de producao |
| SDK de LLM | `openai` (AzureOpenAI) | mais recente | Raciocinio do Planner, Verifier e Response Generator |
| Validacao de Dados | Pydantic | v2 | Schemas MCPRequest / MCPResponse |
| Cliente HTTP | Requests | mais recente | Despacho Router → Clinica |
| Configuracao | python-dotenv | mais recente | Gerenciamento de variaveis de ambiente |
| Persistencia | JSON (`db.json`) | — | Banco de dados de agendamentos por clinica |
| Concorrencia | `threading.Lock` | stdlib | Protecao thread-safe para leitura/escrita do `db.json` |

### 2.2 Especificacao do Protocolo: MCP sobre HTTP (JSON-RPC 2.0)

Toda comunicacao inter-agente segue o **Model Context Protocol** transportado sobre HTTP utilizando o envelope JSON-RPC 2.0.

**Schema da Requisicao** (`shared/mcp_types.py` — `MCPRequest`):

```json
{
    "jsonrpc": "2.0",
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "method": "tools/call",
    "params": {
        "name": "book_appointment",
        "arguments": {
            "doctor": "Dr. Ricardo Lopes",
            "date": "2025-07-21",
            "time": "09:00",
            "patient_name": "Carlos Teste",
            "cpf": "123.456.789-00"
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
    "result": {
        "status": "confirmed",
        "appointment": {
            "doctor": "Dr. Ricardo Lopes",
            "date": "2025-07-21",
            "time": "09:00",
            "patient_name": "Carlos Teste",
            "cpf": "123.456.789-00",
            "specialty": "Cardiology"
        },
        "message": "Consulta agendada com sucesso."
    },
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
**System Prompt:** `prompts/planner.txt` (variante CoT: `prompts/planner_cot.txt`)

O Planner converte uma consulta de saude em linguagem natural em um **grafo de passos** executavel — um array JSON ordenado onde cada elemento representa uma operacao atomica em uma clinica. Suporta **historico de conversacao** para fluxos multi-turn (ex.: usuario lista horarios, depois escolhe um para agendar). O system prompt e carregado de um arquivo externo (`prompts/planner.txt`) para facilitar leitura e manutencao.

```
Entrada: "quero marcar uma consulta com um cardiologista"
           |
           v
     +-------------------------------------+
     |  Azure OpenAI (gpt-4o, temp=0.0)   |
     |  System Prompt: schema restrito     |
     |  + registro de 6 clinicas           |
     |  + catalogo de ferramentas          |
     |  + historico de conversacao         |
     |  + Regra 10: multi-clinica          |
     +-------------------------------------+
           |
           v
Saida:  [
          {"step_id": 1, "clinic": "clinic_a", "action": "list_available_slots", "parameters": {}},
          {"step_id": 2, "clinic": "clinic_c", "action": "list_available_slots", "parameters": {}}
        ]
```

**Restricoes deterministicas aplicadas via system prompt:**
1. Apenas clinicas presentes no registro podem ser referenciadas (`clinic_a` a `clinic_f`).
2. Apenas nomes de ferramentas do catalogo exato sao permitidos (ver secao 2.4).
3. Cada passo e delimitado a uma unica clinica — **sem joins entre clinicas** em um unico passo (Preservacao de Privacidade).
4. A saida e estritamente JSON sem blocos markdown ou comentarios em linguagem natural.
5. A temperatura e definida como `0.0` para minimizar o nao-determinismo.
6. O historico de conversacao permite que o Planner extraia detalhes de compromissos anteriores para reagendamento e cancelamento.
7. Consultas de agendamento, disponibilidade e qualquer referencia a especialidades medicas sao classificadas como relacionadas a saude.
8. Reagendamento extrai dados originais do historico de conversacao.
9. Cancelamento extrai dados da consulta do historico de conversacao.
10. **Roteamento Multi-Clinica:** Quando a especialidade consultada possui mais de uma clinica (ex.: Cardiologia tem `clinic_a` E `clinic_c`), o Planner DEVE gerar um passo por clinica para consultar TODAS elas, permitindo comparacao de disponibilidade.

**Variante Chain-of-Thought (CoT):**
O Planner oferece um metodo alternativo `decompose_cot()` que exige raciocinio explicito antes de produzir o grafo de passos:

```json
{
  "reasoning": [
    "O usuario quer marcar uma consulta com cardiologista.",
    "Cardiologia e tratada pela clinic_a e clinic_c (Regra 10).",
    "Preciso listar os horarios disponiveis em AMBAS as clinicas.",
    "Nenhuma combinacao de dados entre clinicas e necessaria."
  ],
  "steps": [
    {"step_id": 1, "clinic": "clinic_a", "action": "list_available_slots", "parameters": {}},
    {"step_id": 2, "clinic": "clinic_c", "action": "list_available_slots", "parameters": {}}
  ]
}
```

Isso fornece uma trilha de raciocinio auditavel para avaliacao academica.

**Mecanismo de fallback:** Se o LLM retornar JSON nao parseavel, o Planner encapsula a saida bruta em um passo de fallback (`action: "raw_response"`) para que o pipeline nao quebre.

#### 2.3.2 Logica do Verifier — Validacao Deterministica do Agente Observador

**Arquivo:** `orchestrator_host/verifier.py`
**System Prompt:** `prompts/verifier.txt`
**Referencia:** Burke et al. (2024)

O Verifier recebe os **resultados agregados** de todos os passos despachados (potencialmente de multiplas clinicas) e os valida contra tres regras de seguranca deterministicas:

| Regra # | Verificacao | Justificativa |
|---|---|---|
| R1 | A resposta NAO contem dosagens de medicamentos fabricadas ou planos de tratamento sem fundamento nos dados clinicos. | **Mitigacao de Alucinacoes** — impede que o LLM invente informacoes medicas. |
| R2 | A resposta NAO expoe Informacoes Pessoais Identificaveis de OUTROS pacientes (nomes completos, documentos governamentais, enderecos). | **Preservacao de Privacidade** — aplica Minimizacao de Dados na camada de saida. |
| R3 | A resposta NAO recomenda acoes fora do escopo do agente (ex.: diagnosticar sem um medico). | **Barreiras de Seguranca** — previne aconselhamento medico que gere responsabilidade legal. |

**Excecoes de PII (SEGURAS — nunca devem ser sinalizadas):**
- Identificadores anonimos como "CARD-001", "DERM-002", "ORTH-D001", "DERM-F001" — tokens opacos do sistema.
- Nomes de medicos/profissionais de saude — informacao profissional publica.
- Nome e CPF do PROPRIO USUARIO em confirmacoes de agendamento — o usuario forneceu esses dados voluntariamente para identificacao e eles sao ESPERADOS no recibo de agendamento.

**Serializacao:** Os dados agregados sao serializados com `json.dumps(agent_response, ensure_ascii=False)` para produzir JSON valido (aspas duplas, `true`/`false`) em vez de representacao Python (`str()`), garantindo que o LLM do Verifier interprete os dados corretamente.

**Schema de saida da validacao:**

```json
{"safe": true,  "note": "OK"}
{"safe": false, "note": "Resposta contem dosagem fabricada para Amiodarona."}
```

**Comportamento do pipeline:**
- `safe: true` → os resultados prosseguem para o Response Generator e depois sao exibidos ao usuario final.
- `safe: false` → os resultados sao **bloqueados**; apenas a `note` explicando a violacao e mostrada.

#### 2.3.3 Logica do Response Generator — Geracao de Resposta em Linguagem Natural

**Arquivo:** `orchestrator_host/main.py` (funcao `_generate_response`)
**System Prompt:** `prompts/response_generator.txt`

Apos o Verifier aprovar os dados, o Orquestrador transforma os resultados estruturados em uma resposta conversacional. O prompt do sistema (`RESPONSE_SYSTEM_PROMPT`), carregado de `prompts/response_generator.txt`, inclui:

1. **Descricao do schema JSON** que o LLM recebera:
   - `user_query`: a pergunta original do paciente
   - `clinic_data[]`: lista de resultados, cada um com `clinic`, `action`, `result`, `error`

2. **Regras explicitas:**
   - Responder no MESMO IDIOMA do usuario
   - Se `result` contem dados (slots, pacientes, consultas), SEMPRE apresenta-los — nunca dizer "nao ha resultados" quando o JSON mostra dados
   - Se `result` contem `available_slots`, listar TODOS os horarios com data, hora e nome do medico
   - NUNCA inventar ou fabricar dados
   - Ser profissional como um recepcionista de clinica
   - Manter respostas concisas mas completas

3. **Regra 9 — Multiplas Clinicas:** Quando `clinic_data` contem resultados de mais de uma clinica para a mesma acao, apresentar TODOS os horarios de TODAS as clinicas juntos, indicando claramente a qual clinica cada horario pertence. Quando o usuario pede o horario "mais proximo" ou "mais perto", identificar e destacar o horario mais cedo entre todas as clinicas, mas ainda listar as demais opcoes.

**Payload enviado ao LLM (exemplo multi-clinica):**

```json
{
    "user_query": "quero marcar uma consulta com um cardiologista",
    "clinic_data": [
        {
            "clinic": "clinic_a",
            "action": "list_available_slots",
            "result": {
                "specialty": "Cardiology",
                "available_slots": [
                    {"doctor": "Dr. Ricardo Lopes", "specialty": "Cardiologia", "date": "2025-07-21", "time": "09:00", "available": true},
                    {"doctor": "Dr. Ricardo Lopes", "specialty": "Cardiologia", "date": "2025-07-21", "time": "10:30", "available": true}
                ],
                "note": "Para confirmar o agendamento, informe o horario desejado."
            },
            "error": null
        },
        {
            "clinic": "clinic_c",
            "action": "list_available_slots",
            "result": {
                "specialty": "Cardiology",
                "available_slots": [
                    {"doctor": "Dr. Fernando Mendes", "specialty": "Cardiologia", "date": "2025-07-18", "time": "10:00", "available": true},
                    {"doctor": "Dr. Fernando Mendes", "specialty": "Cardiologia", "date": "2025-07-19", "time": "14:00", "available": true}
                ],
                "note": "Para confirmar o agendamento, informe o horario desejado."
            },
            "error": null
        }
    ]
}
```

#### 2.3.4 Fluxo de Chamada de Ferramentas — Sequencia Ponta a Ponta

```
 Usuario               Planner             Router              Clinica A/C        Verifier          Response Gen
  |                      |                   |                    |                  |                  |
  |-- consulta --------->|                   |                    |                  |                  |
  |                      |-- grafo passos -->|                    |                  |                  |
  |                      |  (1 passo por     |                    |                  |                  |
  |                      |   clinica)        |                    |                  |                  |
  |                      |                   |-- MCPRequest ----->| clinic_a         |                  |
  |                      |                   |   POST /mcp        |                  |                  |
  |                      |                   |<-- MCPResponse ----|                  |                  |
  |                      |                   |                    |                  |                  |
  |                      |                   |-- MCPRequest ----->| clinic_c         |                  |
  |                      |                   |   POST /mcp        |                  |                  |
  |                      |                   |<-- MCPResponse ----|                  |                  |
  |                      |                   |                    |                  |                  |
  |                      |                   |-- agregado --------------------------->|                  |
  |                      |                   |                    |                  |-- safe: true ---->|
  |                      |                   |                    |                  |                  |
  |<------------------------------------------------------------------------------------------resposta-|
```

### 2.4 Ferramentas Disponiveis por Clinica

Todas as 6 clinicas expoem uma interface de ferramentas identica com **7 ferramentas**, diferenciada apenas pelos dados de dominio subjacentes. Clinicas da mesma especialidade possuem **descricoes e capacidades uniformes** — a unica diferenca entre elas sao os medicos, horarios e pacientes.

#### Ferramentas de Consulta (Dados Mock em Memoria)

| Ferramenta | Parametros | Retorno | Nota de Privacidade |
|---|---|---|---|
| `list_patients` | *(nenhum)* | `{"patients": [{"patient_id", "condition"}]}` | Retorna apenas IDs e condicoes — **sem nomes ou PII**. Dados mock codificados em memoria. |
| `get_patient` | `patient_id: str` | `{"patient": {registro completo}}` | Registro completo delimitado a um unico paciente. Dados mock codificados em memoria. |
| `query` | `query: str` | `{"specialty", "query", "matches": [...]}` | Busca por texto livre; retorna apenas IDs e condicoes. Dados mock codificados em memoria. |

#### Ferramentas de Agendamento (Banco de Dados JSON Persistente)

| Ferramenta | Parametros | Retorno | Nota |
|---|---|---|---|
| `list_available_slots` | `doctor: str` *(opcional)* | `{"specialty", "available_slots": [{doctor, specialty, date, time, available}], "note"}` | Retorna apenas horarios com `available: true` do `db.json` local. Filtro opcional por medico. |
| `book_appointment` | `doctor: str`, `date: str`, `time: str`, `patient_name: str`, `cpf: str` | `{"status": "confirmed", "appointment": {...}, "message"}` | Marca o slot como `available: false` e salva dados do paciente no `db.json`. `patient_name` e `cpf` sao injetados automaticamente pelo Orquestrador. |
| `reschedule_appointment` | `original_date: str`, `original_time: str`, `doctor: str`, `new_date: str`, `new_time: str`, `patient_name: str`, `cpf: str` | `{"status": "rescheduled", "original_appointment": {...}, "new_appointment": {...}, "message"}` | Libera o slot original (`available: true`) e reserva o novo (`available: false`) no `db.json`. Dados originais extraidos do historico de conversacao pelo Planner. |
| `cancel_appointment` | `doctor: str`, `date: str`, `time: str`, `patient_name: str`, `cpf: str` | `{"status": "cancelled", "cancelled_appointment": {...}, "message"}` | Marca o slot como `available: true` e remove dados do paciente no `db.json`. Dados extraidos do historico de conversacao pelo Planner. |

### 2.5 Fluxos de Interacao Multi-Turn

O sistema suporta tres fluxos conversacionais principais, agora com roteamento multi-clinica:

#### Fluxo de Agendamento (2 turnos)
```
Turn 1: "quero marcar uma consulta com cardiologista"
        → Planner gera 2 passos: list_available_slots para clinic_a E clinic_c (Regra 10)
        → Ambas as clinicas retornam seus horarios disponiveis do db.json
        → Resposta: lista consolidada de horarios de AMBAS as clinicas, horario mais proximo destacado

Turn 2: "pode ser com o Dr. Fernando dia 18 as 10h"
        → Planner identifica clinic_c pelo contexto → book_appointment
        → db.json da clinic_c atualizado: slot marcado como available: false
        → Resposta: confirmacao do agendamento
```

#### Fluxo de Reagendamento (3 turnos)
```
Turn 1-2: (mesmo que agendamento acima)

Turn 3: "preciso reagendar para o dia 19 as 14h"
        → Planner extrai consulta original do historico
        → reschedule_appointment em clinic_c com dados originais e novos
        → db.json da clinic_c atualizado: slot original liberado, novo slot reservado
        → Resposta: confirmacao do reagendamento
```

#### Fluxo de Cancelamento (3 turnos)
```
Turn 1-2: (mesmo que agendamento acima)

Turn 3: "preciso cancelar minha consulta"
        → Planner extrai dados da consulta do historico
        → cancel_appointment em clinic_c
        → db.json da clinic_c atualizado: slot marcado como available: true
        → Resposta: confirmacao do cancelamento
```

---

## 3. Arquitetura do Banco de Dados JSON

### 3.1 Visao Geral

A v3.0.0 introduz um sistema de persistencia baseado em arquivos JSON (`db.json`) para os dados de agendamento. Cada clinica mantem seu proprio arquivo `db.json` no seu diretorio, formando um **silo de dados federado** para agendamentos.

```
clinic_agents/
  clinic_a/db.json    ← Cardiologia (silo A)
  clinic_b/db.json    ← Dermatologia (silo B)
  clinic_c/db.json    ← Cardiologia (silo C)
  clinic_d/db.json    ← Ortopedia (silo D)
  clinic_e/db.json    ← Ortopedia (silo E)
  clinic_f/db.json    ← Dermatologia (silo F)
```

### 3.2 Schema do `db.json`

Cada `db.json` contem um objeto raiz com uma chave `"slots"` que mapeia para um array de objetos de horario:

```json
{
  "slots": [
    {
      "doctor": "Dr. Ricardo Lopes",
      "specialty": "Cardiologia",
      "date": "2025-07-21",
      "time": "09:00",
      "available": true,
      "patient_name": null,
      "cpf": null
    },
    {
      "doctor": "Dr. Ricardo Lopes",
      "specialty": "Cardiologia",
      "date": "2025-07-21",
      "time": "10:30",
      "available": true,
      "patient_name": null,
      "cpf": null
    }
  ]
}
```

| Campo | Tipo | Descricao |
|---|---|---|
| `doctor` | `str` | Nome completo do medico. |
| `specialty` | `str` | Sub-especialidade ou especialidade geral. |
| `date` | `str` | Data no formato `YYYY-MM-DD`. |
| `time` | `str` | Hora no formato `HH:MM`. |
| `available` | `bool` | `true` = horario livre; `false` = horario reservado. |
| `patient_name` | `str \| null` | Nome do paciente que reservou o horario, ou `null` se disponivel. |
| `cpf` | `str \| null` | CPF do paciente que reservou o horario, ou `null` se disponivel. |

### 3.3 Modulo Compartilhado `shared/db.py`

O modulo `shared/db.py` centraliza toda a logica de leitura/escrita do `db.json` e os 4 handlers de agendamento, evitando duplicacao de codigo entre as 6 clinicas:

| Funcao | Responsabilidade |
|---|---|
| `_load_slots(db_path)` | Le e retorna o array `slots` do `db.json` no caminho especificado. |
| `_save_slots(db_path, slots)` | Grava o array `slots` atualizado no `db.json` com `ensure_ascii=False` e indentacao. |
| `handle_list_available_slots(db_path, specialty, ...)` | Filtra e retorna apenas slots com `available: true`. Aceita filtro opcional por medico. |
| `handle_book_appointment(db_path, specialty, ...)` | Localiza o slot, marca `available: false`, salva `patient_name` e `cpf`. Persiste no `db.json`. |
| `handle_cancel_appointment(db_path, specialty, ...)` | Localiza o slot reservado, marca `available: true`, limpa dados do paciente. Persiste no `db.json`. |
| `handle_reschedule_appointment(db_path, specialty, ...)` | Libera o slot original e reserva o novo slot em uma unica operacao atomica. Persiste no `db.json`. |

### 3.4 Thread-Safety

Todas as operacoes de leitura e escrita no `db.json` sao protegidas por um `threading.Lock()` global no modulo `shared/db.py`. Isso garante que requisicoes concorrentes (ex.: dois usuarios tentando reservar o mesmo horario simultaneamente) nao corrompam os dados.

```python
_lock = threading.Lock()

def handle_book_appointment(db_path, specialty, ...):
    with _lock:
        slots = _load_slots(db_path)
        # ... localiza e atualiza o slot ...
        _save_slots(db_path, slots)
```

### 3.5 Aplicacao Parcial (`functools.partial`)

Cada servidor de clinica utiliza `functools.partial` para vincular os handlers compartilhados ao seu `_DB_PATH` e `_SPECIALTY` especificos. Isso permite que o mesmo codigo em `shared/db.py` sirva todas as 6 clinicas com dados diferentes:

```python
from functools import partial
from shared.db import handle_list_available_slots, handle_book_appointment, ...

_DB_PATH = Path(__file__).resolve().parent / "db.json"
_SPECIALTY = "Cardiology"

_handle_list_available_slots = partial(handle_list_available_slots, _DB_PATH, _SPECIALTY)
_handle_book_appointment = partial(handle_book_appointment, _DB_PATH, _SPECIALTY)
```

### 3.6 Separacao de Dados: Mock vs. Persistente

O sistema utiliza duas fontes de dados distintas por clinica:

| Fonte | Ferramentas | Armazenamento | Mutabilidade |
|---|---|---|---|
| **Banco de dados mock** (codificado em memoria) | `list_patients`, `get_patient`, `query` | Variavel Python no `server.py` | Somente leitura (dados simulados para demonstracao) |
| **Banco de dados JSON** (`db.json`) | `list_available_slots`, `book_appointment`, `cancel_appointment`, `reschedule_appointment` | Arquivo `db.json` no diretorio da clinica | Leitura e escrita (persistencia real de agendamentos) |

Esta separacao garante que os dados de pacientes (mock) permanecem imutaveis enquanto os agendamentos sao persistidos de forma realista.

---

## 4. Estrategia de Privacidade e Seguranca

### 4.1 Privacidade por Design

A arquitetura garante privacidade em **cinco camadas estruturais**, tornando o vazamento de dados uma violacao de fronteiras do sistema ao inves de uma escolha de politica:

```
Camada 1 — Isolamento de Processo    Cada clinica executa como um processo separado
                                     do sistema operacional. Sem memoria compartilhada,
                                     sem sistema de arquivos compartilhado. Os 6 silos
                                     sao completamente independentes.

Camada 2 — Escopo de Rede            O Router despacha uma requisicao por clinica.
                                     Nenhum payload JSON-RPC referencia duas clinicas.
                                     No roteamento multi-clinica, cada clinica recebe
                                     sua propria requisicao isolada.

Camada 3 — Minimizacao de Dados      list_patients e query retornam apenas patient_id
                                     e condition. Registros completos exigem chamadas
                                     explicitas de get_patient com um ID conhecido.

Camada 4 — Isolamento de Persistencia  Cada clinica grava agendamentos em seu proprio
                                     db.json local. Nenhum arquivo de banco de dados e
                                     compartilhado entre clinicas. Dados de pacientes
                                     (nome, CPF) sao gravados apenas no db.json da
                                     clinica onde o agendamento foi realizado.

Camada 5 — Verificacao de Saida      O Verifier (Agente Observador) escaneia os
                                     resultados agregados (potencialmente de multiplas
                                     clinicas) em busca de PII antes que cheguem ao
                                     usuario.
```

### 4.2 Residencia de Dados

Os dados sao residentes em dois niveis:

**Dados em Memoria (Mock):**
Os dados de pacientes (simulados no banco de dados codificado de cada clinica) **permanecem locais** ao processo do Agente Clinico em todos os momentos.

**Dados Persistidos (JSON):**
Os dados de agendamento sao gravados no arquivo `db.json` local de cada clinica. Esses arquivos residem no diretorio da clinica e nao sao acessiveis por outras clinicas.

**Comportamento do Orquestrador:**
- O Orchestrator Host **nao persiste** nenhuma resposta clinica. Os resultados existem apenas em variaveis Python efemeras durante o ciclo de vida da requisicao.
- O Router transmite apenas os **parametros da consulta** para as clinicas (ex.: `patient_id`, texto de `query`, dados de agendamento) — nunca extracoes em massa de dados.
- As respostas das clinicas sao mantidas em uma lista `aggregated_results` que e coletada pelo garbage collector quando a iteracao do loop CLI termina.
- Dados de identificacao do paciente (nome, CPF) sao mantidos em memoria durante a sessao e injetados apenas nos passos que os requerem.

### 4.3 Minimizacao de Dados nos Payloads MCP

O design de requisicao/resposta MCP aplica o principio de **Minimizacao de Dados** (LGPD Art. 6, III):

| Principio | Implementacao |
|---|---|
| **Limitacao de Finalidade** | Cada `MCPRequest.params.name` especifica exatamente uma ferramenta. A clinica nao pode ser solicitada a "extrair tudo." |
| **Payload Minimo** | `list_patients` retorna apenas `patient_id` + `condition`. Nomes, idades e medicamentos sao excluidos a menos que uma chamada direcionada de `get_patient` seja feita. |
| **Persistencia Isolada** | Os arquivos `db.json` gravam apenas os dados minimos necessarios para o agendamento: medico, data, hora, nome e CPF do paciente. Nenhum dado clinico (condicoes, exames, medicamentos) e gravado no `db.json`. |
| **Integridade do Envelope** | Cada `MCPResponse.id` correlaciona 1:1 com uma requisicao, prevenindo replay de resposta ou contaminacao cruzada. |
| **Dados de Identificacao Isolados** | Nome e CPF do paciente sao injetados pelo Orquestrador apenas nos passos que requerem identificacao (agendamento, reagendamento, cancelamento). Nao sao enviados em consultas de busca. |

### 4.4 Protecao dos Arquivos `db.json`

Os arquivos `db.json` contem dados pessoais (nome e CPF de pacientes que agendaram consultas). As seguintes protecoes se aplicam:

| Protecao | Implementacao |
|---|---|
| **Isolamento de processo** | Cada clinica acessa apenas seu proprio `db.json` via `_DB_PATH` local. |
| **Sem acesso cruzado** | Nenhum handler de ferramenta recebe o caminho de `db.json` de outra clinica. |
| **Thread-safety** | `threading.Lock()` previne corrupcao por acesso concorrente. |
| **Gitignore** | Arquivos `db.json` com dados reais devem ser incluidos no `.gitignore` em producao. |
| **Limpeza de dados** | `cancel_appointment` remove nome e CPF do slot (define como `null`). |

### 4.5 Modelo de Ameacas (Escopo)

| Ameaca | Mitigacao |
|---|---|
| Agregacao de dados entre clinicas | O Router despacha uma clinica por requisicao. O prompt do Planner proibe passos entre clinicas. No roteamento multi-clinica, cada clinica recebe uma requisicao isolada. |
| LLM alucinando dados medicos | A Regra R1 do Verifier verifica dosagens/tratamentos sem fundamento. |
| Vazamento de PII na saida agregada | A Regra R2 do Verifier escaneia nomes, IDs e enderecos antes da exibicao. |
| Invocacao de ferramenta nao autorizada | Os servidores clinicos retornam erro `-32602` para ferramentas desconhecidas. |
| LLM ignorando dados reais das clinicas | O RESPONSE_SYSTEM_PROMPT descreve explicitamente o schema JSON e obriga a apresentacao fiel de todos os dados retornados. |
| Serializacao degradada no Verifier | Corrigido: `json.dumps()` em vez de `str()` para garantir JSON valido. |
| Corrupcao de `db.json` por acesso concorrente | `threading.Lock()` no modulo `shared/db.py` garante atomicidade de leitura/escrita. |
| Acesso indevido ao `db.json` de outra clinica | Cada servidor vincula `_DB_PATH` ao seu proprio diretorio via `functools.partial`. Nao ha mecanismo para referenciar outro `db.json`. |
| Interceptacao de rede | Fora do escopo para prototipo. Producao: terminacao TLS em cada endpoint. |

---

## 5. Estrategia de Metricas de Avaliacao

As seguintes metricas fornecem evidencia quantitativa para avaliacao da tese. Todas as medicoes sao derivadas de logs do sistema capturados durante os testes de integracao.

### 5.1 Taxa de Sucesso de Tarefa (TSR)

Mede a proporcao de consultas de usuario de ponta a ponta que completam o pipeline inteiro (Planner → Router → Verifier → Response Generator) sem falha em nenhum componente.

$$
TSR = \frac{\text{Consultas com todos os passos retornando } result \neq null \text{ E } verifier.safe = true}{\text{Total de consultas submetidas}} \times 100
$$

| Classificacao | Faixa de TSR |
|---|---|
| Excelente | >= 90% |
| Aceitavel | 70%–89% |
| Insuficiente | < 70% |

### 5.2 Precisao de Chamada de Ferramenta (TCA)

Mede a capacidade do Planner de gerar nomes de ferramentas corretos e rotear para a clinica apropriada, isolado de falhas de rede ou do lado da clinica.

$$
TCA = \frac{\text{Passos onde } action \in \text{TOOL\_HANDLERS} \text{ E } clinic \in \text{REGISTRY}}{\text{Total de passos gerados pelo Planner}} \times 100
$$

**Metodo de medicao:** Para cada saida do Planner, comparar `step.action` contra as `TOOL_HANDLERS.keys()` da clinica alvo e `step.clinic` contra as `Router.registry.keys()` (6 clinicas: `clinic_a` a `clinic_f`).

### 5.3 Taxa de Alucinacao (HR)

Mede com que frequencia o sistema produz respostas sinalizadas pelo Verifier como contendo informacao medica fabricada ou sem fundamento.

$$
HR = \frac{\text{Consultas onde } verifier.safe = false \text{ E a nota referencia a Regra R1}}{\text{Total de consultas submetidas}} \times 100
$$

**Metodo de medicao:** Parsear `VerificationResult.note` dos logs do Verifier. Classificar cada ocorrencia de `safe=false` pela regra que a disparou (R1: alucinacao, R2: PII, R3: violacao de escopo).

### 5.4 Taxa de Violacao de Privacidade (PVR)

Metrica complementar que mede os disparos da Regra R2 do Verifier.

$$
PVR = \frac{\text{Consultas onde } verifier.safe = false \text{ E a nota referencia a Regra R2}}{\text{Total de consultas submetidas}} \times 100
$$

### 5.5 Precisao de Roteamento Multi-Clinica (MCRA)

Metrica nova na v3.0.0 que mede a capacidade do Planner de gerar passos para TODAS as clinicas relevantes quando uma especialidade possui multiplas clinicas.

$$
MCRA = \frac{\text{Consultas multi-clinica onde o Planner gerou passos para TODAS as clinicas da especialidade}}{\text{Total de consultas que requerem roteamento multi-clinica}} \times 100
$$

**Metodo de medicao:** Para cada consulta que referencia uma especialidade com multiplas clinicas (Cardiologia: clinic_a + clinic_c; Dermatologia: clinic_b + clinic_f; Ortopedia: clinic_d + clinic_e), verificar se o Planner gerou exatamente um passo para cada clinica da especialidade.

### 5.6 Protocolo de Avaliacao

Para gerar metricas estatisticamente significativas:

1. Preparar um **conjunto de testes com N >= 30 consultas de saude** abrangendo as tres especialidades (Cardiologia, Dermatologia, Ortopedia), casos extremos (clinicas desconhecidas, sintomas ambiguos) e entradas adversariais (solicitacoes de diagnosticos, tentativas de extracao de PII).
2. Incluir consultas que exercitem o **roteamento multi-clinica** (ex.: "quero marcar com cardiologista" deve acionar clinic_a e clinic_c).
3. Executar cada consulta atraves do pipeline completo com **structured logging** capturando: saida do Planner, respostas do Router, vereditos do Verifier, resposta final gerada.
4. Calcular TSR, TCA, HR, PVR e MCRA a partir dos logs.
5. Apresentar resultados em formato tabular com intervalos de confianca de 95% quando aplicavel.

---

## 6. Roteiro de Implementacao

### Fase 1 — Configuracao do Ambiente

| Tarefa | Detalhe | Artefato |
|---|---|---|
| 1.1 | Criar raiz do projeto e estrutura de diretorios | Arvore `tcc-healthcare-agents/` |
| 1.2 | Inicializar ambiente virtual Python (`python3 -m venv .venv`) | `.venv/` |
| 1.3 | Instalar dependencias a partir do `requirements.txt` | `pip install -r requirements.txt` |
| 1.4 | Configurar `.env` com credenciais do Azure OpenAI | `.env` (no gitignore) |
| 1.5 | Validar conectividade com o LLM via teste de fumaca | `AzureOpenAI.chat.completions.create()` retorna OK |

**Entregavel:** Ambiente reproduzivel onde `import openai` e `import fastapi` funcionam com sucesso.

### Fase 2 — Modulo Compartilhado e Banco de Dados JSON

| Tarefa | Detalhe | Artefato |
|---|---|---|
| 2.1 | Definir modelos Pydantic `MCPRequest` e `MCPResponse` | `shared/mcp_types.py` |
| 2.2 | Implementar modulo `shared/db.py` com helpers de leitura/escrita e 4 handlers de agendamento thread-safe | `shared/db.py` |
| 2.3 | Criar arquivos `db.json` para cada clinica com slots iniciais | `clinic_agents/clinic_*/db.json` (6 arquivos) |
| 2.4 | Validar leitura/escrita do `db.json` com testes manuais | JSON valido apos operacoes de book/cancel |

**Entregavel:** Modulo compartilhado funcional com persistencia JSON e protecao thread-safe.

### Fase 3 — Implementacao dos Servidores MCP (6 Trabalhadores Federados)

| Tarefa | Detalhe | Artefato |
|---|---|---|
| 3.1 | Implementar servidor FastAPI da Clinica A (Cardiologia, porta 8001) com `functools.partial` para vincular handlers ao `db.json` local | `clinic_agents/clinic_a/server.py` |
| 3.2 | Implementar servidor FastAPI da Clinica B (Dermatologia, porta 8002) | `clinic_agents/clinic_b/server.py` |
| 3.3 | Implementar servidor FastAPI da Clinica C (Cardiologia, porta 8003) | `clinic_agents/clinic_c/server.py` |
| 3.4 | Implementar servidor FastAPI da Clinica D (Ortopedia, porta 8004) | `clinic_agents/clinic_d/server.py` |
| 3.5 | Implementar servidor FastAPI da Clinica E (Ortopedia, porta 8005) | `clinic_agents/clinic_e/server.py` |
| 3.6 | Implementar servidor FastAPI da Clinica F (Dermatologia, porta 8006) | `clinic_agents/clinic_f/server.py` |
| 3.7 | Criar script de inicializacao para todos os 6 servidores | `clinic_agents/start_clinics.sh` |
| 3.8 | Validar cada endpoint `/mcp` independentemente via `curl` | Respostas JSON-RPC com payloads `result` corretos |

**Entregavel:** Seis Servidores MCP executando independentemente que aceitam requisicoes JSON-RPC 2.0 e retornam dados especificos do dominio, com persistencia de agendamentos via `db.json`.

**Nota de Interoperabilidade:** Todas as 6 clinicas compartilham o mesmo contrato `MCPRequest`/`MCPResponse` de `shared/mcp_types.py` e os mesmos handlers de agendamento de `shared/db.py`, garantindo interoperabilidade a nivel de protocolo sem acoplar suas implementacoes internas.

**Nota de Uniformidade:** Clinicas da mesma especialidade possuem descricoes e capacidades identicas. A diferenciacao ocorre apenas nos dados: medicos diferentes, horarios diferentes, pacientes diferentes.

### Fase 4 — Logica do Orquestrador (Cliente MCP)

| Tarefa | Detalhe | Artefato |
|---|---|---|
| 4.1 | Implementar `Planner` com system prompt restrito incluindo catalogo de 7 ferramentas, registro de 6 clinicas e Regra 10 (roteamento multi-clinica) | `orchestrator_host/planner.py` |
| 4.2 | Implementar variante Chain-of-Thought do Planner (`decompose_cot`) | `orchestrator_host/planner.py` |
| 4.3 | Implementar `Router` com registro de 6 clinicas e despacho JSON-RPC, incluindo injecao automatica de dados do paciente | `orchestrator_host/router.py` |
| 4.4 | Implementar `Verifier` (Agente Observador) com tres regras de seguranca, excecoes de PII e serializacao JSON adequada | `orchestrator_host/verifier.py` |
| 4.5 | Implementar `RESPONSE_SYSTEM_PROMPT` com Regra 9 (apresentacao multi-clinica com destaque do horario mais proximo) | `orchestrator_host/main.py` |
| 4.6 | Conectar todos os componentes no loop CLI do `main.py` com identificacao do paciente e historico de conversacao | `orchestrator_host/main.py` |
| 4.7 | Validar pipeline completo: consulta → decomposicao → despacho multi-clinica → verificacao → resposta | Teste CLI ponta a ponta |

**Entregavel:** Um Orquestrador funcional que decompoe consultas, roteia para ate 6 clinicas (com roteamento multi-clinica), filtra a saida atraves do Verifier e gera respostas em linguagem natural com comparacao entre clinicas.

**Nota de Desacoplamento:** Cada modulo do Orquestrador (`Planner`, `Router`, `Verifier`) e uma classe independente sem dependencias cruzadas. Eles se comunicam apenas atraves de estruturas de dados Python (`list[dict]`, `MCPResponse`, `VerificationResult`), possibilitando testes unitarios independentes.

### Fase 5 — Testes de Integracao e Logging (Evidencia para o TCC)

| Tarefa | Detalhe | Artefato |
|---|---|---|
| 5.1 | Criar teste de cenario de cancelamento (3 turnos: lista → agenda → cancela) | `tests/test_cancel_scenario.py` |
| 5.2 | Criar teste de cenario de reagendamento (3 turnos: lista → agenda → reagenda) | `tests/test_reschedule_scenario.py` |
| 5.3 | Criar teste unificado dos tres fluxos (4 turnos: lista → agenda → reagenda → cancela + validacoes de serializacao e payload) | `tests/test_three_flows.py` |
| 5.4 | Criar teste de roteamento multi-clinica (2 turnos: lista slots em ambas clinicas de cardiologia → agenda na clinica com horario mais proximo) | `tests/test_multi_clinic_nearest.py` |
| 5.5 | Projetar conjunto de testes com >= 30 consultas (normais, casos extremos, adversariais, multi-clinica) | `tests/test_queries.json` |
| 5.6 | Adicionar logging estruturado (JSON lines) ao Planner, Router e Verifier | `logs/pipeline_YYYYMMDD.jsonl` |
| 5.7 | Executar conjunto de testes completo e capturar logs | Arquivos de log brutos |
| 5.8 | Calcular TSR, TCA, HR, PVR e MCRA a partir dos logs | Tabela resumo de metricas |
| 5.9 | Gerar diagramas Mermaid e capturas de tela para apendice da tese | Evidencia visual |

**Entregavel:** Dados de avaliacao quantitativa e artefatos visuais prontos para inclusao nos capitulos de Metodologia e Resultados do TCC.

---

## Apendice A — Mapa de Arquivos do Projeto

```
tcc-healthcare-agents/
|
+-- .env                              # Credenciais Azure OpenAI (no gitignore)
+-- .env.example                      # Template para novos contribuidores
+-- .gitignore                        # Protege .env, __pycache__ e db.json (producao)
+-- requirements.txt                  # Dependencias Python
|
+-- docs/                             # Documentacao versionada
|   +-- v1.0.0/
|   |   +-- BLUEPRINT_TECNICO.md      # Blueprint PT v1.0.0 (arquivo historico)
|   |   +-- TECHNICAL_BLUEPRINT.md    # Blueprint EN v1.0.0 (arquivo historico)
|   +-- v2.0.0/
|   |   +-- BLUEPRINT_TECNICO.md      # Blueprint PT v2.0.0 (arquivo historico)
|   |   +-- TECHNICAL_BLUEPRINT.md    # Blueprint EN v2.0.0 (arquivo historico)
|   +-- v3.0.0/
|       +-- BLUEPRINT_TECNICO.md      # Blueprint PT v3.0.0 (versao atual)
|
+-- prompts/                          # System prompts (arquivos externos)
|   +-- planner.txt                   # Prompt do Planner (10 regras, 6 clinicas)
|   +-- planner_cot.txt               # Prompt do Planner com Chain-of-Thought
|   +-- verifier.txt                  # Prompt do Verifier (validacao de seguranca)
|   +-- response_generator.txt        # Prompt do Response Generator (9 regras)
|
+-- shared/
|   +-- __init__.py
|   +-- mcp_types.py                  # MCPRequest, MCPResponse (Pydantic)
|   +-- db.py                         # Helpers JSON DB + 4 handlers de agendamento
|
+-- orchestrator_host/                # Cliente MCP — Orquestrador Federado
|   +-- __init__.py
|   +-- main.py                       # Ponto de entrada CLI (Pipeline de 5 etapas)
|   +-- planner.py                    # Decomposicao de Tarefas via Azure OpenAI (+ CoT)
|   +-- router.py                     # Roteamento Dinamico com registro de 6 clinicas
|   +-- verifier.py                   # Agente Observador [Burke et al. 2024]
|
+-- clinic_agents/                    # Servidores MCP — Trabalhadores Federados
|   +-- __init__.py
|   +-- start_clinics.sh              # Script de inicializacao para 6 servidores
|   +-- clinic_a/
|   |   +-- __init__.py
|   |   +-- server.py                 # Silo de Cardiologia (porta 8001, 7 ferramentas)
|   |   +-- db.json                   # Banco de dados de agendamentos — Cardiologia A
|   +-- clinic_b/
|   |   +-- __init__.py
|   |   +-- server.py                 # Silo de Dermatologia (porta 8002, 7 ferramentas)
|   |   +-- db.json                   # Banco de dados de agendamentos — Dermatologia B
|   +-- clinic_c/
|   |   +-- __init__.py
|   |   +-- server.py                 # Silo de Cardiologia (porta 8003, 7 ferramentas)
|   |   +-- db.json                   # Banco de dados de agendamentos — Cardiologia C
|   +-- clinic_d/
|   |   +-- __init__.py
|   |   +-- server.py                 # Silo de Ortopedia (porta 8004, 7 ferramentas)
|   |   +-- db.json                   # Banco de dados de agendamentos — Ortopedia D
|   +-- clinic_e/
|   |   +-- __init__.py
|   |   +-- server.py                 # Silo de Ortopedia (porta 8005, 7 ferramentas)
|   |   +-- db.json                   # Banco de dados de agendamentos — Ortopedia E
|   +-- clinic_f/
|       +-- __init__.py
|       +-- server.py                 # Silo de Dermatologia (porta 8006, 7 ferramentas)
|       +-- db.json                   # Banco de dados de agendamentos — Dermatologia F
|
+-- tests/                            # Testes de integracao
    +-- test_cancel_scenario.py       # Cenario: lista → agenda → cancela
    +-- test_reschedule_scenario.py   # Cenario: lista → agenda → reagenda
    +-- test_three_flows.py           # Cenario unificado dos tres fluxos
    +-- test_multi_clinic_nearest.py  # Cenario: multi-clinica, horario mais proximo
```

## Apendice B — Glossario de Termos

| Termo | Definicao |
|---|---|
| **Aplicacao Parcial** | Tecnica funcional (`functools.partial`) onde uma funcao generica recebe parte de seus argumentos antecipadamente, produzindo uma nova funcao especializada. Usada para vincular `_DB_PATH` e `_SPECIALTY` aos handlers compartilhados de `shared/db.py`. |
| **Banco de Dados JSON** | Arquivo `db.json` local a cada clinica que armazena os dados de agendamento (horarios, disponibilidade, dados do paciente). Lido e gravado pelo modulo `shared/db.py` com protecao thread-safe. |
| **Chain-of-Thought (CoT)** | Tecnica de prompting onde o LLM explicita seu raciocinio passo a passo antes de produzir a saida final, melhorando a qualidade da decomposicao e fornecendo trilha de auditoria. |
| **Desacoplamento** | Principio de design onde componentes interagem atraves de interfaces definidas (MCP) sem conhecimento interno um do outro. |
| **Grafo de Passos** | Uma lista ordenada de operacoes atomicas produzida pelo Planner, cada uma direcionada a uma clinica. Na v3.0.0, pode conter multiplos passos para clinicas diferentes da mesma especialidade. |
| **Handler de Ferramenta** | Uma funcao registrada em um Servidor MCP que executa uma operacao de dominio especifica quando invocada via `tools/call`. |
| **Hub-and-Spoke** | Topologia de rede onde toda comunicacao flui atraves de um hub central (Orquestrador); os spokes (Clinicas) nunca se comunicam diretamente. |
| **Interoperabilidade** | A capacidade de agentes clinicos heterogeneos se comunicarem via um protocolo compartilhado (JSON-RPC 2.0 / MCP). |
| **Minimizacao de Dados** | Transmitir apenas o minimo de dados necessarios para cada operacao (LGPD Art. 6, III). |
| **Multi-Turn** | Interacao conversacional com multiplos turnos onde o contexto de turnos anteriores influencia o processamento do turno atual. |
| **Response Generator** | Capacidade interna do Orquestrador que transforma dados estruturados validados em respostas conversacionais em linguagem natural usando LLM. Na v3.0.0, inclui a Regra 9 para apresentacao consolidada de multiplas clinicas. |
| **Roteamento Multi-Clinica** | Comportamento do Planner (Regra 10) onde consultas a uma especialidade com multiplas clinicas geram um passo de execucao para cada clinica, permitindo comparacao de disponibilidade entre silos federados. |
| **Agente Observador** | Um agente de auditoria independente que valida saidas sem participar de sua geracao (Burke et al. 2024). |
| **Silo de Dados Federado** | Um armazenamento de dados isolado que nao compartilha registros brutos com sistemas externos. Na v3.0.0, cada clinica constitui um silo com dois componentes: banco mock em memoria e `db.json` persistente. |
| **Validacao Deterministica** | Regras de verificacao que produzem resultados consistentes e reproduziveis dada a mesma entrada (temperatura 0.0). |

---

> **Documento gerado para uso academico.**
> Arquitetura: Orquestrador-Trabalhadores Federado Hierarquico com Observador.
> Protocolo: Model Context Protocol (MCP) sobre HTTP / JSON-RPC 2.0.
> Versao: 3.0.0
