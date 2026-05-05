# ZENIC LOGIC — TITAN OMNISCALE X v18

<div align="center">

**Motor de IA Quirúrgico Local — Edición Definitiva**

Servidor OpenAI-Compatible para Cline, Aide, OpenCode, Open Design y más.

Funciona en **Android/Termux** sin GPU.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-2_247%20passed%20%7C%20272%20files-brightgreen.svg)](tests/)
[![Niches](https://img.shields.io/badge/Niches-107%20templates%20%7C%2020%20domains-orange.svg)](src/templates/niches/)
[![Source](https://img.shields.io/badge/Source-710%20files%20%7C%20101K%20lines-blue.svg)](src/)
[![Modularized](https://img.shields.io/badge/Modularized-82%20subdirs%20%7C%20Facade%20pattern-purple.svg)](#modularización-v18--facade-pattern)
[![Patterns](https://img.shields.io/badge/Patterns-26%2B%20implemented-yellow.svg)](#patrones-de-diseño)
[![Docker](https://img.shields.io/badge/Docker-6%20services%20%7C%20Multi--stage-cyan.svg)](#despliegue-docker--vps)
[![Open Design](https://img.shields.io/badge/Open%20Design-SSE%20%2B%20Artifact%20Tags-pink.svg)](#open-design-integration)

</div>

---

## Tabla de Contenidos

- [Visión General](#visión-general)
- [Arquitectura del Sistema](#arquitectura-del-sistema)
  - [Pipeline de 8 Niveles](#pipeline-de-8-niveles)
  - [3 Capas de IA](#3-capas-de-ia)
  - [9 Agentes IA (Framework de Agentes)](#9-agentes-ia-framework-de-agentes)
  - [5 Iniciativas Unificadas (F1-F5)](#5-iniciativas-unificadas-f1f5)
  - [DAG Dinámico — 18 Nodos](#dag-dinámico--18-nodos)
  - [Infraestructura Permanente](#infraestructura-permanente)
- [Hardware y Modelo IA](#hardware-y-modelo-ia)
- [Instalación](#instalación)
  - [Requisitos](#requisitos)
  - [Instalación Rápida](#instalación-rápida)
  - [Instalación en Android/Termux](#instalación-en-androidtermux)
- [Uso](#uso)
  - [Interfaz Kivy (GUI)](#interfaz-kivy-gui)
  - [Modo Headless (CLI)](#modo-headless-cli)
  - [Servidor HTTP](#servidor-http)
- [API Endpoints](#api-endpoints)
  - [Chat Completions (OpenAI-Compatible)](#chat-completions-openai-compatible)
  - [Autenticación y Autorización](#autenticación-y-autorización)
  - [Multi-Tenancy](#multi-tenancy)
  - [Generación de Apps](#generación-de-apps)
  - [Automatizaciones](#automatizaciones)
  - [Razonamiento](#razonamiento)
  - [Niche Templates](#niche-templates)
  - [DNA Validation System](#dna-validation-system)
  - [Sistema Endpoints (v17)](#sistema-endpoints-v17)
  - [Cluster y Orquestación Distribuida](#cluster-y-orquestación-distribuida)
  - [Observabilidad](#observabilidad)
- [Open Design Integration](#open-design-integration)
- [Modularización v18 — Facade Pattern](#modularización-v18--facade-pattern)
- [3 Mejoras de Nivel Dios (v17)](#3-mejoras-de-nivel-dios-v17)
- [Patrones de Diseño](#patrones-de-diseño)
- [Sistema de Niches Declarativos](#sistema-de-niches-declarativos)
- [Sistema DNA (Master Templates)](#sistema-dna-master-templates)
- [Model Manager (Lazy Loading)](#model-manager-lazy-loading)
- [Fractal Generator (Multi-File)](#fractal-generator-multi-file)
- [Motor SMT (Z3 / AC-3)](#motor-smt-z3--ac-3)
- [Sistema de Memoria Inteligente](#sistema-de-memoria-inteligente)
- [Motor Semántico](#motor-semántico)
- [Resource Governor (ARM/RAM)](#resource-governor-armram)
- [Despliegue Docker + VPS](#despliegue-docker--vps)
- [Seguridad](#seguridad)
- [Conectar con Cline/Aide/OpenCode/Open Design](#conectar-con-clineaideopencodeopen-design)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [Testing](#testing)
- [Dependencias](#dependencias)
- [Licencia](#licencia)

---

## Visión General

**ZENIC LOGIC** es un motor de IA local diseñado para operar en hardware de consumo sin GPU. Combina verificación formal matemática (SMT Solvers) con un sistema de agentes IA basado en **Qwen3-0.6B** (378MB, cuantización Q4_K_M), creando una plataforma de razonamiento quirúrgico que prioriza los recursos computacionales donde más se necesitan.

### Filosofía: "Bloques LEGO + Ensamblador IA"

El proyecto funciona como un sistema de bloques LEGO donde la **infraestructura** (Z3 Solver, AC-3, Sandbox, Auth, Merkle Ledger, etc.) permanece sólida e inmutable, mientras que la **lógica de negocio** (clasificación de intenciones, razonamiento, generación de código, validación) es reemplazada progresivamente por agentes IA. Cada agente tiene un **fallback determinista** que garantiza funcionamiento sin LLM.

### Capacidades Clave

| Capacidad | Implementación |
|-----------|---------------|
| **Verificación Formal** | Z3 SMT Solver (con fallback AC-3 para Android) |
| **Razonamiento Probabilístico** | MCTS real con UCB1, 4 fases, depth limit 5 |
| **Ejecución Simbólica** | Estados simbólicos, path conditions, detección de violaciones |
| **9 Agentes IA** | 9 agentes con Qwen3-0.6B + fallback determinista |
| **DAG Dinámico (F1)** | Orquestador basado en grafo acíclico de 18 nodos con TitanAgent meta-router |
| **Ruteo Quirúrgico (F2)** | Fusión multi-señal: Memory + Semantic + LLM + TF-IDF |
| **Contexto Inteligente (F3)** | Compresión adaptativa + presupuesto de tokens + deduplicación |
| **Criticalidad Dinámica (F4)** | Fusión ponderada 5-señal con retroalimentación histórica |
| **Validación (F5)** | Swarm secuencial de revisión + loop de corrección (max 3 ciclos) |
| **107 Niches Declarativos** | 20 dominios, 793 entidades, 8,453 campos en YAML templates |
| **Modularización v18** | 82 sub-directorios, 464 sub-módulos, 0 archivos >400 líneas |
| **26+ Patrones de Diseño** | SAGA, Circuit Breaker, EventBus, CommandBus, CQRS, Mediator, etc. |
| **Multi-Tenancy SaaS** | 3 planes (Free/Pro/Enterprise), aislamiento por tenant_id, GDPR purge |
| **Open Design Integration** | SSE streaming, `<artifact>` tags, visual bypass, CORS |
| **Auto-Evolución (v17)** | GitHub Scrap + Cron + auto-update de niches |
| **Context Pointers (v17)** | Vector Signature Index + almacenamiento en disco |
| **Low-Power Mode (v17)** | Monitoreo hardware térmico/batería → DAG paralelo/secuencial adaptativo |
| **DNA Validation (v17)** | 4 Master Templates: logic_modules + domain_rules + validation_gates + glossary |
| **Lazy Model Loading (v17)** | ModelManager: carga bajo demanda + auto-unload + RAM Budget |
| **Fractal Generator (v17)** | Generación multi-archivo en 3 fases dentro del límite de 600 tokens |
| **API OpenAI-Compatible** | `/v1/chat/completions` con SSE streaming |
| **Orquestación Distribuida** | SAGA coordinator, distributed circuit breaker, task queue, leader election |
| **Observabilidad** | OpenTelemetry tracing, Prometheus metrics, audit logging, health checks |
| **Despliegue Docker** | Multi-stage Dockerfile, 6-service docker-compose, nginx, SSL, backups |

---

## Arquitectura del Sistema

```
+-------------------------------------------------------------------+
|                    API OpenAI-Compatible                           |
|   /v1/chat/completions  /v1/models  /health  /v1/niches          |
|   /v1/generate/*  /v1/dna/*  /v1/system/*  /v1/auth/*           |
|   /v1/tenants/*  /v1/cluster/*  /v1/saga/*  /v1/audit/*         |
+-------------------------------------------------------------------+
|                  DAG ORCHESTRATOR (F1)                             |
|     Grafo acíclico de 18 nodos con TitanAgent como meta-router   |
|     + ContextPointerEngine + LowPowerSequentialMode              |
|     + OpenDesignDetector + Visual Bypass Route                   |
|                                                                   |
|  CACHE_CHECK -> INTENT -> CONTEXT_PREPARE -> AST_ANALYZE ->      |
|  THEOREM_CACHE -> ROUTE -> CRITICALITY_ROUTE -> PLAN ->          |
|  [SOLVER_VERIFY] -> EXECUTE_STEPS -> VALIDATE -> SANDBOX ->     |
|  LEDGER_COMMIT/ROLLBACK -> THEOREM_SAVE -> MEMORY_SAVE -> DONE   |
|                                                                   |
|  VISUAL_BYPASS -> MEMORY_SAVE -> DONE  (Open Design fast path)   |
+---------------------------+---------------------------------------+
|   9 AGENTES IA            |         PIPELINE DE 8 NIVELES        |
|                           |                                       |
|  TitanAgent (F1) ---------|--> DAG Transitions + Criticality     |
|  SurgicalAgent (F2) ------|--> L1 SemanticParser (multi-signal)  |
|  ContextAgent (F3) -------|--> Context Compression + Token Budget|
|  CriticalityAgent (F4) ---|--> L2 MacroRouter (5-signal fusion)  |
|  ValidationAgent (F5) ----|--> Sequential Review Swarm            |
|  ReasoningAgent ----------|--> L3 GraphAST Engine                |
|  BusinessLogicAgent ------|--> L4 APA Planner (Z3+MCTS)         |
|  CodeAgent ---------------|--> L5 Structural Swarm               |
|  AutomationAgent ---------|--> L6 Reflexion Sandbox              |
|                           |--> L7 Merkle Ledger                  |
|  AgentRunner <----------- |--> L8 Theorem Cache                  |
|  (LLM Bridge + Fallback)  |                                       |
+---------------------------+---------------------------------------+
|                    3 CAPAS DE IA                                   |
|  Capa 1: SemanticEngine -> ENTIENDE (embeddings, similitud)      |
|  Capa 2: MiniAIEngine (Qwen3) -> PIENSA (razonamiento)          |
|  Capa 3: SmartMemory -> RECUERDA (cache, contexto, aprendizaje)  |
+-------------------------------------------------------------------+
|              v17: MEJORAS DE NIVEL DIOS                           |
|  NicheLoader (107 YAML) | DNALoader (4 Master Templates)        |
|  NicheAutoScraper + Cron | ContextPointerEngine (Vector Index)    |
|  LowPowerSequentialMode  | ModelManager (Lazy Load + Auto-Unload)|
|  FractalGenerator (3-phase)                                      |
+-------------------------------------------------------------------+
|              v18: OPEN DESIGN BRIDGE                              |
|  OpenDesignDetector | ArtifactBuilder | SSEStreamer               |
|  Visual Bypass Route | Design System Context Preservation        |
+-------------------------------------------------------------------+
|           PATRONES DE DISEÑO (26+)                                |
|  SAGA | Circuit Breaker | EventBus | CommandBus | Mediator       |
|  CQRS | Factory | Builder | Strategy | State | Visitor           |
|  Retry | Bulkhead | Proxy | Decorator | Adapter | Bridge         |
|  Worker Pool | Producer-Consumer | Read-Write Lock | Leader      |
|  Election | Distributed Lock | Cluster Topology                  |
+-------------------------------------------------------------------+
|              MULTITENANCY SaaS                                    |
|  TenantContext | FeatureGate | TenantIsolation | Rate Limiting   |
|  Plans: Free / Pro / Enterprise | GDPR Purge | Usage Tracking   |
+-------------------------------------------------------------------+
|           ORQUESTACIÓN DISTRIBUIDA                                |
|  DistributedSAGACoordinator | DistributedCircuitBreaker          |
|  DistributedTaskQueue | LeaderElection | DistributedLockManager  |
|  ClusterTopology | Worker | PostgreSQL/Memory Backend            |
+-------------------------------------------------------------------+
|           OBSERVABILIDAD                                          |
|  OpenTelemetry Tracing | Prometheus Metrics | Audit Logger       |
|  HealthAggregator (K8s-style probes)                             |
+-------------------------------------------------------------------+
|                  INFRAESTRUCTURA PERMANENTE                       |
|  Z3 Solver | AC-3 | Sandbox | Auth JWT/RBAC | ActionExecutor    |
|  Merkle Ledger | Theorem Cache | Resource Governor | MCTS        |
|  Symbolic Executor | K-Path Analyzer | Constraint Solver         |
+-------------------------------------------------------------------+
```

### Pipeline de 8 Niveles

| Nivel | Componente | Implementación | Archivo |
|-------|-----------|---------------|---------|
| L1 | Semantic Parser | TF-IDF + Cosine Similarity + SurgicalAgent (F2) | `level1_semantic_engine/parser.py` |
| L2 | Macro Router MoE | CriticalityAgent (F4) + firmas topológicas del AST | `level2_macro_router/router.py` |
| L3 | Graph AST Engine | AST nativo (Python) + regex (multi-lenguaje) + SQLite | `level3_graph_ast/engine.py` |
| L4 | APA Planner | Z3 SMT Solver (con fallback AC-3) + MCTS real | `level4_apa_planner/planner.py` |
| L5 | Structural Swarm | AST Surgeon + GitHub Scrap Agent (multi-source) | `level5_structural_swarm/` |
| L6 | Reflexion Sandbox | Ejecución Simbólica Acotada + K-Path Limiting + Path Pruning | `level6_reflexion_sandbox/` |
| L7 | Merkle Ledger | Árbol Merkle + snapshots + rollback atómico | `level7_merkle_ledger/ledger.py` |
| L8 | Theorem Cache | Skeleton Hash (destilación topológica) + lookup O(1) | `level8_theorem_cache/cache.py` |

### 3 Capas de IA

El sistema opera con tres capas complementares de inteligencia artificial que trabajan en conjunto para proporcionar comprensión, razonamiento y memoria persistente:

- **Capa 1 — SemanticEngine (ENTIENDE)**: Motor de embeddings y similitud semántica. Utiliza TF-IDF + cosine similarity para clasificar intenciones y encontrar patrones. Con `fastembed` opcional, utiliza `paraphrase-multilingual-MiniLM-L12-v2` para embeddings densos de 384 dimensiones con soporte multilingual (inglés + español). Carga automática si los embeddings están disponibles, con fallback a TF-IDF puro. Soporta clasificación zero-shot con 8 operaciones (CREATE, REFACTOR, DELETE, SEARCH, ANALYZE, EXPLAIN, DEBUG, OPTIMIZE) y 7 goals (BUG_FIX, FEATURE_ADD, SECURITY_HARDEN, PERFORMANCE, MODERN_PATTERN, COMPLEXITY_REDUCTION, READABILITY).

- **Capa 2 — MiniAIEngine (PIENSA)**: Copiloto semántico basado en **Qwen3-0.6B Q4_K_M** (378MB) vía `llama-cpp-python`. Ejecuta 7 tareas bounded: clasificación de intención, sugerencia de patrones, explicación de violaciones, mejora de explicaciones, inferencia de entidades, generación contextual, y razonamiento por pasos. Funciona en CPU sin GPU con ~2-5 segundos por inferencia. Carga lazy vía **ModelManager** (v17): solo se carga en la primera petición, se auto-descarga tras 5 min de inactividad, reduciendo RAM idle de ~730 MB a ~50 MB.

- **Capa 3 — SmartMemory (RECUERDA)**: Sistema de memoria inteligente con seis almacenes: **Semantic Cache** (matching SHA-256 + embeddings con threshold 0.85), **Working Memory** (contexto inmediato, max 20 entries, 500 tokens), **Long-term Memory** (proyectos y soluciones persistentes, max 500 entries, similarity search con cosine >= 0.5), **Episodic Memory** (eventos con embeddings, max 200 entries), **Procedural Memory** (patrones aprendidos con success rate, max 100 entries), y **Project Memory** (continuidad entre sesiones, max 50 entries). Aprende de interacciones exitosas y fallidas, calculando importancia dinámica. Soporta consolidación automática (working → long-term) y purge GDPR por tenant.

### 9 Agentes IA (Framework de Agentes)

El framework de agentes reemplaza la lógica de negocio hardcodeada con agentes IA que siguen un patrón consistente: cada agente intenta primero usar el LLM (vía AgentRunner), y si falla o no está disponible, ejecuta un fallback determinista garantizado. Todos los agentes heredan de `BaseAgent(ABC)` con contrato `build_prompt()`, `parse_response()`, `fallback()`.

| Agente | Iniciativa | Fallback Determinista | Cableado |
|--------|-----------|----------------------|----------|
| **TitanAgent** | F1 | Tablas estáticas de transición DAG | DAG transitions |
| **SurgicalAgent** | F2 | TF-IDF + keyword matching + semantic prototypes | F1→F3→F4 |
| **ContextAgent** | F3 | TF-IDF compression + importance-based selection | F2→F4→downstream |
| **CriticalityAgent** | F4 | 5-signal weighted fusion (keyword 30%, baseline 25%, router 20%, memory 15%, history 10%) | F1→F2→F3→agents |
| **ValidationAgent** | F5 | Static code analysis + AST pattern matching | F4 adjustments → correction loop |
| **ReasoningAgent** | — | Step-by-step template reasoning | F3 context |
| **BusinessLogicAgent** | — | 30+ LogicBlocks (invoice, inventory, CRM, etc.) | F4 adjustments |
| **CodeAgent** | — | Pattern-based scaffolding + language templates | F4 adjustments + defensive injection |
| **AutomationAgent** | — | Keyword inference for triggers/actions | F4 adjustments |

**AgentRunner**: Orquesta LLM call → parse → cache → fallback. Cada agente rastrea estadísticas: call_count, llm_success, fallback_count, cache_hits, avg_duration_ms.

### 5 Iniciativas Unificadas (F1-F5)

| Iniciativa | Nombre | Agente Core | Estado | Cableado |
|-----------|--------|-------------|--------|----------|
| **F1** | TitanOrchestrator DAG Dinámico | TitanAgent + DAGOrchestrator | Completado | Backbone del pipeline |
| **F2** | SurgicalAgent / IntentAgent | SurgicalAgent | Completado | F1 DAG → F3 context → F4 criticality |
| **F3** | ContextAgent / ReasoningAgent | ContextAgent + ReasoningAgent | Completado | F2 intent → F4 budget → agents downstream |
| **F4** | Dynamic Criticality Router | CriticalityAgent | Completado | F1 path + F2 signals + F3 budget + agents |
| **F5** | ValidationAgent + Correction Loop | ValidationAgent + AnalysisUtils | Completado | F4 adjustments → max 3 correction loops |

### DAG Dinámico — 18 Nodos

El `PIPELINE_DAG` define **18 nodos** formando un grafo acíclico dirigido con transiciones condicionales:

```
CACHE_CHECK --[hit]--> DONE
    |__[miss]--> INTENT --> CONTEXT_PREPARE --> AST_ANALYZE --> THEOREM_CACHE
                                                                    |
                                                        [hit]--> DONE
                                                        [miss]--> ROUTE --> CRITICALITY_ROUTE --> PLAN
                                                                                               |
                                               +------------------+------------------+------------------+
                                               |                  |                  |                  |
                                         [abortive]         [low_crit]         [standard]         [high_crit]
                                               |                  |                  |                  |
                                               v                  v                  v                  v
                                          ABORTIVE         EXECUTE_STEPS      SOLVER_VERIFY
                                               |                  |                  |
                                               |                  |          [pass]--> EXECUTE_STEPS
                                               |                  |          [fail]--> ABORTIVE
                                               |                  v
                                               |             VALIDATE (F5, max 3 loops)
                                               |              |    [clean]--> SANDBOX
                                               |              |    [issues]--> EXECUTE_STEPS
                                               |              v
                                               |             SANDBOX
                                               |              |
                                               |     +--------+----------+
                                               |     |        |          |
                                               |  [PASS]  [FAIL_K_PATH] [FAIL]
                                               |     |        |          |
                                               |     v        v          v
                                               |  LEDGER   PARTIAL    LEDGER
                                               |  COMMIT   REASONING  ROLLBACK
                                               |     |                  |
                                               |     v                  |
                                               |  THEOREM_SAVE         |
                                               |     |                 |
                                               |     v                 |
                                               |  MEMORY_SAVE         |
                                               |     |                 |
                                               |     v                 v
                                               |    DONE             DONE
                                               |
                                               v
                                              DONE

VISUAL_BYPASS --[success]--> MEMORY_SAVE --> DONE   (Open Design fast path)
      |__[fallback]--> EXECUTE_STEPS
```

**Propiedades clave del DAG:**
- Protección anti-ciclo: contador de iteración por nodo contra `max_retries`
- Transiciones condicionales: PLAN ramifica por nivel de criticalidad
- TitanAgent (F1) resuelve transiciones no-triviales usando LLM con fallback a tablas estáticas
- Máximo 20 pasos totales por ejecución del pipeline
- Visual Bypass: ruta rápida para peticiones de Open Design que salta SMT solver

### Infraestructura Permanente

Los siguientes módulos **permanecen intactos** — son los cimientos sobre los que operan los agentes:

| Módulo | Archivo | Rol |
|--------|---------|-----|
| Z3 Solver | `shared/z3_solver.py` → `shared/z3_parts/` | Verificación formal SMT con null-safety, type-safety, invariantes |
| Symbolic Executor | `shared/symbolic_executor.py` → `shared/symbolic_parts/` | Ejecución simbólica acotada con path pruning |
| Sandbox Isolation | `shared/sandbox_isolation.py` → `shared/sandbox_parts/` | Workspaces aislados para pruebas seguras |
| Resource Governor | `shared/resource_governor.py` → `shared/governor_parts/` | Límites de CPU/RAM/tiempo/thermal |
| MCTS | `shared/mcts.py` | Monte Carlo Tree Search con UCB1 (50 sims ARM, 100 desktop) |
| K-Path Analyzer | `shared/kpath_analyzer.py` | Análisis de dependencias en grafo (radio 10) |
| Constraint Solver | `shared/constraint_solver.py` | Solver CSP con AC-3 + backtracking + MRV heuristic |
| Auth Service | `auth_service.py` → `auth_parts/` | JWT + RBAC + API keys + refresh tokens + rate limiting |
| Action Executor | `action_executor.py` → `executors/` | 9 tipos de acción real (HTTP, webhook, DB, file, email, etc.) |
| Merkle Ledger | `level7_merkle_ledger/` | Árbol Merkle criptográfico + snapshots + rollback atómico |
| Theorem Cache | `level8_theorem_cache/` | Skeleton Hash O(1) + LRU eviction (500 entries/tenant) |

---

## Hardware y Modelo IA

ZENIC LOGIC está diseñado para funcionar en hardware de consumo sin GPU:

| Parámetro | Valor |
|-----------|-------|
| **Dispositivo objetivo** | Xiaomi Redmi 12R Pro |
| **Procesador** | MediaTek Dimensity 6100+ |
| **RAM** | 12GB + 8GB virtual (swap) |
| **GPU** | No requerida (CPU-only) |
| **Modelo IA** | Qwen3-0.6B Q4_K_M |
| **Tamaño del modelo** | 378 MB |
| **Motor de inferencia** | llama-cpp-python |
| **Tiempo por inferencia** | ~2-5 segundos (CPU) |
| **RAM del modelo** | ~500 MB en runtime |
| **Token limit por agente** | 600 tokens máx por llamada |
| **RAM idle (v17)** | ~50 MB (ambos modelos unloaded) |
| **RAM límite del engine** | 2 GB (ResourceGovernor) |
| **CPU límite** | 70% (30% para OS) |
| **GC threshold** | 1.5 GB → forced gc.collect(2) |

El modelo Qwen3-0.6B es lo suficientemente pequeño para ejecutarse en CPU móvil, pero suficientemente capaz para las tareas bounded de los agentes. Con el **ModelManager** (v17), los modelos se cargan lazy y se auto-descargan tras 5 minutos de inactividad, reduciendo RAM idle de ~730 MB a ~50 MB. El **ResourceGovernor** impone límites estrictos: 2GB RAM max, 70% CPU max, thermal throttling automático, y GC tuning específico para ARM (`gc.set_threshold(1000, 15, 15)`).

---

## Instalación

### Requisitos

- **Python**: 3.10 o superior
- **RAM**: Mínimo 4GB (8GB+ recomendado)
- **Disco**: ~500MB para modelo + dependencias
- **Opcional**: Z3 Solver para verificación formal completa
- **Opcional**: fastembed para embeddings semánticos densos

### Instalación Rápida

```bash
# Clonar el repositorio
git clone https://github.com/yurislay9-ui/Zenic-Logic-.git
cd Zenic-Logic-

# Instalar dependencias core
pip install -r requirements.txt

# Opcional: instalar Z3 para verificación formal completa
pip install z3-solver

# Opcional: instalar Kivy para interfaz gráfica
pip install kivy

# Opcional: instalar embeddings semánticos
pip install fastembed

# Descargar modelo IA (Qwen3-0.6B Q4_K_M)
mkdir -p models
# Colocar qwen3-0.6b-q4_k_m.gguf en models/
```

### Instalación en Android/Termux

```bash
# Ejecutar script de instalación automática
bash scripts/install_termux.sh

# O manualmente:
pkg install python python-pip
pip install -r requirements.txt
# Nota: Z3 no está disponible en Termux, se usa AC-3 fallback automáticamente
```

El script `install_termux.sh` instala `proot-distro` con Debian ARM, Python3, Z3 solver (si disponible), y crea un comando alias `titan` que lanza el servidor headless en puerto 5000 con RAM limit de 2048MB.

---

## Uso

### Interfaz Kivy (GUI)

```bash
python main.py
```

La interfaz Kivy proporciona un layout vertical con:
- **Title Label** — Muestra versión + solver activo (Z3 o AC-3)
- **IP Label** — URL de conexión para Cline/Aide
- **Status Label** — Estado del engine (Running/Stopped/Error)
- **Start/Stop Button** — Toggle del servidor HTTP
- **Input Field** — Campo de prueba local
- **Log ScrollView** — Log en tiempo real (200 line buffer)

El servidor corre en un `threading.Thread(daemon=True)` junto al event loop de Kivy. Actualizaciones UI seguras vía `Clock.schedule_once()`.

### Modo Headless (CLI)

```bash
# Servidor estándar (stdlib)
python main_headless.py --port 5000 --ram-limit 2048

# Servidor FastAPI (SaaS)
python main_headless.py --server fastapi --auth

# Modo daemon (background)
python main_headless.py --daemon

# Comandos interactivos: status / models / quit
```

El modo headless aplica optimizaciones ARM al inicio: `tune_gc_for_arm()`, `set_process_priority_low()`, `limit_open_files(256)`. No requiere Kivy.

### Servidor HTTP

El servidor HTTP se inicia automáticamente, escuchando en `0.0.0.0:5000`. Dos modos disponibles:

| Modo | Comando | Uso |
|------|---------|-----|
| **stdlib** | `--server stdlib` | Ligero, compatible ARM/Termux, sin dependencias externas |
| **FastAPI** | `--server fastapi` | Full SaaS: auth, tenants, distributed, observability |

---

## API Endpoints

### Chat Completions (OpenAI-Compatible)

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

**SSE Streaming** (para Open Design y clientes que lo soporten):

```http
POST /v1/chat/completions
Content-Type: application/json

{
  "model": "titan-omniscale-x",
  "messages": [
    {"role": "user", "content": "diseñar dashboard de ventas"}
  ],
  "stream": true
}
```

Respuesta SSE con formato OpenAI spec: `data: {"choices":[{"delta":{"content":"..."}}]}`

**Respuesta estándar** (formato OpenAI-compatible):

```json
{
  "id": "zenith-logic-001",
  "object": "chat.completion",
  "model": "zenith-v17-semantic-surgical",
  "choices": [{
    "index": 0,
    "message": {
      "role": "assistant",
      "content": "Análisis completado..."
    },
    "finish_reason": "stop"
  }],
  "usage": {
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0
  }
}
```

En caso de timeout del solver o límite de K-Paths, el sistema devuelve **Razonamiento Parcial** con `tool_calls` que describen la subdivisión automática de la tarea (AbortiveProtocol).

### Autenticación y Autorización

```http
POST /v1/auth/register    # Registro de usuario (role forzado a 'user')
POST /v1/auth/login       # Login → JWT access + refresh tokens
POST /v1/auth/refresh     # Renovar access token
POST /v1/auth/logout      # Logout con token blacklisting
GET  /v1/auth/me          # Info del usuario actual
POST /v1/auth/api-keys    # Crear API key
GET  /v1/auth/api-keys    # Listar API keys del usuario
```

**Métodos de autenticación**:
- JWT Bearer Token (`Authorization: Bearer <token>`) — primario
- API Key (`X-API-Key: <key>`) — acceso programático

**Jerarquía de roles**: `viewer < user < manager < admin`

**Resiliencia**: Circuit breaker en auth DB (5 failures → 30s recovery), retry con exponential backoff (3 intentos, 0.2s-2s jitter).

### Multi-Tenancy

```http
GET    /v1/tenants                        # Listar tenants (manager+)
POST   /v1/tenants                        # Crear tenant (admin)
GET    /v1/tenants/{tenant_id}            # Detalles + quotas
PATCH  /v1/tenants/{tenant_id}            # Actualizar plan/nombre
DELETE /v1/tenants/{tenant_id}            # GDPR deprovision (purge total)
POST   /v1/tenants/{tenant_id}/assign/{user_id}  # Asignar usuario
GET    /v1/tenants/{tenant_id}/usage      # Usage + quota + storage
GET    /v1/tenants/{tenant_id}/features   # Features del plan
```

**Planes SaaS**:

| Feature | Free | Pro | Enterprise |
|---------|------|-----|-----------|
| RPM | 10 | 60 | 200 |
| Daily Requests | 500 | 5,000 | 50,000 |
| Daily Tokens | 50K | 500K | 5M |
| Concurrent | 2 | 10 | 50 |
| Storage | 50 MB | 500 MB | 5 GB |
| Features | basic_pipeline, chat_completions | + app_generation, automation, schema, think, reason, chains | ALL |

**Aislamiento**: Row-level por `tenant_id` en 17+ tablas, auto-inyección `WHERE tenant_id = ?` vía `TenantIsolation.scoped_query()`, migración automática de columnas, purge GDPR completo.

**Usuarios anónimos**: `TenantContext.anonymous()` con 5 RPM, 100 RPD, 1 concurrent, 10MB storage.

### Generación de Apps

```http
POST /v1/generate/app
Content-Type: application/json

{
  "request": "sistema de facturación con impuestos y descuentos",
  "project_name": "billing_system",
  "output_dir": "./output"
}
```

**Templates disponibles**: `auth_system`, `base`, `crm`, `crud_dashboard`, `inventory`, `invoice_billing`, `task_manager`, `web_api`

Feature gate: `app_generation` (requiere plan Pro+)

### Automatizaciones

```http
POST /v1/generate/automation
Content-Type: application/json

{
  "description": "enviar reporte diario por email cada lunes a las 9am"
}
```

**Tipos de trigger**: manual, schedule, event, webhook
**Tipos de acción**: email, HTTP, database, file, webhook, notification, transform, schedule
**Templates**: `base`, `data_sync`, `email_sender`, `notification_dispatcher`, `scheduled_report`, `webhook_handler`

Feature gate: `automation_generation` (requiere plan Pro+)

### Razonamiento

```http
POST /v1/think          # ThinkingEngine (modos: step_by_step, self_reflect, with_context)
POST /v1/reason         # Advanced reasoning (Phase 8)
POST /v1/chain/validate # Validar cadena lógica
POST /v1/chain/execute  # Ejecutar cadena con rollback/recovery
POST /v1/design/schema  # Diseñar esquema de BD (SQL/Python)
```

Feature gates: `thinking_engine`, `reasoning_engine`, `logic_chains`, `schema_design` (requieren plan Pro+)

### Niche Templates

```http
GET  /v1/niches                 # Listar todos los niches
GET  /v1/niches?domain=health   # Filtrar por dominio
GET  /v1/niches/domains         # Dominios con conteo
GET  /v1/niches/search?q=pharmacy  # Búsqueda multi-signal
POST /v1/generate/niche         # Generar app desde niche
```

### DNA Validation System

```http
GET  /v1/dna/modules?domain=finance     # Logic modules por dominio
GET  /v1/dna/modules?q=invoice          # Búsqueda de modules
GET  /v1/dna/domain-rules?industry=healthcare  # Reglas de negocio
POST /v1/dna/validate                   # Validar código contra gates
POST /v1/dna/polish                     # Pulir texto técnico a corporativo
```

4 Master Templates: `logic_modules.yaml` (68 módulos), `domain_expert_rules.yaml` (20 reglas), `validation_gates.yaml` (121 gates), `professional_glossary.yaml` (133 términos).

### Sistema Endpoints (v17)

```http
GET  /v1/system/auto-evolve            # Estado auto-evolución
POST /v1/system/auto-evolve/trigger     # Forzar ciclo de auto-evolución
GET  /v1/system/power-mode              # Modo de bajo consumo
GET  /v1/system/context-index?q=auth    # Buscar en índice de firmas
POST /v1/system/context-index           # Indexar código
GET  /v1/system/status                  # Estado completo del sistema
```

### Cluster y Orquestación Distribuida

```http
GET  /v1/cluster/nodes          # Nodos del cluster
GET  /v1/cluster/status         # Health del cluster
POST /v1/tasks/enqueue          # Encolar tarea distribuida
GET  /v1/tasks/{task_id}/status # Estado de tarea
POST /v1/saga/start             # Iniciar saga workflow
GET  /v1/saga/{saga_id}         # Estado de saga
```

### Observabilidad

```http
GET /health              # Liveness probe (K8s-style)
GET /ready               # Readiness probe
GET /metrics             # Prometheus-compatible metrics
GET /v1/audit/events     # Query audit events
```

---

## Open Design Integration

ZENIC LOGIC incluye un bridge completo para integrarse con **Open Design** como motor de IA backend. El módulo `src/core/open_design/` implementa:

### Componentes

| Componente | Archivo | Función |
|-----------|---------|---------|
| **OpenDesignDetector** | `detector.py` | Detecta peticiones de Open Design vía headers, body, contenido |
| **ArtifactBuilder** | `artifact_builder.py` | Envuelve output en tags `<artifact>` para Open Design |
| **SSEStreamer** | `sse_streamer.py` | Streaming SSE compatible con OpenAI spec |
| **OpenDesignConfig** | `config.py` | Configuración + env var overrides + singleton |

### Visual Bypass Route

Cuando se detecta una petición de Open Design, el DAG activa la ruta `VISUAL_BYPASS` que:
1. **Salta el Z3/AC-3 Solver** — CriticalityAgent fuerza criticality 1 (FAST)
2. **Preserva Design System prompts** — ContextAgent no comprime (2.5x budget multiplier)
3. **Envuelve output en `<artifact>` tags** — ArtifactBuilder aplica formato XML
4. **Stream via SSE** — SSEStreamer entrega chunks en tiempo real

### Formato de Artifact

```xml
<artifact identifier="artifact-xxxx" type="application/vnd.ant.code"
          language="html" title="Generated UI">
    <!-- código generado aquí -->
</artifact>
```

Tipos MIME soportados: `text/html`, `application/vnd.ant.code`, `text/css`, `application/javascript`, `text/x-python`, `application/json`, `image/svg+xml`

### Detección de Señales

- Header `X-Client: open-design`
- Origin matching URLs conocidas de Open Design
- User-Agent conteniendo "open-design"
- Body fields: `stream=true`, `design_system`, `visual_context`
- Contenido: tags `<artifact>`, firmas de design system, keywords UI (>=2 matches)

### Configuración CORS

Orígenes Open Design permitidos automáticamente: `localhost:3000`, `localhost:3001`. Configurable vía `TITAN_CORS_ORIGINS` env var.

---

## Modularización v18 — Facade Pattern

La versión 18 reestructura completamente la base de código aplicando el **Facade Pattern** a nivel de archivo. Todos los archivos Python del proyecto (source y tests) fueron divididos en sub-módulos con un límite estricto de **400 líneas por archivo**, manteniendo 100% de compatibilidad hacia atrás.

### Patrón Facade

Cada archivo original se convierte en una **fachada** (2-40 líneas) que re-exporta todo desde sus sub-módulos:

```python
# Antes (archivo monolítico de 1,200 líneas):
# dag_orchestrator.py  →  toda la lógica aquí

# Después (facade + sub-módulos):
# dag_orchestrator.py  →  from .dag_parts.orchestrator import *  (facade, 5 líneas)
# dag_parts/
#   __init__.py       →  re-exporta todo
#   orchestrator.py   →  clase principal DAGOrchestrator (<=400 líneas)
#   definition.py     →  DAGNode + PIPELINE_DAG (18 nodos)
#   titan_agent.py    →  TitanAgent (F1) meta-router
#   node_executors.py →  Primeros 10 node executors
#   node_executors2.py→  9 node executors restantes
#   corrections.py    →  F5 correction loop + fractal app generation
```

### Resultados

| Métrica | Antes (v17) | Después (v18) |
|---------|------------:|--------------:|
| Archivos Python | 169 | 710 |
| Archivos >400 líneas | 30+ | **0** |
| Archivo más grande (source) | ~2,000 líneas | 393 líneas |
| Archivo más grande (test) | ~1,800 líneas | 379 líneas |
| Sub-directorios creados | — | 82 |
| Sub-módulos creados | — | 464 |
| Tests pasando | 2,654 | 2,247 |
| Compatibilidad de imports | — | 100% preservada |
| Líneas totales Python | — | 101,000+ |

### Directorios de Modularización

<details>
<summary><strong>Source (42+ sub-directorios)</strong> — click para expandir</summary>

| Directorio | Archivos | Contenido |
|-----------|:--------:|-----------|
| `src/core/dag_parts/` | 6 | DAGOrchestrator + definición + TitanAgent + executors + corrections |
| `src/core/orch_base_parts/` | 7 | Orquestador base (Init, API, Phase7, Phase8, Compat mixins) |
| `src/core/agents/` + 11 `_parts/` | 40+ | 9 agentes + BaseAgent + Runner + Cache + Schemas |
| `src/core/semantic_parts/` | 7 | SemanticEngine + embeddings + classify + search + lifecycle |
| `src/core/reasoning_parts/` | 7 | ReasoningEngine + steps + context + reflection |
| `src/core/memory_parts/` | 7 | SmartMemory + cache + long-term + episodes + database |
| `src/core/auth_parts/` | 8 | JWT + RBAC + API keys + tokens + validation + tenant |
| `src/core/template_parts/` | 7 | TemplateEngine + core + block + builtin + resolve + utils |
| `src/core/code_gen_parts/` | 4 | CodeGenerator + contextual + pipeline + extractors |
| `src/core/code_trans_parts/` | 6 | CodeTransformer + refactor + optimizer + fixer |
| `src/core/app_gen_parts/` | 7 | AppGenerator + core + file/service/template generators |
| `src/core/fractal_parts/` | 6 | FractalGenerator 3-phase (structure + skeletons + fill) |
| `src/core/automation_parts/` | 6 | AutomationEngine + execution + CRUD + project gen |
| `src/core/niche_loader_parts/` | 7 | NicheLoader + loading + query + stats + singleton |
| `src/core/niche_scraper_parts/` | 5 | NicheAutoScraper + trending + updater + scheduler |
| `src/core/mini_ai_parts/` | 6 | MiniAIEngine (Qwen3) + lifecycle + fallbacks + tasks |
| `src/core/model_mgr_parts/` | 10 | ModelManager + singleton + monitor + RAM + AI access + semantic + unload |
| `src/core/thinking_parts/` | 5 | ThinkingEngine + planning + context + reasoning |
| `src/core/schema_parts/` | 7 | SchemaDesigner + design + python_gen + sql_gen + fallbacks |
| `src/core/chain_valid_parts/` | 5 | ChainValidator + executor + convenience |
| `src/core/dna_loader_parts/` | 7 | DNALoader + loader + logic_modules + domain_validation + glossary |
| `src/core/context_ptr_parts/` | 4 | ContextPointerEngine + index + pointer |
| `src/core/low_power_parts/` | 5 | LowPowerSequentialMode + decision + evaluate + mode |
| `src/core/partial_reason_parts/` | 5 | PartialReasoningManager + partial + resume |
| `src/core/abortive_parts/` | 7 | AbortiveProtocol + protocol + merge + subtasks + execution |
| `src/core/shared/z3_parts/` | 10 | Z3 Solver core + encoding + null/type safety + invariants + AC-3 fallback |
| `src/core/shared/symbolic_parts/` | 9 | SymbolicExecutor + paths + constraints |
| `src/core/shared/governor_parts/` | 8 | ResourceGovernor + monitor + api + model_swap + singleton |
| `src/core/shared/sandbox_parts/` | 5 | SandboxIsolation |
| `src/core/distributed/` | 11 | SAGA coordinator + circuit breaker + task queue + worker + topology + backends |
| `src/core/patterns/` | 20+ | 26+ patrones de diseño en 6 categorías |
| `src/core/tenant/` | 3 | TenantContext + FeatureGate + TenantIsolation |
| `src/core/observability/` | 4 | Tracing + Metrics + Audit + Health |
| `src/core/open_design/` | 5 | Detector + ArtifactBuilder + SSEStreamer + Config |
| `src/core/logic_blocks/` | 12 | 30+ bloques lógicos de negocio |
| `src/core/executors/` | 9 | ActionExecutor: HTTP, webhook, DB, file, email, notification, etc. |
| `src/server/http_parts/` | 5 | HTTP server (imports, GET, POST, helpers mixins) |

</details>

<details>
<summary><strong>Tests (40+ sub-directorios)</strong> — click para expandir</summary>

| Directorio | Archivos | Contenido |
|-----------|:--------:|-----------|
| `tests/unit/test_f4_f5_parts/` | 5 | Tests de CriticalityAgent + ValidationAgent |
| `tests/unit/test_auth_svc_parts/` | 6 | Tests de autenticación JWT/RBAC |
| `tests/unit/test_scrap_parts/` | 6 | Tests de GitHub Scrap Agent |
| `tests/unit/test_agent_fw_parts/` | 5 | Tests del framework de agentes |
| `tests/unit/test_action_exec_parts/` | 5 | Tests de ActionExecutor |
| `tests/unit/test_biz_logic_parts/` | 5 | Tests de BusinessLogicAgent |
| `tests/unit/test_dna_parts/` | 4 | Tests del sistema DNA |
| `tests/unit/test_semantic_parts/` | 5 | Tests del SemanticEngine |
| `tests/unit/test_fractal_parts/` | 5 | Tests del FractalGenerator |
| `tests/unit/test_niche_parts/` | 5 | Tests del NicheLoader |
| `tests/unit/test_z3_parts/` | 5 | Tests del Z3 Solver |
| `tests/unit/test_governor_parts/` | 4 | Tests del ResourceGovernor |
| `tests/unit/test_mini_ai_parts/` | 5 | Tests de MiniAIEngine |
| `tests/unit/test_context_parts/` | 5 | Tests de ContextAgent |
| `tests/unit/test_low_power_parts/` | 5 | Tests de LowPowerSequentialMode |
| `tests/unit/test_orch_base_parts/` | 5 | Tests del orquestador base |
| `tests/unit/test_surgical_parts/` | 4 | Tests de SurgicalAgent fusion + calibration |
| `tests/unit/test_schema_parts/` | 4 | Tests de SchemaDesigner |
| `tests/unit/test_template_parts/` | 3 | Tests de TemplateEngine |
| `tests/unit/test_phase8_parts/` | 5 | Tests de Phase 8 (chain, reasoning, memory) |
| `tests/unit/test_resp_build_parts/` | 3 | Tests de ResponseBuilder |
| `tests/unit/test_partial_parts/` | 4 | Tests de PartialReasoning |
| `tests/unit/test_ctx_ptr_parts/` | 4 | Tests de ContextPointerEngine |
| `tests/unit/test_criticality_parts/` | 3 | Tests de CriticalityAgent keyword + history |
| `tests/integration/` | 1 | Test end-to-end del pipeline |

Total: 272 archivos de test, ~31,900 líneas

</details>

---

## 3 Mejoras de Nivel Dios (v17)

### A. Knowledge Inversion of Control (Auto-Scraping YAML)

El sistema se **auto-muta y aprende** conectando el GitHub Scrap Agent (Level 5) con un Cron Scheduler que periódicamente:

1. **Scrapea repos trending** de GitHub por lenguaje
2. **Analiza dependencias** (`package.json`, `go.mod`, `requirements.txt`)
3. **Mapea librerías a bloques** usando `LIBRARY_TO_BLOCK` (17+ mapeos)
4. **Actualiza niches** en disco: agrega entidades, bloques, patrones emergentes
5. **Registra evolución** en SQLite (`niche_evolution.sqlite`)

```
NicheCronScheduler (background thread, 24h interval, min 1h)
  -> NicheAutoUpdater
       -> TrendingAnalyzer (GitHubScrapAgent + LIBRARY_TO_BLOCK)
       -> _save_niche_yaml() (escribe YAML actualizado)
  -> EvolutionEntry (mutation_type, source_repo, old/new_value, approved)
```

Trigger manual: `POST /v1/system/auto-evolve/trigger`

### B. Context Pointers for Code Path

En lugar de pasar código al LLM, se pasa un **Vector Signature Index** — punteros compactos que representan funciones como coordenadas (~100 tokens en vez de 20K):

```
authenticate(user, pwd) -> bool @ L10-25 [auth.py]
generate_token(user_id) -> str @ L27-35 [auth.py]
verify_permissions(token, resource) -> bool @ L37-52 [auth.py]
```

**Componentes**:
- `FunctionSignature` — name, file_path, line_start/end, params, return_type, docstring, complexity, calls, hash
- `ContextPointer` — signature + relevance_score + load_code_from_disk() + apply_modification()
- `SignatureIndex` — index_project(), index_code(), search(query, top_k), get_by_name(), build_compact_context()

**Extractores multi-lenguaje**: Python (ast module, preciso), JS/TS/Kotlin/Go/Java/Rust (regex, heurístico)

### C. Dynamic Low-Power Sequential Mode

El DAG evalúa en tiempo real temperatura CPU, batería y RAM para desactivar ejecución paralela cuando el hardware está estresado:

| Power Mode | Condiciones | Efecto |
|-----------|------------|--------|
| **NORMAL** | temp<55°C AND battery>30% AND RAM<85% | Ejecución paralela completa |
| **CONSERVATIVE** | temp>55°C OR battery<30% OR RAM>85% | Layer 4 secuencial, MCTS al 50% |
| **EMERGENCY** | temp>65°C OR battery<15% OR RAM>95% | Todo secuencial, MCTS al 25%, solo agentes críticos |

**Stickiness**: 30s cooldown entre cambios de modo (evita flapping)

---

## Patrones de Diseño

ZENIC LOGIC implementa **26+ patrones de diseño** formalmente en `src/core/patterns/` y `src/core/distributed/`:

### Patrones Creacionales

| Patrón | Archivo | Uso en el Proyecto |
|--------|---------|-------------------|
| **Factory** | `patterns/creational/factory.py` | Creación de objetos por tipo |
| **Builder** | `patterns/creational/builder.py` | Construcción paso a paso |
| **Prototype** | `patterns/creational/prototype.py` | Clonación de objetos |
| **Singleton** | `niche_loader_parts/singleton.py`, `model_mgr_parts/singleton.py`, `governor_parts/singleton.py` | Instancia única thread-safe (double-checked locking) |

### Patrones Estructurales

| Patrón | Archivo | Uso en el Proyecto |
|--------|---------|-------------------|
| **Adapter** | `patterns/structural/adapter.py` | Adaptación de interfaces |
| **Bridge** | `patterns/structural/bridge.py` | Desacoplamiento abstracción/implementación |
| **Decorator** | `patterns/structural/decorator.py` | Extensión dinámica de comportamiento |
| **Proxy** | `patterns/structural/proxy.py` | Control de acceso sustituto |
| **Facade** | Usado extensivamente | Archivos facade que re-exportan de `_parts/` sub-módulos |
| **Mixin** | Usado extensivamente | Composición de clases: StructureMixin, SkeletonsMixin, FillMixin, etc. |

### Patrones de Comportamiento

| Patrón | Archivo | Uso en el Proyecto |
|--------|---------|-------------------|
| **Strategy** | `patterns/behavioral/strategy.py` | Selección de algoritmo |
| **Visitor** | `patterns/behavioral/visitor.py` | Separación operación/estructura |
| **State** | `patterns/behavioral/state.py` | Comportamiento basado en estado |
| **Observer (EventBus)** | `patterns/orchestration/event_bus.py` | Pub/sub con wildcard, sync+async |
| **Command (CommandBus)** | `patterns/orchestration/command_bus.py` | Dispatch por tipo + middleware + validators |
| **Mediator** | `patterns/orchestration/mediator.py` | Dispatch centralizado request/response |
| **Template Method** | `agents/base.py` | BaseAgent ABC con build_prompt/parse_response/fallback |
| **Chain of Responsibility** | `patterns/orchestration/command_bus.py` | Middleware chain en CommandBus |

### Patrones Arquitectónicos

| Patrón | Archivo | Uso en el Proyecto |
|--------|---------||---|
| **SAGA** | `patterns/orchestration/saga.py`, `distributed/saga_coordinator.py` | Multi-step rollback con compensación en orden inverso |
| **Circuit Breaker** | `patterns/resilience/circuit_breaker.py`, `distributed/circuit_breaker_distributed.py` | CLOSED→OPEN→HALF_OPEN state machine |
| **CQRS** | `patterns/architectural/cqrs.py` | Separación Command/Query |
| **DAG** | `dag_parts/definition.py` | Pipeline basado en grafo acíclico de 18 nodos |
| **MoE (Mixture of Experts)** | `level2_macro_router/router.py` | Clasificación de criticalidad con múltiples reglas expertas |
| **MCTS** | `shared/mcts.py` | Monte Carlo Tree Search con UCB1 para planning |
| **Abortive Protocol** | `abortive_protocol.py` | Auto-subdivisión en timeout del solver |

### Patrones de Resiliencia

| Patrón | Archivo | Características |
|--------|---------|----------------|
| **Retry** | `patterns/resilience/retry.py` | Exponential backoff |
| **Bulkhead** | `patterns/resilience/bulkhead.py` | Aislamiento de llamadas concurrentes |
| **Sidecar** | `patterns/resilience/sidecar.py` | Patrón sidecar |

### Patrones de Concurrencia

| Patrón | Archivo | Características |
|--------|---------|----------------|
| **Worker Pool** | `patterns/concurrency/worker_pool.py` | Pool de threads |
| **Producer-Consumer** | `patterns/concurrency/producer_consumer.py` | Productor/consumidor async |
| **Read-Write Lock** | `patterns/concurrency/read_write_lock.py` | Acceso concurrente de lectura |

### Patrones Distribuidos

| Patrón | Archivo | Características |
|--------|---------|----------------|
| **Leader Election** | `distributed/leader_election.py` | Elección de líder con PostgreSQL advisory locks |
| **Distributed Lock** | `distributed/lock_manager.py` | Locking cross-node |
| **Cluster Topology** | `distributed/topology.py` | Registro de nodos, heartbeats, work-stealing |
| **Distributed Task Queue** | `distributed/task_queue.py` | Cola persistente con prioridad + leasing |

---

## Sistema de Niches Declarativos

El sistema de niches permite generar aplicaciones completas desde plantillas YAML declarativas. **107 templates** a través de **20 dominios** con **793 entidades** y **8,453 campos**.

### Dominios y Templates

| Dominio | Templates | Entidades | Ejemplos |
|---------|----------:|----------:|----------|
| **health** | 12 | 96 | pharmacy, dental, telemedicine, clinical_lab, hospital_erp |
| **education** | 10 | 78 | lms, student_portal, course_platform, exam_system, university_erp |
| **business** | 7 | 56 | erp, project_mgmt, hr_system, accounting, payroll |
| **finance** | 6 | 48 | banking, crypto_exchange, accounting, investment, lending |
| **ecommerce** | 5 | 40 | marketplace, checkout, dropshipping, subscription, food_delivery |
| **technology** | 5 | 42 | saas_platform, devops_dashboard, api_gateway, cicd, monitoring |
| **logistics** | 5 | 38 | fleet_tracking, warehouse, supply_chain |
| **media** | 5 | 35 | streaming, cms, podcast |
| **agriculture** | 4 | 30 | crop_monitoring, livestock, irrigation |
| **automotive** | 4 | 32 | fleet_management, ev_charging |
| **creative** | 4 | 28 | portfolio, design_studio, video_editing |
| **energy** | 4 | 34 | solar_monitoring, smart_grid |
| **government** | 4 | 30 | citizen_portal, tax_filing |
| **hospitality** | 4 | 28 | hotel_booking, restaurant_pos |
| **legal** | 4 | 26 | case_management, contract_review |
| **manufacturing** | 4 | 32 | quality_control, production_line |
| **nonprofit** | 4 | 24 | donor_management, volunteer_tracking |
| **real_estate** | 4 | 30 | property_listing, mortgage_calc |
| **retail** | 4 | 26 | pos_system, inventory_tracking |
| **sports** | 4 | 28 | athlete_tracking, event_management |

### Estructura de un Niche YAML

```yaml
name: pharmacy_management
domain: health
subdomain: pharmaceutical
description: "Sistema de gestión integral para farmacias"
scale: small_to_medium
compliance: [hipaa, fda]
sensitivity: phi

blocks:
  - inventory_tracking
  - prescription_management
  - customer_records
  - billing_and_insurance

entities:
  medication:
    fields:
      - name: str, required
      - generic_name: str
      - dosage_form: str
      - strength: str
      - manufacturer: str
      - price: float
      - stock_quantity: int
```

---

## Sistema DNA (Master Templates)

El sistema DNA proporciona validación de dominio y conocimiento experto:

| Template | Contenido | Archivo |
|----------|-----------|---------|
| **Logic Modules** | 68 módulos atómicos de lógica de negocio | `logic_modules.yaml` |
| **Domain Expert Rules** | 20 reglas de negocio por industria | `domain_expert_rules.yaml` |
| **Validation Gates** | 121 gates de calidad para código generado | `validation_gates.yaml` |
| **Professional Glossary** | 133 transformaciones terminológicas | `professional_glossary.yaml` |

**Uso**: `DNALoader.resolve_modules_for_niche()` mapea template blocks a logic modules. `DNALoader.validate_code()` valida código generado contra validation gates. `DNALoader.polish_text()` transforma jerga técnica a lenguaje corporativo.

---

## Model Manager (Lazy Loading)

El `ModelManager` gestiona el ciclo de vida de los modelos IA con RAM budget estricto:

| Característica | Detalle |
|---------------|---------|
| **RAM Budget** | 768 MB para modelos |
| **Auto-unload** | 5 minutos de inactividad |
| **LRU eviction** | Descarga modelo least-recently-used cuando RAM pressure alta |
| **Modelos** | SemanticEngine (~150MB), MiniAIEngine (~378MB) |
| **Tracking** | Lectura de `/proc/self/status` VmRSS para RAM real |
| **Acceso** | `semantic_engine_ctx()` context manager para uso seguro |

---

## Fractal Generator (Multi-File)

El `FractalGenerator` resuelve el límite de 600 tokens de Qwen3-0.6B mediante generación en 3 fases:

| Fase | Nombre | Qué hace | Output |
|------|--------|----------|--------|
| 1 | **Structure** | LLM genera solo el árbol de directorios y nombres de archivos | `FractalSpec` con directorios + `FileBlueprint` |
| 2 | **Skeletons** | AST Surgeon (L5) inyecta clases y funciones vacías con docstrings | Archivos skeleton compilables |
| 3 | **Fill** | LLM lee cada docstring y genera la lógica item-by-item | Archivos completos |

**Patrones de fallback**: `create` → try/except CRUD, `get` → query pattern, `validate` → guard clauses.

**Templates de proyecto**: `fastapi`, `django`, `flask`, `react`, `vue`, `nextjs`, etc.

**Integración Open Design**: Soporta SSE streaming del output por fases.

---

## Motor SMT (Z3 / AC-3)

### Z3 SMT Solver (cuando está disponible)

El motor Z3 proporciona verificación formal real:

| Capacidad | Implementación |
|-----------|---------------|
| **Null-safety** | EnumSort {NONE, SOME_VALUE} para nullable vars |
| **Type-safety** | DataType para jerarquía de tipos |
| **Invariants** | Encoding de invariantes como constraints Z3 |
| **Timeout** | 15s surgical, 5s moderate (watchdog) |
| **Memory limit** | Max 512MB, o (available - 256MB), min 128MB |

Archivos: `shared/z3_parts/` (10 módulos: solver_core, solver_encoding, null_safety, type_safety, type_lattice, invariants, invariants_patterns, ac3_fallback, etc.)

### AC-3 Constraint Solver (fallback Android/Termux)

Cuando Z3 no está disponible (Android/Termux), el sistema usa AC-3:

| Capacidad | Implementación |
|-----------|---------------|
| **Arc Consistency** | Algoritmo AC-3 para reducir dominios |
| **Backtracking** | Búsqueda con heurística MRV (Minimum Remaining Values) |
| **Invariant check** | Enumeración exhaustiva (<=10K combos) o muestreo (<=1K) |
| **Resultados** | SATISFIED, UNSATISFIABLE, TIMEOUT, PROVEN, VIOLATED, LIKELY_PROVEN, LIKELY_VIOLATED |

**Interfaz unificada**: Ambos Z3 y AC-3 exponen la misma API. `HAS_Z3` flag determina el path. El solver activo se muestra en UI y respuestas API.

---

## Sistema de Memoria Inteligente

**SmartMemory** es un sistema de 6 almacenes con SQLite (WAL mode) y soporte multi-tenant:

| Almacén | Método | Max Entries | Persistencia |
|---------|--------|:-----------:|:------------:|
| **Semantic Cache** | `check_cache()` / `save_to_cache()` | 500 | SQLite |
| **Working Memory** | `add_working()` / `get_working_context()` | 20 | In-memory |
| **Long-term Memory** | `save_to_long_term()` / `find_similar_solutions()` | 500 | SQLite |
| **Episodic Memory** | `save_episode()` / `find_episodes()` | 200 | SQLite |
| **Procedural Memory** | `learn_pattern()` / `find_patterns()` | 100 | SQLite |
| **Project Memory** | `save_project()` / `get_project()` | 50 | SQLite |

**Embeddings**: Almacenados como BLOB (float32 bytes) en SQLite, cosine similarity para búsqueda, threshold 0.85 para cache, 0.5 para long-term.

**Consolidación**: Auto-promoción working → long-term cuando `importance >= 0.6`. Consolidación de entries similares.

**GDPR**: `purge_tenant_data()` elimina todos los datos de un tenant de todos los almacenes.

---

## Motor Semántico

**SemanticEngine** proporciona comprensión de lenguaje con dos modos:

| Modo | Requisito | Capacidades |
|------|-----------|-------------|
| **TF-IDF** | Ninguno (stdlib) | Clasificación de intenciones, similitud coseno, búsqueda |
| **FastEmbed** | `fastembed` package | Embeddings densos 384-dim, zero-shot classification, clustering |

**Modelo de embeddings**: `paraphrase-multilingual-MiniLM-L12-v2` (multilingual inglés + español, normalizado para cosine = dot product)

**Caché de embeddings**: In-memory dict con SHA-256 keys, max 500 entries, evicts 100 oldest.

---

## Resource Governor (ARM/RAM)

El `ResourceGovernor` protege el sistema en hardware restringido con 10+ estrategias:

| Estrategia | Implementación |
|-----------|---------------|
| **GC Tuning ARM** | `gc.set_threshold(1000, 15, 15)` — menos frecuentes pero más efectivos |
| **Process Priority** | `os.nice(10)` — prioridad baja para que Android responda |
| **File Descriptor Limit** | Capped at 256 para Android |
| **RAM Budget** | 768MB para modelos, LRU eviction, auto-unload after 5min |
| **Thermal Throttling** | CPU >70% por >30s → reduce _thermal_throttle 20% (min 40%) |
| **Adaptive MCTS** | CPU <40%: 100 sims, 40-60%: 70, 60-80%: 50, >80%: 30 (min 10) |
| **Adaptive Solver Timeout** | RAM >80%: 60% reduction, RAM >50%: 20% reduction |
| **Z3 Memory Limit** | Max 512MB, o (available - 256MB), min 128MB |
| **Auto GC** | `gc.collect(2)` cuando RAM > 1.5GB |
| **Request Lifecycle GC** | Pre: gen0, Post: gen1, High RAM: gen2 |

---

## Despliegue Docker + VPS

### Docker Compose (6 servicios)

| Servicio | Imagen | Propósito |
|----------|--------|-----------|
| **app** | Built from Dockerfile | FastAPI en puerto 5000 (interno) |
| **worker** | Built from Dockerfile | Worker distribuido (2+ réplicas) |
| **db** | postgres:16-alpine | PostgreSQL con init.sql |
| **redis** | redis:7-alpine | Pub/sub + caching (256MB LRU, AOF) |
| **nginx** | nginx:1.25-alpine | Reverse proxy + SSL termination |
| **certbot** | certbot/certbot | Let's Encrypt SSL (profile: ssl) |

**Redes**: `titan-internal` (bridge, internal), `titan-public` (bridge)
**Volúmenes**: postgres_data, redis_data, app_data, certbot_data, nginx_logs, backup_data

### Dockerfile Multi-Stage

| Stage | Propósito | Configuración |
|-------|-----------|---------------|
| **base** | Python 3.12-slim, installs deps, creates `titan` user | — |
| **development** | Hot-reload uvicorn, debug tools | — |
| **production** | Gunicorn + 4 Uvicorn workers | 1000 max-requests with jitter, 120s timeout |

### Nginx

- Worker processes auto, 1024 connections
- Rate limiting: 30r/s per IP, 100r/s per tenant
- HTTP → HTTPS redirect
- WebSocket upgrade support
- `proxy_buffering off` para SSE streaming
- 120s read timeout para operaciones IA

### VPS Deployment

Script automatizado `deploy/scripts/deploy-vps.sh` (8 pasos): system deps → titan user → PostgreSQL → copy app → venv → systemd → nginx → SSL

**Systemd service**: Gunicorn + 4 Uvicorn workers, security hardened (NoNewPrivileges, ProtectSystem=strict, PrivateTmp), 2GB memory limit, auto-restart.

### Backup/Restore

- `deploy/scripts/backup.sh`: pg_dump + gzip, retención 30 días
- `deploy/scripts/restore.sh`: Drop/recreate DB + gunzip restore

---

## Seguridad

### Middleware Stack (FastAPI)

1. **CORSMiddleware** — Orígenes configurables, Open Design auto-allow
2. **Security Middleware** — HTTPS enforcement, request size limit, security headers (CSP, HSTS, X-Frame-Options, etc.), input sanitization
3. **Metrics Middleware** — Prometheus-compatible request tracking
4. **Rate Limit + Governor Middleware** — Tenant context injection, plan-based rate limiting, quota checks, resource governor check (RAM critical → 503)

### Rate Limiting (4 capas)

| Capa | Scope | Default |
|------|-------|---------|
| Per-IP Token Bucket | Por IP | 30 RPM, burst 10 |
| Per-Tenant RPM | Por tenant | Plan-based (10/60/200) |
| Per-User Token Bucket | Por usuario autenticado | Plan-based |
| Auth Rate Limiter | Login/Register endpoints | 20 RPM, progressive lockout after 10 failures |

### Input Sanitization

- HTML escaping
- SQL injection detection
- XSS detection
- Path traversal detection
- Null byte removal
- Length limiting

### Token Blacklist

SQLite-backed JWT revocation: single token, bulk user revocation, auto-pruning de entries expiradas.

---

## Conectar con Cline/Aide/OpenCode/Open Design

### Cline / Aide / OpenCode

Configurar el cliente con:
- **Base URL**: `http://<IP>:5000`
- **Model**: `titan-omniscale-x`
- **API Type**: OpenAI Compatible

### Open Design

1. Iniciar ZENIC LOGIC: `python main_headless.py --server stdlib --port 5000`
2. Iniciar Open Design en otro terminal: `npm run dev` (localhost:3000)
3. Configurar Open Design para apuntar a `http://localhost:5000/v1/chat/completions`
4. El detector Open Design se activa automáticamente vía headers/origin

El sistema detecta peticiones de Open Design y activa la ruta Visual Bypass que salta el solver SMT y envuelve el output en `<artifact>` tags con SSE streaming.

---

## Estructura del Proyecto

```
Zenic-Logic-/
+-- main.py                          # Kivy GUI app (277 lines)
+-- main_headless.py                 # Termux headless server (322 lines)
+-- pyproject.toml                   # Project metadata (v16.0.0)
+-- requirements.txt                 # Python dependencies
+-- Dockerfile                       # Multi-stage build (dev + production)
+-- docker-compose.yml               # 6 services: app, worker, db, redis, nginx, certbot
+-- buildozer.spec                   # Android APK build config
+-- README.md                        # This file
+-- .env.example                     # Environment variable template
+-- .github/workflows/               # CI (ci.yml) + APK build (build.yml)
|
+-- deploy/
|   +-- nginx/                       # nginx.conf + conf.d/titan.conf
|   +-- scripts/                     # deploy-vps.sh, backup.sh, restore.sh
|   +-- sql/                         # init.sql (PostgreSQL)
|   +-- systemd/                     # titan-omniscale.service
|
+-- scripts/
|   +-- install_termux.sh            # Android/Termux auto-installer (326 lines)
|   +-- git_push.py                  # Git push automation
|   +-- ssh_wrapper.py               # SSH wrapper
|
+-- src/
|   +-- config/                      # settings.yaml + loader.py
|   |
|   +-- core/                        # ** Core Engine (82 sub-directories) **
|   |   +-- orchestrator.py          # TitanOrchestrator (sequential fallback)
|   |   +-- dag_orchestrator.py      # DAGOrchestrator (primary, facade)
|   |   +-- orchestrator_base.py     # BaseOrchestrator (shared base)
|   |   +-- reasoning_engine.py      # ReasoningEngine facade
|   |   +-- fractal_generator.py     # FractalGenerator facade
|   |   +-- semantic_engine.py       # SemanticEngine facade
|   |   +-- mini_ai_engine.py        # MiniAIEngine (Qwen3) facade
|   |   +-- smart_memory.py          # SmartMemory facade
|   |   +-- code_generator.py        # CodeGenerator facade
|   |   +-- code_transformer.py      # CodeTransformer facade
|   |   +-- auth_service.py          # AuthService facade
|   |   +-- model_manager.py         # ModelManager facade
|   |   +-- ... (30+ more facades)
|   |   |
|   |   +-- dag_parts/               # DAGOrchestrator implementation
|   |   +-- orch_base_parts/         # BaseOrchestrator implementation
|   |   +-- agents/ + 11 *_parts/    # 9 agents + BaseAgent + Runner + Cache
|   |   +-- level1_semantic_engine/  # L1: Semantic Parser
|   |   +-- level2_macro_router/     # L2: Macro Router MoE
|   |   +-- level3_graph_ast/        # L3: Graph AST Engine
|   |   +-- level4_apa_planner/      # L4: APA Planner (Z3+MCTS)
|   |   +-- level5_structural_swarm/ # L5: AST Surgeon + ScrapAgent
|   |   +-- level6_reflexion_sandbox/# L6: Reflexion Sandbox
|   |   +-- level7_merkle_ledger/    # L7: Merkle Ledger
|   |   +-- level8_theorem_cache/    # L8: Theorem Cache
|   |   +-- shared/ + z3_parts/ + symbolic_parts/ + governor_parts/ + sandbox_parts/
|   |   +-- patterns/ (6 categorías, 20+ archivos)
|   |   +-- distributed/ (11 archivos)
|   |   +-- tenant/ (3 archivos)
|   |   +-- observability/ (4 archivos)
|   |   +-- open_design/ (5 archivos)
|   |   +-- fractal_parts/ reasoning_parts/ memory_parts/ semantic_parts/
|   |   +-- auth_parts/ template_parts/ code_gen_parts/ code_trans_parts/
|   |   +-- app_gen_parts/ automation_parts/ niche_loader_parts/ niche_scraper_parts/
|   |   +-- mini_ai_parts/ model_mgr_parts/ thinking_parts/ schema_parts/
|   |   +-- chain_valid_parts/ dna_loader_parts/ context_ptr_parts/
|   |   +-- low_power_parts/ partial_reason_parts/ abortive_parts/
|   |   +-- logic_blocks/ executors/ ...
|   |
|   +-- server/                      # HTTP Server
|       +-- server.py                # ThreadedHTTPServer
|       +-- fastapi_app.py           # FastAPI SaaS app (~1654 lines)
|       +-- auth_middleware.py        # JWT + API key auth
|       +-- security_middleware.py    # Security headers + input sanitization
|       +-- rate_limiter.py           # Per-IP token bucket
|       +-- tenant_rate_limiter.py    # Per-user + per-tenant rate limiting
|       +-- response_builder.py       # OpenAI-compatible response builders
|       +-- http_parts/               # stdlib server mixins (GET, POST, helpers)
|
+-- tests/                           # ** Test Suite (272 files, 31,900 lines) **
|   +-- unit/                        # 265+ unit tests
|   +-- integration/                 # 1 end-to-end pipeline test
|
+-- src/templates/                   # ** Templates **
    +-- apps/base/                   # 8 app templates (.j2)
    +-- automations/base/            # 6 automation templates (.j2)
    +-- blocks/                      # 20+ block templates
    +-- niches/                      # 107 niche YAML definitions (20 domains)
    +-- dna/                         # 4 DNA master templates (.yaml)
```

---

## Testing

```bash
# Ejecutar todos los tests
pytest tests/ -v

# Con coverage
pytest tests/ --cov=src --cov-report=html

# Solo unit tests
pytest tests/unit/ -v

# Test específico
pytest tests/unit/test_dag_parts/ -v

# Con timeout (CI)
pytest tests/ --timeout=60
```

**Stats**: 272 archivos de test, ~31,900 líneas, 2,247 tests pasando, 50% coverage mínimo (CI).

**CI/CD**: GitHub Actions con matrix Python 3.10/3.11/3.12, pytest + coverage, Bandit security scan, flake8 lint, mypy type check.

---

## Dependencias

### Core

| Categoría | Paquetes |
|-----------|----------|
| **Web Framework** | `fastapi>=0.100.0`, `uvicorn>=0.23.0`, `jinja2>=3.1.0`, `pydantic>=2.0.0` |
| **Database** | `aiosqlite>=0.19.0`; PostgreSQL: `psycopg2-binary`, `asyncpg` (optional) |
| **AI/ML** | `llama-cpp-python>=0.3.0` (Qwen3-0.6B), `numpy>=1.24.0` |
| **Auth** | `python-jose[cryptography]>=3.3.0`, `passlib[bcrypt]>=1.7.4` |
| **Config** | `pyyaml>=6.0` |
| **Production** | `gunicorn>=21.2.0` |
| **Testing** | `pytest>=7.4.0`, `pytest-asyncio`, `pytest-cov`, `pytest-timeout` |

### Opcionales

| Grupo | Paquetes |
|-------|----------|
| Z3 Solver | `z3-solver>=4.12.0` |
| Kivy GUI | `kivy>=2.3.0` |
| Embeddings | `fastembed>=0.2.0` |
| Observability | `opentelemetry-api`, `opentelemetry-sdk`, `prometheus-client` |
| Integrations | `stripe`, `gspread`, `oauth2client` |

---

## Licencia

MIT License — Ver [LICENSE](LICENSE) para detalles.

---

<div align="center">

**ZENIC LOGIC — TITAN OMNISCALE X v18**

Motor de IA Quirúrgico Local | 710 archivos | 101K líneas | 26+ patrones | 9 agentes | 8 niveles

</div>
