<div align="center">

# ZENIC LOGIC v18

### Motor de IA Quirurgico Local — Arquitectura SRP 48 Agentes + Unified DAG

**Servidor OpenAI-Compatible** para Cline, Aide, OpenCode, Open Design y mas.
Funciona en **Android/Termux** sin GPU. IA solo como arbitro binario YES/NO.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Agents](https://img.shields.io/badge/Agents-48%20%7C%209%20Layers-orange.svg)](src/core/agents_v2/)
[![DAG Nodes](https://img.shields.io/badge/DAG_Nodes-59%20%7C%203_Parallel_Groups-critical.svg)](src/core/dag_parts/unified_definition.py)
[![Tests](https://img.shields.io/badge/Tests-381%20passed-brightgreen.svg)](tests/)
[![AI%20Only](https://img.shields.io/badge/AI%20Usage-1%20Agent%20%7C%20Binary%20YES%2FNO-red.svg)](src/core/agents_v2/verdict/verdict_engine.py)
[![Deterministic](https://img.shields.io/badge/Fallback-100%25%20Deterministic-purple.svg)](ARCHITECTURE_V18_SR_DESIGN.md)
[![SharedMemory](https://img.shields.io/badge/Inter--Agent-SharedMemoryBus%20%7C%20SQLite%20WAL-informational.svg)](src/core/shared/shared_memory_bus.py)

</div>

---

## Filosofia

> **Un agente = una funcion. Sin excepciones.**

ZENIC LOGIC v18 es una reestructuracion radical del sistema de agentes siguiendo el Principio de Responsabilidad Unica (SRP). Los 9 agentes monoliticos originales fueron descompuestos en **48 agentes atomicos**, cada uno con exactamente una responsabilidad, un fallback determinista, y proteccion completa con circuit breaker, retry y auditoria. El orquestador unificado (Unified DAG) maneja **59 nodos** con ejecucion paralela via `asyncio.gather()`, comunicacion inter-agente por **SharedMemoryBus** con respaldo SQLite WAL, y cache de ruteo LRU con TTL.

### 6 Invariantes Arquitectonicos

| # | Invariante | Regla |
|---|-----------|-------|
| 1 | **No LLM directo** | Ningun agente llama al LLM directamente. Todo va por VerdictEngine. |
| 2 | **Solo SI/NO** | El LLM solo puede responder YES o NO. Cualquier otra respuesta = NO. |
| 3 | **Fallback determinista** | Cada agente funciona sin IA. El sistema opera 100% sin modelo. |
| 4 | **Sin duplicacion** | Cada funcion existe en exactamente un agente. Duplicar = error de diseno. |
| 5 | **Auditoria total** | Cada llamada y decision tiene registro con evidencia. |
| 6 | **Veto de seguridad** | Si SecurityScanner dice NO, es NO. Sin override posible. |

---

## Arquitectura del Unified DAG Orchestrator

El sistema opera con un **DAG (Directed Acyclic Graph) unificado** que fusiona el DAG v16 con el Pipeline v18 en un solo grafo de **59 nodos** con 3 grupos paralelos, ejecucion condicional por rutas, y retro-compatibilidad total con v16.

```
USER INPUT
    |
    v
+------------------------------------------------------------------+
|  ENTRY: CACHE_CHECK → BILINGUAL_ROUTE → INTENT_CLASSIFY           |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  PHASE 1: UNDERSTAND (100% Determinista)                          |
|                                                                    |
|  [ENTITY_EXTRACT ∥ TARGET_RESOLVE]  ← PARALELO (asyncio.gather)  |
|                     |                                              |
|                     v                                              |
|              CRITICALITY_SCORE                                     |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  PHASE 2: CONTEXT (100% Determinista)                             |
|                                                                    |
|  [MEMORY_COLLECT ∥ SEMANTIC_PREP]  ← PARALELO (asyncio.gather)   |
|                     |                                              |
|                     v                                              |
|  RELEVANCE_SCORE → CONTEXT_COMPRESS → CONTEXT_PREFETCH            |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  ROUTING: AST_ANALYZE → THEOREM_CACHE → ROUTE → ROUTE_DECISION    |
|                                                                    |
|  ROUTE_DECISION → {code | biz | auto | reason | high_crit |       |
|                    visual | abortive}                              |
+------------------------------------------------------------------+
    |
    +-------+--------+-------+--------+
    |       |        |       |        |
    v       v        v       v        v
+--------+ +------+ +-----+ +------+ +--------+
| CODE   | | BIZ  | |AUTO | |REASON| |SOLVER  |
| PATH   | | PATH | |PATH | | PATH | |VERIFY  |
| 6 nodes| |8 nodes| |6 nds| |5 nds | |+Abort. |
+--------+ +------+ +-----+ +------+ +--------+
    |       |        |       |        |
    +-------+--------+-------+--------+
            |
            v
+------------------------------------------------------------------+
|  PHASE 4: VALIDATE (100% Determinista)                             |
|                                                                    |
|  SECURITY_SCAN → SYNTAX_VALIDATE → RISK_CALC → FIX_SUGGEST       |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  PHASE 5: VERDICT (IA Solo Si Necesario)                          |
|                                                                    |
|  EVIDENCE_COLLECT → CONSENSUS_RESOLVE → VERDICT                   |
|                                         |                         |
|                              Consenso ≥ HIGH → Decision (Sin IA)  |
|                              Consenso < HIGH → A43 VerdictEngine  |
|                                                 (Qwen: YES/NO)    |
+------------------------------------------------------------------+
    |
    v
+------------------------------------------------------------------+
|  PHASE 6: SANDBOX → LEDGER_COMMIT/ROLLBACK → THEOREM_SAVE        |
|           → MEMORY_SAVE → DONE                                    |
+------------------------------------------------------------------+
```

### Componentes del Unified DAG

| Componente | Descripcion | Rendimiento |
|-----------|-------------|-------------|
| **UnifiedDAGOrchestrator** | Fusiona DAG v16 + Pipeline v18 en un solo grafo paralelo | 59 nodos, 3 parallel groups |
| **SharedMemoryBus** | Comunicacion inter-agente ultra-rapida con RingBuffer + Mailbox + SharedState | send() < 0.05ms, receive() < 0.05ms |
| **FastConnectionPool** | Pool de conexiones SQLite con thread-local caching y WAL mode | get() < 0.01ms, 10-50x batch speedup |
| **RoutingCache** | LRU cache para decisiones de ruteo TitanAgent (100 entradas, TTL 5 min) | Elimina llamadas LLM redundantes |
| **Per-Node Latency** | Tracking de latencia por nodo (deque, ultimos 100) | Diagnostico de cuellos de botella |

### SharedMemoryBus — Arquitectura Interna

```
                    SharedMemoryBus
  +---------------------------------------------------+
  |                                                    |
  |  +-------------+  +-------------+  +------------+  |
  |  | RingBuffer  |  | AgentMailbox|  | SharedState|  |
  |  | 1024 slots  |  | per-agent   |  | KV + RWLock|  |
  |  | 4KB/slot    |  | priority    |  | TTL + CB   |  |
  |  | zero-copy   |  | heapq O(1)  |  | namespace  |  |
  |  +------+------+  +------+------+  +-----+------+  |
  |         |               |                |          |
  |         +----------+----+----------------+          |
  |                    |                                |
  |          +---------v----------+                     |
  |          | PersistenceLayer  |                     |
  |          | SQLite WAL-mode   |                     |
  |          | Batch 50ms/100ops |                     |
  |          +--------------------+                     |
  |                                                    |
  |          +--------------------+                     |
  |          |   BusMetrics       |                     |
  |          |   Lock-free counts |                     |
  |          +--------------------+                     |
  +---------------------------------------------------+
```

---

## Arquitectura de 9 Capas — 48 Agentes SRP

```
 CAPA 1: UNDERSTANDING          CAPA 2: MEMORY & CONTEXT
 A01 IntentClassifier           A05 MemoryCollector
 A02 EntityExtractor            A06 RelevanceScorer
 A03 TargetResolver             A07 ContextCompressor
 A04 CriticalityScorer          A08 ContextPrefetcher
 A48 BilingualRouter

 CAPA 3: BUSINESS               CAPA 4: CODE OPS
 A09 InvoiceProcessor           A17 CodeGenerator
 A10 InventoryManager           A18 CodeRefactorer
 A11 CRMPipeline                A19 CodeOptimizer
 A12 TaskScheduler              A20 CodeFixer
 A13 ReportGenerator            A21 ProjectScaffolder
 A14 NotificationDispatcher     A22 DefensiveInjector
 A15 DataAnalyzer
 A16 OperationRouter

 CAPA 5: VALIDATION             CAPA 6: AUTOMATION
 A23 SecurityScanner            A29 TriggerInferrer
 A24 SyntaxValidator            A30 ActionInferrer
 A25 ChainValidator             A31 ScheduleParser
 A26 ConfigValidator            A32 ConditionExtractor
 A27 RiskCalculator             A33 AutomationNamer
 A28 FixSuggester               A34 WorkflowSerializer

 CAPA 7: REASONING              CAPA 8: VERDICT (AI Arbiter)
 A35 ProblemDetector            A40 DeterministicPipeline
 A36 StepDecomposer             A41 EvidenceCollector
 A37 TemplateReasoner           A42 ConsensusResolver
 A38 ConfidenceEstimator        A43 VerdictEngine ← UNICO punto con IA
 A39 ConclusionExtractor

 CAPA 9: INFRASTRUCTURE
 A44 AgentRunner
 A45 HealthMonitor
 A46 AuditLogger
 A47 CircuitBreakerManager
```

---

## Registro Completo de Agentes

### Capa 1 — Understanding (Parse & Classify)

| # | Agente | Responsabilidad | Usa IA? |
|---|--------|----------------|---------|
| A01 | `IntentClassifier` | Clasificar intencion en (operacion, goal) | NO |
| A02 | `EntityExtractor` | Extraer entidades nombradas (archivos, lenguajes, funciones) | NO |
| A03 | `TargetResolver` | Resolver archivo/componente objetivo y lenguaje | NO |
| A04 | `CriticalityScorer` | Calcular nivel de criticality (1=FAST, 2=MODERATE, 3=SURGICAL) | NO |
| A48 | `BilingualRouter` | Detectar idioma y rutar a manejadores EN/ES | NO |

### Capa 2 — Memory & Context

| # | Agente | Responsabilidad | Usa IA? |
|---|--------|----------------|---------|
| A05 | `MemoryCollector` | Recolectar entradas de memoria relevantes | NO |
| A06 | `RelevanceScorer` | Puntuar entradas de memoria por relevancia | NO |
| A07 | `ContextCompressor` | Comprimir contexto al presupuesto de tokens | NO |
| A08 | `ContextPrefetcher` | Pre-cargar memorias probablemente necesarias | NO |

### Capa 3 — Business Operations

| # | Agente | Responsabilidad | Usa IA? |
|---|--------|----------------|---------|
| A09 | `InvoiceProcessor` | Procesar calculos y validaciones de facturas | NO |
| A10 | `InventoryManager` | Rastrear niveles de inventario y alertas de stock | NO |
| A11 | `CRMPipeline` | Gestionar etapas del pipeline CRM y conversiones | NO |
| A12 | `TaskScheduler` | Programar y gestionar tareas con prioridad/deadlines | NO |
| A13 | `ReportGenerator` | Generar reportes de negocio desde agregaciones | NO |
| A14 | `NotificationDispatcher` | Enviar notificaciones por canales (email, SMS, push) | NO |
| A15 | `DataAnalyzer` | Realizar analisis estadistico y deteccion de patrones | NO |
| A16 | `OperationRouter` | Rutear operaciones al agente procesador correcto | NO |

### Capa 4 — Code Operations

| # | Agente | Responsabilidad | Usa IA? |
|---|--------|----------------|---------|
| A17 | `CodeGenerator` | Generar codigo desde plantillas y requerimientos | NO |
| A18 | `CodeRefactorer` | Refactorizar/transformar codigo existente | NO |
| A19 | `CodeOptimizer` | Optimizar codigo para rendimiento | NO |
| A20 | `CodeFixer` | Corregir bugs y errores en codigo | NO |
| A21 | `ProjectScaffolder` | Generar scaffolding de proyecto y boilerplate | NO |
| A22 | `DefensiveInjector` | Inyectar patrones de codigo defensivo para criticality F4 | NO |

### Capa 5 — Validation & Security

| # | Agente | Responsabilidad | Usa IA? |
|---|--------|----------------|---------|
| A23 | `SecurityScanner` | Escanear patrones peligrosos (exec, eval, injection) | NO |
| A24 | `SyntaxValidator` | Validar sintaxis de codigo via parsing AST | NO |
| A25 | `ChainValidator` | Validar compatibilidad y completitud de cadenas logicas | NO |
| A26 | `ConfigValidator` | Validar esquemas y valores de configuracion | NO |
| A27 | `RiskCalculator` | Calcular score de riesgo agregado desde validaciones | NO |
| A28 | `FixSuggester` | Sugerir correcciones para problemas de validacion | NO |

### Capa 6 — Automation

| # | Agente | Responsabilidad | Usa IA? |
|---|--------|----------------|---------|
| A29 | `TriggerInferrer` | Inferir tipo de trigger desde descripcion | NO |
| A30 | `ActionInferrer` | Inferir tipo de accion desde descripcion | NO |
| A31 | `ScheduleParser` | Parsear schedule en lenguaje natural a cron/intervalo | NO |
| A32 | `ConditionExtractor` | Extraer logica condicional desde descripcion | NO |
| A33 | `AutomationNamer` | Generar nombre descriptivo para automatizacion | NO |
| A34 | `WorkflowSerializer` | Serializar automatizacion en workflow ejecutable | NO |

### Capa 7 — Reasoning (Deterministic Decomposition)

| # | Agente | Responsabilidad | Usa IA? |
|---|--------|----------------|---------|
| A35 | `ProblemDetector` | Detectar tipo de problema (logico, aritmetico, estructural) | NO |
| A36 | `StepDecomposer` | Descomponer problema en pasos de razonamiento ordenados | NO |
| A37 | `TemplateReasoner` | Aplicar razonamiento basado en plantillas para tipos conocidos | NO |
| A38 | `ConfidenceEstimator` | Estimar confianza en un resultado de razonamiento | NO |
| A39 | `ConclusionExtractor` | Extraer conclusion final desde pasos de razonamiento | NO |

### Capa 8 — Verdict Engine (AI Arbiter)

| # | Agente | Responsabilidad | Usa IA? |
|---|--------|----------------|---------|
| A40 | `DeterministicPipeline` | Ejecutar 7 tareas deterministas sin IA | NO |
| A41 | `EvidenceCollector` | Recolectar evidencia a favor/en contra de una decision | NO |
| A42 | `ConsensusResolver` | Resolver evidencia en consenso o escalar a IA | NO |
| A43 | `VerdictEngine` | Preguntar a Qwen SI/NO (solo en empates) | **SI** (binario) |

### Capa 9 — Infrastructure & Resilience

| # | Agente | Responsabilidad | Usa IA? |
|---|--------|----------------|---------|
| A44 | `AgentRunner` | Ejecutar agentes con circuit breaker + retry + bulkhead | NO |
| A45 | `HealthMonitor` | Rastrear salud de todos los agentes y LLM | NO |
| A46 | `AuditLogger` | Registrar todas las decisiones de agentes | NO |
| A47 | `CircuitBreakerManager` | Gestionar circuit breakers por agente | NO |

---

## Patrones de Resiliencia

Cada agente esta protegido por una combinacion de patrones de resiliencia:

### Circuit Breaker (por agente)

```
CLOSED ──[3 fallos]──> OPEN ──[60s]──> HALF_OPEN ──[2 exitos]──> CLOSED
                              │                     │
                              │    [1 fallo]─────────┘
                              v
                         Fallback inmediato (0ms)
```

- Cuando OPEN: todas las llamadas retornan fallback determinista inmediatamente
- No hay espera, no hay timeouts, no hay desperdicio de recursos
- Logeado como "circuit_open_fallback"

### Retry con Exponential Backoff

```
delay = base_delay x (2.0 ** (attempt - 1))
delay = min(delay, max_delay)
delay += random(0, 0.3 x delay)  # jitter
```

| Config | Valor |
|--------|-------|
| Max attempts | 3 |
| Base delay | 1.0s |
| Max delay | 10.0s |
| Jitter | 0-30% |

### Configuracion por Capa

| Capa | Circuit Breaker | Retry | Bulkhead | Timeout |
|------|:---:|:---:|:---:|:---:|
| A01-A04 | 3f/60s | 3x exp | 4 conc | 5s |
| A05-A08 | 5f/30s | 3x exp | 8 conc | 3s |
| A09-A15 | 3f/60s | 3x exp | 2 conc | 10s |
| A16 | 3f/30s | 2x exp | 4 conc | 2s |
| A17-A22 | 3f/60s | 3x exp | 4 conc | 15s |
| A23-A28 | 5f/30s | 2x exp | 8 conc | 5s |
| A29-A34 | 3f/30s | 3x exp | 4 conc | 3s |
| A35-A39 | 3f/60s | 3x exp | 4 conc | 10s |
| A40-A42 | 5f/30s | 3x exp | 8 conc | 5s |
| **A43** | **3f/60s** | **3x exp** | **1 conc** | **5s** |
| A44 | 5f/30s | 3x exp | 4 conc | 30s |
| A45-A47 | 5f/30s | 2x exp | 2 conc | 3s |
| A48 | 3f/30s | 2x exp | 4 conc | 1s |

---

## Flujo de Veredicto: Ejemplos End-to-End

### Caso: Consenso claro (sin IA)

```
"Crear modulo auth.py con JWT"

A41 EvidenceCollector:
  FOR:  SecurityResult.safe=true (0.9), SyntaxResult.valid=true (0.8)
  AGAINST: (ninguno)

A42 ConsensusResolver:
  score_for = 0.9x1.5 + 0.8x1.2 = 2.31
  score_against = 0
  confidence = CERTAIN (1.0)
  needs_llm = FALSE

RESULTADO: YES (aprobado) — Sin IA necesaria
Tiempo: <30ms (todo determinista)
```

### Caso: Empate (requiere IA)

```
"Permitir este plugin de evaluacion dinamica?"

A41 EvidenceCollector:
  FOR:  SyntaxResult.valid=true (0.8)
  AGAINST: SecurityResult.safe=false: eval() detectado (0.9)

A42 ConsensusResolver:
  score_for = 0.8x1.2 = 0.96
  score_against = 0.9x1.5 = 1.35
  confidence = LOW (|score| < 0.3)
  needs_llm = TRUE

A43 VerdictEngine (3 llamadas a Qwen):
  Intento 1: "NO"
  Intento 2: "NO"
  Mayoria: 2/3 = NO

RESULTADO: NO (rechazado) — eval() bloqueado
Tiempo: ~200ms (2 llamadas LLM)
```

### Caso: IA caida (circuit breaker OPEN)

```
A47 CircuitBreakerManager:
  Breaker para "verdict_engine": OPEN (3 fallos consecutivos)

A43 VerdictEngine:
  Circuit OPEN → Fallback NO inmediato
  No se intenta llamada LLM

RESULTADO: NO (fallback) — Principio de precaucion
Tiempo: 0ms
```

---

## Hardware y Modelo IA

| Parametro | Valor |
|-----------|-------|
| Dispositivo objetivo | Xiaomi Redmi 12R Pro |
| Procesador | MediaTek Dimensity 6100+ |
| RAM | 12GB + 8GB virtual (swap) |
| GPU | No requerida (CPU-only) |
| Modelo IA | Qwen3-0.6B Q4_K_M (378MB) |
| Motor de inferencia | llama-cpp-python |
| Tiempo por inferencia | ~2-5s (CPU) |
| RAM idle (modelos unloaded) | ~50 MB |
| RAM limite del engine | 2 GB (ResourceGovernor) |

---

## Instalacion

### Requisitos

- **Python**: 3.10+
- **RAM**: Minimo 4GB (8GB+ recomendado)
- **Disco**: ~500MB para modelo + dependencias
- **Opcional**: Z3 Solver, fastembed, Textual (TUI)

### Instalacion Rapida

```bash
# Clonar el repositorio
git clone https://github.com/yurislay9-ui/Zenic-Logic-.git
cd Zenic-Logic-

# Instalar dependencias core
pip install -r requirements.txt

# Opcional: Z3 para verificacion formal
pip install z3-solver

# Opcional: Embeddings semanticos
pip install fastembed

# Opcional: Interfaz grafica
pip install textual

# Descargar modelo IA
mkdir -p models
# Colocar qwen3-0.6b-q4_k_m.gguf en models/
```

### Instalacion en Android/Termux

```bash
bash scripts/install_termux.sh

# O manualmente:
pkg install python python-pip
pip install -r requirements.txt
# Z3 no disponible en Termux → AC-3 fallback automatico
```

---

## Uso

### Modo Headless (CLI)

```bash
# Servidor estandar
python main_headless.py --port 5000 --ram-limit 2048

# Servidor FastAPI (SaaS)
python main_headless.py --server fastapi --auth

# Modo daemon (background)
python main_headless.py --daemon
```

### Interfaz Textual (TUI)

```bash
# Instalar Textual (interfaz de terminal interactiva)
pip install textual

# Ejecutar la interfaz TUI
python main.py
```

### API OpenAI-Compatible

```http
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "titan-omniscale-x",
  "messages": [
    {"role": "user", "content": "crear modulo auth.py con JWT"}
  ],
  "temperature": 0.15,
  "max_tokens": 600,
  "stream": false
}
```

---

## API Endpoints

### Core

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/v1/chat/completions` | Chat OpenAI-compatible (SSE streaming soportado) |
| GET | `/v1/models` | Listar modelos disponibles |
| GET | `/health` | Liveness probe (K8s-style) |
| GET | `/ready` | Readiness probe |

### Autenticacion

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/v1/auth/register` | Registro de usuario |
| POST | `/v1/auth/login` | Login → JWT tokens |
| POST | `/v1/auth/refresh` | Renovar access token |
| POST | `/v1/auth/logout` | Logout con blacklisting |
| POST | `/v1/auth/api-keys` | Crear API key |

### Multi-Tenancy

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET/POST | `/v1/tenants` | Listar/crear tenants |
| GET/PATCH/DELETE | `/v1/tenants/{id}` | Gestionar tenant |
| GET | `/v1/tenants/{id}/usage` | Uso y quotas |
| POST | `/v1/tenants/{id}/assign/{user_id}` | Asignar usuario |

**Planes**: Free (10 RPM) / Pro (60 RPM) / Enterprise (200 RPM)

### Generacion & Razonamiento

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| POST | `/v1/generate/app` | Generar aplicacion completa |
| POST | `/v1/generate/automation` | Generar automatizacion |
| POST | `/v1/think` | ThinkingEngine (step_by_step, self_reflect, with_context) |
| POST | `/v1/reason` | Razonamiento avanzado |
| POST | `/v1/chain/validate` | Validar cadena logica |
| POST | `/v1/design/schema` | Disenar esquema de BD |

### Niche & DNA

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/v1/niches` | Listar niches (107 templates, 20 dominios) |
| GET | `/v1/niches/search?q=` | Busqueda multi-senal |
| GET | `/v1/dna/modules` | Logic modules por dominio |
| POST | `/v1/dna/validate` | Validar codigo contra gates |

### Cluster & Observabilidad

| Metodo | Endpoint | Descripcion |
|--------|----------|-------------|
| GET | `/v1/cluster/nodes` | Nodos del cluster |
| POST | `/v1/saga/start` | Iniciar saga workflow |
| GET | `/metrics` | Prometheus metrics |
| GET | `/v1/audit/events` | Query audit events |

---

## Estructura del Proyecto

```
Zenic-Logic-/
├── main.py                          # Interfaz Textual (TUI)
├── main_headless.py                 # Servidor CLI
├── pyproject.toml                   # Configuracion del proyecto
├── requirements.txt                 # Dependencias
├── ARCHITECTURE_V18_SR_DESIGN.md    # Spec de arquitectura V18
├── WORKLOG.md                       # Registro de trabajo
│
├── src/
│   ├── config/                      # Configuracion (YAML + loader)
│   ├── core/
│   │   ├── agents_v2/               # ← 48 Agentes SRP (V18)
│   │   │   ├── understanding/       # Capa 1: A01-A04, A48
│   │   │   ├── memory/              # Capa 2: A05-A08
│   │   │   ├── business/            # Capa 3: A09-A16
│   │   │   ├── code_ops/            # Capa 4: A17-A22
│   │   │   ├── validation/          # Capa 5: A23-A28
│   │   │   ├── automation/          # Capa 6: A29-A34
│   │   │   ├── reasoning/           # Capa 7: A35-A39
│   │   │   ├── verdict/             # Capa 8: A40-A43
│   │   │   ├── infrastructure/      # Capa 9: A44-A47
│   │   │   ├── resilience/          # Patrones: BaseAgent, CB, Health, Audit
│   │   │   ├── schemas/             # Tipos compartidos (single source of truth)
│   │   │   └── pipeline_orchestrator.py  # Orquestador pipeline v18
│   │   │
│   │   ├── dag_parts/               # Unified DAG Orchestrator (59 nodos)
│   │   │   ├── unified_orchestrator.py   # Orquestador unificado v16+v18
│   │   │   ├── unified_definition.py     # Definicion del DAG (59 nodos)
│   │   │   ├── orchestrator.py           # DAGOrchestrator v16
│   │   │   ├── definition.py             # DAG v16 definition
│   │   │   ├── node_executors.py         # Ejecutores de nodos v16
│   │   │   ├── corrections.py            # Bucle de correcciones
│   │   │   └── titan_agent.py            # Meta-router TitanAgent (F1)
│   │   │
│   │   ├── shared/                  # Infraestructura compartida
│   │   │   ├── shared_memory_bus.py      # SharedMemoryBus (RingBuffer + Mailbox + SQLite WAL)
│   │   │   ├── fast_connection_pool.py   # FastPool (thread-local SQLite pool)
│   │   │   ├── z3_parts/                 # Z3 Solver (11 modulos)
│   │   │   ├── symbolic_parts/           # Symbolic Executor (8 modulos)
│   │   │   ├── governor_parts/           # Resource Governor (7 modulos)
│   │   │   ├── sandbox_parts/            # Sandbox Isolation (4 modulos)
│   │   │   ├── constants.py, contracts.py, types.py
│   │   │   ├── db_utils.py, db_initializer.py
│   │   │   ├── retry.py, timeout.py
│   │   │   └── tenant_utils.py, ast_utils.py
│   │   │
│   │   ├── agents/                  # Agentes originales (v17, backward compat)
│   │   ├── memory_parts/            # SmartMemory (6 almacenes)
│   │   ├── semantic_parts/          # SemanticEngine (embeddings)
│   │   ├── reasoning_parts/         # ReasoningEngine original
│   │   ├── mini_ai_parts/           # MiniAIEngine (Qwen3-0.6B)
│   │   ├── template_parts/          # TemplateEngine
│   │   ├── code_gen_parts/          # CodeGenerator original
│   │   ├── auth_parts/              # JWT + RBAC + API keys
│   │   ├── open_design/             # SSE + Artifact Builder
│   │   ├── distributed/             # SAGA + Circuit Breaker distribuido
│   │   ├── tenant/                  # Multi-tenancy
│   │   ├── observability/           # Tracing + Metrics + Health
│   │   ├── patterns/                # Design patterns library (18 modulos)
│   │   └── ...                      # 40+ sub-modulos mas
│   │
│   └── server/                      # FastAPI HTTP server
│       ├── fastapi_app.py
│       ├── server.py
│       ├── auth_middleware.py
│       ├── security_middleware.py
│       └── rate_limiter.py
│
├── tests/
│   ├── unit/
│   │   ├── test_layer5_validation.py     # 78 tests
│   │   ├── test_layer6_automation.py     # 66 tests
│   │   ├── test_layer7_reasoning.py      # 91 tests
│   │   ├── test_layer8_verdict.py        # 84 tests
│   │   ├── test_layer9_infrastructure.py # 62 tests
│   │   └── ...                           # 270+ tests heredados
│   └── integration/
│       └── test_pipeline.py
│
└── deploy/
    ├── docker-compose.yml
    ├── nginx/
    ├── sql/
    └── scripts/
```

---

## Testing

```bash
# Ejecutar tests de agentes V18 (capas 5-9)
pytest tests/unit/test_layer5_validation.py tests/unit/test_layer6_automation.py \
       tests/unit/test_layer7_reasoning.py tests/unit/test_layer8_verdict.py \
       tests/unit/test_layer9_infrastructure.py -v

# Resultado: 381 passed en ~1.0s

# Ejecutar todos los tests
pytest tests/ -v

# Con cobertura
pytest tests/ --cov=src --cov-report=term-missing
```

---

## 3 Capas de IA

El sistema opera con tres capas complementarias de inteligencia artificial:

- **Capa 1 — SemanticEngine (ENTIENDE)**: Motor de embeddings y similitud semantica. TF-IDF + cosine similarity para clasificar intenciones. Con `fastembed` opcional: `paraphrase-multilingual-MiniLM-L12-v2` (384 dimensiones, multilingual EN+ES).

- **Capa 2 — MiniAIEngine (PIENSA)**: Copiloto semantico basado en **Qwen3-0.6B Q4_K_M** (378MB) via `llama-cpp-python`. En v18, solo se usa a traves de A43 VerdictEngine para veredictos binarios SI/NO. Carga lazy via ModelManager: se auto-descarga tras 5 min de inactividad.

- **Capa 3 — SmartMemory (RECUERDA)**: Sistema de memoria inteligente con 6 almacenes: Semantic Cache, Working Memory, Long-term Memory, Episodic Memory, Procedural Memory, Project Memory. Aprende de interacciones exitosas y fallidas.

---

## Patrones de Diseno Implementados

| Categoria | Patrones |
|-----------|----------|
| Resiliencia | Circuit Breaker, Retry + Exponential Backoff, Bulkhead, Timeout |
| Observabilidad | Health Monitor, Audit Logger, Structured Logging |
| Concurrencia | Worker Pool, Producer-Consumer, Read-Write Lock |
| Distribucion | SAGA, Leader Election, Distributed Lock, Cluster Topology |
| Arquitectura | CQRS, Mediator, Event Bus, Command Bus, Strategy, State |
| Creacion | Factory, Builder, Prototype, Singleton |
| Estructural | Facade, Adapter, Bridge, Decorator, Proxy |

---

## Seguridad

- **JWT + RBAC**: Autenticacion con tokens de acceso y renovacion. Jerarquia de roles: `viewer < user < manager < admin`
- **API Keys**: Acceso programatico con keys generadas por usuario
- **Circuit Breaker en Auth**: 5 fallos → 30s recovery, retry con exponential backoff
- **Multi-Tenancy**: Aislamiento por tenant_id en 17+ tablas, purge GDPR
- **Security Veto**: Si SecurityScanner detecta patrones peligrosos (eval, exec, injection), el resultado es NO sin override posible
- **Sandbox Isolation**: Workspaces aislados para pruebas seguras de codigo generado
- **Merkle Ledger**: Arbol criptografico con snapshots y rollback atomico

---

## Open Design Integration

El sistema incluye un bridge completo para Open Design como motor de IA backend:

- **OpenDesignDetector**: Detecta peticiones de Open Design via headers, body, contenido
- **ArtifactBuilder**: Envuelve output en tags `<artifact>` para Open Design
- **SSEStreamer**: Streaming SSE compatible con OpenAI spec
- **Visual Bypass Route**: Ruta rapida que salta el SMT solver y preserva design system prompts

---

## Conectar con Cline/Aide/OpenCode

```json
{
  "apiKey": "your-api-key",
  "baseURL": "http://YOUR_IP:5000/v1",
  "model": "titan-omniscale-x"
}
```

---

## Dependencias

### Core

| Paquete | Version | Uso |
|---------|---------|-----|
| fastapi | >=0.100.0 | Framework web |
| uvicorn | >=0.23.0 | Servidor ASGI |
| pydantic | >=2.0.0 | Validacion de datos |
| aiosqlite | >=0.19.0 | Base de datos async |
| numpy | >=1.24.0 | Calculos numericos |
| python-jose | >=3.3.0 | JWT tokens |
| passlib | >=1.7.4 | Hashing de passwords |

### Opcional

| Paquete | Uso |
|---------|-----|
| z3-solver | Verificacion formal SMT |
| fastembed | Embeddings semanticos densos |
| textual | Interfaz de terminal (TUI) |
| llama-cpp-python | Motor de inferencia Qwen3 |
| stripe | Pagos con Stripe |

---

## Licencia

MIT License — ver [LICENSE](LICENSE) para detalles.

---

<div align="center">

**ZENIC LOGIC v18** — 48 Agentes SRP | Unified DAG 59 Nodos | SharedMemoryBus | Determinista por Diseno | IA Solo como Arbitro

</div>
