# ZENIC LOGIC — TITAN OMNISCALE X v17

<div align="center">

**Motor de IA Quirúrgico Local — Edición Definitiva**

Servidor OpenAI-Compatible para Cline, Aide, OpenCode y más.

Funciona en **Android/Termux** sin GPU.

[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-2_654%20methods%20%7C%2079%20files-brightgreen.svg)](tests/)
[![Niches](https://img.shields.io/badge/Niches-103%20templates%20%7C%2020%20domains-orange.svg)](src/templates/niches/)
[![Source](https://img.shields.io/badge/Source-90%20files%20%7C%2042K%20lines-blue.svg)](src/)

</div>

---

## Tabla de Contenidos

- [Visión General](#visión-general)
- [Arquitectura del Sistema](#arquitectura-del-sistema)
  - [Pipeline de 8 Niveles](#pipeline-de-8-niveles)
  - [3 Capas de IA](#3-capas-de-ia)
  - [9 Agentes IA (Framework de Agentes)](#9-agentes-ia-framework-de-agentes)
  - [5 Iniciativas Unificadas (F1–F5)](#5-iniciativas-unificadas-f1f5)
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
  - [Listar Modelos](#listar-modelos)
  - [Health Check](#health-check)
  - [Niche Templates](#niche-templates)
  - [DNA Validation System](#dna-validation-system)
  - [Generación de Apps](#generación-de-apps)
  - [Automatizaciones](#automatizaciones)
  - [Lógica de Negocio](#lógica-de-negocio)
  - [Autenticación](#autenticación)
  - [Razonamiento](#razonamiento)
- [3 Mejoras de Nivel Dios (v17)](#3-mejoras-de-nivel-dios-v17)
  - [A. Knowledge Inversion of Control (Auto-Scraping YAML)](#a-knowledge-inversion-of-control-auto-scraping-yaml)
  - [B. Context Pointers for Code Path](#b-context-pointers-for-code-path)
  - [C. Dynamic Low-Power Sequential Mode](#c-dynamic-low-power-sequential-mode)
- [Sistema de Niches Declarativos](#sistema-de-niches-declarativos)
- [Sistema DNA (Master Templates)](#sistema-dna-master-templates)
- [Model Manager (Lazy Loading)](#model-manager-lazy-loading)
- [Fractal Generator (Multi-File)](#fractal-generator-multi-file)
- [Conectar con Cline/Aide/OpenCode](#conectar-con-clineaideopencode)
- [Estructura del Proyecto](#estructura-del-proyecto)
- [DAG Dinámico (F1) — Detalle](#dag-dinámico-f1--detalle)
- [Sistema de Agentes IA — Detalle](#sistema-de-agentes-ia--detalle)
- [Pipeline de 8 Niveles — Detalle](#pipeline-de-8-niveles--detalle)
- [Motor SMT (Z3 / AC-3)](#motor-smt-z3--ac-3)
- [Principio de Aislamiento Quirúrgico](#principio-de-aislamiento-quirúrgico)
- [Configuración YAML](#configuración-yaml)
- [Testing](#testing)
- [Plantillas de Generación](#plantillas-de-generación)
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
| **DAG Dinámico (F1)** | Orquestador basado en grafo acíclico con TitanAgent meta-router |
| **Ruteo Quirúrgico (F2)** | Fusión multi-señal: Memory + Semantic + LLM + TF-IDF |
| **Contexto Inteligente (F3)** | Compresión adaptativa + presupuesto de tokens + deduplicación |
| **Criticalidad Dinámica (F4)** | Fusión ponderada 5-señal con retroalimentación histórica |
| **107 Niches Declarativos** | 20 dominios, 793 entidades, 8,453 campos en YAML templates |
| **Auto-Evolución (v17)** | GitHub Scrap + Cron + auto-update de niches — el sistema muta y aprende |
| **Context Pointers (v17)** | Vector Signature Index + almacenamiento en disco — 100 tokens en vez de 20K |
| **Low-Power Mode (v17)** | Monitoreo hardware térmico/batería → DAG paralelo/secuencial adaptativo |
| **DNA Validation (v17)** | 4 Master Templates: logic_modules + domain_rules + validation_gates + glossary |
| **Lazy Model Loading (v17)** | ModelManager: carga bajo demanda + auto-unload + RAM Budget |
| **Fractal Generator (v17)** | Generación multi-archivo en 3 fases dentro del límite de 600 tokens |
| **API OpenAI-Compatible** | `/v1/chat/completions` para Cline, Aide, OpenCode |
| **Memoria Inteligente** | SmartMemory con cache semántico y aprendizaje episódico |
| **Caché de Teoremas** | Skeleton Hash para bypass O(1) en mutaciones repetidas |
| **Generación de Apps** | 8 templates de aplicación, 6 templates de automatización |
| **Autenticación** | JWT + RBAC con refresh tokens |
| **Multi-plataforma** | Desktop, Android/Termux, headless CLI |

---

## Arquitectura del Sistema

```
┌───────────────────────────────────────────────────────────────────┐
│                    API OpenAI-Compatible                           │
│   /v1/chat/completions  /v1/models  /health  /v1/niches          │
│   /v1/generate/niche  /v1/dna/*  /v1/system/*                    │
├───────────────────────────────────────────────────────────────────┤
│                  DAG ORCHESTRATOR (F1)                             │
│     Grafo acíclico con TitanAgent como meta-router                │
│     + ContextPointerEngine + LowPowerSequentialMode               │
│     CACHE_CHECK → INTENT → CONTEXT_PREPARE → AST_ANALYZE →       │
│     THEOREM_CACHE → ROUTE → CRITICALITY_ROUTE → PLAN →           │
│     SOLVER_VERIFY → EXECUTE_STEPS → SANDBOX → LEDGER →           │
│     THEOREM_SAVE → MEMORY_SAVE → DONE                             │
├──────────────────────┬────────────────────────────────────────────┤
│   9 AGENTES IA       │         PIPELINE DE 8 NIVELES              │
│                      │                                            │
│  TitanAgent (F1) ────│──→ DAG Transitions + Criticality Paths     │
│  SurgicalAgent (F2) ─│──→ L1 SemanticParser (multi-signal fusion)│
│  ContextAgent (F3) ──│──→ Context Compression + Token Budget     │
│  CriticalityAgent(F4)│──→ L2 MacroRouter (5-signal fusion)       │
│  ReasoningAgent ─────│──→ L3 GraphAST Engine                     │
│  BusinessLogicAgent ─│──→ L4 APA Planner (Z3+MCTS)              │
│  CodeAgent ──────────│──→ L5 Structural Swarm                    │
│  AutomationAgent ────│──→ L6 Reflexion Sandbox                   │
│  ValidationAgent ────│──→ L7 Merkle Ledger                       │
│                      │──→ L8 Theorem Cache                        │
│  AgentRunner ←───────│                                            │
│  (LLM Bridge)        │                                            │
├──────────────────────┴────────────────────────────────────────────┤
│                    3 CAPAS DE IA                                   │
│  Capa 1: SemanticEngine → ENTIENDE (embeddings, similitud)       │
│  Capa 2: MiniAIEngine (Qwen3) → PIENSA (razonamiento)           │
│  Capa 3: SmartMemory → RECUERDA (cache, contexto, aprendizaje)   │
├───────────────────────────────────────────────────────────────────┤
│              v17: MEJORAS DE NIVEL DIOS                            │
│  NicheLoader (103 YAML) │ DNALoader (4 Master Templates)         │
│  NicheAutoScraper + Cron│ ContextPointerEngine (Vector Index)     │
│  LowPowerSequentialMode │ ModelManager (Lazy Load + Auto-Unload)  │
│  FractalGenerator (3-phase)                                       │
├───────────────────────────────────────────────────────────────────┤
│                  INFRAESTRUCTURA PERMANENTE                        │
│  Z3 Solver | AC-3 | Sandbox | Auth JWT/RBAC | ActionExecutor     │
│  Merkle Ledger | Theorem Cache | Resource Governor | MCTS         │
│  Symbolic Executor | K-Path Analyzer | Constraint Solver          │
└───────────────────────────────────────────────────────────────────┘
```

### Pipeline de 8 Niveles

| Nivel | Componente | Implementación |
|-------|-----------|---------------|
| L1 | Semantic Parser | TF-IDF + Cosine Similarity + SurgicalAgent (F2) |
| L2 | Macro Router MoE | CriticalityAgent (F4) + firmas topológicas del AST |
| L3 | Graph AST Engine | AST nativo (Python) + regex (multi-lenguaje) + SQLite |
| L4 | APA Planner | Z3 SMT Solver (con fallback AC-3) + MCTS real |
| L5 | Structural Swarm | AST Surgeon + GitHub Scrap Agent |
| L6 | Reflexion Sandbox | Ejecución Simbólica Acotada + K-Path Limiting + Path Pruning |
| L7 | Merkle Ledger | Árbol Merkle + snapshots + rollback atómico |
| L8 | Theorem Cache | Skeleton Hash (destilación topológica) + lookup O(1) |

### 3 Capas de IA

El sistema opera con tres capas complementarias de inteligencia artificial que trabajan en conjunto para proporcionar comprensión, razonamiento y memoria persistente:

- **Capa 1 — SemanticEngine (ENTIENDE)**: Motor de embeddings y similitud semántica. Utiliza TF-IDF + cosine similarity para clasificar intenciones y encontrar patrones. Con `fastembed` opcional, utiliza embeddings densos para mayor precisión. Carga automática si los embeddings están disponibles, con fallback a TF-IDF puro.

- **Capa 2 — MiniAIEngine (PIENSA)**: Copiloto semántico basado en **Qwen3-0.6B Q4_K_M** (378MB) vía `llama-cpp-python`. Ejecuta 7 tareas bounded: clasificación de intención, sugerencia de patrones, explicación de violaciones, mejora de explicaciones, inferencia de entidades, generación contextual, y razonamiento por pasos. Funciona en CPU sin GPU con ~2-5 segundos por inferencia. Carga lazy vía **ModelManager** (v17): solo se carga en la primera petición, se auto-descarga tras 5 min de inactividad.

- **Capa 3 — SmartMemory (RECUERDA)**: Sistema de memoria inteligente con tres almacenes: **Working Memory** (contexto inmediato, TTL configurable), **Long-term Memory** (proyectos y episodios persistentes), y **Semantic Cache** (cache de consultas frecuentes con matching semántico). Aprende de interacciones exitosas y fallidas, calculando importancia dinámica basada en tipo de operación, longitud de respuesta y resultado.

### 9 Agentes IA (Framework de Agentes)

El framework de agentes reemplaza la lógica de negocio hardcodeada con agentes IA que siguen un patrón consistente: cada agente intenta primero usar el LLM (vía AgentRunner), y si falla o no está disponible, ejecuta un fallback determinista garantizado.

| Agente | Fase | Líneas | Reemplaza | Cableado |
|--------|------|-------:|-----------|----------|
| **TitanAgent** | F1 | — | Dispatch estático if/elif (185+ líneas) | DAG transitions |
| **SurgicalAgent** | F2 | 572 | SemanticParser + SemanticEngine + MiniAI classify | F1→F3→F4 |
| **ContextAgent** | F3 | 752 | SmartMemory.get_working_context() + contexto disperso | F2→F4→downstream |
| **CriticalityAgent** | F4 | 631 | MacroRouter + TitanAgent.CRITICALITY_PATHS + 3 sitios aislados | F1→F2→F3→agents |
| **IntentAgent** | Legacy | 593 | SemanticParser + SemanticEngine + MiniAI | F2 lo reemplaza |
| **ReasoningAgent** | F3 | 532 | ReasoningEngine + ThinkingEngine.reason() | F3 context |
| **BusinessLogicAgent** | F3 | 636 | LogicBuilder (30+ LogicBlocks) | F4 adjustments |
| **CodeAgent** | F4 | 1,043 | CodeGenerator + CodeTransformer + AppGenerator | F4 adjustments |
| **AutomationAgent** | F4 | 507 | AutomationEngine keyword inference | F4 adjustments |
| **ValidationAgent** | F5 | 599 | ChainValidator + code quality checks | F4 adjustments |

### 5 Iniciativas Unificadas (F1–F5)

Las iniciativas F1-F4 representan la evolución del orquestador estático hacia un sistema dinámico basado en DAG con agentes quirúrgicos. Cada iniciativa se "cablea" a las anteriores, creando un pipeline unificado donde la información fluye sin duplicación:

| Iniciativa | Nombre | Agente Core | Estado | Cableado |
|-----------|--------|-------------|--------|----------|
| **F1** | TitanOrchestrator DAG Dinámico | TitanAgent + DAGOrchestrator | Completado | Backbone del pipeline |
| **F2** | SurgicalAgent / IntentAgent | SurgicalAgent | Completado | F1 DAG → F3 context → F4 criticality |
| **F3** | ContextAgent / ReasoningAgent | ContextAgent + ReasoningAgent | Completado | F2 intent → F4 budget → agents downstream |
| **F4** | Dynamic Criticality Router | CriticalityAgent | Completado | F1 path + F2 signals + F3 budget + agents |
| **F5** | ExplainAgent / ValidationAgent | ValidationAgent + AnalysisUtils | Completado | F4 adjustments → explain output |

**Flujo unificado de información:**
```
User Query
  → CACHE_CHECK (SmartMemory)
  → INTENT (SurgicalAgent F2: multi-signal fusion)
  → CONTEXT_PREPARE (ContextAgent F3: compression + budget)
  → AST_ANALYZE (GraphASTEngine)
  → THEOREM_CACHE (O(1) lookup)
  → ROUTE (MacroRouter MoE)
  → CRITICALITY_ROUTE (CriticalityAgent F4: 5-signal fusion → adjustments)
  → PLAN (APA Planner: low_crit / standard / high_crit)
  → SOLVER_VERIFY (Z3/AC-3 para criticalidad alta)
  → EXECUTE_STEPS (CodeAgent, BusinessLogicAgent, etc.)
  → SANDBOX (Reflexion validation)
  → LEDGER_COMMIT / LEDGER_ROLLBACK
  → THEOREM_SAVE → MEMORY_SAVE → DONE
```

### Infraestructura Permanente

Los siguientes módulos **permanecen intactos** — son los cimientos sobre los que operan los agentes:

| Módulo | Archivo | Líneas | Rol |
|--------|---------|-------:|-----|
| Z3 Solver | `shared/z3_solver.py` | 1,908 | Verificación formal SMT |
| Symbolic Executor | `shared/symbolic_executor.py` | 1,948 | Ejecución simbólica acotada |
| Sandbox Isolation | `shared/sandbox_isolation.py` | 620 | Workspaces aislados para pruebas |
| Resource Governor | `shared/resource_governor.py` | 389 | Límites de CPU/RAM/tiempo |
| MCTS | `shared/mcts.py` | 202 | Monte Carlo Tree Search (UCB1) |
| K-Path Analyzer | `shared/kpath_analyzer.py` | 174 | Análisis de dependencias en grafo |
| Constraint Solver | `shared/constraint_solver.py` | 254 | Solver CSP con AC-3 + backtracking |
| Auth Service | `auth_service.py` | 796 | JWT + RBAC + refresh tokens |
| Action Executor | `action_executor.py` | 1,097 | Ejecución real de acciones (no stubs) |
| Merkle Ledger | `level7_merkle_ledger/` | 220 | Snapshots + rollback atómico |
| Theorem Cache | `level8_theorem_cache/` | 228 | Skeleton Hash O(1) |

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

El modelo Qwen3-0.6B es lo suficientemente pequeño para ejecutarse en CPU móvil, pero suficientemente capaz para las tareas bounded de los agentes (clasificación de intención, razonamiento por pasos, generación de código estructurado). Con el **ModelManager** (v17), los modelos se cargan lazy y se auto-descargan tras 5 minutos de inactividad, reduciendo RAM idle de ~730 MB a ~50 MB.

---

## Instalación

### Requisitos

- **Python**: 3.10 o superior
- **RAM**: Mínimo 4GB (8GB+ recomendado)
- **Disco**: ~500MB para modelo + dependencias
- **Opcional**: Z3 Solver para verificación formal completa

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
bash install_termux.sh

# O manualmente:
pkg install python python-pip
pip install -r requirements.txt
# Nota: Z3 no está disponible en Termux, se usa AC-3 fallback automáticamente
```

---

## Uso

### Interfaz Kivy (GUI)

```bash
python main.py
```

La interfaz Kivy proporciona:
- Botón **INICIAR MOTOR** para arrancar el servidor HTTP
- Campo de texto para pruebas locales
- Log en tiempo real de la actividad del motor
- Indicador de solver activo (Z3 o AC-3)

### Modo Headless (CLI)

```bash
python main_headless.py
```

Ejecuta el servidor sin interfaz gráfica, ideal para Termux o servidores.

### Servidor HTTP

El servidor HTTP se inicia automáticamente con cualquiera de los modos anteriores, escuchando en `0.0.0.0:5000`.

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
  "max_tokens": 600
}
```

**Respuesta** (formato OpenAI-compatible):

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

En caso de timeout del solver o límite de K-Paths, el sistema devuelve **Razonamiento Parcial** con `tool_calls` que describen la subdivisión automática de la tarea.

### Listar Modelos

```http
GET /v1/models
```

### Health Check

```http
GET /health
```

### Niche Templates

```http
GET /v1/niches
GET /v1/niches?domain=health
```

Lista todos los niches disponibles, con filtro opcional por dominio. Retorna nombre, conteo de entidades y bloques.

```http
GET /v1/niches/domains
```

Lista todos los dominios con el número de niches por dominio.

```http
GET /v1/niches/search?q=pharmacy
```

Búsqueda multi-signal por keywords (nombre, dominio, subdominio, descripción, compliance).

```http
POST /v1/generate/niche
Content-Type: application/json

{
  "niche": "pharmacy_management",
  "output_dir": "./output"
}
```

Genera una aplicación completa desde un niche template declarativo. Si no se especifica `niche`, se puede pasar `description` para auto-detectar el niche más relevante.

### DNA Validation System

```http
GET /v1/dna/modules?domain=finance
GET /v1/dna/modules?q=invoice
```

Lista los logic modules (bloques atómicos de función) del DNA. Filtrables por dominio o búsqueda.

```http
GET /v1/dna/domain-rules?industry=healthcare
```

Obtiene las reglas de negocio obligatorias para una industria específica.

```http
POST /v1/dna/validate
Content-Type: application/json

{
  "code": "def process_payment(amount): ...",
  "niche": "ecommerce_checkout"
}
```

Valida código contra las validation gates del DNA. Retorna pass/fail/warnings con score.

```http
POST /v1/dna/polish
Content-Type: application/json

{
  "text": "error: can't find user"
}
```

Pule texto técnico a lenguaje corporativo profesional usando el glossary del DNA.

### System Endpoints (v17)

```http
GET /v1/system/auto-evolve
```

Estado del sistema de auto-evolución: cron scheduler, último ciclo, estadísticas de mutación.

```http
POST /v1/system/auto-evolve/trigger
```

Fuerza un ciclo inmediato de auto-evolución (scrapea GitHub trending + actualiza niches).

```http
GET /v1/system/power-mode
```

Estado del modo de bajo consumo: temperatura CPU, batería, modo activo (NORMAL/CONSERVATIVE/EMERGENCY).

```http
GET /v1/system/context-index?q=authenticate
```

Busca en el índice de firmas de código. Retorna punteros compactos a funciones relevantes.

```http
POST /v1/system/context-index
Content-Type: application/json

{
  "code": "def process_order(items): ...",
  "file_path": "orders.py",
  "query": "order processing"
}
```

Indexa código y construye contexto compacto de punteros para el LLM.

### Generación de Apps

```http
POST /generate/app
Content-Type: application/json

{
  "request": "sistema de facturación con impuestos y descuentos",
  "project_name": "billing_system",
  "output_dir": "./output"
}
```

**Templates disponibles**: `auth_system`, `base`, `crm`, `crud_dashboard`, `inventory`, `invoice_billing`, `task_manager`, `web_api`

### Automatizaciones

```http
POST /generate/automation
Content-Type: application/json

{
  "description": "enviar reporte diario por email cada lunes a las 9am"
}
```

**Templates disponibles**: `base`, `data_sync`, `email_sender`, `notification_dispatcher`, `scheduled_report`, `webhook_handler`

### Lógica de Negocio

```http
POST /build/logic
Content-Type: application/json

{
  "description": "calcular factura con impuestos 16% y descuento 10%"
}
```

### Autenticación

```http
POST /auth/register
POST /auth/login
POST /auth/verify
```

Sistema JWT con roles (admin, user) y refresh tokens.

### Razonamiento

```http
POST /think
Content-Type: application/json

{
  "query": "diseñar API REST para gestión de inventario",
  "context": ""
}
```

Modos: `step_by_step`, `self_reflect`, `with_context`

---

## 3 Mejoras de Nivel Dios (v17)

La versión 17 introduce tres mejoras arquitectónicas que transforman ZENIC LOGIC de un sistema estático a una plataforma **auto-mutable**, **consciente del hardware** y **eficiente en contexto**.

### A. Knowledge Inversion of Control (Auto-Scraping YAML)

**Problema**: Los niche templates YAML son estáticos. Un niche de `react_ecommerce` referencia `react@18.2` y `next@13.4`, pero cuando React 19 sale, el template queda obsoleto. El sistema no aprende por sí solo.

**Solución**: El sistema ahora se **auto-muta y aprende** conectando el GitHub Scrap Agent (Level 5) con un Cron Scheduler que periódicamente:

1. **Scrapea repos trending** de GitHub por lenguaje (Python, JavaScript, Go, etc.)
2. **Analiza dependencias** (`package.json`, `go.mod`, `requirements.txt`) vía regex/AST
3. **Mapea librerías a bloques** usando `LIBRARY_TO_BLOCK` (30+ mapeos: `fastapi` → `web_api`, `stripe` → `payment`, etc.)
4. **Actualiza niches** en disco: agrega entidades, bloques, y patrones emergentes
5. **Registra evolución** en SQLite (`niche_evolution.sqlite`) con timestamps y diffs

**Arquitectura**:

```
┌───────────────────────────────────────────────────────┐
│  NicheCronScheduler (background thread)               │
│    Intervalo: 24h (mínimo 1h)                         │
│    Cooldown: 30s entre cambios de modo                │
│    Trigger manual: POST /v1/system/auto-evolve/trigger│
│                                                        │
│  NicheAutoUpdater                                      │
│    ┌─── TrendingAnalyzer                               │
│    │     GitHubScrapAgent → trending repos             │
│    │     _extract_patterns() → deps + libs             │
│    │     LIBRARY_TO_BLOCK (30+ mapeos)                 │
│    │     LIBRARY_TO_ENTITIES (4 mapeos)                │
│    │                                                   │
│    └─── _save_niche_yaml() → escribe YAML actualizado │
│                                                        │
│  EvolutionEntry (dataclass)                            │
│    mutation_type: entity_added / field_added /         │
│                   block_added / pattern_updated        │
│    source_repo, timestamp, old_value, new_value        │
│    approved: bool (para auditoría)                     │
└───────────────────────────────────────────────────────┘
```

**Cableado**: El `NicheCronScheduler` vive dentro del `DAGOrchestrator` y se inicia automáticamente con el servidor. El `NicheAutoUpdater` consume `NicheLoader` para encontrar niches matching y `GitHubScrapAgent` para obtener código trending.

### B. Context Pointers for Code Path

**Problema**: Para codebases de 20K+ tokens, comprimir código en summaries semánticos pierde la estructura exacta. El modelo necesita las coordenadas del código, no el código comprimido.

**Solución**: En lugar de pasar código al LLM, se pasa un **Vector Signature Index** — punteros compactos que representan funciones como coordenadas. El modelo ve ~100 tokens de punteros en vez de 20K tokens de código:

```
📍 authenticate(user, pwd) -> bool @ L10-25 [auth.py]
📍 generate_token(user_id) -> str @ L27-35 [auth.py]
📍 verify_permissions(token, resource) -> bool @ L37-52 [auth.py]
```

**Arquitectura**:

```
┌──────────────────────────────────────────────────────────┐
│  ContextPointerEngine                                     │
│                                                           │
│  FunctionSignature (dataclass)                            │
│    name, file_path, line_start, line_end                  │
│    params, return_type, docstring, complexity             │
│    calls: List[str], hash: str                            │
│    to_pointer() → "📍 name(params) -> ret @ L10-25 [f]"  │
│                                                           │
│  ContextPointer (wrapper)                                 │
│    signature + relevance_score + reason                    │
│    load_code_from_disk() → lee líneas reales del archivo  │
│    apply_modification(new_code) → escribe en disco        │
│                                                           │
│  SignatureIndex (core index)                              │
│    index_project(root) → escanea recursivamente           │
│    index_code(code, file_path) → indexa código inline     │
│    search(query, top_k) → búsqueda keyword con scoring    │
│    get_by_name(name) → lookup exacto                      │
│    build_compact_context(query, max_tokens) → lista de    │
│      punteros para consumo del LLM                        │
│                                                           │
│  Extractores multi-lenguaje:                              │
│    Python: ast module (preciso)                           │
│    JS/TS/Kotlin/Go/Java/Rust: regex (heurístico)         │
│                                                           │
│  Almacenamiento: ~/.titan_omniscale/context_store/        │
└──────────────────────────────────────────────────────────┘
```

**Flujo de uso**: Cuando el DAGOrchestrator necesita operar sobre código, usa `ContextPointerEngine.build_compact_context()` para construir la lista de punteros. El LLM opera sobre coordenadas. Si necesita modificar una función, `ContextPointer.load_code_from_disk()` carga solo las líneas necesarias, y `apply_modification()` usa AST Surgeon para escribir cambios directamente en disco.

### C. Dynamic Low-Power Sequential Mode

**Problema**: En Android/Termux, la ejecución paralela de agentes (Layer 4: Architect, Planner, Risk) puede causar picos de CPU que disparan thermal throttling, agotan la batería, o activan los mecanismos de seguridad del kernel Android que matan procesos.

**Solución**: El DAG evalúa en tiempo real la temperatura del CPU, nivel de batería y uso de RAM. Si el hardware está estresado, desactiva la ejecución paralela y fuerza modo secuencial estricto:

```
┌──────────────────────────────────────────────────────────┐
│  LowPowerSequentialMode                                   │
│                                                           │
│  PowerMode (Enum):                                        │
│    NORMAL       → ejecución paralela completa             │
│    CONSERVATIVE → Layer 4 secuencial, MCTS al 50%        │
│    EMERGENCY    → todo secuencial, MCTS al 25%,          │
│                   solo agentes críticos                   │
│                                                           │
│  HardwareState (dataclass):                               │
│    cpu_usage: float        (de ResourceGovernor)          │
│    ram_usage_mb: float     (de /proc/self/status)         │
│    temperature_c: float    (de /sys/class/thermal/)       │
│    battery_level: int      (de /sys/class/power_supply/)  │
│    battery_charging: bool  (de /sys/class/power_supply/)  │
│    thermal_throttle: bool  (de ResourceGovernor)          │
│                                                           │
│  evaluate() → lee hardware, calcula score, aplica modo   │
│    Stickiness: 30s cooldown entre cambios de modo         │
│    Thresholds:                                            │
│      CONSERVATIVE: temp>55°C OR battery<30% OR RAM>85%   │
│      EMERGENCY:    temp>65°C OR battery<15% OR RAM>95%   │
│                                                           │
│  API para DAGOrchestrator:                                │
│    should_run_parallel_layer4() → bool                    │
│    should_run_parallel_agents() → bool                    │
│    get_mcts_scale() → 1.0 / 0.5 / 0.25                  │
│    get_solver_timeout_scale() → 1.0 / 0.7 / 0.5         │
│    should_postpone_non_critical() → bool                  │
│    get_active_agents() → lista de agentes permitidos      │
│    get_execution_order(layer) → orden de ejecución        │
└──────────────────────────────────────────────────────────┘
```

**Cableado**: El `DAGOrchestrator` consulta `LowPowerSequentialMode.evaluate()` antes de cada paso de ejecución. En modo CONSERVATIVE, Layer 4 (Architect, Planner, Risk) se ejecuta secuencialmente en vez de en paralelo. En modo EMERGENCY, solo se ejecutan agentes críticos y el MCTS reduce simulaciones al 25%. El `NicheCronScheduler` también lo consulta para posponer auto-scraping no crítico.

---

## Sistema de Niches Declarativos

El sistema de niches permite generar aplicaciones completas desde plantillas YAML declarativas, sin tocar código Python. El sistema cargó **107 templates** a través de **20 dominios** con **793 entidades** y **8,453 campos**.

### Dominios y Templates

| Dominio | Templates | Entidades | Ejemplos |
|---------|----------:|----------:|----------|
| **health** | 12 | 96 | pharmacy, dental, telemedicine, clinical_lab |
| **education** | 10 | 78 | lms, student_portal, course_platform |
| **business** | 7 | 56 | erp, project_mgmt, hr_system |
| **finance** | 6 | 48 | banking, crypto_exchange, accounting |
| **ecommerce** | 5 | 40 | marketplace, checkout, dropshipping |
| **technology** | 5 | 42 | saas_platform, devops_dashboard, api_gateway |
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
      - expiry_date: date
      - requires_prescription: bool

typical_paths:
  - "/medications" -> inventory_tracking
  - "/prescriptions" -> prescription_management

triggers:
  - low_stock_alert: inventory.stock_quantity < threshold
  - expiry_warning: medication.expiry_date - today < 30_days

compliance: [HIPAA, FDA]
data_sensitivity: high
backup_frequency: daily
access_control: role_based
audit_trail: true
```

### Cableado

```
NicheLoader (456 líneas)
  → scan src/templates/niches/**/*.yaml
  → NicheTemplate dataclass (name, domain, entities, blocks, compliance, etc.)
  → search() / filter_by_compliance() / suggest_for_description()
  → to_composition_plan() → CompositionPlan para TemplateEngine

TemplateEngine (955 líneas)
  → get_niche_plan() → resolve NicheTemplate → CompositionPlan
  → render_niche() → render all blocks with Jinja2 + DNA validation
  → 6 métodos niche: list_niches, list_domains, search_niches, get_niche_plan, render_niche, validate_niche_code

HTTP Handler (853 líneas)
  → GET /v1/niches
  → GET /v1/niches/domains
  → GET /v1/niches/search?q=
  → POST /v1/generate/niche
```

---

## Sistema DNA (Master Templates)

El **DNA Loader** carga 4 "Master DNA Templates" que eliminan la improvisación en la generación de código. Cada template aporta una dimensión diferente de calidad:

| DNA Template | Archivo | Rol |
|-------------|---------|-----|
| **Logic Modules** | `logic_modules.yaml` | Repositorio de funciones atómicas con verificación |
| **Domain Expert Rules** | `domain_expert_rules.yaml` | Reglas de negocio obligatorias por industria |
| **Validation Gates** | `validation_gates.yaml` | Juez de calidad con auto-fix strategies |
| **Professional Glossary** | `professional_glossary.yaml` | Pulidor de lenguaje técnico a corporativo |

### API del DNALoader (674 líneas)

```python
from src.core.dna_loader import get_dna_loader

dna = get_dna_loader()

# Logic Modules
dna.get_module("invoice_calculate_tax")
dna.get_modules_by_domain("finance")
dna.search_modules("payment processing")
dna.resolve_modules_for_niche("pharmacy_management", niche_blocks)

# Domain Rules
dna.get_domain_rules("healthcare")
dna.get_mandatory_logic("healthcare")  # reglas no negociables
dna.find_industry_for_niche("health")  # → "healthcare"

# Validation Gates
dna.get_global_gates("security")       # gates de seguridad globales
dna.get_domain_gates("finance")        # gates específicos de dominio
dna.validate_code(code, "finance")     # → pass/fail/warnings/score

# Professional Glossary
dna.polish_text("error: can't find user")  # → "User record not found"
dna.polish_error("NullPointer exception")  # → "Required data reference is missing"
dna.describe_feature("CRUD")               # → "Create, Read, Update, Delete operations"
```

---

## Model Manager (Lazy Loading)

El **ModelManager** (464 líneas) implementa carga híbrida de modelos para maximizar rendimiento en hardware móvil:

| Modo | RAM Idle | Boot Time | Comportamiento |
|------|---------:|----------:|----------------|
| **Eager** (legacy) | ~730 MB | ~60s | Carga ambos modelos al inicio |
| **Lazy** (v17) | ~50 MB | <5s | Carga solo cuando se necesita |

### Características

- **Lazy Loading**: Los modelos se cargan en la primera petición que los requiere
- **Auto-Unload**: Tras 5 minutos de inactividad, los modelos se descargan automáticamente
- **RAM Budget**: Si la RAM supera el 90% del presupuesto, fuerza unload del modelo menos reciente
- **Context Managers**: `ai_engine_ctx()` y `semantic_engine_ctx()` para uso seguro con auto-cleanup

### Variables de Entorno

```bash
TITAN_LAZY_LOAD=true        # Habilitar lazy loading (default: true)
TITAN_AUTO_UNLOAD=true      # Auto-unload tras idle timeout
TITAN_MODEL_IDLE_TIMEOUT=300  # Segundos de idle antes de unload (default: 300)
TITAN_RAM_BUDGET_MB=800     # Presupuesto RAM en MB (default: 800)
```

---

## Fractal Generator (Multi-File)

El **FractalGenerator** (1,038 líneas) resuelve el problema de generar proyectos multi-archivo dentro del límite de 600 tokens de salida de Qwen3-0.6B. Divide la generación en 3 fases:

### Fase 1: Structural
Genera el árbol de directorios y la lista de archivos con sus descripciones. Si el LLM falla, usa templates predefinidos (`auth_system`, `crud_dashboard`, `inventory`) o un template genérico.

### Fase 2: Skeletons
Genera esqueletos de código: clases vacías con docstrings, funciones con `pass`, imports organizados. Incluye reparación de sintaxis para Python (`_fix_python_skeleton`).

### Fase 3: Fill
Rellena la lógica item-by-item (cada función/método individualmente), compatible con el límite de 600 tokens. Si el LLM falla, usa generación determinista basada en patrones:

- `create/add` → try/save pattern
- `get/list` → try/query pattern
- `update` → try/update pattern
- `delete` → try/delete pattern
- `validate` → try/validate pattern

### Invocación

```python
from src.core.fractal_generator import FractalGenerator

gen = FractalGenerator(code_agent=code_agent, ai_engine=mini_ai)

# Fase 1: Estructura
spec = gen.generate_structure("sistema de inventario", "crud_dashboard", "inventory_app")

# Fase 2: Esqueletos
spec = gen.generate_skeletons(spec)

# Fase 3: Rellenar lógica
result = gen.fill_logic(spec, output_dir="./output")
```

---

## Conectar con Cline/Aide/OpenCode

1. Inicia el motor ZENIC LOGIC
2. En VS Code, configura tu herramienta:
   - **API Provider**: OpenAI Compatible
   - **Base URL**: `http://TU_IP:5000/v1`
   - **Model**: `titan-omniscale-x`
3. La herramienta enviará peticiones al motor local

---

## Estructura del Proyecto

```
Zenic-Logic-/
├── main.py                          # Punto de entrada Kivy (GUI)
├── main_headless.py                 # Punto de entrada headless (CLI)
├── models/
│   └── qwen3-0.6b-q4_k_m.gguf      # Modelo IA Qwen3 (378MB)
├── src/
│   ├── core/
│   │   ├── dag_orchestrator.py      # F1: DAG Dinámico + TitanAgent (1,859 líneas)
│   │   ├── orchestrator.py          # Orquestador legacy (1,194 líneas, backward compat)
│   │   ├── semantic_engine.py       # Capa 1: ENTIENDE
│   │   ├── mini_ai_engine.py        # Capa 2: PIENSA (Qwen3)
│   │   ├── smart_memory.py          # Capa 3: RECUERDA (979 líneas)
│   │   ├── agents/                  # Framework de Agentes IA (7,221 líneas)
│   │   │   ├── __init__.py          # Exports del módulo (9 agentes + schemas)
│   │   │   ├── base.py              # BaseAgent + AgentResult (194 líneas)
│   │   │   ├── runner.py            # AgentRunner (LLM bridge, 216 líneas)
│   │   │   ├── schemas.py           # Pydantic input/output schemas (272 líneas)
│   │   │   ├── prompts.py           # System prompts + PromptBuilder (245 líneas)
│   │   │   ├── cache.py             # AgentCache (195 líneas)
│   │   │   ├── intent_shared.py     # Shared intent utilities (295 líneas)
│   │   │   ├── surgical_agent.py    # F2: SurgicalAgent multi-signal (536 líneas)
│   │   │   ├── context_agent.py     # F3: ContextAgent compression (727 líneas)
│   │   │   ├── criticality_agent.py # F4: CriticalityAgent router (631 líneas)
│   │   │   ├── intent_agent.py      # IntentAgent legacy (523 líneas)
│   │   │   ├── reasoning_agent.py   # ReasoningAgent (532 líneas)
│   │   │   ├── business_logic_agent.py # BusinessLogicAgent (636 líneas)
│   │   │   ├── code_agent.py        # CodeAgent (1,043 líneas)
│   │   │   ├── automation_agent.py  # AutomationAgent (507 líneas)
│   │   │   └── validation_agent.py  # ValidationAgent (599 líneas)
│   │   ├── reasoning_engine.py      # ReasoningEngine (719 líneas, Legacy)
│   │   ├── thinking_engine.py       # ThinkingEngine (857 líneas, Legacy)
│   │   ├── logic_builder.py         # LogicBuilder 30+ blocks (2,920 líneas, Legacy)
│   │   ├── code_generator.py        # CodeGenerator (819 líneas, Legacy)
│   │   ├── code_transformer.py      # CodeTransformer (442 líneas, Legacy)
│   │   ├── app_generator.py         # AppGenerator (1,293 líneas, Legacy)
│   │   ├── automation_engine.py     # AutomationEngine (1,020 líneas, Legacy)
│   │   ├── chain_validator.py       # ChainValidator (490 líneas, Legacy)
│   │   ├── template_engine.py       # Jinja2 Template Engine (955 líneas)
│   │   ├── auth_service.py          # JWT + RBAC (801 líneas)
│   │   ├── action_executor.py       # Real Action Execution (1,097 líneas)
│   │   ├── abortive_protocol.py     # Auto-subdivision en timeout (676 líneas)
│   │   ├── partial_reasoning.py     # OpenAI-compatible partial response (382 líneas)
│   │   ├── schema_designer.py       # DB Schema Designer (481 líneas)
│   │   ├── analysis_utils.py        # Quality reports + explanations (140 líneas)
│   │   ├── subtask_descriptor.py    # Subtask description (60 líneas)
│   │   ├── │── v17: Nuevos módulos ──────────────────────────────
│   │   ├── niche_loader.py          # YAML niche template loader (456 líneas)
│   │   ├── niche_auto_scraper.py    # Auto-evolution engine (494 líneas)
│   │   ├── dna_loader.py            # DNA Master Templates (674 líneas)
│   │   ├── context_pointer_engine.py # Context Pointers / Vector Index (466 líneas)
│   │   ├── low_power_sequential.py  # ARM-optimized sequential mode (421 líneas)
│   │   ├── model_manager.py         # Lazy model loading + auto-unload (464 líneas)
│   │   ├── fractal_generator.py     # Fractal multi-file generator (1,038 líneas)
│   │   ├── env_loader.py            # .env loader (282 líneas)
│   │   ├── local_engine.py          # Legacy local engine (292 líneas)
│   │   ├── level1_semantic_engine/  # L1: TF-IDF + semantic parsing
│   │   ├── level2_macro_router/     # L2: Criticality + AST signatures
│   │   ├── level3_graph_ast/        # L3: AST analysis + SQLite
│   │   ├── level4_apa_planner/      # L4: Z3 + MCTS planning
│   │   ├── level5_structural_swarm/ # L5: AST Surgeon + Scrap
│   │   ├── level6_reflexion_sandbox/ # L6: Symbolic execution
│   │   ├── level7_merkle_ledger/    # L7: Merkle tree + rollback
│   │   ├── level8_theorem_cache/    # L8: Skeleton hash cache
│   │   └── shared/                  # Infraestructura compartida (5,877 líneas)
│   │       ├── z3_solver.py         # SMT Solver (Z3 / AC-3 fallback)
│   │       ├── symbolic_executor.py # Symbolic execution engine
│   │       ├── sandbox_isolation.py # Workspace isolation
│   │       ├── resource_governor.py # CPU/RAM/time limits
│   │       ├── mcts.py              # Monte Carlo Tree Search
│   │       ├── kpath_analyzer.py    # K-Path dependency analysis
│   │       ├── constraint_solver.py # CSP solver (AC-3 + backtracking)
│   │       ├── db_initializer.py    # Database initialization
│   │       ├── contracts.py         # Shared types + constants
│   │       ├── types.py             # Type definitions
│   │       ├── structured_logging.py # Structured logging
│   │       ├── timeout.py           # Timeout enforcement
│   │       └── code_constraints.py  # Code constraint definitions
│   ├── api/
│   │   └── server.py                # FastAPI alternative server
│   ├── config/
│   │   ├── settings.yaml            # Configuración general
│   │   ├── timeouts.yaml            # Presupuestos computacionales
│   │   ├── critical_nodes.yaml      # Patrones de nodos críticos
│   │   └── loader.py                # YAML config loader
│   ├── server/                      # HTTP server (1,319 líneas)
│   │   ├── server.py                # ThreadedHTTPServer
│   │   ├── http_handler.py          # Request handler (853 líneas, 20+ endpoints)
│   │   ├── response_builder.py      # OpenAI-compatible responses
│   │   └── rate_limiter.py          # Rate limiting
│   └── templates/                   # Templates
│       ├── dna/                     # 4 DNA Master Templates
│       │   ├── validation_gates.yaml
│       │   ├── professional_glossary.yaml
│       │   ├── logic_modules.yaml
│       │   └── domain_expert_rules.yaml
│       ├── apps/                    # 8 app templates (9 Jinja2 files)
│       ├── automations/             # 6 automation templates (5 Jinja2 files)
│       ├── blocks/                  # Code block templates
│       │   ├── auth/                # 3 auth block templates
│       │   ├── business_logic/      # 7 business logic templates
│       │   ├── data/                # 4 data block templates
│       │   └── integrations/        # 7 integration templates
│       └── niches/                  # 103 YAML templates en 20 dominios
│           ├── agriculture/ (4)     ├── health/ (12)
│           ├── automotive/ (4)      ├── hospitality/ (4)
│           ├── business/ (7)        ├── legal/ (4)
│           ├── creative/ (4)        ├── logistics/ (5)
│           ├── ecommerce/ (5)       ├── manufacturing/ (4)
│           ├── education/ (10)      ├── media/ (5)
│           ├── energy/ (4)          ├── nonprofit/ (4)
│           ├── finance/ (6)         ├── real_estate/ (4)
│           ├── government/ (4)      ├── retail/ (4)
│           └── technology/ (5)      ├── sports/ (4)
├── tests/                           # 42 test files, ~13,695 líneas
│   ├── conftest.py                  # Session-scoped temp dir fixture
│   ├── integration/
│   │   └── test_pipeline.py
│   └── unit/                        # 30+ unit test files
├── pyproject.toml                   # Project config + pytest
├── requirements.txt                 # Core dependencies
├── pytest.ini                       # Pytest configuration
├── buildozer.spec                   # Android build spec
├── titanomniscale.kv                # Kivy UI definition
├── install_termux.sh                # Termux installer
├── git_push.py                      # Git push helper
└── ssh_wrapper.py                   # SSH wrapper
```

---

## DAG Dinámico (F1) — Detalle

### Arquitectura del DAG

El DAGOrchestrator reemplaza el dispatch estático if/elif de 185+ líneas con un grafo dirigido acíclico donde cada nodo es un paso del pipeline y las transiciones son condicionales según el resultado del paso anterior. El grafo se define en ~30 líneas de `DAGNode` dataclasses:

```
CACHE_CHECK ──[hit]──→ DONE
     │
   [miss]
     ↓
   INTENT ──(dynamic)──→ CONTEXT_PREPARE
     ↓
CONTEXT_PREPARE ──→ AST_ANALYZE ──→ THEOREM_CACHE
                                           │
                                        [hit]──→ DONE
                                        [miss]
                                           ↓
                                        ROUTE ──→ CRITICALITY_ROUTE ──→ PLAN
                                                                       │
                                                        ┌──────────────┼──────────────┐
                                                        ↓              ↓              ↓
                                                   [abortive]    [low_crit]    [high_crit]
                                                        ↓              ↓              ↓
                                                    ABORTIVE    EXECUTE_STEPS  SOLVER_VERIFY
                                                        ↓              ↓              ↓
                                                     DONE         ┌─────┘      [pass]──→ EXECUTE_STEPS
                                                                  ↓
                                                              SANDBOX
                                                             ╱       ╲
                                                        [PASS]     [FAIL]
                                                           ↓         ↓
                                                   LEDGER_COMMIT  LEDGER_ROLLBACK
                                                           ↓         ↓
                                                   THEOREM_SAVE    DONE
                                                           ↓
                                                   MEMORY_SAVE
                                                           ↓
                                                         DONE
```

### TitanAgent: Meta-Router del DAG

TitanAgent es el agente F1 que decide las transiciones del DAG cuando son no triviales (nodos INTENT y PLAN). Funciona en dos modos:

1. **LLM mode**: Envía contexto (nodo actual, resultado, operation, goal, criticality) al LLM y recibe el nombre del siguiente nodo
2. **Fallback determinista**: Usa tablas estáticas de mapeo (operation → nodo, criticality → path) que reproducen exactamente el comportamiento del pipeline secuencial original

### Ventajas sobre el Orquestador Original

| Característica | Orquestador Original | DAGOrchestrator (F1) |
|---------------|---------------------|---------------------|
| Dispatch | if/elif 185+ líneas | DAG de 16 nodos |
| Transiciones | Hardcodeadas | Condicionales + dinámicas |
| Feedback loops | No soportados | Máx. 3 iteraciones por nodo |
| Criticality routing | Estático | F4 CriticalityAgent dinámico |
| Context prep | Sin compresión | F3 ContextAgent adaptativo |
| Skip de nodos | No | criticality_skip por nodo |
| Safety | Sin límite de pasos | Máx. 20 pasos totales |
| Hardware aware | No | v17: LowPowerSequentialMode |

---

## Sistema de Agentes IA — Detalle

### TitanAgent (F1)

**Rol**: Meta-router que decide transiciones del DAG dinámicamente.

**Reemplaza**: El dispatch estático if/elif de 185+ líneas del orquestador original.

**Flujo**:
1. Si el nodo tiene transición directa en tabla → usar esa
2. Si el nodo es INTENT o PLAN → TitanAgent decide usando LLM o fallback
3. Fallback determinista: Tablas estáticas INTENT_TRANSITIONS y CRITICALITY_PATHS

**Output**: Nombre del siguiente nodo del DAG (string válido de PIPELINE_DAG).

### SurgicalAgent (F2)

**Rol**: Comprensión semántica quirúrgica — clasifica la intención con fusión multi-señal.

**Reemplaza**: `SemanticParser` (TF-IDF + keyword maps) + `SemanticEngine._fallback_classify` (keyword matching) + `MiniAIEngine.classify_intent` — 3 puntos dispersos de clasificación unificados en 1 agente.

**Arquitectura 4-Cable** (orden de costo ascendente):

```
┌─────────────────────────────────────────────────┐
│  CABLE 1: SmartMemory cache ──► hit? → return   │
│  CABLE 2: SemanticEngine embed ──► high conf? →  │
│  CABLE 3: LLM (AgentRunner) ──► valid JSON? →   │
│  CABLE 4: TF-IDF determinista ──► always works   │
└─────────────────────────────────────────────────┘
```

**Fusión multi-señal**:
- Si LLM + SemanticEngine coinciden → confianza ALTA (0.7-1.0)
- Si solo LLM o solo Semantic → confianza MEDIA (0.4-0.7)
- Si solo TF-IDF → confianza BAJA (0.0-0.4)
- Calibración adaptativa: Ajusta confianza según historial de aciertos por operación

**Salida**: `IntentOutput` → `to_intent_payload()` → compatible con el pipeline existente (MacroRouter, APAPlanner, etc.)

**Operaciones**: `CREATE`, `REFACTOR`, `DELETE`, `SEARCH`, `ANALYZE`, `EXPLAIN`, `DEBUG`, `OPTIMIZE`

**Objetivos**: `COMPLEXITY_REDUCTION`, `MODERN_PATTERN`, `BUG_FIX`, `FEATURE_ADD`, `SECURITY_HARDEN`, `PERFORMANCE`, `READABILITY`

**Cableado**: El DAGOrchestrator invoca `classify_with_runner()` en el nodo INTENT, y el resultado fluye a ContextAgent (F3) y CriticalityAgent (F4).

### ContextAgent (F3)

**Rol**: Gestión de ventana de contexto con compresión adaptativa y presupuesto de tokens.

**Reemplaza**: `SmartMemory.get_working_context()` (truncación sin inteligencia) + `ReasoningAgent._get_memory_context()` (duplica lógica) + contexto disperso en cada agente.

**Arquitectura 4-Cable**:

```
┌──────────────────────────────────────────────────────┐
│  CABLE 1: Compresión Adaptativa                      │
│    LLM → resumen semántico (si Qwen disponible)     │
│    TF-IDF → extracción de keywords (sin LLM)        │
│    Raw → truncación inteligente (siempre funciona)   │
│                                                       │
│  CABLE 2: Scoring de Relevancia                      │
│    Relevancia a intent (op/goal/criticality)         │
│    Recencia temporal (decaimiento exponencial)       │
│    Peso de importancia (SmartMemory.importance)      │
│                                                       │
│  CABLE 3: Presupuesto de Tokens                      │
│    INTENT:50t | REASON:150t | CODE:200t              │
│    VALIDATE:100t | RESERVE:100t                      │
│                                                       │
│  CABLE 4: Contexto Cross-Agent                       │
│    Deduplicación entre llamadas de agentes           │
│    Pre-fetch de memorias relevantes por intent       │
│    Cache compartido de contexto comprimido           │
└──────────────────────────────────────────────────────┘
```

**Presupuesto de tokens** (se ajusta por operation/goal):

| Agente | Presupuesto Base | CREATE | DEBUG | EXPLAIN |
|--------|----------------:|-------:|------:|--------:|
| intent | 50t | 30t | 30t | 50t |
| reasoning | 150t | 150t | 200t | 200t |
| code | 200t | 250t | 150t | 100t |
| validation | 100t | 70t | 100t | 100t |
| reserve | 100t | 100t | 100t | 100t |

**Cableado**: El DAGOrchestrator invoca `prepare_context()` en el nodo CONTEXT_PREPARE. El contexto comprimido y presupuesto se inyectan en todos los agentes downstream. F4 (CriticalityAgent) puede modificar el presupuesto con `context_budget_modifier`.

### CriticalityAgent (F4)

**Rol**: Ruteo Dinámico de Criticalidad — unifica la inferencia de criticalidad desde múltiples señales.

**Reemplaza**: `MacroRouter.route()` (keywords + AST) + `TitanAgent.CRITICALITY_PATHS` (mapping estático) + `SurgicalAgent._infer_criticality()` (keywords) + `ContextAgent._allocate_budget()` (ajustes por goal) + `SmartMemory.compute_importance()` (peso por operación) — 5 sitios aislados unificados en 1 agente.

**Resuelve**:
- **Type mismatch**: IntentOutput.criticality=str vs RoutingPayload.criticality=int → siempre produce int (1/2/3)
- **Criticalidad estática**: Se adapta al contexto semántico vía LLM
- **Lógica duplicada**: 3 sitios infieren criticalidad independientemente → 1 fusión centralizada
- **Sin retroalimentación**: Historial de evaluaciones para patrones recurrentes

**Arquitectura 3-Cable**:

```
┌──────────────────────────────────────────────────────────┐
│  CABLE 1: LLM Inference (si Qwen disponible)            │
│    Prompt → "Rate criticality of {op}/{goal} on {target}"│
│    Parse → level:int + reason:str + adjustments:dict     │
│                                                          │
│  CABLE 2: Semantic Engine (si embeddings disponibles)    │
│    Comparar operación vs patrones críticos conocidos     │
│    Similarity score → nivel de criticalidad              │
│                                                          │
│  CABLE 3: Deterministic Multi-Signal (siempre funciona) │
│    5 señales con fusión ponderada:                       │
│    ┌─────────────────────────────────────────────┐       │
│    │ Signal 1: Keywords críticos    (peso: 0.30) │       │
│    │ Signal 2: Operation/Goal map   (peso: 0.25) │       │
│    │ Signal 3: MacroRouter topology (peso: 0.20) │       │
│    │ Signal 4: SmartMemory importance (peso: 0.15)│      │
│    │ Signal 5: Historical pattern   (peso: 0.10) │       │
│    └─────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────┘
```

**Output**: `CriticalityOutput` canónico que alimenta:

| Consumidor | Qué usa | Cómo se cablea |
|-----------|---------|---------------|
| F1 (DAG) | `path` → "low_crit"/"standard"/"high_crit" | `_exec_plan()` usa `crit_output.path` |
| F3 (Context) | `adjustments.context_budget_modifier` | `_exec_criticality_route()` modifica `context_output.token_budget` |
| CodeAgent | `adjustments.code_agent` | `set_criticality_adjustments()` en CodeAgent |
| BusinessLogicAgent | `adjustments.business_agent` | `set_criticality_adjustments()` en BusinessLogicAgent |
| MacroRouter | No puede bajar criticalidad | `if crit_output.level > router_crit: routing.criticality = crit_output.level` |

**Ajustes comportamentales por nivel**:

| Nivel | CodeAgent | BusinessLogicAgent | Context Budget |
|-------|-----------|-------------------|----------------|
| 1 (FAST) | Sin validación extra, error handling básico, complejidad máx 15 | Sin auditoría, 1 capa validación, sin rollback | 0.8x (menos contexto) |
| 2 (MODERATE) | Validación extra, error handling completo, complejidad máx 10 | Con auditoría, 2 capas, con rollback | 1.0x (estándar) |
| 3 (SURGICAL) | Security checks + validación + error handling defensivo, complejidad máx 5 | Auditoría + 3 capas + rollback + idempotency | 1.3x (más contexto) |

### IntentAgent (Legacy)

**Rol**: Comprensión semántica original — clasifica la intención del usuario.

**Estado**: Mantenido por compatibilidad. `SurgicalAgent` (F2) lo reemplaza como clasificador primario en el DAGOrchestrator.

### ReasoningAgent (F3)

**Rol**: Razonamiento avanzado unificado — piensa paso a paso.

**Reemplaza**: `ReasoningEngine` (720 líneas, 3 modos step_by_step/self_reflect/with_context) + `ThinkingEngine.reason()` + `chain_of_thought()` (858 líneas).

**Modos**:
- **step_by_step**: Descompone el problema en pasos numerados con conclusiones
- **self_reflect**: Genera → evalúa → refina (más confiable, más costoso)
- **with_context**: Razonamiento con inyección de memoria + semántica

**Fallback**: Razonamiento determinista por tipo de problema (api, auth, database, invoice, inventory, crm, automation) con templates predefinidos.

### BusinessLogicAgent (F3)

**Rol**: Ejecución de lógica de negocio impulsada por IA.

**Reemplaza**: `LogicBuilder` (2,764 líneas con 30+ LogicBlocks en 6 categorías) + `ThinkingEngine._identify_entities()` + `_generate_endpoints()`.

**Tipos de operación**: `invoice`, `inventory`, `crm`, `task`, `report`, `notification`, `analytics`, `custom`

**Cada operación tiene**:
- Lógica IA (LLM → JSON con datos, side effects, insights)
- Fallback determinista completo (cálculos de impuestos, seguimiento de inventario, pipeline de ventas, priorización de tareas, etc.)

**Cableado F4**: Recibe `adjustments.business_agent` de CriticalityAgent para ajustar auditoría, capas de validación y rollback según criticalidad.

### CodeAgent (F4)

**Rol**: Generación y transformación de código unificada.

**Reemplaza**: `CodeGenerator` (820 líneas) + `CodeTransformer` (443 líneas) + `AppGenerator` legacy f-string generation.

**Tareas**:
- **generate**: Código nuevo desde requisitos (Python, Kotlin, Go, JavaScript)
- **transform**: Refactorización de código existente (AST-based para Python)
- **optimize**: Optimización con detección de anti-patrones
- **fix**: Corrección de bugs (missing colons, bare except, etc.)
- **scaffold**: Estructura de proyecto completa con tests

**Características del fallback**:
- Python: AST-based refactoring, type annotation addition, complexity analysis
- Multi-lenguaje: Templates deterministas con patrón Manager
- Scaffolding: Genera main.py, requirements.txt, config.py, tests/

**Cableado F4**: Recibe `adjustments.code_agent` de CriticalityAgent para ajustar validación extra, security checks, error handling y docstring level según criticalidad.

### AutomationAgent (F4)

**Rol**: Diseño inteligente de automatizaciones desde lenguaje natural.

**Reemplaza**: `AutomationEngine._infer_trigger()` + `_infer_actions()` + `_parse_schedule()` + `_extract_name()` — keyword matching reemplazado por IA.

**Tipos de trigger**: `schedule` (cron/interval), `event`, `webhook`, `manual`

**Tipos de acción**: `email`, `http`, `db`, `file`, `webhook`, `notification`, `transform`, `schedule`, `log`

**Bilingüe**: Keywords de inferencia en inglés y español (ej: "cada hora" → hourly, "cuando" → event trigger).

### ValidationAgent (F5)

**Rol**: Validación inteligente de código y cadenas lógicas.

**Reemplaza**: `ChainValidator` (250 líneas) + `CodeTransformer` bug detection.

**Tipos de validación**:
- **code**: Seguridad (eval, exec, injection), calidad (bare except, print), AST analysis (missing returns, resource leaks)
- **chain**: Compatibilidad entre bloques, completitud, longitud
- **config**: JSON/YAML válido, secret keys, debug mode

**Patrones de seguridad**: 11 patrones de vulnerabilidad (eval, exec, command injection, pickle, yaml.load, weak hashes, SELECT *, format injection, etc.)

**Risk score**: 0.0 (seguro) → 1.0 (peligroso) basado en severity y cantidad de issues.

### AgentRunner y Flujo de Ejecución

El `AgentRunner` es el puente entre los agentes y el LLM. Su flujo de ejecución:

```
1. Check cache → si hit, devolver resultado cacheado (O(1))
2. Build prompt → llamar al LLM vía MiniAIEngine
   - max_tokens: 600 por llamada
   - temperature: 0.15 (más determinista)
   - timeout: 10 segundos
3. Parse response → validar contra esquema Pydantic
4. Si falla → retry (1 vez)
5. Si falla de nuevo → fallback determinista
6. Cache resultado exitoso
```

### Fallback Determinista

Cada agente implementa un fallback 100% determinista que funciona sin LLM, sin embeddings, sin dependencias externas. Esto garantiza que el sistema **siempre** produce una respuesta útil, incluso en hardware sin modelo IA cargado.

| Agente | Fallback Strategy |
|--------|------------------|
| TitanAgent | Tablas estáticas INTENT_TRANSITIONS + CRITICALITY_PATHS |
| SurgicalAgent | SmartMemory cache → SemanticEngine → TF-IDF + regex bilingüe (EN/ES) |
| ContextAgent | Scoring de relevancia + TF-IDF compression + raw truncation |
| CriticalityAgent | Fusión ponderada 5-señal (keywords + op/goal + router + memory + history) |
| ReasoningAgent | Templates por tipo de problema |
| BusinessLogicAgent | Cálculos directos por operación |
| CodeAgent | Templates deterministas por lenguaje |
| AutomationAgent | Keyword inference (EN/ES) |
| ValidationAgent | Reglas estáticas + AST analysis |

---

## Pipeline de 8 Niveles — Detalle

### Nivel 1: Semantic Parser

El primer nivel del pipeline analiza la petición del usuario utilizando TF-IDF y cosine similarity para identificar la operación solicitada, el objetivo y el contexto. Integra el `SurgicalAgent` (F2) como clasificador primario con fusión multi-señal, con fallback al parser TF-IDF original cuando el agente IA no está disponible. El parser soporta extracción de bloques de código markdown, detección de lenguaje por extensión de archivo, y mapeo de entidades nombradas (funciones, clases, archivos).

### Nivel 2: Macro Router MoE

El Macro Router aplica un modelo de expertos (MoE) para clasificar la criticidad de la petición y determinar qué niveles del pipeline deben activarse. El `CriticalityAgent` (F4) unifica la inferencia de criticalidad desde 5 señales: keywords críticos, operation/goal baseline, MacroRouter AST topology, SmartMemory importance, y patrones históricos. La regla del 80/20 aplica: el 80% de las peticiones se resuelven en ~50ms (criticidad baja, ruta directa), mientras que el 100% de la capacidad libre se dedica al 20% crítico. F4 puede elevar la criticalidad del MacroRouter pero nunca la baja.

### Nivel 3: Graph AST Engine

El motor de AST construye un grafo de dependencias del código fuente utilizando el AST nativo de Python (para código Python) y regex multi-lenguaje (para Kotlin, Go, JavaScript, etc.). El grafo se almacena en SQLite y permite consultas de dependencia, análisis de complejidad ciclomática, y detección de patrones arquitectónicos. La información del AST alimenta los niveles superiores del pipeline para razonamiento informado.

### Nivel 4: APA Planner

El planificador APA (Automated Planning and Acting) utiliza dos motores complementarios: **Z3 SMT Solver** para verificación formal (cuando está instalado) y **AC-3 + backtracking** como fallback determinista (siempre disponible). El componente **MCTS** (Monte Carlo Tree Search) explora el espacio de mutaciones posibles con UCB1, 4 fases (Selección, Expansión, Simulación, Backpropagation), depth limit 5, y 100 simulaciones. El presupuesto computacional está controlado por watchdog: 15 segundos para Z3 quirúrgico, 5 segundos para moderado. En v17, el **LowPowerSequentialMode** puede escalar las simulaciones MCTS (50% o 25%) según temperatura y batería.

### Nivel 5: Structural Swarm

El enjambre estructural opera con dos agentes: el **AST Surgeon** que realiza cirugía precisa en nodos del AST (reemplazar, eliminar, insertar funciones/clases) preservando la estructura del código, y el **GitHub Scrap Agent** que busca patrones modernos en repositorios públicos para inspirar soluciones. En v17, el GitHub Scrap Agent también alimenta el sistema de **Auto-Evolución** a través del `TrendingAnalyzer`, que extrae dependencias y patrones emergentes para actualizar los niche templates automáticamente.

### Nivel 6: Reflexion Sandbox

El sandbox de reflexión ejecuta validación simbólica acotada del código generado. El motor de ejecución simbólica crea estados simbólicos con path conditions, detecta violaciones de invariantes, y calcula la cobertura de caminos. Los límites cinemáticos incluyen: K-Paths de radio 10 (la onda de validación no explora más de 10 enlaces jerárquicos desde el nodo de mutación), y Path Pruning de side effects (corta ramas con I/O externo, inyectando mocks deterministas). Si la validación falla por K-Path excesivo, se activa el Protocolo Abortivo.

### Nivel 7: Merkle Ledger

El ledger Merkle mantiene un registro criptográfico de todos los cambios aplicados al código. Cada mutación genera un snapshot con hash SHA-256, y el sistema puede hacer rollback atómico a cualquier estado previo. Los workspaces están aislados (sandbox isolation) con TTL configurable, garantizando que las pruebas nunca afectan el código en producción. El rollback es instantáneo: simplemente se restaura el snapshot anterior.

### Nivel 8: Theorem Cache

La innovación más potente del sistema. El caché de teoremas convierte la verificación O(n) en lookup O(1) mediante destilación topológica: extrae el "esqueleto" del AST (eliminando nombres de variables, valores literales, y detalles de implementación), genera un hash criptográfico de la topología sintáctica pura, y lo asocia al resultado de la verificación. Cuando un patrón lógico equivalente aparece nuevamente (incluso con nombres diferentes), el sistema lo reconoce y bypasa completamente la verificación, reduciendo de 15 segundos a ~2 milisegundos.

---

## Motor SMT (Z3 / AC-3)

| Característica | Con Z3 instalado | Sin Z3 (Android/Termux) |
|----------------|-----------------|------------------------|
| **Verificación** | Completa (enteros, arrays, cuantificadores) | AC-3 + backtracking CSP |
| **Timeout** | 15s quirúrgico, 5s moderado | 5s determinista |
| **Proof** | Satisfiability proof + counterexamples | Constraint satisfaction |
| **Instalación** | `pip install z3-solver` | Incluido (sin acción requerida) |

El sistema detecta automáticamente si Z3 está disponible y selecciona el solver apropiado. En Android/Termux donde Z3 no compila, el fallback AC-3 proporciona verificación suficiente para la mayoría de escenarios.

---

## Principio de Aislamiento Quirúrgico

El **Principio de Aislamiento Quirúrgico (PAQ)** es la filosofía central de ZENIC LOGIC. En lugar de aplicar verificación formal a todo el código (lo cual causa explosión de estado), el sistema aplica "triaje médico":

| Escenario | Estrategia | Costo CPU | Tiempo |
|-----------|-----------|-----------|--------|
| Componente visual (botón, UI) | Nivel 2 detecta baja criticidad → compilación AST directa | ~5% | <50ms |
| Pasarela de pagos / Auth | Nivel 2 detecta alta criticidad → Z3 + ejecución simbólica | ~80% | 12-15s |
| Mutaciones repetitivas (ORM) | Primera: verificación completa → Nivel 8 hashea | ~60% → ~2% | 10s → 3ms |

El `CriticalityAgent` (F4) automatiza este triaje con fusión multi-señal, determinando dinámicamente qué nivel de verificación se necesita para cada operación. Las operaciones de baja criticalidad (FAST_STANDARD) saltan SOLVER_VERIFY, las moderadas (DEEP_MODERATE) ejecutan el pipeline estándar, y las críticas (SURGICAL_CRITICAL) activan Z3 + security checks + error handling defensivo.

**Protocolo Abortivo**: Si Z3 excede el timeout de 15 segundos, el sistema hace rollback atómico y subdivide automáticamente la tarea en unidades independientes manejables.

**Razonamiento Parcial**: Si K-Paths excede el límite (10), el sistema devuelve una respuesta OpenAI-compatible con `tool_calls` describiendo la subdivisión, permitiendo al cliente reanudar la ejecución parcial.

---

## Configuración YAML

Los archivos de configuración están en `src/config/`:

### `settings.yaml`
Configuración general: directorio del proyecto, timeouts globales, parámetros del modelo.

### `timeouts.yaml`
Presupuestos computacionales por componente:
- Z3: 15000ms quirúrgico, 5000ms moderado
- MCTS: 100 simulaciones, depth limit 5
- K-Paths: radio máximo 10
- Agentes: 10000ms por llamada, max_tokens 600

### `critical_nodes.yaml`
Patrones para identificar nodos críticos en el AST:
- Auth: `/auth`, `/login`, `password`, `token`, `jwt`
- Crypto: `encrypt`, `decrypt`, `hash`, `ssl`
- Database: `/db`, `migration`, `schema`
- Payments: `/payment`, `/stripe`, `/billing`

---

## Testing

```bash
# Ejecutar todos los tests
pytest

# Con verbose y coverage
pytest -v --cov=src --cov-report=term-missing

# Solo tests unitarios
pytest tests/unit/

# Solo tests de integración
pytest tests/integration/

# Solo tests de agentes F1-F4
pytest tests/unit/test_agent_framework.py tests/unit/test_surgical_agent.py \
       tests/unit/test_context_agent.py tests/unit/test_intent_agent.py \
       tests/unit/test_reasoning_and_business_agents.py tests/unit/test_f4_f5_agents.py
```

**Cobertura de tests**: 42 archivos de test, ~13,695 líneas de tests, 570+ tests pasados.

| Suite de Tests | Archivo | Líneas | Enfoque |
|---------------|---------|-------:|---------|
| Agent Framework | `test_agent_framework.py` | 736 | BaseAgent, AgentRunner, AgentCache |
| SurgicalAgent (F2) | `test_surgical_agent.py` | 513 | Multi-signal fusion, calibración |
| ContextAgent (F3) | `test_context_agent.py` | 500 | Compresión, scoring, presupuesto |
| IntentAgent | `test_intent_agent.py` | 541 | Clasificación de intención (EN/ES) |
| Reasoning + Business | `test_reasoning_and_business_agents.py` | 493 | ReasoningAgent + BusinessLogicAgent |
| F4 + F5 Agents | `test_f4_f5_agents.py` | 971 | CodeAgent + AutomationAgent + ValidationAgent + CriticalityAgent |
| Phase 8 Intelligence | `test_phase8_intelligence.py` | 531 | ReasoningEngine + ChainValidator |
| Scrap Agent | `test_scrap_agent.py` | 818 | GitHub Scrap Agent |
| Symbolic Executor | `test_symbolic_executor.py` | 518 | Ejecución simbólica |
| Auth Service | `test_auth_service.py` | 697 | JWT + RBAC |
| Integration | `test_pipeline.py` | 326 | Pipeline completo end-to-end |

---

## Plantillas de Generación

### Aplicaciones (8 templates)

| Template | Descripción | Archivos |
|----------|-------------|----------|
| `auth_system` | Sistema de autenticación completo | models, routes, middleware, tests |
| `base` | Aplicación base con CRUD | models, routes, config, tests |
| `crm` | CRM con pipeline de ventas | lead models, stages, reports |
| `crud_dashboard` | Dashboard con operaciones CRUD | models, api, frontend templates |
| `inventory` | Sistema de inventario | product models, stock tracking, alerts |
| `invoice_billing` | Facturación con impuestos | invoice models, tax calc, PDF gen |
| `task_manager` | Gestor de tareas | task models, priorities, assignments |
| `web_api` | API REST con FastAPI | models, routes, auth, docs |

### Automatizaciones (6 templates)

| Template | Descripción |
|----------|-------------|
| `base` | Workflow base con trigger + action |
| `data_sync` | Sincronización de datos entre sistemas |
| `email_sender` | Envío programado de correos |
| `notification_dispatcher` | Despacho de notificaciones multi-canal |
| `scheduled_report` | Generación y envío de reportes |
| `webhook_handler` | Procesamiento de webhooks entrantes |

### Niches Declarativos (103 templates en 20 dominios)

Ver [Sistema de Niches Declarativos](#sistema-de-niches-declarativos) para el detalle completo.

### DNA Master Templates (4 templates)

Ver [Sistema DNA (Master Templates)](#sistema-dna-master-templates) para el detalle completo.

---

## Dependencias

### Core (requeridas)

| Paquete | Versión | Rol |
|---------|---------|-----|
| `fastapi` | >=0.100.0 | Framework web |
| `uvicorn` | >=0.23.0 | Servidor ASGI |
| `pydantic` | >=2.0.0 | Validación de schemas |
| `jinja2` | >=3.1.0 | Motor de templates |
| `aiosqlite` | >=0.19.0 | Base de datos async |
| `numpy` | >=1.24.0 | Cálculos numéricos |
| `python-jose` | >=3.3.0 | JWT tokens |
| `passlib` | >=1.7.4 | Hashing de contraseñas |
| `aiohttp` | >=3.8.0 | HTTP client async |
| `apscheduler` | >=3.10.0 | Programación de tareas |
| `aiofiles` | >=23.0.0 | File I/O async |

### Opcionales

| Paquete | Rol | Instalación |
|---------|-----|-------------|
| `z3-solver` | Verificación formal SMT | `pip install z3-solver` |
| `kivy` | Interfaz gráfica | `pip install kivy` |
| `fastembed` | Embeddings semánticos densos | `pip install fastembed` |
| `llama-cpp-python` | Motor de inferencia LLM | `pip install llama-cpp-python` |
| `stripe` | Integración de pagos | `pip install stripe` |
| `gspread` | Google Sheets integration | `pip install gspread` |

### Testing

| Paquete | Versión | Rol |
|---------|---------|-----|
| `pytest` | >=7.4.0 | Framework de tests |
| `pytest-asyncio` | >=0.21.0 | Tests async |
| `pytest-cov` | >=4.1.0 | Coverage reporting |

---

## Licencia

MIT License — Ver archivo [LICENSE](LICENSE) para detalles.

---

<div align="center">

**ZENIC LOGIC — TITAN OMNISCALE X v17**

*Ingeniería de software algorítmica 100% local, libre de alucinaciones sintácticas, inmaculada a nivel de compilación y totalmente funcional incluso bajo hardware Edge de mínimos recursos.*

*Ahora con Auto-Evolución, Context Pointers y Low-Power Mode — el sistema muta, aprende y se adapta al hardware en tiempo real.*

</div>
