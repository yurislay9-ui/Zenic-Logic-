# ZENIC LOGIC v18 — Single-Responsibility Agent Architecture

## Complete Architecture Redesign: Deterministic-by-Default, AI-Only-as-Arbiter

---

## TABLE OF CONTENTS

1. [Design Philosophy](#1-design-philosophy)
2. [Complete New Agent Registry](#2-complete-new-agent-registry)
3. [Old → New Agent Mapping](#3-old--new-agent-mapping)
4. [Dependency & Communication Graph](#4-dependency--communication-graph)
5. [Binary Verdict Flow: End-to-End](#5-binary-verdict-flow-end-to-end)
6. [Resilience Patterns Per Agent](#6-resilience-patterns-per-agent)
7. [Deterministic Logic Replaces AI](#7-deterministic-logic-replaces-ai)
8. [File Structure](#8-file-structure)
9. [Bilingual Support (EN/ES)](#9-bilingual-support-enes)
10. [Backward Compatibility](#10-backward-compatibility)

---

## 1. DESIGN PHILOSOPHY

### Core Principles

| # | Principle | Rule |
|---|-----------|------|
| 1 | **Single Responsibility** | Each agent has EXACTLY ONE function. No exceptions. |
| 2 | **Deterministic-by-Default** | Every agent works WITHOUT AI. AI is the exception, not the rule. |
| 3 | **AI = Binary Arbiter Only** | Qwen ONLY answers YES or NO. It NEVER generates, classifies, or explains. |
| 4 | **Fail-Safe by Design** | Any failure, timeout, or ambiguity → conservative default (NO / empty / safe fallback). |
| 5 | **No Duplication** | Each function exists in EXACTLY ONE agent. No overlaps. |
| 6 | **Resilience at Every Layer** | Every agent has circuit breaker, retry with backoff, health monitor, audit trail. |
| 7 | **Evidence Before AI** | Evidence is collected deterministically. AI only sees evidence summaries, never raw input. |

### Architectural Invariants

```
INVARIANT 1: No agent may call the LLM directly.
             ALL LLM calls go through VerdictEngine.

INVARIANT 2: The LLM can only return "YES" or "NO".
             Any other response is treated as "NO".

INVARIANT 3: Every agent MUST have a deterministic fallback.
             The system MUST work 100% without AI.

INVARIANT 4: No two agents may share the same responsibility.
             Duplication is a design error, not redundancy.

INVARIANT 5: Every agent call is audited.
             Every decision has an evidence trail.

INVARIANT 6: Security veto is absolute.
             If SecurityScanner says NO, it is NO. No override possible.
```

---

## 2. COMPLETE NEW AGENT REGISTRY

### Layer 1: Understanding (Parse & Classify)

| # | Agent Name | Single Responsibility | Input | Output | Uses AI? |
|---|-----------|----------------------|-------|--------|----------|
| A01 | **IntentClassifier** | Classify user intent into (operation, goal) | `RawMessage` | `IntentResult{operation, goal, confidence}` | NO |
| A02 | **EntityExtractor** | Extract named entities (files, languages, functions, code blocks) | `RawMessage` | `EntityResult{files[], langs[], functions[], code_blocks[]}` | NO |
| A03 | **TargetResolver** | Resolve target file/component and programming language | `EntityResult + Context` | `TargetResult{target_file, language, scope}` | NO |
| A04 | **CriticalityScorer** | Compute criticality level (1=FAST, 2=MODERATE, 3=SURGICAL) | `IntentResult + TargetResult + Context` | `CriticalityResult{level, path, reason, adjustments}` | NO |

### Layer 2: Memory & Context

| # | Agent Name | Single Responsibility | Input | Output | Uses AI? |
|---|-----------|----------------------|-------|--------|----------|
| A05 | **MemoryCollector** | Collect relevant memory entries from all stores | `IntentResult + TargetResult` | `MemoryEntries{working[], long_term[], episodic[], procedural[]}` | NO |
| A06 | **RelevanceScorer** | Score memory entries by relevance to current task | `MemoryEntries + IntentResult` | `ScoredEntries{entries[], scores[]}` | NO |
| A07 | **ContextCompressor** | Compress context to fit within token budget | `ScoredEntries + Budget` | `CompressedContext{text, ratio, tokens_used}` | NO |
| A08 | **ContextPrefetcher** | Prefetch likely-needed memories proactively | `IntentResult + History` | `PrefetchResult{prefetched[], hints[]}` | NO |

### Layer 3: Business Operations (One Per Domain)

| # | Agent Name | Single Responsibility | Input | Output | Uses AI? |
|---|-----------|----------------------|-------|--------|----------|
| A09 | **InvoiceProcessor** | Process invoice calculations and validations | `BusinessData{type=invoice}` | `InvoiceResult{totals, tax, discounts, valid}` | NO |
| A10 | **InventoryManager** | Track inventory levels, reorder points, stock alerts | `BusinessData{type=inventory}` | `InventoryResult{levels, alerts, reorder[]}` | NO |
| A11 | **CRMPipeline** | Manage CRM pipeline stages and conversions | `BusinessData{type=crm}` | `CRMResult{stages, conversions, forecasts}` | NO |
| A12 | **TaskScheduler** | Schedule and manage tasks with priority/deadlines | `BusinessData{type=task}` | `TaskResult{schedule, conflicts, priorities}` | NO |
| A13 | **ReportGenerator** | Generate business reports from data aggregations | `BusinessData{type=report}` | `ReportResult{content, format, charts[]}` | NO |
| A14 | **NotificationDispatcher** | Send notifications across channels (email, SMS, push) | `BusinessData{type=notification}` | `NotificationResult{sent, channel, status}` | NO |
| A15 | **DataAnalyzer** | Perform statistical analysis and pattern detection | `BusinessData{type=analytics}` | `AnalyticsResult{metrics, trends, insights}` | NO |
| A16 | **OperationRouter** | Route business operations to the correct processor agent | `BusinessData{type=any}` | `RoutedOperation{target_agent, transformed_input}` | NO |

### Layer 4: Code Operations (One Per Task)

| # | Agent Name | Single Responsibility | Input | Output | Uses AI? |
|---|-----------|----------------------|-------|--------|----------|
| A17 | **CodeGenerator** | Generate code from templates + requirements | `CodeRequest{task=generate}` | `CodeResult{code, language, files[]}` | NO |
| A18 | **CodeRefactorer** | Refactor/transform existing code | `CodeRequest{task=transform}` | `CodeResult{code, changes[], diff}` | NO |
| A19 | **CodeOptimizer** | Optimize code for performance | `CodeRequest{task=optimize}` | `CodeResult{code, improvements[], metrics}` | NO |
| A20 | **CodeFixer** | Fix bugs and errors in code | `CodeRequest{task=fix}` | `CodeResult{code, fixes[], remaining_issues[]}` | NO |
| A21 | **ProjectScaffolder** | Generate project scaffolding and boilerplate | `CodeRequest{task=scaffold}` | `ScaffoldResult{files[], structure{}, config}` | NO |
| A22 | **DefensiveInjector** | Inject defensive code patterns for F4 criticality | `CodeResult + CriticalityResult` | `CodeResult{code, injected_patterns[], audit_entries[]}` | NO |

### Layer 5: Validation & Security

| # | Agent Name | Single Responsibility | Input | Output | Uses AI? |
|---|-----------|----------------------|-------|--------|----------|
| A23 | **SecurityScanner** | Scan for dangerous patterns (exec, eval, injection) | `CodeText` | `SecurityResult{safe, threats[], risk_score}` | NO |
| A24 | **SyntaxValidator** | Validate code syntax via AST parsing | `CodeText + Language` | `SyntaxResult{valid, errors[], line_numbers[]}` | NO |
| A25 | **ChainValidator** | Validate logic chain compatibility and completeness | `ChainSpec` | `ChainResult{valid, incompatibilities[], missing[]}` | NO |
| A26 | **ConfigValidator** | Validate configuration schemas and values | `ConfigData` | `ConfigResult{valid, issues[], defaults_applied[]}` | NO |
| A27 | **RiskCalculator** | Calculate aggregate risk score from all validations | `SecurityResult + SyntaxResult + ChainResult` | `RiskResult{score, level, recommendations[]}` | NO |
| A28 | **FixSuggester** | Suggest fixes for validation issues | `ValidationIssues[]` | `FixSuggestions{suggestions[], priorities[], auto_fixable[]}` | NO |

### Layer 6: Automation

| # | Agent Name | Single Responsibility | Input | Output | Uses AI? |
|---|-----------|----------------------|-------|--------|----------|
| A29 | **TriggerInferrer** | Infer trigger type (manual/schedule/event/webhook) from description | `AutoDescription` | `TriggerSpec{type, config, description}` | NO |
| A30 | **ActionInferrer** | Infer action type (email/http/db/file/webhook/notification) from description | `AutoDescription` | `ActionSpec{type, config, description}` | NO |
| A31 | **ScheduleParser** | Parse natural language schedule into cron/interval | `ScheduleDescription` | `ScheduleSpec{type, cron, interval_seconds, description}` | NO |
| A32 | **ConditionExtractor** | Extract conditional logic from automation description | `AutoDescription` | `ConditionResult{conditions[], logic_tree}` | NO |
| A33 | **AutomationNamer** | Generate descriptive name for automation | `TriggerSpec + ActionSpec + Context` | `NameResult{name, slug}` | NO |
| A34 | **WorkflowSerializer** | Serialize automation into executable workflow spec | `TriggerSpec + ActionSpec + ScheduleSpec + Conditions` | `WorkflowSpec{yaml, json, executable}` | NO |

### Layer 7: Reasoning (Deterministic Decomposition)

| # | Agent Name | Single Responsibility | Input | Output | Uses AI? |
|---|-----------|----------------------|-------|--------|----------|
| A35 | **ProblemDetector** | Detect the type of problem (logical, arithmetic, structural, etc.) | `QueryText` | `ProblemType{type, subtype, complexity}` | NO |
| A36 | **StepDecomposer** | Break a problem into ordered reasoning steps | `QueryText + ProblemType` | `Steps{steps[], dependencies[], order}` | NO |
| A37 | **TemplateReasoner** | Apply template-based reasoning for known problem types | `ProblemType + Context` | `ReasoningResult{answer, template_used, confidence}` | NO |
| A38 | **ConfidenceEstimator** | Estimate confidence in a reasoning result | `ReasoningResult + Evidence[]` | `ConfidenceResult{score, factors[], recommendation}` | NO |
| A39 | **ConclusionExtractor** | Extract the final conclusion from reasoning steps | `Steps + Results` | `Conclusion{text, supported_by[], strength}` | NO |

### Layer 8: Verdict Engine (AI Arbiter — Only Point Where AI Is Used)

| # | Agent Name | Single Responsibility | Input | Output | Uses AI? |
|---|-----------|----------------------|-------|--------|----------|
| A40 | **DeterministicPipeline** | Execute all 7 deterministic tasks without AI | `RawInput` | `PipelineResult{7 results}` | NO |
| A41 | **EvidenceCollector** | Collect evidence for/against a decision | `Text + Code + Language` | `Evidence[]{for, against, weight, type}` | NO |
| A42 | **ConsensusResolver** | Resolve evidence into consensus or flag for AI | `Evidence[]` | `ConsensusResult{verdict, confidence, needs_llm}` | NO |
| A43 | **VerdictEngine** | Ask Qwen a binary YES/NO question (only on ties) | `VerdictInput{question, evidence}` | `VerdictOutput{YES/NO, confidence, source}` | **YES** (binary only) |

### Layer 9: Infrastructure & Resilience

| # | Agent Name | Single Responsibility | Input | Output | Uses AI? |
|---|-----------|----------------------|-------|--------|----------|
| A44 | **AgentRunner** | Execute agent with circuit breaker + retry + bulkhead | `Agent + Input` | `AgentResult{success, data, source, duration}` | NO |
| A45 | **HealthMonitor** | Track health of all agents and LLM | `Agent Stats` | `HealthSnapshot{healthy, success_rates[], latencies[]}` | NO |
| A46 | **AuditLogger** | Log all agent decisions for post-mortem analysis | `DecisionEvent` | `AuditEntry{timestamp, agent, decision, evidence}` | NO |
| A47 | **CircuitBreakerManager** | Manage circuit breakers per agent | `AgentName` | `CircuitState{closed/open/half_open}` | NO |
| A48 | **BilingualRouter** | Detect language and route to EN/ES handlers | `RawMessage` | `LanguageResult{lang, translated_if_needed}` | NO |

---

## 3. OLD → NEW AGENT MAPPING

### IntentAgent (11 functions) → Split Into:

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| Intent classification (operation+goal) | **A01 IntentClassifier** | Deterministic keyword scoring |
| Target extraction (file+language) | **A03 TargetResolver** | Uses A02 EntityExtractor output |
| Code block detection | **A02 EntityExtractor** | Regex-based, no AI |
| Named entity extraction | **A02 EntityExtractor** | Regex + patterns |
| Criticality evaluation | **A04 CriticalityScorer** | Weighted signal fusion |
| Template type inference | **A37 TemplateReasoner** | Lookup table |
| Legacy bridge to IntentPayload | **CompatibilityAdapter** (thin shim) | Deprecation path |
| GitHub query generation | **Removed** (not core responsibility) | Move to scraper module |
| SmartMemory caching | **A05 MemoryCollector** | Shared infrastructure |
| SemanticEngine classification | **A01 IntentClassifier** | Uses semantic similarity as signal |
| Bilingual support EN/ES | **A48 BilingualRouter** | Single point of language handling |

### SurgicalAgent (10 functions) → ELIMINATED (All Functions Are Duplicates)

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| Intent classification | **A01 IntentClassifier** | **DUPLICATE REMOVED** |
| 4-Cable architecture | **A44 AgentRunner** + pipeline | Replaced by ordered pipeline |
| Multi-signal fusion | **A42 ConsensusResolver** | Single source of truth |
| Adaptive calibration | **A04 CriticalityScorer** | Part of scoring logic |
| Entity extraction | **A02 EntityExtractor** | **DUPLICATE REMOVED** |
| Target & language extraction | **A03 TargetResolver** | **DUPLICATE REMOVED** |
| Criticality inference | **A04 CriticalityScorer** | **DUPLICATE REMOVED** |
| Template type inference | **A37 TemplateReasoner** | **DUPLICATE REMOVED** |
| IntentPayload compatibility | **CompatibilityAdapter** | Deprecation path |
| Result caching | **A44 AgentRunner** (built-in) | Centralized caching |

### ReasoningAgent (12 functions) → Split Into:

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| Step-by-step reasoning | **A36 StepDecomposer** | Deterministic decomposition |
| Self-reflection (generate→evaluate→refine) | **Removed as LLM-dependent** | Use deterministic template + verdict |
| Context-injected reasoning | **A36 StepDecomposer** + A05-A08 | Uses context pipeline |
| Problem type detection | **A35 ProblemDetector** | Keyword + pattern matching |
| Template-based reasoning | **A37 TemplateReasoner** | Lookup tables |
| Step decomposition | **A36 StepDecomposer** | Algorithmic decomposition |
| Semantic augmentation | **A41 EvidenceCollector** | Collects semantic signals |
| Memory-augmented reasoning | **A05 MemoryCollector** + A36 | Memory as input to steps |
| Confidence estimation | **A38 ConfidenceEstimator** | Statistical + heuristic |
| Free-text conclusion extraction | **A39 ConclusionExtractor** | Pattern-based extraction |
| Legacy bridging | **CompatibilityAdapter** | Deprecation path |
| SmartMemory caching | **A05 MemoryCollector** | Shared infrastructure |

### AutomationAgent (8 functions) → Split Into:

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| Trigger inference | **A29 TriggerInferrer** | Keyword + pattern matching |
| Action inference | **A30 ActionInferrer** | Keyword + pattern matching |
| Schedule parsing | **A31 ScheduleParser** | Regex + date parsing |
| Conditional logic extraction | **A32 ConditionExtractor** | Logic tree builder |
| Automation naming | **A33 AutomationNamer** | Template composition |
| Action config generation | **A30 ActionInferrer** | Config is part of action spec |
| Workflow serialization | **A34 WorkflowSerializer** | YAML/JSON serialization |
| SmartMemory caching | **A05 MemoryCollector** | Shared infrastructure |

### BusinessLogicAgent (11 functions) → Split Into:

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| Invoice processing | **A09 InvoiceProcessor** | Pure calculation |
| Inventory management | **A10 InventoryManager** | CRUD + thresholds |
| CRM pipeline | **A11 CRMPipeline** | Stage management |
| Task scheduling | **A12 TaskScheduler** | Priority queue + conflicts |
| Report generation | **A13 ReportGenerator** | Template + aggregation |
| Notification dispatch | **A14 NotificationDispatcher** | Channel routing |
| Data analytics | **A15 DataAnalyzer** | Statistical functions |
| Custom operations | **A16 OperationRouter** | Fallback routing |
| F4 Criticality system | **A22 DefensiveInjector** | Separate from business logic |
| CriticalityAgent integration | **A04 CriticalityScorer** | Unified scoring |
| Operation routing | **A16 OperationRouter** | Single routing point |

### CodeAgent (9 functions) → Split Into:

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| Code generation | **A17 CodeGenerator** | Template-based generation |
| Code transformation/refactoring | **A18 CodeRefactorer** | AST-based transforms |
| Code optimization | **A19 CodeOptimizer** | Performance patterns |
| Code fixing | **A20 CodeFixer** | Bug pattern matching |
| Project scaffolding | **A21 ProjectScaffolder** | File tree generation |
| Defensive code injection (F4) | **A22 DefensiveInjector** | Security hardening |
| LLM response parsing | **Removed** (no LLM in agents) | LLM only in VerdictEngine |
| Solver insight extraction | **A39 ConclusionExtractor** | Pattern extraction |
| AST context analysis | **A24 SyntaxValidator** | AST parsing |

### ContextAgent (10 functions) → Split Into:

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| Context window management | **A07 ContextCompressor** | Budget allocation |
| CABLE 1: Collect memory entries | **A05 MemoryCollector** | Unified memory access |
| CABLE 2: Score entries by relevance | **A06 RelevanceScorer** | Scoring algorithm |
| CABLE 3: Adaptive compression | **A07 ContextCompressor** | Token-aware compression |
| CABLE 4: Prefetch relevant memories | **A08 ContextPrefetcher** | Proactive fetching |
| Token budget allocation | **A07 ContextCompressor** | Part of compression |
| Cross-agent deduplication | **A06 RelevanceScorer** | Dedup during scoring |
| Shared context cache | **A05 MemoryCollector** | Centralized cache |
| Design system preservation | **A07 ContextCompressor** | Priority in compression |
| Drop-in SmartMemory replacement | **A05 MemoryCollector** | Backward compatible API |

### CriticalityAgent (10 functions) → Split Into:

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| Dynamic criticality routing | **A04 CriticalityScorer** | Weighted signal fusion |
| Signal 1: Keywords (0.30) | **A04 CriticalityScorer** | Part of scoring |
| Signal 2: Op/Goal baseline (0.25) | **A04 CriticalityScorer** | Part of scoring |
| Signal 3: SmartMemory importance (0.15) | **A04 CriticalityScorer** + A05 | Memory signal |
| Signal 4: MacroRouter AST (0.20) | **A24 SyntaxValidator** → A04 | AST signal fed to scorer |
| Signal 5: Historical (0.10) | **A04 CriticalityScorer** | Historical tracking |
| Visual bypass | **A04 CriticalityScorer** | Bypass logic |
| Downstream agent configuration | **A22 DefensiveInjector** | Applies adjustments |
| Existing criticality preservation | **A04 CriticalityScorer** | Compatibility |
| Confidence scoring | **A38 ConfidenceEstimator** | Unified confidence |

### ValidationAgent (7 functions) → Split Into:

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| Code validation (security patterns) | **A23 SecurityScanner** | Security focus |
| Python AST validation | **A24 SyntaxValidator** | Syntax focus |
| Chain validation | **A25 ChainValidator** | Chain focus |
| Config validation | **A26 ConfigValidator** | Config focus |
| Risk score calculation | **A27 RiskCalculator** | Aggregate risk |
| Fix suggestions | **A28 FixSuggester** | Fix focus |
| ChainValidator compatibility | **A25 ChainValidator** | Direct replacement |

### AgentRunner (7 functions) → Split Into:

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| Agent execution pipeline | **A44 AgentRunner** | Core execution |
| Circuit Breaker protection | **A47 CircuitBreakerManager** | Per-agent breakers |
| Retry with exponential backoff | **A44 AgentRunner** (uses A47) | Integrated retry |
| Bulkhead concurrency limiting | **A44 AgentRunner** | Integrated bulkhead |
| Result caching | **A44 AgentRunner** | Integrated cache |
| Statistics tracking | **A45 HealthMonitor** | Centralized stats |
| Thread-safe stats | **A45 HealthMonitor** | Thread-safe by design |

### MiniAIEngine / Qwen AI → **A43 VerdictEngine Only**

| Old Function | New Agent | Notes |
|-------------|-----------|-------|
| 7 deterministic tasks | **A40 DeterministicPipeline** | Already deterministic in v17 |
| verdict() → YES/NO | **A43 VerdictEngine** | **ONLY place AI is used** |

---

## 4. DEPENDENCY & COMMUNICATION GRAPH

### 4.1 Pipeline Flow (Happy Path)

```
User Input
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 1: UNDERSTAND (All Deterministic, No AI)                 │
│                                                                  │
│  RawMessage ──► A48 BilingualRouter ──► A01 IntentClassifier    │
│                          │                   │                   │
│                          ▼                   ▼                   │
│                    A02 EntityExtractor ──► A03 TargetResolver   │
│                                              │                   │
│                                              ▼                   │
│                                        A04 CriticalityScorer    │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 2: CONTEXT (All Deterministic, No AI)                    │
│                                                                  │
│  A05 MemoryCollector ──► A06 RelevanceScorer ──► A07 Compressor │
│         │                                                       │
│         ▼                                                       │
│  A08 ContextPrefetcher                                          │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 3: EXECUTE (All Deterministic, No AI)                    │
│                                                                  │
│  A16 OperationRouter ──► {                                       │
│      A09 InvoiceProcessor                                        │
│      A10 InventoryManager                                        │
│      A11 CRMPipeline                                             │
│      A12 TaskScheduler                                           │
│      A13 ReportGenerator                                         │
│      A14 NotificationDispatcher                                  │
│      A15 DataAnalyzer                                            │
│      A17 CodeGenerator                                           │
│      A18 CodeRefactorer                                          │
│      A19 CodeOptimizer                                           │
│      A20 CodeFixer                                               │
│      A21 ProjectScaffolder                                       │
│      A29-A34 Automation Agents                                   │
│      A35-A39 Reasoning Agents                                    │
│  }                                                              │
│                                                                  │
│  A22 DefensiveInjector (applies F4 adjustments post-execution)   │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 4: VALIDATE (All Deterministic, No AI)                   │
│                                                                  │
│  A23 SecurityScanner ──┐                                        │
│  A24 SyntaxValidator  ──┼──► A27 RiskCalculator                 │
│  A25 ChainValidator    ──┤        │                              │
│  A26 ConfigValidator   ──┘        ▼                              │
│                            A28 FixSuggester                      │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 5: VERDICT (AI Arbiter — ONLY If Needed)                 │
│                                                                  │
│  A40 DeterministicPipeline ──► A41 EvidenceCollector             │
│                                      │                           │
│                                      ▼                           │
│                               A42 ConsensusResolver              │
│                                      │                           │
│                          ┌───────────┴───────────┐              │
│                          │                       │              │
│                    Consensus ≥ HIGH         Consensus < HIGH     │
│                          │                       │              │
│                          ▼                       ▼              │
│                     Decision Made        A43 VerdictEngine       │
│                     (No AI needed)       (Qwen: YES/NO)         │
│                                                  │              │
│                                          ┌───────┴──────┐       │
│                                          │              │       │
│                                     Circuit OK    Circuit OPEN   │
│                                          │              │       │
│                                    YES or NO    Fallback NO     │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 6: AUDIT & MONITOR (All Deterministic)                   │
│                                                                  │
│  A46 AuditLogger ◄──── Every Decision                            │
│  A45 HealthMonitor ◄─── Every Agent Execution                    │
│  A47 CircuitBreakerManager ◄─ Every LLM Call                    │
└──────────────────────────────────────────────────────────────────┘
```

### 4.2 Agent Dependency Matrix

```
Agent    Depends On
───────  ──────────
A01      A48 (BilingualRouter)
A02      A48
A03      A02
A04      A01, A03, A05
A05      A01
A06      A05, A01
A07      A06
A08      A01, A05
A09-A15  A04, A07 (criticality + context)
A16      A01, A04 (to route correctly)
A17-A21  A04, A07, A03 (criticality + context + target)
A22      A04 (criticality adjustments)
A23      (none - standalone)
A24      (none - standalone)
A25      (none - standalone)
A26      (none - standalone)
A27      A23, A24, A25, A26
A28      A27
A29-A34  A01, A07
A35-A39  A07, A05
A40      (none - standalone pipeline)
A41      A40
A42      A41
A43      A42, A47
A44      A47, A45
A45      (all agents report stats)
A46      (all agents report decisions)
A47      (standalone infrastructure)
A48      (none - first in pipeline)
```

### 4.3 Communication Protocol

All inter-agent communication uses a **typed message bus**:

```python
@dataclass
class AgentMessage:
    sender: str              # Agent name (e.g., "A01_IntentClassifier")
    recipient: str           # Agent name or "broadcast"
    message_type: str        # "request", "response", "error", "verdict_needed"
    payload: Dict[str, Any]  # Typed data
    correlation_id: str      # For request-response matching
    timestamp: float
    trace_id: str            # Distributed tracing
```

---

## 5. BINARY VERDICT FLOW: END-TO-END

### 5.1 Complete Flow Example: "Create a payment gateway with Stripe"

```
STEP 1: A48 BilingualRouter
  Input:  "Create a payment gateway with Stripe"
  Output: {lang: "en", text: "Create a payment gateway with Stripe"}
  Method: langdetect keyword matching (deterministic)
  Time:   <1ms

STEP 2: A01 IntentClassifier
  Input:  "Create a payment gateway with Stripe"
  Output: {operation: "CREATE", goal: "FEATURE_ADD", confidence: 0.85}
  Method: Keyword scoring: "create"→CREATE(2pts), "gateway"→FEATURE_ADD(1pt)
  Evidence: keyword_CREATE=0.8, keyword_FEATURE_ADD=0.6
  Time:   <1ms

STEP 3: A02 EntityExtractor
  Input:  "Create a payment gateway with Stripe"
  Output: {files: [], langs: [], functions: [], code_blocks: [],
           frameworks: ["Stripe"], domains: ["payment"]}
  Method: Regex + keyword matching
  Time:   <1ms

STEP 4: A03 TargetResolver
  Input:  EntityResult from A02
  Output: {target_file: "payment_gateway.py", language: "python",
           scope: "new_module"}
  Method: Template composition from framework + domain
  Time:   <1ms

STEP 5: A04 CriticalityScorer
  Input:  IntentResult + TargetResult
  Signals:
    - Keywords: "payment" → critical (0.30)
    - Operation: CREATE + FEATURE_ADD → moderate baseline (0.25)
    - Domain: "payment" + "Stripe" → high importance (0.15)
    - No AST available → skip (0.20)
    - No history → default (0.10)
  Output: {level: 3 (SURGICAL), path: "high_crit", confidence: 0.88,
           adjustments: {audit_trail: true, rollback: true,
                        validation_layers: 3, defensive_injection: true}}
  Method: Weighted signal fusion with threshold gates
  Time:   <1ms

STEP 6: A05-A08 Context Pipeline
  A05 MemoryCollector: Collects past payment gateway implementations
  A06 RelevanceScorer: Scores by similarity to current task
  A07 ContextCompressor: Fits within 500 token budget
  A08 ContextPrefetcher: Preloads Stripe API patterns
  Time:   <5ms

STEP 7: A16 OperationRouter
  Input:  {operation: "CREATE", domain: "payment"}
  Output: Routes to A17 CodeGenerator with payment template
  Time:   <1ms

STEP 8: A17 CodeGenerator
  Input:  CodeRequest{task="generate", requirements="payment gateway with Stripe",
          language="python", template="payment_stripe"}
  Method: Template library lookup → fill placeholders deterministically
  Output: CodeResult{code: "...stripe payment code...", language: "python"}
  Time:   <10ms

STEP 9: A22 DefensiveInjector
  Input:  CodeResult + CriticalityResult(level=3 SURGICAL)
  Injects:
    - Input validation for all payment amounts
    - Try/except with rollback on payment failure
    - Audit logging for all transactions
    - Idempotency keys for retry safety
  Output: CodeResult{code: "...hardened payment code..."}
  Time:   <5ms

STEP 10: A23 SecurityScanner
  Input:  Hardened code
  Scans:  No exec(), eval(), pickle, subprocess, etc.
  Output: SecurityResult{safe: true, threats: [], risk_score: 0.0}
  Time:   <1ms

STEP 11: A24 SyntaxValidator
  Input:  Code + "python"
  Method: ast.parse()
  Output: SyntaxResult{valid: true, errors: []}
  Time:   <2ms

STEP 12: A27 RiskCalculator
  Input:  SecurityResult + SyntaxResult
  Output: RiskResult{score: 0.05, level: "low", recommendations: []}
  Time:   <1ms

═══════════════════════════════════════════════════════════════════
  VERDICT CHECK: Is consensus clear?
═══════════════════════════════════════════════════════════════════

  A41 EvidenceCollector:
    FOR:  SecurityResult.safe=true (weight=0.9)
          SyntaxResult.valid=true (weight=0.8)
          CriticalityResult.confidence=0.88 (weight=0.7)
          CodeGenerator.confidence=0.9 (weight=0.6)
    AGAINST: (none)

  A42 ConsensusResolver:
    score_for = 0.9×1.5 + 0.8×1.2 + 0.7×0.8 + 0.6×0.6 = 3.02
    score_against = 0
    normalized = 3.02/3.02 = 1.0
    confidence = CERTAIN
    needs_llm = FALSE ✅

  RESULT: YES (approved) — No AI needed! 🎉
  Total time: <30ms (all deterministic)
```

### 5.2 Verdict Flow When AI IS Needed (Ambiguous Case)

```
Example: "Should we allow this dynamic code evaluation plugin?"

  A41 EvidenceCollector:
    FOR:  SyntaxResult.valid=true (weight=0.8)
          TemplateReasoner.found_match=true (weight=0.6)
    AGAINST: SecurityResult.safe=false: eval() detected (weight=0.9)

  A42 ConsensusResolver:
    score_for = 0.8×1.2 + 0.6×0.6 = 1.32
    score_against = 0.9×1.5 = 1.35
    normalized = (1.32-1.35)/2.67 = -0.011
    confidence = LOW (|score| < 0.3)
    needs_llm = TRUE ⚠️

  ══════════════════════════════════════════════════════
    AI ARBITRATION REQUIRED
  ══════════════════════════════════════════════════════

  A47 CircuitBreakerManager:
    Check breaker for "verdict_engine": CLOSED ✅

  A43 VerdictEngine:
    Prompt (AI NEVER sees raw code):
    ┌─────────────────────────────────────────────────┐
    │ You are a binary decision maker.                │
    │ Answer with ONLY one word: YES or NO.           │
    │                                                  │
    │ Evidence FOR: Syntax valid; template match found │
    │ Evidence AGAINST: eval() detected; security risk│
    │ Consensus score: -0.01 (near tie)               │
    │ Question: Should this code be approved?          │
    │                                                  │
    │ Answer with ONLY: YES or NO                     │
    └─────────────────────────────────────────────────┘

    Multi-attempt consensus (3 calls to Qwen):
      Attempt 1: "NO"  ←
      Attempt 2: "NO"  ←
      Early exit: 2/3 = majority NO

    Result: NO (consensus 2/3)
    Confidence: 0.67
    Source: llm_consensus
    Time: ~200ms (2 × ~100ms LLM calls)

  A46 AuditLogger:
    Records: {question, verdict, source, confidence, evidence, latency}

  FINAL RESULT: NO (rejected) — Plugin blocked due to eval() ✅
```

### 5.3 Verdict Flow When AI Is Down (Circuit Breaker OPEN)

```
  A47 CircuitBreakerManager:
    Check breaker for "verdict_engine": OPEN ❌
    (3 consecutive LLM failures in last 60 seconds)

  A43 VerdictEngine:
    Circuit is OPEN → Immediate fallback NO
    No LLM call attempted
    Time: 0ms

  RESULT: NO (fallback) — Precaution principle ✅

  A45 HealthMonitor:
    Records: circuit_breaker_rejection
    Auto-recovery: After 60s, breaker transitions to HALF_OPEN
    Then allows 1 test call to check if LLM recovered
```

---

## 6. RESILIENCE PATTERNS PER AGENT

### 6.1 Resilience Configuration Matrix

| Agent | Circuit Breaker | Retry | Bulkhead | Health Monitor | Audit | Timeout |
|-------|:-:|:-:|:-:|:-:|:-:|:-:|
| A01-A04 | ✓ (3f/60s) | ✓ (3×, exp) | ✓ (4conc) | ✓ | ✓ | 5s |
| A05-A08 | ✓ (5f/30s) | ✓ (3×, exp) | ✓ (8conc) | ✓ | ✓ | 3s |
| A09-A15 | ✓ (3f/60s) | ✓ (3×, exp) | ✓ (2conc) | ✓ | ✓ | 10s |
| A16 | ✓ (3f/30s) | ✓ (2×, exp) | ✓ (4conc) | ✓ | ✓ | 2s |
| A17-A22 | ✓ (3f/60s) | ✓ (3×, exp) | ✓ (4conc) | ✓ | ✓ | 15s |
| A23-A28 | ✓ (5f/30s) | ✓ (2×, exp) | ✓ (8conc) | ✓ | ✓ | 5s |
| A29-A34 | ✓ (3f/30s) | ✓ (3×, exp) | ✓ (4conc) | ✓ | ✓ | 3s |
| A35-A39 | ✓ (3f/60s) | ✓ (3×, exp) | ✓ (4conc) | ✓ | ✓ | 10s |
| A40-A42 | ✓ (5f/30s) | ✓ (3×, exp) | ✓ (8conc) | ✓ | ✓ | 5s |
| **A43** | **✓ (3f/60s)** | **✓ (3×, exp)** | **✓ (1conc)** | **✓** | **✓** | **5s** |
| A44 | ✓ (5f/30s) | ✓ (3×, exp) | ✓ (4conc) | ✓ | ✓ | 30s |
| A45-A47 | ✓ (5f/30s) | ✓ (2×, exp) | ✓ (2conc) | ✓ | ✓ | 3s |
| A48 | ✓ (3f/30s) | ✓ (2×, exp) | ✓ (4conc) | ✓ | ✓ | 1s |

Legend: `3f/60s` = 3 failures to trip, 60s recovery timeout; `exp` = exponential backoff

### 6.2 Resilience Pattern Details

#### Circuit Breaker (Per-Agent Instance)

```python
class AgentCircuitBreaker:
    """
    Each agent has its own circuit breaker instance.
    
    State Machine:
        CLOSED → OPEN:      failure_threshold consecutive failures
        OPEN → HALF_OPEN:   recovery_timeout elapsed
        HALF_OPEN → CLOSED: success_threshold consecutive successes
        HALF_OPEN → OPEN:   Any failure in half-open
    
    When OPEN:
        - All calls return deterministic fallback immediately
        - No waiting, no timeouts, no resource waste
        - Logged as "circuit_open_fallback"
    """
    config:
        failure_threshold: 3      # Consecutive failures to trip
        recovery_timeout: 60.0    # Seconds before trying again
        half_open_max_calls: 1    # Test calls in half-open
        success_threshold: 2      # Successes to close circuit
```

#### Retry with Exponential Backoff (Per-Agent Config)

```python
class AgentRetryConfig:
    """
    Every agent call is wrapped with retry logic.
    
    For deterministic agents: retry is fast (no LLM to wait for).
    For VerdictEngine: retry includes LLM call delays.
    
    Jitter prevents thundering herd when multiple agents retry.
    """
    config:
        max_attempts: 3           # Maximum tries before giving up
        base_delay: 1.0           # First retry delay (seconds)
        max_delay: 10.0           # Cap on delay
        exponential_base: 2.0     # Multiplier per attempt
        jitter: True              # Random jitter 0-30%
        jitter_max: 0.3           # Jitter multiplier
        timeout_per_attempt: 5.0  # Per-try timeout (seconds)
    
    delay_formula:
        delay = base_delay * (exponential_base ** (attempt - 1))
        delay = min(delay, max_delay)
        if jitter: delay += random(0, jitter_max * delay)
```

#### Bulkhead (Per-Agent Pool)

```python
class AgentBulkhead:
    """
    Each agent has a concurrency limit.
    Prevents one slow agent from consuming all resources.
    
    Critical agents (A43 VerdictEngine): max_concurrent=1
    Fast agents (A23 SecurityScanner): max_concurrent=8
    I/O agents (A05 MemoryCollector): max_concurrent=4
    """
    config:
        max_concurrent: varies    # See matrix above
        max_queue: 20             # Queue before rejection
        timeout: 30.0             # Wait time before BulkheadFullError
```

#### Health Monitor (Global)

```python
class GlobalHealthMonitor:
    """
    Monitors all agents' health in a centralized dashboard.
    Sliding window of last 50 calls per agent.
    
    Unhealthy threshold: success_rate < 0.3
    Warning threshold: success_rate < 0.7
    
    Auto-actions:
    - If agent is unhealthy → log warning + suggest circuit breaker
    - If VerdictEngine is unhealthy → auto-degrade to fallback-only
    - If >50% agents unhealthy → system-wide alert
    """
    config:
        window_size: 50           # Calls per sliding window
        unhealthy_threshold: 0.3  # Below this = unhealthy
        warning_threshold: 0.7    # Below this = warning
```

#### Audit Logger (Per-Decision)

```python
class AuditLogger:
    """
    Every agent decision is logged with full context.
    Circular buffer to limit memory (<1MB total).
    
    Enables:
    - Post-mortem analysis of failures
    - Compliance auditing
    - Pattern detection (e.g., "LLM consistently returns NO for auth questions")
    - Performance regression detection
    """
    config:
        max_entries: 200          # Per agent circular buffer
        total_max: 2000           # Global audit buffer
        fields: [
            "timestamp", "agent", "input_hash", "output_hash",
            "source", "confidence", "duration_ms", "retry_count",
            "circuit_breaker_state", "evidence_summary"
        ]
```

### 6.3 Failure Recovery Flow

```
Agent Call Fails
    │
    ▼
┌─────────────────────────────────────────────┐
│ ATTEMPT 1: Retry with exponential backoff   │
│   delay = 1.0s + jitter                     │
│   → If success: Record success, return      │
│   → If failure: Continue                    │
├─────────────────────────────────────────────┤
│ ATTEMPT 2: Retry with exponential backoff   │
│   delay = 2.0s + jitter                     │
│   → If success: Record success, return      │
│   → If failure: Continue                    │
├─────────────────────────────────────────────┤
│ ATTEMPT 3: Retry with exponential backoff   │
│   delay = 4.0s + jitter                     │
│   → If success: Record success, return      │
│   → If failure: All retries exhausted       │
├─────────────────────────────────────────────┤
│ CIRCUIT BREAKER: Record failure             │
│   → If consecutive_failures >= threshold:   │
│     Circuit → OPEN                          │
│     All subsequent calls → immediate fallback│
├─────────────────────────────────────────────┤
│ FALLBACK: Return deterministic result       │
│   → Every agent has a fallback() method     │
│   → Fallback is ALWAYS safe and correct     │
│   → Fallback result has source="fallback"   │
├─────────────────────────────────────────────┤
│ HEALTH MONITOR: Record failure              │
│   → Update sliding window                   │
│   → If agent unhealthy: escalate alert      │
├─────────────────────────────────────────────┤
│ AUDIT: Log the entire failure sequence      │
│   → Including all retry attempts            │
│   → Including circuit breaker state         │
│   → Including fallback result               │
└─────────────────────────────────────────────┘
```

---

## 7. DETERMINISTIC LOGIC REPLACES AI

### 7.1 Complete Replacement Table

| Task That Used AI | AI Approach (Old) | Deterministic Approach (New) | Speed Gain |
|---|---|---|---|
| Intent classification | LLM: 2 calls, ~8s, JSON parsing | Keyword scoring with weighted signals | 8000× |
| Entity extraction | LLM: 1 call, ~5s, JSON parsing | Regex + pattern matching | 5000× |
| Pattern suggestion | LLM: 1 call, ~4s | Lookup table + heuristics | 4000× |
| Template gap filling | LLM: 1 call, ~4s, JSON parsing | Context mapping + defaults | 4000× |
| Pattern generation | LLM: 1 call, ~6s | Template library composition | 6000× |
| Violation explanation | LLM: 1 call, ~3s | Violation catalog lookup | 3000× |
| Subtask description | LLM: 1 call, ~3s | Algorithmic name composition | 3000× |
| Code generation | LLM: 1-3 calls, ~15s | Template library + placeholder fill | 1500× |
| Business logic | LLM: 1-2 calls, ~10s | Per-domain calculation functions | 1000× |
| Criticality scoring | LLM: 0-1 calls, ~5s | Weighted signal fusion (5 signals) | 5000× |
| Reasoning steps | LLM: 2-5 calls, ~20s | Template decomposition + step ordering | 20000× |
| Validation | LLM: 1-2 calls, ~8s | AST parsing + regex security scan | 8000× |

### 7.2 Where AI Is Still Used (Binary Verdict ONLY)

| Use Case | When AI Is Called | Fallback If AI Down |
|----------|------------------|-------------------|
| Consensus tie-breaking | ConsensusResolver score < 0.3 | Default NO (precaution principle) |
| Ambiguous security verdict | Security evidence conflicts | Default NO (security veto) |
| Uncertain classification | Top-2 operations have similar scores | Default to lower-criticality path |
| Novel pattern evaluation | No template match, no cache hit | Default to conservative template |

### 7.3 AI Guarantee: Impossible to Get Wrong Response

```
┌──────────────────────────────────────────────────────────────┐
│                  AI RESPONSE SANDBOX                         │
│                                                              │
│  Input to AI:  Only evidence summary + binary question      │
│  Output from AI: Raw string (e.g., "YES", "NO", "I think") │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  PARSER (deterministic, no AI)                       │    │
│  │                                                       │    │
│  │  1. Strip <think...</think > blocks from Qwen3       │    │
│  │  2. Take FIRST WORD only                              │    │
│  │  3. Convert to uppercase                              │    │
│  │  4. Match:                                            │    │
│  │     "YES"       → Verdict.YES                         │    │
│  │     "NO"        → Verdict.NO                          │    │
│  │     "YEAH"      → Verdict.YES (contains YES)          │    │
│  │     "NOPE"      → Verdict.NO (contains NO)            │    │
│  │     ANYTHING ELSE → None → Treated as NO              │    │
│  │                                                       │    │
│  │  5. Multi-attempt consensus:                          │    │
│  │     Ask 3 times, majority wins                        │    │
│  │     If 2+ say YES → YES                              │    │
│  │     If 2+ say NO or ambiguous → NO                    │    │
│  │     If all fail → NO (fallback)                       │    │
│  │                                                       │    │
│  │  6. Circuit Breaker:                                  │    │
│  │     If OPEN → NO immediately (no LLM call)           │    │
│  │     If HALF_OPEN → 1 test call, failure → OPEN       │    │
│  │                                                       │    │
│  │  7. Timeout:                                          │    │
│  │     If no response in 5s → NO                        │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                              │
│  GUARANTEE: The AI CANNOT produce a "bad" generative        │
│  response because the parser only accepts YES or NO.         │
│  Every other response is treated as NO (safe default).       │
│                                                              │
│  It is MATHEMATICALLY IMPOSSIBLE for the AI to:              │
│  - Generate code (output is only YES/NO)                     │
│  - Classify into categories (output is only YES/NO)          │
│  - Explain anything (output is only YES/NO)                  │
│  - Be confused with the wrong agent (output is only YES/NO) │
│  - Inject malicious content (never reaches downstream)       │
└──────────────────────────────────────────────────────────────┘
```

---

## 8. FILE STRUCTURE

```
src/
├── core/
│   ├── __init__.py
│   │
│   ├── agents/                          # ALL 48 agents
│   │   ├── __init__.py
│   │   ├── base.py                      # BaseAgent, AgentResult (unchanged)
│   │   ├── schemas.py                   # All input/output dataclasses
│   │   ├── prompts.py                   # Prompt templates (for legacy compat)
│   │   ├── message_bus.py              # AgentMessage, MessageBus
│   │   │
│   │   ├── understand/                  # Layer 1: Understanding
│   │   │   ├── __init__.py
│   │   │   ├── intent_classifier.py     # A01: Intent → (operation, goal)
│   │   │   ├── entity_extractor.py      # A02: Extract files, langs, funcs
│   │   │   ├── target_resolver.py       # A03: Resolve target + language
│   │   │   ├── criticality_scorer.py    # A04: Score criticality level
│   │   │   └── bilingual_router.py      # A48: Detect language EN/ES
│   │   │
│   │   ├── context/                     # Layer 2: Memory & Context
│   │   │   ├── __init__.py
│   │   │   ├── memory_collector.py      # A05: Collect from all stores
│   │   │   ├── relevance_scorer.py      # A06: Score by relevance
│   │   │   ├── context_compressor.py    # A07: Compress to budget
│   │   │   └── context_prefetcher.py    # A08: Prefetch proactively
│   │   │
│   │   ├── business/                    # Layer 3: Business Operations
│   │   │   ├── __init__.py
│   │   │   ├── operation_router.py      # A16: Route to correct processor
│   │   │   ├── invoice_processor.py     # A09: Invoice calculations
│   │   │   ├── inventory_manager.py     # A10: Inventory tracking
│   │   │   ├── crm_pipeline.py          # A11: CRM stages
│   │   │   ├── task_scheduler.py        # A12: Task scheduling
│   │   │   ├── report_generator.py      # A13: Report generation
│   │   │   ├── notification_dispatcher.py # A14: Notification sending
│   │   │   └── data_analyzer.py         # A15: Statistical analysis
│   │   │
│   │   ├── code/                        # Layer 4: Code Operations
│   │   │   ├── __init__.py
│   │   │   ├── code_generator.py        # A17: Code generation
│   │   │   ├── code_refactorer.py       # A18: Code refactoring
│   │   │   ├── code_optimizer.py        # A19: Code optimization
│   │   │   ├── code_fixer.py            # A20: Bug fixing
│   │   │   ├── project_scaffolder.py    # A21: Project scaffolding
│   │   │   └── defensive_injector.py    # A22: F4 defensive injection
│   │   │
│   │   ├── validation/                  # Layer 5: Validation & Security
│   │   │   ├── __init__.py
│   │   │   ├── security_scanner.py      # A23: Security pattern scan
│   │   │   ├── syntax_validator.py      # A24: AST syntax validation
│   │   │   ├── chain_validator.py       # A25: Chain validation
│   │   │   ├── config_validator.py      # A26: Config validation
│   │   │   ├── risk_calculator.py       # A27: Aggregate risk score
│   │   │   └── fix_suggester.py         # A28: Fix suggestions
│   │   │
│   │   ├── automation/                  # Layer 6: Automation
│   │   │   ├── __init__.py
│   │   │   ├── trigger_inferrer.py      # A29: Trigger inference
│   │   │   ├── action_inferrer.py       # A30: Action inference
│   │   │   ├── schedule_parser.py       # A31: Schedule parsing
│   │   │   ├── condition_extractor.py   # A32: Conditional logic
│   │   │   ├── automation_namer.py      # A33: Automation naming
│   │   │   └── workflow_serializer.py   # A34: Workflow serialization
│   │   │
│   │   ├── reasoning/                   # Layer 7: Reasoning
│   │   │   ├── __init__.py
│   │   │   ├── problem_detector.py      # A35: Problem type detection
│   │   │   ├── step_decomposer.py       # A36: Step decomposition
│   │   │   ├── template_reasoner.py     # A37: Template reasoning
│   │   │   ├── confidence_estimator.py  # A38: Confidence estimation
│   │   │   └── conclusion_extractor.py  # A39: Conclusion extraction
│   │   │
│   │   ├── verdict/                     # Layer 8: Verdict Engine (AI Arbiter)
│   │   │   ├── __init__.py
│   │   │   ├── deterministic_pipeline.py # A40: 7 deterministic tasks
│   │   │   ├── evidence_collector.py     # A41: Evidence collection
│   │   │   ├── consensus_resolver.py     # A42: Consensus resolution
│   │   │   └── verdict_engine.py         # A43: Binary YES/NO (AI)
│   │   │
│   │   └── infrastructure/              # Layer 9: Infrastructure
│   │       ├── __init__.py
│   │       ├── agent_runner.py           # A44: Execution with resilience
│   │       ├── health_monitor.py         # A45: Health tracking
│   │       ├── audit_logger.py           # A46: Decision auditing
│   │       └── circuit_breaker_manager.py # A47: Per-agent breakers
│   │
│   ├── patterns/                        # Design Patterns (existing, enhanced)
│   │   ├── __init__.py
│   │   ├── resilience/
│   │   │   ├── __init__.py
│   │   │   ├── circuit_breaker.py       # Existing → keep
│   │   │   ├── retry.py                 # Existing → keep
│   │   │   ├── bulkhead.py              # Existing → keep
│   │   │   └── sidecar.py              # Existing → keep
│   │   ├── behavioral/
│   │   │   ├── __init__.py
│   │   │   ├── strategy.py              # For agent selection
│   │   │   ├── state.py                 # For circuit breaker states
│   │   │   └── visitor.py               # For audit traversal
│   │   └── structural/
│   │       ├── __init__.py
│   │       ├── adapter.py               # For backward compatibility
│   │       ├── bridge.py                # For agent-transport bridge
│   │       └── proxy.py                 # For agent access control
│   │
│   ├── compatibility/                   # Backward Compatibility Shims
│   │   ├── __init__.py
│   │   ├── intent_agent_compat.py       # Old IntentAgent → new agents
│   │   ├── surgical_agent_compat.py     # Old SurgicalAgent → new agents
│   │   ├── reasoning_agent_compat.py    # Old ReasoningAgent → new agents
│   │   ├── business_agent_compat.py     # Old BusinessLogicAgent → new agents
│   │   ├── code_agent_compat.py         # Old CodeAgent → new agents
│   │   ├── context_agent_compat.py      # Old ContextAgent → new agents
│   │   ├── criticality_agent_compat.py  # Old CriticalityAgent → new agents
│   │   └── validation_agent_compat.py   # Old ValidationAgent → new agents
│   │
│   ├── shared/                          # Shared utilities (existing)
│   │   ├── __init__.py
│   │   ├── types.py
│   │   ├── contracts.py
│   │   ├── code_constraints.py
│   │   ├── sandbox_isolation.py
│   │   ├── structured_logging.py
│   │   ├── timeout.py
│   │   └── ...
│   │
│   ├── orchestrator.py                  # Main pipeline orchestrator
│   ├── mini_ai_engine.py               # Qwen3-0.6B loader (verdict only)
│   ├── semantic_engine.py              # Embeddings (evidence signal)
│   ├── smart_memory.py                 # Memory stores (existing)
│   └── ...
│
├── server/                             # HTTP API (existing)
│   └── ...
│
├── templates/                           # Code templates (existing)
│   └── ...
│
└── config/
    └── settings.yaml                    # Agent configuration
```

### 8.1 Key File: Single Agent Example (A01 IntentClassifier)

```python
# src/core/agents/understand/intent_classifier.py
"""
A01 IntentClassifier — Single Responsibility: Classify user intent.

Deterministic keyword scoring with weighted signals.
NEVER calls the LLM. Always produces a result.
Fallback: Default to SEARCH/FEATURE_ADD.
"""

import re
import time
import logging
from typing import Dict, Any, Optional
from dataclasses import dataclass

from ..base import BaseAgent, AgentResult
from ..schemas import IntentResult
from ..infrastructure.circuit_breaker_manager import CircuitBreakerManager
from ..infrastructure.audit_logger import AuditLogger
from ...patterns.resilience.retry import RetryConfig, with_retry
from ...patterns.resilience.bulkhead import Bulkhead

logger = logging.getLogger(__name__)

# === Deterministic keyword maps (bilingual EN/ES) ===
OP_KEYWORDS: Dict[str, Dict[str, float]] = {
    "CREATE":     {"create": 2.0, "new": 1.5, "add": 1.5, "implement": 1.0,
                   "crear": 2.0, "nuevo": 1.5, "agregar": 1.5, "generar": 1.0},
    "REFACTOR":   {"refactor": 2.0, "restructure": 1.5, "clean": 1.0,
                   "refactorizar": 2.0, "reestructurar": 1.5, "limpiar": 1.0},
    "DELETE":     {"delete": 2.0, "remove": 1.5, "eliminate": 1.0,
                   "eliminar": 2.0, "borrar": 1.5, "quitar": 1.0},
    "SEARCH":     {"search": 2.0, "find": 1.5, "where": 1.0,
                   "buscar": 2.0, "encontrar": 1.5, "donde": 1.0},
    "ANALYZE":    {"analyze": 2.0, "review": 1.5, "check": 1.0,
                   "analizar": 2.0, "revisar": 1.5, "verificar": 1.0},
    "EXPLAIN":    {"explain": 2.0, "describe": 1.5, "what": 1.0,
                   "explicar": 2.0, "describir": 1.5, "como": 1.0},
    "DEBUG":      {"debug": 2.0, "fix": 1.5, "bug": 1.5, "error": 1.0,
                   "depurar": 2.0, "arreglar": 1.5, "corregir": 1.0},
    "OPTIMIZE":   {"optimize": 2.0, "improve": 1.5, "faster": 1.0,
                   "optimizar": 2.0, "mejorar": 1.5, "acelerar": 1.0},
}

GOAL_KEYWORDS: Dict[str, Dict[str, float]] = {
    "BUG_FIX":             {"bug": 2.0, "fix": 1.5, "error": 1.0, "wrong": 1.0},
    "FEATURE_ADD":         {"add": 2.0, "new": 1.5, "feature": 1.5, "implement": 1.0},
    "SECURITY_HARDEN":     {"security": 2.0, "auth": 1.5, "token": 1.0, "crypto": 1.0},
    "PERFORMANCE":         {"optimize": 2.0, "fast": 1.5, "slow": 1.0, "performance": 1.5},
    "MODERN_PATTERN":      {"modern": 2.0, "update": 1.5, "upgrade": 1.0, "migrate": 1.0},
    "COMPLEXITY_REDUCTION": {"simplify": 2.0, "reduce": 1.5, "complex": 1.0},
    "READABILITY":         {"readable": 2.0, "clean": 1.5, "comment": 1.0, "document": 1.0},
}


class IntentClassifier(BaseAgent[IntentResult]):
    """
    A01: Classify user intent into (operation, goal).
    
    Single Responsibility: Intent classification ONLY.
    No entity extraction, no criticality, no caching.
    All deterministic. Never calls LLM.
    """
    
    def __init__(self):
        super().__init__(name="A01_IntentClassifier")
    
    def classify(self, text: str) -> IntentResult:
        """Main method: classify text into operation + goal."""
        start = time.time()
        
        text_lower = text.lower()
        words = set(text_lower.split())
        
        # Score each operation
        op_scores = {}
        for op, keywords in OP_KEYWORDS.items():
            score = sum(
                weight for kw, weight in keywords.items()
                if kw in words or kw in text_lower
            )
            op_scores[op] = score
        
        # Select best operation
        best_op = max(op_scores, key=op_scores.get)
        best_op_score = op_scores[best_op]
        
        # Score each goal
        goal_scores = {}
        for goal, keywords in GOAL_KEYWORDS.items():
            score = sum(
                weight for kw, weight in keywords.items()
                if kw in words or kw in text_lower
            )
            goal_scores[goal] = score
        
        best_goal = max(goal_scores, key=goal_scores.get)
        
        # Confidence: gap between 1st and 2nd
        sorted_ops = sorted(op_scores.values(), reverse=True)
        gap = sorted_ops[0] - sorted_ops[1] if len(sorted_ops) > 1 else sorted_ops[0]
        confidence = min(gap / max(best_op_score, 0.01), 1.0) if best_op_score > 0 else 0.1
        
        duration_ms = int((time.time() - start) * 1000)
        self._update_stats("deterministic", duration_ms)
        
        return IntentResult(
            operation=best_op if best_op_score > 0 else "SEARCH",
            goal=best_goal if goal_scores.get(best_goal, 0) > 0 else "FEATURE_ADD",
            confidence=confidence,
            source="deterministic",
        )
    
    def fallback(self, input_data: Any) -> IntentResult:
        """Safe default: SEARCH + FEATURE_ADD."""
        return IntentResult(
            operation="SEARCH",
            goal="FEATURE_ADD",
            confidence=0.1,
            source="fallback",
        )
    
    # Legacy BaseAgent interface (required by framework)
    def build_prompt(self, input_data: Any) -> tuple:
        return ("", str(input_data))  # Not used — deterministic only
    
    def parse_response(self, raw_response: str, input_data: Any) -> Optional[IntentResult]:
        return None  # Not used — deterministic only
```

---

## 9. BILINGUAL SUPPORT (EN/ES)

### 9.1 Single Point: A48 BilingualRouter

All bilingual logic is centralized in **A48 BilingualRouter**:

```python
class BilingualRouter:
    """
    A48: Detect language and provide bilingual keyword maps.
    
    Single Responsibility: Language detection + keyword routing.
    """
    
    # Unified keyword maps include both EN and ES terms
    KEYWORD_MAPS = {
        "operations": {
            "CREATE": ["create", "new", "add", "crear", "nuevo", "agregar"],
            "DELETE": ["delete", "remove", "eliminar", "borrar", "quitar"],
            "SEARCH": ["search", "find", "buscar", "encontrar", "localizar"],
            "DEBUG":  ["debug", "fix", "bug", "depurar", "arreglar", "corregir"],
            # ... all operations with EN+ES keywords
        },
        "criticality": {
            "critical_keywords": [
                "auth", "login", "password", "token", "payment", "stripe",
                "autenticacion", "contrasena", "pago", "seguridad",
            ],
            "moderate_keywords": [
                "api", "database", "config", "migration",
                "base de datos", "configuracion", "migracion",
            ],
        },
    }
    
    def detect_language(self, text: str) -> str:
        """Detect if text is primarily EN or ES."""
        es_markers = {"el", "la", "los", "las", "de", "en", "que", "un", "una",
                      "por", "para", "con", "sin", "sobre", "entre"}
        words = set(text.lower().split())
        es_count = len(words & es_markers)
        return "es" if es_count >= 2 else "en"
```

### 9.2 All Agents Use Unified Keyword Maps

Every agent's keyword matching includes both EN and ES terms directly in their keyword dictionaries. No separate translation step is needed — the matching is naturally bilingual.

---

## 10. BACKWARD COMPATIBILITY

### 10.1 Compatibility Adapter Layer

For each old agent, a thin compatibility shim preserves the old API:

```python
# src/core/compatibility/intent_agent_compat.py
"""
Backward-compatible IntentAgent that delegates to new single-responsibility agents.
"""

class IntentAgentCompat:
    """
    Drop-in replacement for old IntentAgent.
    Delegates to A01 IntentClassifier + A02 EntityExtractor + A03 TargetResolver.
    """
    
    def __init__(self, semantic_engine=None, smart_memory=None):
        self._classifier = IntentClassifier()
        self._extractor = EntityExtractor()
        self._resolver = TargetResolver()
    
    # Old API preserved
    def classify(self, message: str, context: str = "") -> IntentOutput:
        intent = self._classifier.classify(message)
        entities = self._extractor.extract(message)
        target = self._resolver.resolve(entities)
        return IntentOutput(
            operation=intent.operation,
            goal=intent.goal,
            target=target.target_file,
            language=target.language,
            entities=entities.to_dict(),
            confidence=intent.confidence,
            source=intent.source,
        )
    
    # Old wire() method preserved
    def wire(self, semantic_engine=None, smart_memory=None):
        pass  # No-op, new agents don't need wiring
```

### 10.2 Deprecation Timeline

| Phase | Duration | Action |
|-------|----------|--------|
| Phase 1 | Months 1-2 | Compatibility shims active, new agents in production |
| Phase 2 | Months 3-4 | Warning logs when old API is used |
| Phase 3 | Months 5-6 | Old API removed, shims deprecated |
| Phase 4 | Month 7+ | Clean architecture, no legacy code |

---

## APPENDIX A: AGENT COUNT SUMMARY

| Layer | Old Agent Count | Old Total Functions | New Agent Count | New Functions/Agent |
|-------|:-:|:-:|:-:|:-:|
| Understanding | 2 (Intent+Surgical) | 21 | 5 | 1 |
| Memory/Context | 1 (Context) | 10 | 4 | 1 |
| Business | 1 (BusinessLogic) | 11 | 8 | 1 |
| Code | 1 (Code) | 9 | 6 | 1 |
| Validation | 1 (Validation) | 7 | 6 | 1 |
| Automation | 1 (Automation) | 8 | 6 | 1 |
| Reasoning | 1 (Reasoning) | 12 | 5 | 1 |
| Verdict | 4 (subsystems) | 4 | 4 | 1 |
| Infrastructure | 1 (AgentRunner) | 7 | 4 | 1 |
| **TOTAL** | **13** | **89** | **48** | **1** |

### Duplication Eliminated

- **IntentAgent ↔ SurgicalAgent**: 6 duplicate functions → 0 duplicates
- **BusinessLogicAgent ↔ CriticalityAgent**: 2 overlapping functions → 0 overlaps
- **CodeAgent ↔ ValidationAgent**: 1 overlapping function → 0 overlaps
- **ReasoningAgent ↔ IntentAgent**: 1 overlapping function → 0 overlaps
- **Total duplicates removed: 10**

### AI Usage Reduction

| Metric | Old Architecture | New Architecture |
|--------|:-:|:-:|
| Agents that call LLM | 8 (all) | **1** (VerdictEngine only) |
| LLM call types | 7 bounded + 1 verdict | **1** (binary YES/NO only) |
| Max LLM calls per request | 10+ | **3** (consensus on tie) |
| System works without AI | Partially | **100%** |
| AI can produce wrong response | Yes (generative) | **Impossible** (binary parser) |
| Prompt injection risk | High | **Zero** (AI never sees raw input) |

---

## APPENDIX B: VERDICT ENGINE CONFIGURATION (UNCHANGED FROM v17.1)

The existing VerdictEngine architecture is preserved as-is:

```
4-Layer Architecture:
  Layer 1: SemanticEngine → UNDERSTAND (embeddings, similarity)
  Layer 2: DeterministicPipeline → DO (7 tasks without AI)
  Layer 3: EvidenceCollector + ConsensusResolver → PROVE and DECIDE
  Layer 4: MiniAIEngine (Qwen) → ARBITRATE (only YES/NO on ties)

Resilience (already implemented):
  ✓ Circuit Breaker: 3 failures → OPEN, 60s recovery
  ✓ Retry with exponential backoff: 3 attempts, base 1s, max 10s
  ✓ Health Monitor: sliding window 50 calls, threshold 0.3
  ✓ VerdictAuditor: circular buffer 200 entries
  ✓ Multi-attempt consensus: 3 calls, majority vote
  ✓ Veto system: security/sandbox → auto NO
  ✓ Auto-unload by idle (5min) and RAM pressure (768MB)

CHANGES in v18:
  - VerdictEngine is now the ONLY entry point for LLM calls
  - All agents route their "needs AI" decisions through A43
  - No agent can call MiniAIEngine directly
  - Evidence collection is richer (from all agents in pipeline)
```

---

*End of Architecture Document — ZENIC LOGIC v18 Single-Responsibility Design*
