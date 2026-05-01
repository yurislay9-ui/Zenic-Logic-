# ZENIC LOGIC - TITAN OMNISCALE X v13

## Motor de IA Quirúrgico Local - Edición Definitiva

Servidor OpenAI-Compatible para Cline, Aide, OpenCode y más. Funciona en Android/Termux.

### Arquitectura de 8 Niveles

| Nivel | Componente | Implementación |
|-------|-----------|---------------|
| L1 | Semantic Parser | TF-IDF + Cosine Similarity |
| L2 | Macro Router MoE | Clasificación de criticidad + firmas topológicas del AST |
| L3 | Graph AST Engine | AST nativo (Python) + regex (multi-lenguaje) + SQLite |
| L4 | APA Planner | Z3 SMT Solver (con fallback AC-3) + MCTS real |
| L5 | Structural Swarm | AST Surgeon + GitHub Scrap Agent |
| L6 | Reflexion Sandbox | Ejecución Simbólica Acotada + K-Path Limiting + Path Pruning |
| L7 | Merkle Ledger | Árbol Merkle + snapshots + rollback atómico |
| L8 | Theorem Cache | Skeleton Hash (destilación topológica) + lookup O(1) |

### Solver SMT

- **Con Z3 instalado** (`pip install z3-solver`): Verificación formal completa con teorías de enteros, arrays y cuantificadores
- **Sin Z3** (Android/Termux): Fallback automático a AC-3 + Backtracking CSP Solver

### Características Principales

- **Principio de Aislamiento Quirúrgico**: Solo aplica razonamiento profundo a nodos críticos (auth, crypto, DB)
- **MCTS Real**: UCB1, 4 fases (Selección, Expansión, Simulación, Backpropagation), depth limit 5
- **Ejecución Simbólica Real**: Estados simbólicos, path conditions, detección de violaciones
- **K-Paths desde Grafo**: Mide profundidad real de dependencias en el grafo AST
- **Protocolo Abortivo**: Auto-subdivisión automática cuando el solver hace timeout
- **Razonamiento Parcial**: Response contract OpenAI-compatible con `tool_calls`
- **Timeout Enforcement Real**: `threading.Event` (compatible Android)
- **Caché de Teoremas**: Skeleton Hash para bypass O(1) en mutaciones repetidas
- **Configuración YAML**: Timeouts, K-Paths, nodos críticos configurables sin tocar código

### Configuración

Editar archivos en `src/config/`:
- `settings.yaml`: Configuración general (timeouts, directorio del proyecto)
- `timeouts.yaml`: Presupuestos computacionales (Z3, MCTS, K-Paths)
- `critical_nodes.yaml`: Patrones de nodos críticos

### Uso

```bash
# Instalar dependencias
pip install kivy

# Opcional: instalar Z3 para verificación formal completa
pip install z3-solver

# Ejecutar
python main.py
```

### API Endpoints

- `GET /v1/models` - Lista modelos disponibles
- `POST /v1/chat/completions` - Chat completion (OpenAI-compatible)
- `GET /health` - Health check

### Conectar Cline/Aide

1. Inicia el motor
2. En VS Code, configura Cline:
   - API Provider: OpenAI Compatible
   - Base URL: `http://TU_IP:5000/v1`
   - Model: `titan-omniscale-x`
