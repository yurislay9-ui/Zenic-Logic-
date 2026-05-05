"""
TITAN OMNISCALE X - MiniAIEngine (Qwen3-0.6B Q4_K_M)

Motor de RAZONAMIENTO - La base de pensamiento del sistema.

Arquitectura de 3 capas:
  Capa 1: SemanticEngine → ENTIENDE (embeddings, similitud, clasificación)
  Capa 2: MiniAIEngine (Qwen) → PIENSA (razonamiento, generación, código)  ← ESTE
  Capa 3: SmartMemory → RECUERDA (cache semántico, contexto, aprendizaje)

Qwen es el MOTOR PRINCIPAL de razonamiento. NO hace semántica (para eso
está SemanticEngine). Qwen hace lo que SemanticEngine NO puede:
  - Razonar sobre código
  - Generar snippets
  - Explicar violaciones en lenguaje natural
  - Sugerir nombres descriptivos
  - Rellenar templates con lógica

7 Tareas Bounded (max ~50 tokens/call):
  1. classify_intent()     ~10 tokens - Razonar sobre intención (backup de SemanticEngine)
  2. extract_entities()    ~20 tokens - Extraer entidades (backup de regex)
  3. suggest_pattern()     ~30 tokens - Sugerir patrón de reemplazo
  4. fill_template_gaps()  ~50 tokens - Rellenar huecos de template
  5. generate_pattern()    ~20 lines  - Generar snippet de patrón
  6. explain_violation()   ~50 tokens - Explicar violación del sandbox
  7. describe_subtask()    ~30 tokens - Describir subtask

Cada método tiene FALLBACK DETERMINÍSTICO que funciona sin modelo.
Si el modelo falla, timeout, o da mala respuesta → fallback automático.

Optimizado para:
  - Xiaomi Redmi 12R Pro (12+8GB, MediaTek Dimensity 6100+)
  - Qwen3-0.6B Q4_K_M (378MB, ~25-30 tok/s en ARM)
  - llama-cpp-python con n_ctx=2048, n_threads=4
"""

from .mini_ai_parts import *  # noqa: F401,F403
from .mini_ai_parts import MiniAIEngine, IntentResult  # noqa: F401

__all__ = [
    "MiniAIEngine", "IntentResult",
    "MODEL_DIR", "MODEL_FILENAME", "MODEL_PATH",
    "MAX_TOKENS_CLASSIFY", "MAX_TOKENS_EXTRACT", "MAX_TOKENS_PATTERN",
    "MAX_TOKENS_TEMPLATE", "MAX_TOKENS_GENERATE", "MAX_TOKENS_EXPLAIN",
    "MAX_TOKENS_SUBTASK", "LLM_TIMEOUT_S", "N_CTX", "N_THREADS", "TEMPERATURE",
]
