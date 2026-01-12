"""
AI Strategy Generator utilities
"""
import ast
import re
from typing import Any
from config.settings import OLLAMA_BASE_URL, OLLAMA_MODEL_GENERATION, OLLAMA_OPTIONS
from utils.ollama_client import OllamaClient


class StrategyGenerator:
    """Handles AI strategy generation logic"""

    def __init__(self, base_url: str = OLLAMA_BASE_URL, model: str = OLLAMA_MODEL_GENERATION):
        self.ollama = OllamaClient(base_url=base_url, model=model, options=OLLAMA_OPTIONS)

    def set_ai_client(self, client: Any) -> None:
        self.ollama = client

    def update_ollama_settings(self, base_url: str, model: str, options: dict | None = None) -> None:
        self.ollama.update_settings(base_url=base_url, model=model, options=options)

    def generate_strategy_code(self, user_idea: str) -> str:
        if not user_idea or not user_idea.strip():
            raise ValueError("Strategy description is empty")

        if not self.ollama.is_available():
            raise RuntimeError("AI provider is not available. Configure it in Settings.")

        idea = user_idea.strip()
        code = self.ollama.generate_strategy(idea)
        if not code or not isinstance(code, str):
            raise RuntimeError("AI returned empty response")

        code = self._clean_code(code)
        code = self._upgrade_legacy_signals(code)
        ok, err = self._validate_strategy_code(code)
        if ok:
            return code

        repaired = self.ollama.repair_strategy_code(idea, code, err)
        repaired = self._clean_code(repaired)
        repaired = self._upgrade_legacy_signals(repaired)
        ok2, err2 = self._validate_strategy_code(repaired)
        if not ok2:
            repaired2 = self.ollama.repair_strategy_code(idea, repaired, err2)
            repaired2 = self._clean_code(repaired2)
            repaired2 = self._upgrade_legacy_signals(repaired2)
            ok3, err3 = self._validate_strategy_code(repaired2)
            if not ok3:
                raise RuntimeError(f"Ollama generated invalid strategy code after repair: {err3}")
            return repaired2
        return repaired

    def clean_code(self, text: str) -> str:
        return self._clean_code(text)

    def upgrade_legacy_signals(self, code: str) -> str:
        return self._upgrade_legacy_signals(code)

    def validate_strategy_code(self, code: str):
        return self._validate_strategy_code(code)

    def _clean_code(self, text: str) -> str:
        t = (text or "").strip().lstrip("\ufeff")

        m = re.search(r"```(?:python)?\s*\n(.*?)\n```", t, flags=re.IGNORECASE | re.DOTALL)
        if m:
            t = str(m.group(1) or "").strip()
        else:
            if t.startswith("```"):
                t = re.sub(r"^```[a-zA-Z0-9_+-]*\s*\n", "", t)
                t = re.sub(r"\n```\s*$", "", t)

        t = re.sub(r"^\s*(CODE_CHANGE|CODE)\s*:\s*\n", "", t, flags=re.IGNORECASE)

        start = re.search(r"^(?:\s*(?:#|\"\"\"|'''|from\s+|import\s+|class\s+|@))", t, flags=re.MULTILINE)
        if start:
            t = t[start.start():]

        return t.strip() + "\n"

    def _upgrade_legacy_signals(self, code: str) -> str:
        if not isinstance(code, str) or not code.strip():
            return code

        has_entry = bool(re.search(r"^\s*def\s+populate_entry_trend\s*\(", code, flags=re.MULTILINE))
        has_exit = bool(re.search(r"^\s*def\s+populate_exit_trend\s*\(", code, flags=re.MULTILINE))
        has_buy = bool(re.search(r"^\s*def\s+populate_buy_trend\s*\(", code, flags=re.MULTILINE))
        has_sell = bool(re.search(r"^\s*def\s+populate_sell_trend\s*\(", code, flags=re.MULTILINE))

        out = code
        if not has_entry and has_buy:
            out = re.sub(
                r"(^\s*def\s+)populate_buy_trend(\s*\()",
                r"\1populate_entry_trend\2",
                out,
                flags=re.MULTILINE,
            )
        if not has_exit and has_sell:
            out = re.sub(
                r"(^\s*def\s+)populate_sell_trend(\s*\()",
                r"\1populate_exit_trend\2",
                out,
                flags=re.MULTILINE,
            )

        out = re.sub(r"(dataframe\s*\[\s*['\"])buy(['\"]\s*\])", r"\1enter_long\2", out)
        out = re.sub(r"(dataframe\s*\[\s*['\"])sell(['\"]\s*\])", r"\1exit_long\2", out)
        out = re.sub(r"(dataframe\.loc\[[^\]]*,\s*['\"])buy(['\"]\s*\])", r"\1enter_long\2", out)
        out = re.sub(r"(dataframe\.loc\[[^\]]*,\s*['\"])sell(['\"]\s*\])", r"\1exit_long\2", out)

        return out

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
