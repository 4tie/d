"""
Strategy service for orchestrating AI strategy operations
"""
from utils.ollama_client import OllamaClient
from utils.strategy_generator import StrategyGenerator
from utils.strategy_saver import StrategySaver
from utils.backtest_runner import run_backtest, summarize_backtest_data, build_trade_forensics
from utils.performance_store import AIPerformanceStore
from config.settings import BOT_CONFIG_PATH

class StrategyService:
    """Service layer for strategy generation and saving operations"""
    
    def __init__(self):
        self.generator = StrategyGenerator()
        self.analysis_client = OllamaClient(base_url=self.generator.ollama.base_url, model=self.generator.ollama.model, options=self.generator.ollama.options)
        self.risk_client = OllamaClient(base_url=self.generator.ollama.base_url, model=self.generator.ollama.model, options=self.generator.ollama.options)
        self.saver = StrategySaver()
        self.performance_store = AIPerformanceStore()

    def update_ollama_settings(self, base_url: str, model: str, options: dict | None = None, task_models: dict | None = None) -> None:
        generation_model = model
        analysis_model = model
        risk_model = model
        if isinstance(task_models, dict):
            generation_model = str(task_models.get("strategy_generation") or generation_model)
            analysis_model = str(task_models.get("strategy_analysis") or analysis_model)
            risk_model = str(task_models.get("risk_assessment") or risk_model)

        self.generator.update_ollama_settings(base_url=base_url, model=generation_model, options=options)
        self.analysis_client.update_settings(base_url=base_url, model=analysis_model, options=options)
        self.risk_client.update_settings(base_url=base_url, model=risk_model, options=options)
    
    def generate_strategy_code(self, user_idea: str) -> str:
        if not user_idea or not user_idea.strip():
            raise ValueError("Strategy description is empty")

        return self.generator.generate_strategy_code(user_idea)
    
    def save_strategy_code(self, code: str, filename: str = "AIStrategy.py") -> bool:
        if not code or not code.strip():
            raise ValueError("No strategy code to save")

        return self.saver.save_strategy(code, filename=filename)

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

        if not self.generator.ollama.is_available():
            raise RuntimeError("Ollama is not available. Start it with: ollama serve")

        code = self.generator.clean_code(str(strategy_code))
        ok, err = self.generator.validate_strategy_code(code)
        if not ok:
            raise RuntimeError(f"Invalid input strategy code: {err}")

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

            refined_raw = self.analysis_client.refine_strategy_with_backtest(user_goal, current_code, payload)
            refined_code = self.generator.clean_code(refined_raw)
            ok2, err2 = self.generator.validate_strategy_code(refined_code)
            if not ok2:
                repaired = self.generator.ollama.repair_strategy_code(user_goal or "refine", refined_code, err2)
                repaired = self.generator.clean_code(repaired)
                ok3, err3 = self.generator.validate_strategy_code(repaired)
                if not ok3:
                    raise RuntimeError(f"AI produced invalid refined strategy code after repair: {err3}")
                refined_code = repaired

            iterations.append(
                {
                    "iteration": i + 1,
                    "input_code": current_code,
                    "analysis": analysis,
                    "risk": risk,
                    "backtest_payload": payload,
                    "refined_code": refined_code,
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
