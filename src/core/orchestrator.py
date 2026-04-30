from pathlib import Path
from src.config.loader import load_settings
from src.core.shared.db_initializer import initialize_databases
from src.core.level1_semantic_engine.parser import SemanticParser
from src.core.level2_macro_router.router import MacroRouter
from src.core.level3_graph_ast.engine import GraphASTEngine
from src.core.level4_apa_planner.planner import APAPlanner
from src.core.level5_structural_swarm.scrap_agent import GitHubScrapAgent
from src.core.level5_structural_swarm.ast_surgeon import ASTSurgeon
from src.core.level6_reflexion_sandbox.executor import ReflexionSandbox
from src.core.level7_merkle_ledger.ledger import MerkleLedger
from src.core.level8_theorem_cache.cache import TheoremCache

class TitanOrchestrator:
    def __init__(self):
        initialize_databases()
        self.settings = load_settings()
        self.p_dir = self.settings.get("project_dir", ".")

        self.parser = SemanticParser()
        self.router = MacroRouter()
        self.ast = GraphASTEngine()
        self.planner = APAPlanner()
        self.scrap = GitHubScrapAgent()
        self.surgeon = ASTSurgeon()
        self.sandbox = ReflexionSandbox()
        self.ledger = MerkleLedger()
        self.cache = TheoremCache()

        self.ast.scan_project(self.p_dir)

    async def execute(self, msg: str) -> dict:
        # N1 & N8
        intent = self.parser.parse(msg)
        if self.cache.lookup(intent): return {"status": "CACHED", "code": "// Servido desde Caché O(1)"}

        # N2 & N4
        routing = self.router.route(intent)
        plan = self.planner.generate_plan(routing)

        # N5
        code, lang = "", "python"
        if ".kt" in intent.target: lang = "kotlin"
        elif ".go" in intent.target: lang = "go"

        for step in plan.steps:
            if step.action == "SCRAPE_GITHUB": code = await self.scrap.fetch_modern_code(step.constraints.get("query",""), lang)
            elif step.action == "REPLACE_AST_NODE":
                try:
                    file_path = Path(f"{self.p_dir}/{intent.target}")
                    source_code = file_path.read_text(encoding="utf-8") if file_path.exists() else ""
                    code = self.surgeon.mutate_node(source_code, step.target_node_name, "// OPT\n", lang)
                except Exception:
                    code = "// NEW"

        if not code:
            return {"status": "NO_OP", "code": "", "error": "No new code generated"}

        # N7 (Snap) -> N6 (Trial) -> N7 (Commit/Rollback)
        self.ledger.snapshot(intent.target, self.p_dir)
        trial = await self.sandbox.validate_code(code, lang, intent.target)

        if trial.status == "PASS":
            node = self.ledger.commit(intent.target, code, self.p_dir)
            self.cache.save(intent, "PROVEN", {"h": node.hash_sha256[:8]})
            return {"status": "SUCCESS", "code": code, "hash": node.hash_sha256[:12]}
        else:
            self.ledger.rollback(intent.target, self.p_dir)
            return {"status": "ROLLBACK", "code": code, "error": trial.error_message}
