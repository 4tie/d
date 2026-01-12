"""
Strategy service for orchestrating AI strategy operations
"""
import os
import re
import time
import ast
import json
from utils.ollama_client import OllamaClient
from utils.strategy_generator import StrategyGenerator
from utils.strategy_saver import StrategySaver
from utils.backtest_runner import run_backtest, summarize_backtest_data, build_trade_forensics
from utils.performance_store import AIPerformanceStore
from config.settings import BOT_CONFIG_PATH, STRATEGY_DIR

class StrategyService:
    """Service layer for strategy generation and saving operations"""
    
    def __init__(self):
        self.generator = StrategyGenerator()
        self.ollama_client = self.generator.ollama
        self.analysis_client = OllamaClient(base_url=self.generator.ollama.base_url, model=self.generator.ollama.model, options=self.generator.ollama.options)
        self.risk_client = OllamaClient(base_url=self.generator.ollama.base_url, model=self.generator.ollama.model, options=self.generator.ollama.options)
        self.chat_client = OllamaClient(base_url=self.generator.ollama.base_url, model=self.generator.ollama.model, options=self.generator.ollama.options)
        self.repair_client = OllamaClient(base_url=self.generator.ollama.base_url, model=self.generator.ollama.model, options=self.generator.ollama.options)
        self.repair_fallback_client: OllamaClient | None = None
        self.refine_client = OllamaClient(base_url=self.generator.ollama.base_url, model=self.generator.ollama.model, options=self.generator.ollama.options)
        self.refine_fallback_client: OllamaClient | None = None
        self.saver = StrategySaver()
        self.performance_store = AIPerformanceStore()

    def update_ollama_settings(self, base_url: str, model: str, options: dict | None = None, task_models: dict | None = None) -> None:
        generation_model = model
        analysis_model = model
        risk_model = model
        chat_model = model
        repair_model = model
        repair_fallback_model = ""
        refine_model = model
        refine_fallback_model = ""
        if isinstance(task_models, dict):
            generation_model = str(task_models.get("strategy_generation") or generation_model)
            analysis_model = str(task_models.get("strategy_analysis") or analysis_model)
            risk_model = str(task_models.get("risk_assessment") or risk_model)
            chat_model = str(task_models.get("chat") or chat_model)
            repair_model = str(task_models.get("strategy_repair") or repair_model)
            repair_fallback_model = str(task_models.get("strategy_repair_fallback") or "")
            refine_model = str(task_models.get("strategy_refine") or refine_model)
            refine_fallback_model = str(task_models.get("strategy_refine_fallback") or "")

        self.generator.update_ollama_settings(base_url=base_url, model=generation_model, options=options)
        self.analysis_client.update_settings(base_url=base_url, model=analysis_model, options=options)
        self.risk_client.update_settings(base_url=base_url, model=risk_model, options=options)
        self.chat_client.update_settings(base_url=base_url, model=chat_model, options=options)
        self.repair_client.update_settings(base_url=base_url, model=repair_model, options=options)
        if repair_fallback_model.strip():
            if self.repair_fallback_client is None:
                self.repair_fallback_client = OllamaClient(base_url=base_url, model=repair_fallback_model.strip(), options=options)
            else:
                self.repair_fallback_client.update_settings(base_url=base_url, model=repair_fallback_model.strip(), options=options)
        else:
            self.repair_fallback_client = None

        self.refine_client.update_settings(base_url=base_url, model=refine_model, options=options)
        if refine_fallback_model.strip():
            if self.refine_fallback_client is None:
                self.refine_fallback_client = OllamaClient(base_url=base_url, model=refine_fallback_model.strip(), options=options)
            else:
                self.refine_fallback_client.update_settings(base_url=base_url, model=refine_fallback_model.strip(), options=options)
        else:
            self.refine_fallback_client = None

    def chat(
        self,
        message: str,
        history: list[dict] | None = None,
        strategy_code: str | None = None,
        context: dict | None = None,
    ) -> dict:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message is required")

        if not self.chat_client.is_available():
            raise RuntimeError("Ollama is not available. Start it with: ollama serve")

        msgs: list[dict] = []
        if isinstance(history, list):
            for m in history[-60:]:
                if not isinstance(m, dict):
                    continue
                role = str(m.get("role") or "").strip().lower()
                content = str(m.get("content") or "").strip()
                if role not in ("user", "assistant"):
                    continue
                if not content:
                    continue
                msgs.append({"role": role, "content": content})

        strategy_snip = ""
        facts_json = ""
        if isinstance(strategy_code, str) and strategy_code.strip():
            cleaned_full = self.generator.clean_code(strategy_code)
            cleaned_full = self.generator.upgrade_legacy_signals(cleaned_full)
            strategy_snip = cleaned_full[:8000]
            try:
                facts = self._extract_strategy_facts_from_code(cleaned_full)
            except Exception as e:
                facts = {"parse_error": str(e)}
            try:
                facts_json = json.dumps(facts, indent=2, ensure_ascii=False)
            except Exception:
                facts_json = str(facts)

        ctx_lines: list[str] = []
        if isinstance(context, dict):
            for k in (
                "selected_filename",
                "active_strategy",
                "timeframe",
                "last_backtest_profit_pct",
                "last_backtest_max_dd_pct",
                "last_backtest_total_trades",
                "last_backtest_trades_per_day",
            ):
                v = context.get(k)
                if v is None:
                    continue
                s = str(v).strip()
                if not s:
                    continue
                ctx_lines.append(f"{k}: {s}")
        ctx_txt = "\n".join(ctx_lines).strip()

        hist_txt = "\n".join(
            [
                ("USER: " + m["content"]) if m["role"] == "user" else ("4tiee: " + m["content"])
                for m in msgs
            ]
        ).strip()

        prompt = (
            "You are 4tiee, an expert Freqtrade strategy assistant.\n"
            "Answer clearly and concisely.\n"
            "Do not invent facts. If you lack data, say what is missing and ask a precise follow-up question.\n"
        )

        if ctx_txt:
            prompt += "\nUI context:\n" + ctx_txt + "\n"

        if facts_json:
            prompt += (
                "\nVERIFIED_STRATEGY_FACTS (extracted from the strategy code; authoritative):\n"
                + facts_json[:8000]
                + "\n"
                + "Rules:\n"
                + "- If a parameter value is not present above, say it is not provided.\n"
                + "- minimal_roi values are decimals (0.05 means 5%).\n"
                + "- stoploss is a negative decimal (-0.10 means -10%).\n"
                + "- If the value is an expr/parameter object, do NOT guess the numeric value.\n"
            )

        last_bt = None
        last_tf = None
        if isinstance(context, dict):
            last_bt = context.get("last_backtest_summary")
            last_tf = context.get("last_trade_forensics")

        if isinstance(last_bt, dict) or isinstance(last_tf, dict):
            blob = {"backtest_summary": last_bt, "trade_forensics": last_tf}
            try:
                prompt += "\nLAST_BACKTEST_JSON (from local performance store):\n" + json.dumps(blob, indent=2, ensure_ascii=False)[:8000] + "\n"
            except Exception:
                pass

        kb_query = "\n".join(
            [
                "freqtrade strategy chat",
                message.strip()[:2000],
                strategy_snip[:2000] if strategy_snip else "",
                hist_txt[:2000] if hist_txt else "",
            ]
        ).strip()
        kb_context = ""
        try:
            kb_context = str(self.chat_client._build_kb_context(kb_query) or "").strip()
        except Exception:
            kb_context = ""

        if kb_context:
            prompt += "\nKnowledge base context (retrieved from local docs):\n" + kb_context + "\n"

        if strategy_snip:
            prompt += "\nCurrent strategy code (may be partial):\n" + strategy_snip + "\n"

        if hist_txt:
            prompt += "\nConversation so far:\n" + hist_txt + "\n"

        prompt += "\nUSER: " + message.strip() + "\n4tiee:"

        reply = self.chat_client.generate_text(prompt, use_cache=False)
        reply = str(reply or "").strip()
        if not reply:
            raise RuntimeError("AI chat returned empty response")

        return {"reply": reply, "model_used": str(getattr(self.chat_client, "model", "") or "")}

    def repair_strategy_code(self, code: str, user_idea: str = "") -> dict:
        if not isinstance(code, str) or not code.strip():
            raise ValueError("code is required")

        if not self.repair_client.is_available():
            raise RuntimeError("Ollama is not available. Start it with: ollama serve")

        idea = str(user_idea or "").strip() or "repair"
        gen = self.generator

        cleaned = gen.clean_code(code)
        cleaned = gen.upgrade_legacy_signals(cleaned)

        ok, err = gen.validate_strategy_code(cleaned)
        if ok:
            return {
                "strategy_code": cleaned,
                "repaired": False,
                "original_error": "",
                "validation": {"ok": True, "error": ""},
            }

        original_error = str(err or "")
        current_code = cleaned
        current_error = original_error

        clients: list[OllamaClient] = [self.repair_client]
        if self.repair_fallback_client is not None:
            clients.append(self.repair_fallback_client)

        request_errors: list[str] = []

        for client in clients:
            for _attempt in range(2):
                try:
                    repaired_raw = client.repair_strategy_code(idea, current_code, current_error)
                except Exception as e:
                    request_errors.append(f"model={getattr(client, 'model', '')}: {e}")
                    break

                repaired = gen.clean_code(repaired_raw)
                repaired = gen.upgrade_legacy_signals(repaired)
                ok2, err2 = gen.validate_strategy_code(repaired)
                if ok2:
                    return {
                        "strategy_code": repaired,
                        "repaired": True,
                        "original_error": original_error,
                        "validation": {"ok": True, "error": ""},
                        "model_used": str(getattr(client, "model", "") or ""),
                    }

                current_code = repaired
                current_error = str(err2 or "")

        if request_errors and not clients:
            raise RuntimeError("Ollama request failed: " + " | ".join(request_errors))

        if request_errors and current_error == original_error:
            # If all requests failed before we even got a new validation error, expose the request errors.
            current_error = original_error + " | " + " | ".join(request_errors)

        return {
            "strategy_code": current_code,
            "repaired": True,
            "original_error": original_error,
            "validation": {"ok": False, "error": current_error},
            "model_used": str(getattr(self.repair_client, "model", "") or ""),
        }
    
    def generate_strategy_code(self, user_idea: str) -> str:
        if not user_idea or not user_idea.strip():
            raise ValueError("Strategy description is empty")

        return self.generator.generate_strategy_code(user_idea)
    
    def save_strategy_code(self, code: str, filename: str = "AIStrategy.py") -> bool:
        if not code or not code.strip():
            raise ValueError("No strategy code to save")

        return self.saver.save_strategy(code, filename=filename)

    @staticmethod
    def _safe_selected_filename(filename: str) -> str:
        fn = str(filename or "").strip()
        if not fn:
            raise ValueError("selected_filename is required")
        base = os.path.basename(fn)
        if base != fn:
            raise ValueError("selected_filename must be a filename (no directories)")
        if not base.lower().endswith(".py"):
            raise ValueError("selected_filename must end with .py")
        return base

    @staticmethod
    def _score_backtest_summary(
        summary: dict | None,
        trade_forensics: dict | None = None,
        *,
        min_trades_per_day: float | None = None,
        require_min_trades_per_day: bool = False,
        max_fee_dominated_fraction: float | None = None,
        min_edge_to_fee_ratio: float | None = None,
    ) -> float:
        if not isinstance(summary, dict):
            return -10**18
        metrics = summary.get("metrics") if isinstance(summary.get("metrics"), dict) else {}

        profit = metrics.get("profit_total_pct")
        dd = metrics.get("max_drawdown_pct")
        trades = metrics.get("total_trades")
        if trades is None:
            trades = metrics.get("trades")
        if trades is None:
            trades = metrics.get("trade_count")

        if dd is None and isinstance(trade_forensics, dict):
            ra = trade_forensics.get("risk_adjusted") if isinstance(trade_forensics.get("risk_adjusted"), dict) else {}
            dd = ra.get("max_drawdown_pct")

        try:
            profit_f = float(profit)
        except Exception:
            return -10**18

        try:
            dd_f = float(dd) if dd is not None else 0.0
        except Exception:
            dd_f = 0.0

        try:
            trades_i = int(trades) if trades is not None else None
        except Exception:
            trades_i = None

        if trades_i is not None and trades_i <= 0:
            return -10**18

        score = profit_f - (abs(dd_f) * 0.5)

        trades_per_day = None
        fee_dominated_fraction = None
        edge_to_fee_ratio = None

        if isinstance(trade_forensics, dict):
            tfreq = trade_forensics.get("trade_frequency") if isinstance(trade_forensics.get("trade_frequency"), dict) else {}
            avg_tpd = tfreq.get("avg_trades_per_day")
            try:
                trades_per_day = float(avg_tpd) if avg_tpd is not None else None
            except Exception:
                trades_per_day = None

            if trades_per_day is None and trades_i is not None:
                range_days = tfreq.get("range_days")
                try:
                    range_days_i = int(range_days) if range_days is not None else None
                except Exception:
                    range_days_i = None
                if isinstance(range_days_i, int) and range_days_i > 0:
                    trades_per_day = trades_i / float(range_days_i)

            fs = trade_forensics.get("fee_sensitivity") if isinstance(trade_forensics.get("fee_sensitivity"), dict) else {}
            fd = fs.get("fee_dominated_fraction")
            etf = fs.get("edge_to_fee_ratio")
            try:
                fee_dominated_fraction = float(fd) if fd is not None else None
            except Exception:
                fee_dominated_fraction = None
            try:
                edge_to_fee_ratio = float(etf) if etf is not None else None
            except Exception:
                edge_to_fee_ratio = None

        if min_trades_per_day is not None:
            try:
                min_tpd_f = float(min_trades_per_day)
            except Exception:
                min_tpd_f = None

            if isinstance(min_tpd_f, (int, float)) and min_tpd_f > 0:
                if trades_per_day is None:
                    if require_min_trades_per_day:
                        return -10**18
                    score -= 5.0
                elif trades_per_day < min_tpd_f:
                    if require_min_trades_per_day:
                        return -10**18
                    score -= (min_tpd_f - trades_per_day) * 2.0

        if max_fee_dominated_fraction is not None:
            try:
                max_fd_f = float(max_fee_dominated_fraction)
            except Exception:
                max_fd_f = None

            if isinstance(max_fd_f, (int, float)) and max_fd_f >= 0:
                if fee_dominated_fraction is None:
                    score -= 2.0
                elif fee_dominated_fraction > max_fd_f:
                    score -= (fee_dominated_fraction - max_fd_f) * 50.0

        if min_edge_to_fee_ratio is not None:
            try:
                min_etf_f = float(min_edge_to_fee_ratio)
            except Exception:
                min_etf_f = None

            if isinstance(min_etf_f, (int, float)) and min_etf_f > 0:
                if edge_to_fee_ratio is None:
                    score -= 2.0
                elif edge_to_fee_ratio < min_etf_f:
                    score -= (min_etf_f - edge_to_fee_ratio) * 5.0

        return score

    def _next_optimized_filename(self, selected_filename: str) -> str:
        base = self._safe_selected_filename(selected_filename)
        stem, _ext = os.path.splitext(base)
        ts = time.strftime("%Y%m%d_%H%M%S")
        candidate = f"{stem}_aiopt_{ts}.py"

        strategy_dir = str(STRATEGY_DIR or "").strip() or "./user_data/strategies"
        os.makedirs(strategy_dir, exist_ok=True)

        out = candidate
        n = 1
        while os.path.exists(os.path.join(strategy_dir, out)):
            out = f"{stem}_aiopt_{ts}_{n}.py"
            n += 1
            if n > 2000:
                raise RuntimeError("failed to generate unique optimized filename")
        return out

    @staticmethod
    def _extract_strategy_class_name(strategy_code: str) -> str:
        m = re.search(
            r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(.*IStrategy.*\)\s*:\s*$",
            str(strategy_code or ""),
            flags=re.MULTILINE,
        )
        if not m:
            raise RuntimeError("Could not detect strategy class name inheriting from IStrategy")
        return str(m.group(1) or "").strip()

    @staticmethod
    def _rename_strategy_class(strategy_code: str, new_class_name: str) -> str:
        new_name = str(new_class_name or "").strip()
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", new_name):
            raise ValueError("new_class_name must be a valid Python identifier")

        pat = re.compile(
            r"^(\s*class\s+)([A-Za-z_][A-Za-z0-9_]*)(\s*\(.*IStrategy.*\)\s*:\s*)$",
            flags=re.MULTILINE,
        )
        matches = list(pat.finditer(str(strategy_code or "")))
        if len(matches) != 1:
            raise RuntimeError("Expected exactly one IStrategy class definition to rename")

        m = matches[0]
        old = m.group(2)
        if old == new_name:
            return str(strategy_code)

        code = str(strategy_code)
        return code[: m.start(2)] + new_name + code[m.end(2) :]

    @staticmethod
    def _extract_strategy_facts_from_code(strategy_code: str) -> dict:
        if not isinstance(strategy_code, str) or not strategy_code.strip():
            return {}

        try:
            tree = ast.parse(strategy_code)
        except Exception as e:
            return {"parse_error": str(e)}

        strat_cls = None
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                bases_src = [(ast.get_source_segment(strategy_code, b) or "") for b in node.bases]
                if any("IStrategy" in s for s in bases_src):
                    strat_cls = node
                    break

        if strat_cls is None:
            return {"parse_error": "No class inheriting from IStrategy found"}

        allowed = {
            "timeframe",
            "minimal_roi",
            "stoploss",
            "trailing_stop",
            "trailing_stop_positive",
            "trailing_stop_positive_offset",
            "trailing_only_offset_is_reached",
            "use_exit_signal",
            "exit_profit_only",
            "ignore_roi_if_entry_signal",
            "startup_candle_count",
            "process_only_new_candles",
            "can_short",
            "order_types",
            "order_time_in_force",
        }

        facts: dict = {"strategy_class": strat_cls.name}

        def _record(name: str, value_node: ast.AST) -> None:
            try:
                facts[name] = ast.literal_eval(value_node)
            except Exception:
                expr = (ast.get_source_segment(strategy_code, value_node) or "").strip()
                facts[name] = {"expr": expr or None}

        for stmt in strat_cls.body:
            if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                name = stmt.targets[0].id
                if name in allowed:
                    _record(name, stmt.value)
            elif isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                name = stmt.target.id
                if name in allowed and stmt.value is not None:
                    _record(name, stmt.value)

        return facts

    def optimize_strategy_with_backtest_loop(
        self,
        *,
        strategy_code: str,
        selected_filename: str,
        user_goal: str = "",
        max_iterations: int = 3,
        timerange: str | None = None,
        timeframe: str | None = None,
        pairs: str | None = None,
        fee: float | None = None,
        dry_run_wallet: float | None = None,
        max_open_trades: int | None = None,
        min_trades_per_day: float | None = None,
        require_min_trades_per_day: bool = False,
        max_fee_dominated_fraction: float | None = None,
        min_edge_to_fee_ratio: float | None = None,
        job=None,
    ) -> dict:
        if not strategy_code or not str(strategy_code).strip():
            raise ValueError("Strategy code is empty")

        selected_filename = self._safe_selected_filename(selected_filename)

        if max_iterations < 1:
            raise ValueError("max_iterations must be >= 1")
        if max_iterations > 5:
            raise ValueError("max_iterations is capped at 5")

        if not self.refine_client.is_available():
            base = str(getattr(self.refine_client, "base_url", "") or "").strip()
            model = str(getattr(self.refine_client, "model", "") or "").strip()
            hint = (
                "Hint: ensure Ollama is running ('ollama serve'), the Ollama URL/model in Settings are correct, "
                "and the model is pulled ('ollama pull <model>')."
            )
            raise RuntimeError(f"Ollama is not available (url='{base}', model='{model}'). {hint}")

        goal = (user_goal or "").strip()
        if not goal:
            goal = "Improve backtest profitability while controlling drawdown. Make minimal, testable changes."

        code = self.generator.clean_code(str(strategy_code))
        code = self.generator.upgrade_legacy_signals(code)
        ok, err = self.generator.validate_strategy_code(code)
        if not ok:
            repaired_in = self.repair_strategy_code(code, goal or "optimize")
            v = repaired_in.get("validation") if isinstance(repaired_in, dict) else None
            if not (isinstance(v, dict) and bool(v.get("ok"))):
                raise RuntimeError(f"Invalid input strategy code: {err}")
            code = str(repaired_in.get("strategy_code") or "")
            ok2, err2 = self.generator.validate_strategy_code(code)
            if not ok2:
                raise RuntimeError(f"Invalid input strategy code after repair: {err2}")

        def _append_log(line: str) -> None:
            try:
                if job is not None and hasattr(job, "append_log"):
                    job.append_log(line)
            except Exception:
                return

        _append_log("Running baseline backtest")
        baseline_bt = run_backtest(
            strategy_code=code,
            config_path=BOT_CONFIG_PATH,
            timerange=timerange,
            timeframe=timeframe,
            pairs=pairs,
            fee=fee,
            dry_run_wallet=dry_run_wallet,
            max_open_trades=max_open_trades,
        )
        if not isinstance(baseline_bt, dict) or not isinstance(baseline_bt.get("data"), dict):
            raise RuntimeError("Baseline backtest output missing JSON data")

        baseline_data = baseline_bt["data"]
        baseline_summary = summarize_backtest_data(baseline_data)
        baseline_forensics = build_trade_forensics(baseline_data)
        baseline_score = self._score_backtest_summary(
            baseline_summary,
            baseline_forensics,
            min_trades_per_day=min_trades_per_day,
            require_min_trades_per_day=require_min_trades_per_day,
            max_fee_dominated_fraction=max_fee_dominated_fraction,
            min_edge_to_fee_ratio=min_edge_to_fee_ratio,
        )

        store_errors: list[str] = []
        baseline_run_id = None
        try:
            baseline_run_id = self.performance_store.record_run(
                run_type="optimize_baseline",
                strategy_code=code,
                user_goal=goal or None,
                iteration=0,
                timerange=timerange,
                timeframe=timeframe,
                pairs=pairs,
                result_file=str(baseline_bt.get("result_file") or "") or None,
                model_analysis=str(getattr(self.analysis_client, "model", "") or "") or None,
                model_risk=str(getattr(self.risk_client, "model", "") or "") or None,
                analysis_text=None,
                risk_text=None,
                backtest_summary=baseline_summary,
                trade_forensics=baseline_forensics,
                market_context=None,
                extra={
                    "strategy_class": baseline_bt.get("strategy_class"),
                    "stdout_tail": str(baseline_bt.get("stdout", ""))[-2000:],
                    "stderr_tail": str(baseline_bt.get("stderr", ""))[-2000:],
                    "fee": fee,
                    "dry_run_wallet": dry_run_wallet,
                    "max_open_trades": max_open_trades,
                    "min_trades_per_day": min_trades_per_day,
                    "require_min_trades_per_day": require_min_trades_per_day,
                    "max_fee_dominated_fraction": max_fee_dominated_fraction,
                    "min_edge_to_fee_ratio": min_edge_to_fee_ratio,
                },
            )
        except Exception as e:
            store_errors.append(str(e))

        best = {
            "strategy_code": code,
            "strategy_class": baseline_bt.get("strategy_class"),
            "result_file": baseline_bt.get("result_file"),
            "result_kind": baseline_bt.get("result_kind"),
            "zip_member": baseline_bt.get("zip_member"),
            "backtest_summary": baseline_summary,
            "trade_forensics": baseline_forensics,
            "score": baseline_score,
            "performance_run_id": baseline_run_id,
        }

        attempts: list[dict] = []

        for i in range(max_iterations):
            _append_log(f"Optimize iteration {i + 1}/{max_iterations}")

            payload = {
                "iteration": i + 1,
                "selected_filename": selected_filename,
                "backtest_summary": best.get("backtest_summary"),
                "trade_forensics": best.get("trade_forensics"),
                "config": {
                    "timerange": timerange,
                    "timeframe": timeframe,
                    "pairs": pairs,
                    "fee": fee,
                    "dry_run_wallet": dry_run_wallet,
                    "max_open_trades": max_open_trades,
                },
                "goals": {
                    "min_trades_per_day": min_trades_per_day,
                    "require_min_trades_per_day": require_min_trades_per_day,
                    "max_fee_dominated_fraction": max_fee_dominated_fraction,
                    "min_edge_to_fee_ratio": min_edge_to_fee_ratio,
                },
                "baseline": {
                    "score": baseline_score,
                    "backtest_summary": baseline_summary,
                    "trade_forensics": baseline_forensics,
                },
                "current_best": {
                    "score": best.get("score"),
                    "backtest_summary": best.get("backtest_summary"),
                    "trade_forensics": best.get("trade_forensics"),
                },
                "recent_attempts": attempts[-3:],
            }

            try:
                analysis = self.analysis_client.analyze_strategy_with_backtest(best["strategy_code"], payload)
            except Exception as e:
                _append_log(f"AI analysis failed: {e}")
                raise
            if not isinstance(analysis, str) or not analysis.strip():
                raise RuntimeError("AI analysis returned empty response")

            try:
                risk = self.risk_client.assess_risk_with_backtest(best["strategy_code"], payload)
            except Exception as e:
                _append_log(f"AI risk assessment failed: {e}")
                raise
            if not isinstance(risk, str) or not risk.strip():
                raise RuntimeError("AI risk assessment returned empty response")

            _append_log("Asking AI to propose improvements")
            model_refine_used = str(getattr(self.refine_client, "model", "") or "")
            try:
                refined_raw = self.refine_client.refine_strategy_with_backtest(goal, best["strategy_code"], payload)
            except Exception as e:
                _append_log(f"AI refinement failed: {e}")
                raise
            refined_code = self.generator.clean_code(refined_raw)
            refined_code = self.generator.upgrade_legacy_signals(refined_code)
            ok2, err2 = self.generator.validate_strategy_code(refined_code)

            if (not ok2) and self.refine_fallback_client is not None:
                try:
                    model_refine_used = str(getattr(self.refine_fallback_client, "model", "") or "")
                    refined_raw_fb = self.refine_fallback_client.refine_strategy_with_backtest(goal, best["strategy_code"], payload)
                    refined_code_fb = self.generator.clean_code(refined_raw_fb)
                    refined_code_fb = self.generator.upgrade_legacy_signals(refined_code_fb)
                    ok_fb, err_fb = self.generator.validate_strategy_code(refined_code_fb)
                    refined_code = refined_code_fb
                    ok2 = bool(ok_fb)
                    err2 = "" if ok_fb else err_fb
                except Exception:
                    pass

            if not ok2:
                repaired_out = self.repair_strategy_code(refined_code, goal or "optimize")
                v = repaired_out.get("validation") if isinstance(repaired_out, dict) else None
                if not (isinstance(v, dict) and bool(v.get("ok"))):
                    raise RuntimeError(
                        f"AI produced invalid optimized strategy code after repair: {v.get('error') if isinstance(v, dict) else ''}"
                    )
                refined_code = str(repaired_out.get("strategy_code") or "")

            if refined_code.strip() == best["strategy_code"].strip():
                _append_log("AI returned identical code; continuing")
                attempts.append(
                    {
                        "iteration": i + 1,
                        "model_refine": model_refine_used,
                        "analysis": analysis,
                        "risk": risk,
                        "note": "no_change",
                    }
                )
                continue

            _append_log("Running candidate backtest")
            cand_bt = run_backtest(
                strategy_code=refined_code,
                config_path=BOT_CONFIG_PATH,
                timerange=timerange,
                timeframe=timeframe,
                pairs=pairs,
                fee=fee,
                dry_run_wallet=dry_run_wallet,
                max_open_trades=max_open_trades,
            )
            if not isinstance(cand_bt, dict) or not isinstance(cand_bt.get("data"), dict):
                raise RuntimeError("Candidate backtest output missing JSON data")

            cand_data = cand_bt["data"]
            cand_summary = summarize_backtest_data(cand_data)
            cand_forensics = build_trade_forensics(cand_data)
            cand_score = self._score_backtest_summary(
                cand_summary,
                cand_forensics,
                min_trades_per_day=min_trades_per_day,
                require_min_trades_per_day=require_min_trades_per_day,
                max_fee_dominated_fraction=max_fee_dominated_fraction,
                min_edge_to_fee_ratio=min_edge_to_fee_ratio,
            )

            cand_run_id = None
            try:
                cand_run_id = self.performance_store.record_run(
                    run_type="optimize_candidate",
                    strategy_code=refined_code,
                    user_goal=goal or None,
                    iteration=i + 1,
                    timerange=timerange,
                    timeframe=timeframe,
                    pairs=pairs,
                    result_file=str(cand_bt.get("result_file") or "") or None,
                    model_analysis=str(getattr(self.analysis_client, "model", "") or "") or None,
                    model_risk=str(getattr(self.risk_client, "model", "") or "") or None,
                    analysis_text=analysis,
                    risk_text=risk,
                    backtest_summary=cand_summary,
                    trade_forensics=cand_forensics,
                    market_context=None,
                    extra={
                        "strategy_class": cand_bt.get("strategy_class"),
                        "stdout_tail": str(cand_bt.get("stdout", ""))[-2000:],
                        "stderr_tail": str(cand_bt.get("stderr", ""))[-2000:],
                        "model_refine": model_refine_used,
                        "fee": fee,
                        "dry_run_wallet": dry_run_wallet,
                        "max_open_trades": max_open_trades,
                        "min_trades_per_day": min_trades_per_day,
                        "require_min_trades_per_day": require_min_trades_per_day,
                        "max_fee_dominated_fraction": max_fee_dominated_fraction,
                        "min_edge_to_fee_ratio": min_edge_to_fee_ratio,
                    },
                )
            except Exception as e:
                store_errors.append(str(e))

            attempt = {
                "iteration": i + 1,
                "model_refine": model_refine_used,
                "analysis": analysis,
                "risk": risk,
                "score": cand_score,
                "backtest_summary": cand_summary,
                "trade_forensics": cand_forensics,
                "performance_run_id": cand_run_id,
            }
            attempts.append(attempt)

            best_score = float(best.get("score") or -10**18)
            if cand_score > best_score:
                _append_log(
                    f"New best found: score {best_score:.4f} -> {cand_score:.4f}"
                )
                best = {
                    "strategy_code": refined_code,
                    "strategy_class": cand_bt.get("strategy_class"),
                    "result_file": cand_bt.get("result_file"),
                    "result_kind": cand_bt.get("result_kind"),
                    "zip_member": cand_bt.get("zip_member"),
                    "backtest_summary": cand_summary,
                    "trade_forensics": cand_forensics,
                    "score": cand_score,
                    "performance_run_id": cand_run_id,
                }
            else:
                _append_log("Candidate did not beat current best")

        _append_log("Saving best strategy as a new file")
        saved_filename = self._next_optimized_filename(selected_filename)

        saved_ts = time.strftime("%Y%m%d%H%M%S")
        orig_class = self._extract_strategy_class_name(best["strategy_code"])
        saved_strategy_class = f"{orig_class}AiOpt{saved_ts}"
        saved_code = self._rename_strategy_class(best["strategy_code"], saved_strategy_class)

        ok_save = self.save_strategy_code(saved_code, filename=saved_filename)
        if not ok_save:
            raise RuntimeError("Failed to save optimized strategy")

        return {
            "selected_filename": selected_filename,
            "saved_filename": saved_filename,
            "saved_strategy_class": saved_strategy_class,
            "user_goal": goal,
            "config": {
                "timerange": timerange,
                "timeframe": timeframe,
                "pairs": pairs,
                "fee": fee,
                "dry_run_wallet": dry_run_wallet,
                "max_open_trades": max_open_trades,
                "min_trades_per_day": min_trades_per_day,
                "require_min_trades_per_day": require_min_trades_per_day,
                "max_fee_dominated_fraction": max_fee_dominated_fraction,
                "min_edge_to_fee_ratio": min_edge_to_fee_ratio,
            },
            "baseline": {
                "strategy_code": code,
                "strategy_class": baseline_bt.get("strategy_class"),
                "result_file": baseline_bt.get("result_file"),
                "result_kind": baseline_bt.get("result_kind"),
                "zip_member": baseline_bt.get("zip_member"),
                "backtest_summary": baseline_summary,
                "trade_forensics": baseline_forensics,
                "score": baseline_score,
                "performance_run_id": baseline_run_id,
            },
            "best": best,
            "saved": {
                "strategy_code": saved_code,
                "strategy_class": saved_strategy_class,
            },
            "attempts": attempts,
            "performance_store_errors": store_errors,
        }

    def refine_strategy_with_backtest_loop(
        self,
        strategy_code: str,
        user_goal: str = "",
        max_iterations: int = 2,
        timerange: str | None = None,
        timeframe: str | None = None,
        pairs: str | None = None,
        market_context: dict | None = None,
    ) -> dict:
        if not strategy_code or not str(strategy_code).strip():
            raise ValueError("Strategy code is empty")

        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")

        if max_iterations > 5:
            raise ValueError("max_iterations is capped at 5")

        if not self.refine_client.is_available():
            raise RuntimeError("Ollama is not available. Start it with: ollama serve")

        goal = (user_goal or "").strip()
        code = self.generator.clean_code(str(strategy_code))
        code = self.generator.upgrade_legacy_signals(code)
        ok, err = self.generator.validate_strategy_code(code)
        if not ok:
            repaired_in = self.repair_strategy_code(code, goal or "refine")
            v = repaired_in.get("validation") if isinstance(repaired_in, dict) else None
            if not (isinstance(v, dict) and bool(v.get("ok"))):
                raise RuntimeError(f"Invalid input strategy code: {err}")
            code = str(repaired_in.get("strategy_code") or "")
            ok2, err2 = self.generator.validate_strategy_code(code)
            if not ok2:
                raise RuntimeError(f"Invalid input strategy code after repair: {err2}")

        iterations = []
        store_errors: list[str] = []

        current_code = code
        last_backtest_payload = None

        for i in range(max_iterations):
            bt = run_backtest(
                strategy_code=current_code,
                config_path=BOT_CONFIG_PATH,
                timerange=timerange,
                timeframe=timeframe,
                pairs=pairs,
            )

            if not isinstance(bt, dict):
                raise RuntimeError("Backtest runner returned invalid result")
            data = bt.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("Backtest output missing JSON data")

            bt_summary = summarize_backtest_data(data)
            bt_forensics = build_trade_forensics(data)

            payload = {
                "iteration": i + 1,
                "strategy_class": bt.get("strategy_class"),
                "result_file": bt.get("result_file"),
                "stdout_tail": str(bt.get("stdout", ""))[-2000:],
                "stderr_tail": str(bt.get("stderr", ""))[-2000:],
                "backtest_summary": bt_summary,
                "trade_forensics": bt_forensics,
                "market_context": market_context,
            }

            analysis = self.analysis_client.analyze_strategy_with_backtest(current_code, payload)
            if not isinstance(analysis, str) or not analysis.strip():
                raise RuntimeError("AI analysis returned empty response")

            risk = self.risk_client.assess_risk_with_backtest(current_code, payload)
            if not isinstance(risk, str) or not risk.strip():
                raise RuntimeError("AI risk assessment returned empty response")

            model_refine_used = str(getattr(self.refine_client, "model", "") or "")
            refined_raw = self.refine_client.refine_strategy_with_backtest(goal, current_code, payload)
            if not isinstance(refined_raw, str) or not refined_raw.strip():
                refined_raw = ""

            refined_code = self.generator.clean_code(refined_raw)
            refined_code = self.generator.upgrade_legacy_signals(refined_code)
            ok2, err2 = self.generator.validate_strategy_code(refined_code)

            if (not ok2) and self.refine_fallback_client is not None:
                try:
                    model_refine_used = str(getattr(self.refine_fallback_client, "model", "") or "")
                    refined_raw_fb = self.refine_fallback_client.refine_strategy_with_backtest(goal, current_code, payload)
                    refined_code_fb = self.generator.clean_code(refined_raw_fb)
                    refined_code_fb = self.generator.upgrade_legacy_signals(refined_code_fb)
                    ok_fb, err_fb = self.generator.validate_strategy_code(refined_code_fb)
                    if ok_fb:
                        refined_code = refined_code_fb
                        ok2 = True
                        err2 = ""
                    else:
                        refined_code = refined_code_fb
                        err2 = err_fb
                except Exception:
                    pass

            if not ok2:
                repaired_out = self.repair_strategy_code(refined_code, goal or "refine")
                v = repaired_out.get("validation") if isinstance(repaired_out, dict) else None
                if not (isinstance(v, dict) and bool(v.get("ok"))):
                    raise RuntimeError(f"AI produced invalid refined strategy code after repair: {v.get('error') if isinstance(v, dict) else ''}")
                refined_code = str(repaired_out.get("strategy_code") or "")

            iterations.append(
                {
                    "iteration": i + 1,
                    "input_code": current_code,
                    "analysis": analysis,
                    "risk": risk,
                    "backtest_payload": payload,
                    "refined_code": refined_code,
                    "model_refine": model_refine_used,
                }
            )

            try:
                run_id = self.performance_store.record_run(
                    run_type="refine_iteration",
                    strategy_code=current_code,
                    user_goal=(user_goal or "").strip() or None,
                    iteration=i + 1,
                    timerange=timerange,
                    timeframe=timeframe,
                    pairs=pairs,
                    result_file=str(bt.get("result_file") or "") or None,
                    model_analysis=str(getattr(self.analysis_client, "model", "") or "") or None,
                    model_risk=str(getattr(self.risk_client, "model", "") or "") or None,
                    analysis_text=analysis,
                    risk_text=risk,
                    backtest_summary=bt_summary,
                    trade_forensics=bt_forensics,
                    market_context=market_context,
                    extra={
                        "strategy_class": bt.get("strategy_class"),
                        "stdout_tail": payload.get("stdout_tail"),
                        "stderr_tail": payload.get("stderr_tail"),
                    },
                )
                if iterations:
                    iterations[-1]["performance_run_id"] = run_id
            except Exception as e:
                store_errors.append(str(e))

            current_code = refined_code
            last_backtest_payload = payload

        # Final backtest on the last code to provide real, measurable end-state.
        final_bt = run_backtest(
            strategy_code=current_code,
            config_path=BOT_CONFIG_PATH,
            timerange=timerange,
            timeframe=timeframe,
            pairs=pairs,
        )

        if not isinstance(final_bt, dict) or not isinstance(final_bt.get("data"), dict):
            raise RuntimeError("Final backtest output missing JSON data")

        final_data = final_bt["data"]
        final_summary = summarize_backtest_data(final_data)
        final_forensics = build_trade_forensics(final_data)

        final_run_id = None
        try:
            final_run_id = self.performance_store.record_run(
                run_type="refine_final",
                strategy_code=current_code,
                user_goal=(user_goal or "").strip() or None,
                iteration=None,
                timerange=timerange,
                timeframe=timeframe,
                pairs=pairs,
                result_file=str(final_bt.get("result_file") or "") or None,
                model_analysis=str(getattr(self.analysis_client, "model", "") or "") or None,
                model_risk=str(getattr(self.risk_client, "model", "") or "") or None,
                analysis_text=None,
                risk_text=None,
                backtest_summary=final_summary,
                trade_forensics=final_forensics,
                market_context=market_context,
                extra={
                    "strategy_class": final_bt.get("strategy_class"),
                    "stdout_tail": str(final_bt.get("stdout", ""))[-2000:],
                    "stderr_tail": str(final_bt.get("stderr", ""))[-2000:],
                    "iterations": len(iterations),
                },
            )
        except Exception as e:
            store_errors.append(str(e))

        return {
            "user_goal": (user_goal or "").strip(),
            "iterations": iterations,
            "final": {
                "strategy_code": current_code,
                "strategy_class": final_bt.get("strategy_class"),
                "result_file": final_bt.get("result_file"),
                "backtest_summary": final_summary,
                "trade_forensics": final_forensics,
                "stdout_tail": str(final_bt.get("stdout", ""))[-2000:],
                "stderr_tail": str(final_bt.get("stderr", ""))[-2000:],
                "previous_payload": last_backtest_payload,
                "performance_run_id": final_run_id,
            },
            "performance_store_errors": store_errors,
        }

    def analyze_strategy_across_scenarios(
        self,
        strategy_code: str,
        scenarios: list,
        user_goal: str = "",
        market_context: dict | None = None,
    ) -> dict:
        if not strategy_code or not str(strategy_code).strip():
            raise ValueError("Strategy code is empty")

        if not isinstance(scenarios, list) or not scenarios:
            raise ValueError("scenarios must be a non-empty list")

        if len(scenarios) > 6:
            raise ValueError("scenarios is capped at 6")

        if not self.generator.ollama.is_available():
            raise RuntimeError("Ollama is not available. Start it with: ollama serve")

        code = self.generator.clean_code(str(strategy_code))
        ok, err = self.generator.validate_strategy_code(code)
        if not ok:
            raise RuntimeError(f"Invalid input strategy code: {err}")

        scenario_results = []
        store_errors: list[str] = []
        goal = (user_goal or "").strip()

        for i, s in enumerate(scenarios):
            if not isinstance(s, dict):
                raise ValueError("Each scenario must be an object")

            name = s.get("name")
            if not isinstance(name, str) or not name.strip():
                name = f"scenario_{i + 1}"

            timerange = s.get("timerange")
            if timerange is not None and (not isinstance(timerange, str) or not timerange.strip()):
                raise ValueError(f"Invalid timerange in scenario '{name}'")

            timeframe = s.get("timeframe")
            if timeframe is not None and (not isinstance(timeframe, str) or not timeframe.strip()):
                raise ValueError(f"Invalid timeframe in scenario '{name}'")

            pairs = s.get("pairs")
            if pairs is not None and (not isinstance(pairs, str) or not pairs.strip()):
                raise ValueError(f"Invalid pairs in scenario '{name}'")

            bt = run_backtest(
                strategy_code=code,
                config_path=BOT_CONFIG_PATH,
                timerange=timerange,
                timeframe=timeframe,
                pairs=pairs,
            )

            if not isinstance(bt, dict):
                raise RuntimeError("Backtest runner returned invalid result")
            data = bt.get("data")
            if not isinstance(data, dict):
                raise RuntimeError("Backtest output missing JSON data")

            bt_summary = summarize_backtest_data(data)
            bt_forensics = build_trade_forensics(data)

            scenario_results.append(
                {
                    "scenario": {
                        "name": name,
                        "timerange": timerange,
                        "timeframe": timeframe,
                        "pairs": pairs,
                    },
                    "strategy_class": bt.get("strategy_class"),
                    "result_file": bt.get("result_file"),
                    "stdout_tail": str(bt.get("stdout", ""))[-2000:],
                    "stderr_tail": str(bt.get("stderr", ""))[-2000:],
                    "backtest_summary": bt_summary,
                    "trade_forensics": bt_forensics,
                }
            )

            try:
                run_id = self.performance_store.record_run(
                    run_type="scenario_backtest",
                    strategy_code=code,
                    user_goal=goal or None,
                    scenario_name=name,
                    iteration=None,
                    timerange=timerange,
                    timeframe=timeframe,
                    pairs=pairs,
                    result_file=str(bt.get("result_file") or "") or None,
                    model_analysis=None,
                    model_risk=None,
                    analysis_text=None,
                    risk_text=None,
                    backtest_summary=bt_summary,
                    trade_forensics=bt_forensics,
                    market_context=market_context,
                    extra={
                        "strategy_class": bt.get("strategy_class"),
                        "stdout_tail": str(bt.get("stdout", ""))[-2000:],
                        "stderr_tail": str(bt.get("stderr", ""))[-2000:],
                    },
                )
                if scenario_results:
                    scenario_results[-1]["performance_run_id"] = run_id
            except Exception as e:
                store_errors.append(str(e))

        payload = {
            "user_goal": goal,
            "scenarios": scenario_results,
            "market_context": market_context,
        }

        analysis = self.analysis_client.analyze_strategy_with_scenarios(code, payload)
        if not isinstance(analysis, str) or not analysis.strip():
            raise RuntimeError("AI scenario analysis returned empty response")

        risk = self.risk_client.assess_risk_with_scenarios(code, payload)
        if not isinstance(risk, str) or not risk.strip():
            raise RuntimeError("AI scenario risk assessment returned empty response")

        analysis_run_id = None
        try:
            analysis_run_id = self.performance_store.record_run(
                run_type="scenario_analysis",
                strategy_code=code,
                user_goal=goal or None,
                scenario_name=None,
                iteration=None,
                timerange=None,
                timeframe=None,
                pairs=None,
                result_file=None,
                model_analysis=str(getattr(self.analysis_client, "model", "") or "") or None,
                model_risk=str(getattr(self.risk_client, "model", "") or "") or None,
                analysis_text=analysis,
                risk_text=risk,
                backtest_summary=None,
                trade_forensics=None,
                market_context=market_context,
                extra={
                    "scenario_count": len(scenario_results),
                },
            )
        except Exception as e:
            store_errors.append(str(e))

        return {
            "strategy_code": code,
            "user_goal": goal,
            "scenario_results": scenario_results,
            "analysis": analysis,
            "risk": risk,
            "performance_store_errors": store_errors,
            "analysis_run_id": analysis_run_id,
        }
