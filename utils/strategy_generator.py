"""
AI Strategy Generator utilities
"""
import ast
import re
from config.settings import OLLAMA_BASE_URL, OLLAMA_MODEL_GENERATION, OLLAMA_OPTIONS
from utils.ollama_client import OllamaClient


class StrategyGenerator:
    """Handles AI strategy generation logic"""

    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL_GENERATION):
        self.ollama = OllamaClient(base_url=base_url, model=model, options=OLLAMA_OPTIONS)

    def update_ollama_settings(self, base_url: str, model: str, options: dict | None = None) -> None:
        self.ollama.update_settings(base_url=base_url, model=model, options=options)

    def generate_strategy_code(self, user_idea: str) -> str:
        if not user_idea or not user_idea.strip():
            raise ValueError("Strategy description is empty")

        if not self.ollama.is_available():
            raise RuntimeError("Ollama is not available. Start it with: ollama serve")

        idea = user_idea.strip()
        code = self.ollama.generate_strategy(idea)
        if not code or not isinstance(code, str):
            raise RuntimeError("Ollama returned empty response")

        code = self._clean_code(code)
        ok, err = self._validate_strategy_code(code)
        if ok:
            return code

        repaired = self.ollama.repair_strategy_code(idea, code, err)
        repaired = self._clean_code(repaired)
        ok2, err2 = self._validate_strategy_code(repaired)
        if not ok2:
            raise RuntimeError(f"Ollama generated invalid strategy code after repair: {err2}")
        return repaired

    def clean_code(self, text: str) -> str:
        return self._clean_code(text)

    def validate_strategy_code(self, code: str):
        return self._validate_strategy_code(code)

    def _clean_code(self, text: str) -> str:
        # Remove markdown fences if the model accidentally returned them.
        t = text.strip()
        if t.startswith("```"):
            t = re.sub(r"^```[a-zA-Z0-9_+-]*\s*\n", "", t)
            t = re.sub(r"\n```\s*$", "", t)
        return t.strip() + "\n"

    def _validate_strategy_code(self, code: str):
        try:
            tree = ast.parse(code)
        except Exception as e:
            return False, f"Syntax error: {e}"

        def _is_istrategy_base(base: ast.expr) -> bool:
            if isinstance(base, ast.Name):
                return base.id == "IStrategy"
            if isinstance(base, ast.Attribute):
                return base.attr == "IStrategy"
            return False

        candidates: list[ast.ClassDef] = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            if any(_is_istrategy_base(b) for b in node.bases):
                candidates.append(node)

        if not candidates:
            return False, "Missing required strategy class inheriting from IStrategy"

        required = {"populate_indicators", "populate_entry_trend", "populate_exit_trend"}
        best_error = None
        for cls in candidates:
            present = set()
            for node in cls.body:
                if isinstance(node, ast.FunctionDef):
                    present.add(node.name)

            missing = sorted(list(required - present))
            if not missing:
                return True, ""
            best_error = f"Strategy class {cls.name} missing required methods: {', '.join(missing)}"

        return False, str(best_error or "No valid IStrategy class found")
