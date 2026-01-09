"""
AI Analysis tab for strategy insights and loss analysis
"""
import json
from PyQt6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                             QPushButton, QTextEdit, QTabWidget, QScrollArea, QCheckBox, QSpinBox, QMessageBox, QGroupBox, QLineEdit, QApplication)
from PyQt6.QtCore import Qt, QThreadPool
from utils.ollama_client import OllamaClient
from config.settings import OLLAMA_BASE_URL, OLLAMA_MODEL_ANALYSIS, OLLAMA_OPTIONS, BOT_CONFIG_PATH

from utils.qt_worker import Worker
from utils.backtest_runner import run_backtest, summarize_backtest_data, build_trade_forensics
from core.strategy_service import StrategyService

class AIAnalysisTab(QWidget):
    """AI Analysis tab"""
    def __init__(self, client, threadpool: QThreadPool, parent=None):
        super().__init__(parent)
        self.client = client
        self.threadpool = threadpool
        self.strategy_service = StrategyService()
        self.ollama_client = OllamaClient(base_url=OLLAMA_BASE_URL, model=OLLAMA_MODEL_ANALYSIS, options=OLLAMA_OPTIONS)
        self._strategy_analyze_running = False
        self._loss_fetch_running = False
        self._loss_analyze_running = False
        self._improve_running = False
        self._codechange_bt_running = False
        self._last_run_id_for_feedback = None

        self._last_baseline_strategy_code = None
        self._last_baseline_bt_summary = None
        self.setup_ui()

    def _set_last_run_id_for_feedback(self, run_id):
        if isinstance(run_id, int) and run_id > 0:
            self._last_run_id_for_feedback = run_id
            if hasattr(self, "lbl_feedback_target"):
                self.lbl_feedback_target.setText(f"Last run id: {run_id}")
            if hasattr(self, "btn_submit_feedback"):
                self.btn_submit_feedback.setEnabled(True)
            return

        self._last_run_id_for_feedback = None
        if hasattr(self, "lbl_feedback_target"):
            self.lbl_feedback_target.setText("Last run id: (none)")
        if hasattr(self, "btn_submit_feedback"):
            self.btn_submit_feedback.setEnabled(False)

    def update_ollama_settings(self, base_url: str, model: str, options=None, task_models=None) -> None:
        analysis_model = model
        if isinstance(task_models, dict):
            analysis_model = str(task_models.get("strategy_analysis") or analysis_model)

        self.ollama_client.update_settings(base_url=base_url, model=analysis_model, options=options)
        self.strategy_service.update_ollama_settings(base_url=base_url, model=model, options=options, task_models=task_models)
        self.lbl_ollama_status.setText("Checking Ollama connection...")
        self.lbl_ollama_status.setStyleSheet("font-weight: bold; color: orange;")
        self.check_ollama_connection()

    def _build_market_context(self) -> dict:
        ctx = {}
        try:
            cfg = self.client.get_config()
            if isinstance(cfg, dict):
                ctx["bot_config"] = {
                    "strategy": cfg.get("strategy"),
                    "timeframe": cfg.get("timeframe"),
                    "stake_currency": cfg.get("stake_currency"),
                    "dry_run": cfg.get("dry_run"),
                }
        except Exception:
            ctx["bot_config_error"] = "failed to fetch show_config"

        try:
            wl = self.client.get_whitelist()
            if isinstance(wl, list):
                ctx["whitelist"] = wl[:30]
        except Exception:
            ctx["whitelist_error"] = "failed to fetch whitelist"

        try:
            open_trades = self.client.get_open_trades()
            if isinstance(open_trades, list):
                ctx["open_trades"] = open_trades[:10]
        except Exception:
            ctx["open_trades_error"] = "failed to fetch open trades"

        # Add a small candle snapshot for 1 pair if we can infer it.
        try:
            pair = None
            open_trades = ctx.get("open_trades")
            if isinstance(open_trades, list) and open_trades:
                first = open_trades[0]
                if isinstance(first, dict):
                    pair = first.get("pair")

            if not pair:
                wl = ctx.get("whitelist")
                if isinstance(wl, list) and wl:
                    pair = wl[0]

            tf = None
            bot_cfg = ctx.get("bot_config")
            if isinstance(bot_cfg, dict):
                tf = bot_cfg.get("timeframe")

            if pair and tf:
                candles = self.client.get_pair_candles(pair=str(pair), timeframe=str(tf), limit=120)
                if candles is not None:
                    ctx["pair_candles_snapshot"] = {
                        "pair": str(pair),
                        "timeframe": str(tf),
                        "data": candles,
                    }
        except Exception:
            ctx["pair_candles_error"] = "failed to fetch pair_candles"

        return ctx

    def _extract_code_change(self, text: str) -> str | None:
        if not isinstance(text, str) or not text.strip():
            return None

        marker = "CODE_CHANGE:"
        idx = text.find(marker)
        if idx == -1:
            return None

        code = text[idx + len(marker) :].strip()
        if not code:
            return None

        # Strip accidental markdown fences if the model outputs them.
        if code.startswith("```"):
            lines = code.splitlines()
            # remove first fence line
            lines = lines[1:]
            # remove trailing fence if present
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            code = "\n".join(lines).strip()

        return code if code.strip() else None

    def _validate_strategy_code(self, code: str) -> tuple[bool, str]:
        try:
            ok, err = self.strategy_service.generator.validate_strategy_code(code)
            return bool(ok), str(err or "")
        except Exception as e:
            return False, str(e)

    def _apply_code_change_to_editor(self, code: str, target: str) -> None:
        ok, err = self._validate_strategy_code(code)
        if not ok:
            QMessageBox.critical(self, "Invalid code", f"CODE_CHANGE is not a valid AIStrategy: {err}")
            return

        if target == "analysis_input":
            self.txt_strategy_input.setText(code)
        elif target == "improve_current":
            self.txt_current_strategy.setText(code)
        elif target == "improve_output":
            self.txt_improved_strategy.setText(code)

    def _copy_to_clipboard(self, text: str) -> None:
        if not isinstance(text, str):
            return
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(text)

    def _save_code_change_async(self, code: str) -> None:
        ok, err = self._validate_strategy_code(code)
        if not ok:
            QMessageBox.critical(self, "Invalid code", f"CODE_CHANGE is not a valid AIStrategy: {err}")
            return

        if QMessageBox.question(self, "Save strategy", "Save CODE_CHANGE to strategies folder as AIStrategy.py?") != QMessageBox.StandardButton.Yes:
            return

        def _save():
            return self.strategy_service.save_strategy_code(code, filename="AIStrategy.py")

        worker = Worker(_save)

        def _on_result(ok: bool):
            if ok:
                QMessageBox.information(self, "Saved", "Strategy saved to strategies folder.")
            else:
                QMessageBox.critical(self, "Save failed", "Failed to save strategy.")

        def _on_error(msg: str):
            QMessageBox.critical(self, "Save failed", msg)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        self.threadpool.start(worker)

    def _format_bt_compare(self, baseline_summary: dict | None, candidate_summary: dict | None) -> str:
        def _extract_metrics(summary: dict | None) -> dict:
            if not isinstance(summary, dict):
                return {}
            m = summary.get("metrics")
            return m if isinstance(m, dict) else {}

        b = _extract_metrics(baseline_summary)
        c = _extract_metrics(candidate_summary)

        keys = [
            "profit_total_pct",
            "profit_total_abs",
            "max_drawdown_pct",
            "max_drawdown",
            "winrate",
            "win_rate",
            "sharpe",
            "sharpe_ratio",
            "sortino",
            "calmar",
            "total_trades",
            "trade_count",
        ]

        lines = []
        lines.append("CODE_CHANGE_BACKTEST_COMPARE:")
        lines.append("metric | baseline | code_change")
        lines.append("---|---|---")

        seen = set()
        for k in keys:
            if k in seen:
                continue
            seen.add(k)
            bv = b.get(k)
            cv = c.get(k)
            if bv is None and cv is None:
                continue
            lines.append(f"{k} | {bv} | {cv}")

        if len(lines) == 3:
            lines.append("(no comparable metrics found in backtest summaries)")

        return "\n".join(lines)
        
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Ollama Status
        self.lbl_ollama_status = QLabel("Checking Ollama connection...")
        self.lbl_ollama_status.setStyleSheet("font-weight: bold; color: orange;")
        layout.addWidget(self.lbl_ollama_status)
        
        # Analysis Tabs
        self.analysis_tabs = QTabWidget()
        
        # Strategy Analysis Tab
        self.create_strategy_analysis_tab()
        
        # Loss Analysis Tab
        self.create_loss_analysis_tab()
        
        # Strategy Improvement Tab
        self.create_improvement_tab()
        
        layout.addWidget(self.analysis_tabs)
        self.setLayout(layout)
        
        # Check Ollama connection
        self.check_ollama_connection()
    
    def create_strategy_analysis_tab(self):
        """Create strategy analysis sub-tab"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Input section
        input_layout = QHBoxLayout()
        
        lbl_strategy = QLabel("Strategy Code:")
        self.txt_strategy_input = QTextEdit()
        self.txt_strategy_input.setPlaceholderText("Paste your strategy code here for analysis...")
        self.txt_strategy_input.setMaximumHeight(150)
        
        self.btn_analyze_strategy = QPushButton("Analyze strategy")
        self.btn_analyze_strategy.clicked.connect(self.analyze_strategy)
        self.btn_analyze_strategy.setStyleSheet("background-color: #2196F3; color: white; font-weight: bold; padding: 8px;")

        self.chk_refine = QCheckBox("Refine strategy")
        self.chk_refine.setChecked(False)

        self.chk_scenarios = QCheckBox("Scenario analysis (what-if)")
        self.chk_scenarios.setChecked(False)

        self.spin_refine_iters = QSpinBox()
        self.spin_refine_iters.setMinimum(1)
        self.spin_refine_iters.setMaximum(5)
        self.spin_refine_iters.setValue(2)
        self.spin_refine_iters.setEnabled(False)

        self.txt_scenarios = QTextEdit()
        self.txt_scenarios.setPlaceholderText(
            "Enter JSON list of scenarios (max 6). Example: "
            "[{\"name\":\"train\",\"timerange\":\"20220101-20221231\"},"
            "{\"name\":\"test\",\"timerange\":\"20230101-20231231\"}]"
        )
        self.txt_scenarios.setMaximumHeight(110)
        self.txt_scenarios.setVisible(False)

        def _on_refine_toggled(checked: bool):
            self.spin_refine_iters.setEnabled(bool(checked))
            if checked:
                self.chk_scenarios.setChecked(False)

        def _on_scenarios_toggled(checked: bool):
            self.txt_scenarios.setVisible(bool(checked))
            if checked:
                self.chk_refine.setChecked(False)

        self.chk_refine.toggled.connect(_on_refine_toggled)
        self.chk_scenarios.toggled.connect(_on_scenarios_toggled)
        
        input_layout.addWidget(lbl_strategy)
        input_layout.addWidget(self.chk_refine)
        input_layout.addWidget(self.spin_refine_iters)
        input_layout.addWidget(self.chk_scenarios)
        input_layout.addWidget(self.btn_analyze_strategy)
        
        layout.addLayout(input_layout)
        layout.addWidget(self.txt_strategy_input)
        layout.addWidget(self.txt_scenarios)
        
        # Results section
        lbl_results = QLabel("Analysis Results:")
        lbl_results.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.txt_analysis_results = QTextEdit()
        self.txt_analysis_results.setReadOnly(True)
        self.txt_analysis_results.setPlaceholderText("AI analysis will appear here...")
        
        layout.addWidget(lbl_results)
        layout.addWidget(self.txt_analysis_results)

        actions_row = QHBoxLayout()
        self.btn_apply_code_change = QPushButton("Apply code change")
        self.btn_apply_code_change.setEnabled(False)

        self.btn_copy_code_change = QPushButton("Copy code change")
        self.btn_copy_code_change.setEnabled(False)

        self.btn_save_code_change = QPushButton("Save code change")
        self.btn_save_code_change.setEnabled(False)

        self.btn_backtest_code_change = QPushButton("Backtest code change")
        self.btn_backtest_code_change.setEnabled(False)

        actions_row.addWidget(self.btn_apply_code_change)
        actions_row.addWidget(self.btn_copy_code_change)
        actions_row.addWidget(self.btn_save_code_change)
        actions_row.addWidget(self.btn_backtest_code_change)
        layout.addLayout(actions_row)

        self._last_code_change_analysis = None

        def _refresh_actions():
            has = isinstance(self._last_code_change_analysis, str) and self._last_code_change_analysis.strip()
            self.btn_apply_code_change.setEnabled(bool(has))
            self.btn_copy_code_change.setEnabled(bool(has))
            self.btn_save_code_change.setEnabled(bool(has))
            self.btn_backtest_code_change.setEnabled(bool(has) and isinstance(self._last_baseline_bt_summary, dict))

        def _on_apply():
            if isinstance(self._last_code_change_analysis, str):
                self._apply_code_change_to_editor(self._last_code_change_analysis, target="analysis_input")

        def _on_copy():
            if isinstance(self._last_code_change_analysis, str):
                self._copy_to_clipboard(self._last_code_change_analysis)

        def _on_save():
            if isinstance(self._last_code_change_analysis, str):
                self._save_code_change_async(self._last_code_change_analysis)

        def _on_backtest():
            if self._codechange_bt_running:
                return
            if not isinstance(self._last_code_change_analysis, str) or not self._last_code_change_analysis.strip():
                return
            if not isinstance(self._last_baseline_bt_summary, dict):
                QMessageBox.warning(self, "Backtest", "No baseline backtest summary available. Run analysis first.")
                return

            candidate = self._last_code_change_analysis
            ok, err = self._validate_strategy_code(candidate)
            if not ok:
                QMessageBox.critical(self, "Invalid code", f"CODE_CHANGE is not a valid AIStrategy: {err}")
                return

            self._codechange_bt_running = True
            self.btn_backtest_code_change.setEnabled(False)
            self.txt_analysis_results.append("\nRunning backtest for CODE_CHANGE... (this may take a while)")

            def _run_candidate_bt():
                bt_result = run_backtest(strategy_code=candidate, config_path=BOT_CONFIG_PATH)
                if not isinstance(bt_result, dict):
                    raise RuntimeError("Invalid backtest result")
                data = bt_result.get("data")
                if not isinstance(data, dict):
                    raise RuntimeError("Backtest output missing JSON data")
                return summarize_backtest_data(data)

            worker_bt = Worker(_run_candidate_bt)

            def _on_result(summary: dict):
                compare = self._format_bt_compare(self._last_baseline_bt_summary, summary)
                self.txt_analysis_results.append("\n" + ("=" * 60) + "\n" + compare)

            def _on_error(msg: str):
                self.txt_analysis_results.append("\nBacktest error: " + str(msg))

            def _on_finished():
                self._codechange_bt_running = False
                if hasattr(self, "_refresh_code_change_actions_analysis"):
                    self._refresh_code_change_actions_analysis()

            worker_bt.signals.result.connect(_on_result)
            worker_bt.signals.error.connect(_on_error)
            worker_bt.signals.finished.connect(_on_finished)
            self.threadpool.start(worker_bt)

        self.btn_apply_code_change.clicked.connect(_on_apply)
        self.btn_copy_code_change.clicked.connect(_on_copy)
        self.btn_save_code_change.clicked.connect(_on_save)
        self.btn_backtest_code_change.clicked.connect(_on_backtest)

        self._refresh_code_change_actions_analysis = _refresh_actions

        feedback_group = QGroupBox("Feedback")
        feedback_layout = QHBoxLayout()

        self.lbl_feedback_target = QLabel("Last run id: (none)")
        self.spin_feedback_rating = QSpinBox()
        self.spin_feedback_rating.setMinimum(1)
        self.spin_feedback_rating.setMaximum(5)
        self.spin_feedback_rating.setValue(5)
        self.txt_feedback_comments = QLineEdit()
        self.txt_feedback_comments.setPlaceholderText("Optional notes")

        self.btn_submit_feedback = QPushButton("Submit feedback")
        self.btn_submit_feedback.setEnabled(False)

        def _submit_feedback():
            run_id = self._last_run_id_for_feedback
            if not isinstance(run_id, int) or run_id <= 0:
                QMessageBox.warning(self, "Feedback", "No run to rate yet. Run an analysis first.")
                return

            rating = int(self.spin_feedback_rating.value())
            comments = self.txt_feedback_comments.text().strip()
            try:
                fb_id = self.strategy_service.performance_store.record_feedback(
                    run_id=run_id,
                    rating=rating,
                    comments=comments or None,
                )
                self.txt_feedback_comments.setText("")
                QMessageBox.information(self, "Feedback", f"Feedback saved (id={fb_id}).")
            except Exception as e:
                QMessageBox.critical(self, "Feedback", f"Failed to save feedback: {e}")

        self.btn_submit_feedback.clicked.connect(_submit_feedback)

        feedback_layout.addWidget(self.lbl_feedback_target)
        feedback_layout.addWidget(QLabel("Rating"))
        feedback_layout.addWidget(self.spin_feedback_rating)
        feedback_layout.addWidget(self.txt_feedback_comments)
        feedback_layout.addWidget(self.btn_submit_feedback)
        feedback_group.setLayout(feedback_layout)
        layout.addWidget(feedback_group)

        tab.setLayout(layout)
        self.analysis_tabs.addTab(tab, "Strategy Analysis")
    
    def create_loss_analysis_tab(self):
        """Create loss analysis sub-tab"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Controls
        controls_layout = QHBoxLayout()
        
        self.btn_fetch_trades = QPushButton("Fetch recent trades")
        self.btn_fetch_trades.clicked.connect(self.fetch_trades_for_analysis)
        self.btn_fetch_trades.setStyleSheet("background-color: #FF9800; color: white; font-weight: bold; padding: 8px;")
        
        self.btn_analyze_losses = QPushButton("Analyze losses")
        self.btn_analyze_losses.clicked.connect(self.analyze_losses)
        self.btn_analyze_losses.setStyleSheet("background-color: #F44336; color: white; font-weight: bold; padding: 8px;")
        
        self.lbl_drawdown = QLabel("Current Drawdown: ---")
        self.lbl_drawdown.setStyleSheet("font-weight: bold; color: red; font-size: 14px;")
        
        controls_layout.addWidget(self.btn_fetch_trades)
        controls_layout.addWidget(self.btn_analyze_losses)
        controls_layout.addWidget(self.lbl_drawdown)
        
        layout.addLayout(controls_layout)
        
        # Results
        lbl_loss_results = QLabel("Loss Analysis:")
        lbl_loss_results.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.txt_loss_results = QTextEdit()
        self.txt_loss_results.setReadOnly(True)
        self.txt_loss_results.setPlaceholderText("Loss analysis will appear here...")
        
        layout.addWidget(lbl_loss_results)
        layout.addWidget(self.txt_loss_results)

        tab.setLayout(layout)
        self.analysis_tabs.addTab(tab, "Loss Analysis")
    
    def create_improvement_tab(self):
        """Create strategy improvement sub-tab"""
        tab = QWidget()
        layout = QVBoxLayout()
        
        # Input section
        lbl_current = QLabel("Current Strategy:")
        self.txt_current_strategy = QTextEdit()
        self.txt_current_strategy.setPlaceholderText("Paste your current strategy code...")
        self.txt_current_strategy.setMaximumHeight(150)
        
        self.btn_improve = QPushButton("Generate improvements")
        self.btn_improve.clicked.connect(self.generate_improvements)
        self.btn_improve.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 8px;")
        
        layout.addWidget(lbl_current)
        layout.addWidget(self.txt_current_strategy)
        layout.addWidget(self.btn_improve)
        
        # Results section
        lbl_improved = QLabel("Improved Strategy:")
        lbl_improved.setStyleSheet("font-weight: bold; font-size: 14px;")
        
        self.txt_improved_strategy = QTextEdit()
        self.txt_improved_strategy.setPlaceholderText("Improved strategy code will appear here...")
        
        layout.addWidget(lbl_improved)
        layout.addWidget(self.txt_improved_strategy)

        actions_row = QHBoxLayout()
        self.btn_apply_improved_code = QPushButton("Apply code change")
        self.btn_apply_improved_code.setEnabled(False)

        self.btn_copy_improved_code = QPushButton("Copy code change")
        self.btn_copy_improved_code.setEnabled(False)

        self.btn_save_improved_code = QPushButton("Save code change")
        self.btn_save_improved_code.setEnabled(False)

        self.btn_backtest_improved_code = QPushButton("Backtest code change")
        self.btn_backtest_improved_code.setEnabled(False)

        actions_row.addWidget(self.btn_apply_improved_code)
        actions_row.addWidget(self.btn_copy_improved_code)
        actions_row.addWidget(self.btn_save_improved_code)
        actions_row.addWidget(self.btn_backtest_improved_code)
        layout.addLayout(actions_row)

        self._last_code_change_improve = None

        def _refresh_actions():
            has = isinstance(self._last_code_change_improve, str) and self._last_code_change_improve.strip()
            self.btn_apply_improved_code.setEnabled(bool(has))
            self.btn_copy_improved_code.setEnabled(bool(has))
            self.btn_save_improved_code.setEnabled(bool(has))
            self.btn_backtest_improved_code.setEnabled(bool(has) and not self._codechange_bt_running)

        def _on_apply():
            if isinstance(self._last_code_change_improve, str):
                # Apply to current strategy editor (so user can iterate) and also show code-only in output.
                self._apply_code_change_to_editor(self._last_code_change_improve, target="improve_current")
                self._apply_code_change_to_editor(self._last_code_change_improve, target="improve_output")

        def _on_copy():
            if isinstance(self._last_code_change_improve, str):
                self._copy_to_clipboard(self._last_code_change_improve)

        def _on_save():
            if isinstance(self._last_code_change_improve, str):
                self._save_code_change_async(self._last_code_change_improve)

        def _on_backtest():
            if self._codechange_bt_running:
                return
            if not isinstance(self._last_code_change_improve, str) or not self._last_code_change_improve.strip():
                return

            baseline_code = self.txt_current_strategy.toPlainText()
            candidate_code = self._last_code_change_improve

            ok1, err1 = self._validate_strategy_code(baseline_code)
            if not ok1:
                QMessageBox.critical(self, "Invalid code", f"Current strategy is not a valid AIStrategy: {err1}")
                return
            ok2, err2 = self._validate_strategy_code(candidate_code)
            if not ok2:
                QMessageBox.critical(self, "Invalid code", f"CODE_CHANGE is not a valid AIStrategy: {err2}")
                return

            self._codechange_bt_running = True
            self.btn_backtest_improved_code.setEnabled(False)
            self.txt_improved_strategy.append("\nRunning baseline + CODE_CHANGE backtests... (this may take a while)")

            def _run_both():
                bt_base = run_backtest(strategy_code=baseline_code, config_path=BOT_CONFIG_PATH)
                if not isinstance(bt_base, dict) or not isinstance(bt_base.get("data"), dict):
                    raise RuntimeError("Baseline backtest output missing JSON data")
                base_summary = summarize_backtest_data(bt_base["data"])

                bt_cand = run_backtest(strategy_code=candidate_code, config_path=BOT_CONFIG_PATH)
                if not isinstance(bt_cand, dict) or not isinstance(bt_cand.get("data"), dict):
                    raise RuntimeError("CODE_CHANGE backtest output missing JSON data")
                cand_summary = summarize_backtest_data(bt_cand["data"])

                return {"baseline": base_summary, "candidate": cand_summary}

            worker_bt = Worker(_run_both)

            def _on_result(payload: dict):
                base = payload.get("baseline") if isinstance(payload, dict) else None
                cand = payload.get("candidate") if isinstance(payload, dict) else None
                compare = self._format_bt_compare(base, cand)
                self.txt_improved_strategy.append("\n" + ("=" * 60) + "\n" + compare)

            def _on_error(msg: str):
                self.txt_improved_strategy.append("\nBacktest error: " + str(msg))

            def _on_finished():
                self._codechange_bt_running = False
                if hasattr(self, "_refresh_code_change_actions_improve"):
                    self._refresh_code_change_actions_improve()

            worker_bt.signals.result.connect(_on_result)
            worker_bt.signals.error.connect(_on_error)
            worker_bt.signals.finished.connect(_on_finished)
            self.threadpool.start(worker_bt)

        self.btn_apply_improved_code.clicked.connect(_on_apply)
        self.btn_copy_improved_code.clicked.connect(_on_copy)
        self.btn_save_improved_code.clicked.connect(_on_save)
        self.btn_backtest_improved_code.clicked.connect(_on_backtest)

        self._refresh_code_change_actions_improve = _refresh_actions

        tab.setLayout(layout)
        self.analysis_tabs.addTab(tab, "Strategy Improvement")
    
    def check_ollama_connection(self):
        """Check if Ollama is available"""
        def _fetch():
            return self.ollama_client.is_available()

        worker = Worker(_fetch)

        def _on_result(is_ok: bool):
            if is_ok:
                self.lbl_ollama_status.setText("Ollama: Connected")
                self.lbl_ollama_status.setStyleSheet("font-weight: bold; color: green;")
            else:
                self.lbl_ollama_status.setText("Ollama: Disconnected")
                self.lbl_ollama_status.setStyleSheet("font-weight: bold; color: red;")

            self.lbl_ollama_status.setToolTip("If disconnected, start Ollama (ollama serve) and verify the Ollama URL in Settings.")

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(lambda _msg: _on_result(False))
        self.threadpool.start(worker)
    
    def analyze_strategy(self):
        """Analyze the current strategy"""
        if self._strategy_analyze_running:
            return
        strategy_code = self.txt_strategy_input.toPlainText()
        if not strategy_code.strip():
            self.txt_analysis_results.setText("Please enter strategy code to analyze.")
            return

        self._strategy_analyze_running = True
        self.btn_analyze_strategy.setEnabled(False)

        do_refine = bool(self.chk_refine.isChecked())
        refine_iters = int(self.spin_refine_iters.value())
        do_scenarios = bool(self.chk_scenarios.isChecked())

        if do_scenarios:
            raw = self.txt_scenarios.toPlainText().strip()
            if not raw:
                self._strategy_analyze_running = False
                self.btn_analyze_strategy.setEnabled(True)
                self.txt_analysis_results.setText("Scenario analysis enabled but no scenarios JSON provided.")
                return

            try:
                scenarios = json.loads(raw)
            except Exception as e:
                self._strategy_analyze_running = False
                self.btn_analyze_strategy.setEnabled(True)
                self.txt_analysis_results.setText(f"Invalid scenarios JSON: {e}")
                return

            self.txt_analysis_results.setText("Running scenario backtests... (this may take a while)")

            def _run_scenarios():
                return self.strategy_service.analyze_strategy_across_scenarios(
                    strategy_code=strategy_code,
                    scenarios=scenarios,
                    user_goal="",
                    market_context=self._build_market_context(),
                )

            worker = Worker(_run_scenarios)

            def _on_result(result: dict):
                if not isinstance(result, dict):
                    raise RuntimeError("Invalid scenario analysis result")

                analysis = result.get("analysis", "")
                risk = result.get("risk", "")
                store_errors = result.get("performance_store_errors", [])
                self._set_last_run_id_for_feedback(result.get("analysis_run_id"))

                parts = []
                parts.append("Scenario analysis completed.")
                if isinstance(analysis, str) and analysis.strip():
                    parts.append("\n" + ("=" * 60))
                    parts.append("Scenario analysis")
                    parts.append(analysis.strip())
                if isinstance(risk, str) and risk.strip():
                    parts.append("\n" + ("-" * 60))
                    parts.append("Scenario risk assessment")
                    parts.append(risk.strip())

                if isinstance(store_errors, list) and store_errors:
                    parts.append("\n" + ("-" * 60))
                    parts.append("Performance store errors:")
                    for e in store_errors[:5]:
                        if isinstance(e, str) and e.strip():
                            parts.append(e.strip())

                self.txt_analysis_results.setText("\n".join(parts))

            def _on_error(msg: str):
                self.txt_analysis_results.setText(f"Error: {msg}")

            def _on_finished():
                self._strategy_analyze_running = False
                self.btn_analyze_strategy.setEnabled(True)

            worker.signals.result.connect(_on_result)
            worker.signals.error.connect(_on_error)
            worker.signals.finished.connect(_on_finished)
            self.threadpool.start(worker)
            return

        if do_refine:
            self.txt_analysis_results.setText(
                f"Running backtest refinement ({refine_iters} iteration(s))... (this may take a while)"
            )

            def _run_loop():
                return self.strategy_service.refine_strategy_with_backtest_loop(
                    strategy_code=strategy_code,
                    user_goal="",
                    max_iterations=refine_iters,
                    market_context=self._build_market_context(),
                )

            worker = Worker(_run_loop)

            def _on_result(result: dict):
                if not isinstance(result, dict):
                    raise RuntimeError("Invalid refinement result")

                iterations = result.get("iterations", [])
                final = result.get("final", {})
                final_file = final.get("result_file") if isinstance(final, dict) else None
                store_errors = result.get("performance_store_errors", [])

                last_iter_run_id = None
                if isinstance(iterations, list) and iterations:
                    for it in iterations:
                        rid = it.get("performance_run_id") if isinstance(it, dict) else None
                        if isinstance(rid, int) and rid > 0:
                            last_iter_run_id = rid
                self._set_last_run_id_for_feedback(last_iter_run_id or (final.get("performance_run_id") if isinstance(final, dict) else None))

                text_parts = []
                text_parts.append("Refinement completed.")
                if final_file:
                    text_parts.append(f"Final backtest file: {final_file}")

                if isinstance(iterations, list) and iterations:
                    for it in iterations:
                        idx = it.get("iteration")
                        analysis = it.get("analysis", "")
                        risk = it.get("risk", "")
                        text_parts.append("\n" + ("=" * 60))
                        text_parts.append(f"Iteration {idx} analysis")
                        text_parts.append((analysis or "").strip())

                        if isinstance(risk, str) and risk.strip():
                            text_parts.append("\n" + ("-" * 40))
                            text_parts.append(f"Iteration {idx} risk assessment")
                            text_parts.append(risk.strip())

                # Always show the final refined code at the end so user can copy/save.
                final_code = final.get("strategy_code") if isinstance(final, dict) else None
                if isinstance(final_code, str) and final_code.strip():
                    text_parts.append("\n" + ("=" * 60))
                    text_parts.append("Final refined strategy code:")
                    text_parts.append(final_code)

                if isinstance(store_errors, list) and store_errors:
                    text_parts.append("\n" + ("-" * 60))
                    text_parts.append("Performance store errors:")
                    for e in store_errors[:5]:
                        if isinstance(e, str) and e.strip():
                            text_parts.append(e.strip())

                self.txt_analysis_results.setText("\n".join(text_parts))

        else:
            self.txt_analysis_results.setText("Running backtest... (this may take a while)")

            def _run_bt():
                return run_backtest(strategy_code=strategy_code, config_path=BOT_CONFIG_PATH)

            worker = Worker(_run_bt)

            def _on_result(bt_result: dict):
                result_file = bt_result.get("result_file") if isinstance(bt_result, dict) else None
                self.txt_analysis_results.setText(
                    "Backtest finished. Sending results to AI for analysis...\n"
                    + (f"Backtest file: {result_file}\n" if result_file else "")
                )

                def _analyze():
                    if not isinstance(bt_result, dict):
                        raise RuntimeError("Invalid backtest result")
                    data = bt_result.get("data")
                    if not isinstance(data, dict):
                        raise RuntimeError("Backtest output missing JSON data")

                    stdout = bt_result.get("stdout", "")
                    stderr = bt_result.get("stderr", "")

                    bt_summary = summarize_backtest_data(data)
                    bt_forensics = build_trade_forensics(data)

                    payload = {
                        "strategy_class": bt_result.get("strategy_class"),
                        "result_file": bt_result.get("result_file"),
                        "stdout_tail": str(stdout)[-2000:],
                        "stderr_tail": str(stderr)[-2000:],
                        "backtest_summary": bt_summary,
                        "trade_forensics": bt_forensics,
                        "market_context": self._build_market_context(),
                    }

                    text = self.ollama_client.analyze_strategy_with_backtest_contract(strategy_code, payload)
                    store_error = None
                    run_id = None
                    try:
                        run_id = self.strategy_service.performance_store.record_run(
                            run_type="single_backtest_analysis",
                            strategy_code=strategy_code,
                            user_goal=None,
                            scenario_name=None,
                            iteration=None,
                            timerange=None,
                            timeframe=None,
                            pairs=None,
                            result_file=str(bt_result.get("result_file") or "") or None,
                            model_analysis=str(getattr(self.ollama_client, "model", "") or "") or None,
                            model_risk=None,
                            analysis_text=text,
                            risk_text=None,
                            backtest_summary=bt_summary,
                            trade_forensics=bt_forensics,
                            market_context=payload.get("market_context"),
                            extra={
                                "strategy_class": bt_result.get("strategy_class"),
                                "stdout_tail": payload.get("stdout_tail"),
                                "stderr_tail": payload.get("stderr_tail"),
                            },
                        )
                    except Exception as e:
                        store_error = str(e)

                    return {
                        "analysis_text": text,
                        "performance_store_error": store_error,
                        "performance_run_id": run_id,
                        "baseline_bt_summary": bt_summary,
                    }

                worker_ai = Worker(_analyze)

                def _on_ai_result(result: dict):
                    if isinstance(result, dict):
                        text = result.get("analysis_text", "")
                        store_error = result.get("performance_store_error")
                        self._set_last_run_id_for_feedback(result.get("performance_run_id"))
                        out = str(text or "")
                        if isinstance(store_error, str) and store_error.strip():
                            out = out.rstrip() + "\n\n" + ("-" * 60) + "\nPerformance store error:\n" + store_error.strip()
                        self.txt_analysis_results.setText(out)
                        code_change = self._extract_code_change(out)
                        self._last_code_change_analysis = code_change
                        baseline = result.get("baseline_bt_summary")
                        if isinstance(baseline, dict):
                            self._last_baseline_bt_summary = baseline
                        if hasattr(self, "_refresh_code_change_actions_analysis"):
                            self._refresh_code_change_actions_analysis()
                        return
                    self.txt_analysis_results.setText(str(result))

                def _on_ai_error(msg: str):
                    self.txt_analysis_results.setText(f"Error: {msg}")

                def _on_ai_finished():
                    self._strategy_analyze_running = False
                    self.btn_analyze_strategy.setEnabled(True)

                worker_ai.signals.result.connect(_on_ai_result)
                worker_ai.signals.error.connect(_on_ai_error)
                worker_ai.signals.finished.connect(_on_ai_finished)
                self.threadpool.start(worker_ai)

                return

        def _on_error(msg: str):
            self.txt_analysis_results.setText(f"Error: {msg}")

        def _on_finished():
            self._strategy_analyze_running = False
            self.btn_analyze_strategy.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)
    
    def fetch_trades_for_analysis(self):
        """Fetch recent trades for loss analysis"""
        if self._loss_fetch_running:
            return

        self._loss_fetch_running = True
        self.btn_fetch_trades.setEnabled(False)
        self.txt_loss_results.setText("Fetching trades...")

        def _fetch():
            return {
                "trades": self.client.get_trade_history(),
                "profit": self.client.get_profit(),
            }

        worker = Worker(_fetch)

        def _on_result(data):
            trades = data.get("trades", [])
            profit_data = data.get("profit", {})

            if trades:
                self.trade_history = trades
                drawdown = 0
                if isinstance(profit_data, dict):
                    drawdown = profit_data.get('max_drawdown', 0)
                self.lbl_drawdown.setText(f"Current Drawdown: {drawdown:.2f}%")
                self.txt_loss_results.setText("Trades loaded. Click Analyze Losses.")
            else:
                self.txt_loss_results.setText("No trade history available.")

        def _on_error(msg: str):
            self.txt_loss_results.setText(f"Error: {msg}")

        def _on_finished():
            self._loss_fetch_running = False
            self.btn_fetch_trades.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)
    
    def analyze_losses(self):
        """Analyze recent losses"""
        if self._loss_analyze_running:
            return
        if not hasattr(self, 'trade_history'):
            self.txt_loss_results.setText("Please fetch trades first using the 'Fetch Recent Trades' button.")
            return

        self._loss_analyze_running = True
        self.btn_analyze_losses.setEnabled(False)
        self.txt_loss_results.setText("Analyzing losses...")

        def _fetch_drawdown():
            profit_data = self.client.get_profit()
            if isinstance(profit_data, dict):
                return profit_data.get('max_drawdown', 0)
            return 0

        def _analyze(current_drawdown: float):
            return self.ollama_client.analyze_losses(self.trade_history, current_drawdown)

        worker_drawdown = Worker(_fetch_drawdown)

        def _on_drawdown(drawdown: float):
            worker_analysis = Worker(_analyze, drawdown)

            def _on_result(text: str):
                self.txt_loss_results.setText(text)

            def _on_error(msg: str):
                self.txt_loss_results.setText(f"Error: {msg}")

            def _on_finished():
                self._loss_analyze_running = False
                self.btn_analyze_losses.setEnabled(True)

            worker_analysis.signals.result.connect(_on_result)
            worker_analysis.signals.error.connect(_on_error)
            worker_analysis.signals.finished.connect(_on_finished)
            self.threadpool.start(worker_analysis)

        def _on_drawdown_error(msg: str):
            self.txt_loss_results.setText(f"Error: {msg}")
            self._loss_analyze_running = False
            self.btn_analyze_losses.setEnabled(True)

        worker_drawdown.signals.result.connect(_on_drawdown)
        worker_drawdown.signals.error.connect(_on_drawdown_error)
        self.threadpool.start(worker_drawdown)
    
    def generate_improvements(self):
        """Generate strategy improvements"""
        if self._improve_running:
            return
        current_strategy = self.txt_current_strategy.toPlainText()
        if not current_strategy.strip():
            self.txt_improved_strategy.setText("Please enter current strategy code.")
            return

        self._improve_running = True
        self.btn_improve.setEnabled(False)
        self.txt_improved_strategy.setText("Generating improvements...")

        def _fetch_metrics():
            profit_data = self.client.get_profit()
            if not isinstance(profit_data, dict):
                raise RuntimeError("Could not retrieve performance data")

            profit_pct = profit_data.get('profit_all_percent', profit_data.get('profit_all_pct', 0))
            try:
                profit_pct = float(profit_pct)
            except Exception:
                profit_pct = 0.0
            return {
                'profit_pct': profit_pct,
                'max_drawdown': profit_data.get('max_drawdown', 0),
                'total_trades': profit_data.get('trade_count', 0)
            }

        worker_metrics = Worker(_fetch_metrics)

        def _on_metrics(metrics):
            worker_improve = Worker(self.ollama_client.generate_strategy_improvements_contract, current_strategy, metrics)

            def _on_result(text: str):
                out = str(text or "")
                self.txt_improved_strategy.setText(out)
                code_change = self._extract_code_change(out)
                self._last_code_change_improve = code_change
                if hasattr(self, "_refresh_code_change_actions_improve"):
                    self._refresh_code_change_actions_improve()

            def _on_error(msg: str):
                self.txt_improved_strategy.setText(f"Error: {msg}")

            def _on_finished():
                self._improve_running = False
                self.btn_improve.setEnabled(True)

            worker_improve.signals.result.connect(_on_result)
            worker_improve.signals.error.connect(_on_error)
            worker_improve.signals.finished.connect(_on_finished)
            self.threadpool.start(worker_improve)

        def _on_metrics_error(msg: str):
            self.txt_improved_strategy.setText(f"Error: {msg}")
            self._improve_running = False
            self.btn_improve.setEnabled(True)

        worker_metrics.signals.result.connect(_on_metrics)
        worker_metrics.signals.error.connect(_on_metrics_error)
        self.threadpool.start(worker_metrics)
