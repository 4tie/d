import json
import os
import re
from datetime import date, timedelta
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextEdit, QLineEdit,
    QFileDialog, QMessageBox, QComboBox, QDialog, QDialogButtonBox, QDateEdit,
    QListWidget, QListWidgetItem
)
from PyQt6.QtCore import QThreadPool, QTimer, Qt, QDate

from config.settings import BOT_CONFIG_PATH, APP_CONFIG_PATH, load_app_config
from utils.backtest_runner import run_backtest, download_data
from utils.qt_worker import Worker


class BacktestTab(QWidget):
    """Backtest tab"""
    def __init__(self, threadpool: QThreadPool, parent=None):
        super().__init__(parent)
        self.threadpool = threadpool
        self._running = False
        self._prefs_save_timer = QTimer(self)
        self._prefs_save_timer.setSingleShot(True)
        self._prefs_save_timer.timeout.connect(self._save_prefs_to_app_config)
        self._known_pairs = []
        self.setup_ui()
        self._load_defaults_from_bot_config()
        self._load_prefs_from_app_config()

    def setup_ui(self):
        layout = QVBoxLayout()

        top_row = QHBoxLayout()
        self.btn_load_file = QPushButton("Load strategy file")
        self.btn_load_file.clicked.connect(self.load_strategy_file)

        self.timeframe_combo = QComboBox()
        self.timeframe_combo.setEditable(True)
        self.timeframe_combo.setMinimumWidth(90)
        self.timeframe_combo.addItems(["1m", "5m", "15m", "30m", "1h", "4h", "1d"])

        self.pairs_combo = QComboBox()
        self.pairs_combo.setEditable(True)
        self.pairs_combo.setMinimumWidth(220)
        self.pairs_combo.setPlaceholderText("Pairs (optional) - comma or space separated")
        self.pairs_combo.addItem("(no override)", "")
        self.btn_pairs_custom = QPushButton("Custom")
        self.btn_pairs_custom.clicked.connect(self.open_pairs_dialog)

        self.timerange_combo = QComboBox()
        self.timerange_combo.setEditable(True)
        self.timerange_combo.setMinimumWidth(170)
        self.timerange_combo.setPlaceholderText("Timerange (optional), e.g. 20240101-20241231")
        self.timerange_combo.addItem("(no timerange)", "")
        self._add_timerange_presets()
        self.btn_timerange_custom = QPushButton("Custom")
        self.btn_timerange_custom.clicked.connect(self.open_timerange_dialog)

        self.timeframe_combo.currentTextChanged.connect(self._schedule_save_prefs)
        self.pairs_combo.currentTextChanged.connect(self._schedule_save_prefs)
        self.timerange_combo.currentTextChanged.connect(self._schedule_save_prefs)

        self.btn_run = QPushButton("Run backtest")
        self.btn_run.clicked.connect(self.run_backtest_async)

        self.btn_download = QPushButton("Download data")
        self.btn_download.clicked.connect(self.download_data_async)

        top_row.addWidget(self.btn_load_file)
        top_row.addWidget(QLabel("Timeframe:"))
        top_row.addWidget(self.timeframe_combo)
        top_row.addWidget(QLabel("Pairs:"))
        top_row.addWidget(self.pairs_combo)
        top_row.addWidget(self.btn_pairs_custom)
        top_row.addWidget(QLabel("Timerange:"))
        top_row.addWidget(self.timerange_combo)
        top_row.addWidget(self.btn_timerange_custom)
        top_row.addWidget(self.btn_run)
        layout.addLayout(top_row)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.btn_download)
        layout.addLayout(btn_row)

        self.lbl_status = QLabel(f"Config: {BOT_CONFIG_PATH}")
        layout.addWidget(self.lbl_status)

        self.txt_strategy = QTextEdit()
        self.txt_strategy.setPlaceholderText("Paste strategy code here (must include a class inheriting from IStrategy)...")
        self.txt_strategy.setMinimumHeight(180)
        layout.addWidget(QLabel("Strategy Code"))
        layout.addWidget(self.txt_strategy)

        self.txt_summary = QTextEdit()
        self.txt_summary.setReadOnly(True)
        self.txt_summary.setPlaceholderText("Backtest summary will appear here...")
        self.txt_summary.setMinimumHeight(140)
        layout.addWidget(QLabel("Summary"))
        layout.addWidget(self.txt_summary)

        self.txt_raw = QTextEdit()
        self.txt_raw.setReadOnly(True)
        self.txt_raw.setPlaceholderText("Raw backtest JSON and output will appear here...")
        layout.addWidget(QLabel("Raw Result"))
        layout.addWidget(self.txt_raw)

        self.setLayout(layout)

    def _add_timerange_presets(self):
        today = date.today()

        def _add(days: int):
            start = today - timedelta(days=days)
            tr = f"{start.strftime('%Y%m%d')}-{today.strftime('%Y%m%d')}"
            self.timerange_combo.addItem(f"Last {days}d ({tr})", tr)

        for d in [7, 30, 90, 180, 365]:
            _add(d)

        ytd_start = date(today.year, 1, 1)
        ytd = f"{ytd_start.strftime('%Y%m%d')}-{today.strftime('%Y%m%d')}"
        self.timerange_combo.addItem(f"YTD ({ytd})", ytd)

    def _extract_timerange(self, text: str):
        m = re.search(r"(\d{8}-\d{8})", text or "")
        return m.group(1) if m else None

    def _schedule_save_prefs(self, _text: str = ""):
        if self._running:
            return
        self._prefs_save_timer.start(500)

    def _get_current_pairs_value(self):
        pairs_data = self.pairs_combo.currentData()
        if isinstance(pairs_data, str):
            pairs_data = pairs_data.strip()
            return pairs_data

        pairs_text = self.pairs_combo.currentText().strip()
        if not pairs_text or pairs_text.startswith('('):
            return ""
        return pairs_text

    def _get_current_timerange_value(self):
        timerange_data = self.timerange_combo.currentData()
        if isinstance(timerange_data, str):
            timerange_data = timerange_data.strip()
            return timerange_data

        timerange_text = self.timerange_combo.currentText().strip()
        tr = self._extract_timerange(timerange_text) if timerange_text else None
        return tr or ""

    def _save_prefs_to_app_config(self):
        try:
            cfg = load_app_config()
            if not isinstance(cfg, dict):
                return

            bt = cfg.get('backtest')
            if bt is None or not isinstance(bt, dict):
                bt = {}
                cfg['backtest'] = bt

            bt['timeframe'] = self.timeframe_combo.currentText().strip()
            bt['pairs'] = self._get_current_pairs_value()
            bt['timerange'] = self._get_current_timerange_value()

            with open(APP_CONFIG_PATH, 'w', encoding='utf-8') as f:
                json.dump(cfg, f, indent=2)
        except Exception:
            return

    def _load_prefs_from_app_config(self):
        try:
            cfg = load_app_config()
            if not isinstance(cfg, dict):
                return

            bt = cfg.get('backtest')
            if not isinstance(bt, dict):
                return

            tf = bt.get('timeframe')
            if isinstance(tf, str) and tf.strip():
                self.timeframe_combo.setCurrentText(tf.strip())

            pairs = bt.get('pairs')
            if isinstance(pairs, str):
                pairs = pairs.strip()
                if not pairs:
                    idx = self.pairs_combo.findText('(no override)')
                    if idx >= 0:
                        self.pairs_combo.setCurrentIndex(idx)
                else:
                    idx = -1
                    for i in range(self.pairs_combo.count()):
                        d = self.pairs_combo.itemData(i)
                        if isinstance(d, str) and d.strip() == pairs:
                            idx = i
                            break
                    if idx >= 0:
                        self.pairs_combo.setCurrentIndex(idx)
                    else:
                        if self.pairs_combo.findText(pairs) == -1:
                            self.pairs_combo.addItem(pairs, pairs)
                        self.pairs_combo.setCurrentText(pairs)

            tr = bt.get('timerange')
            if isinstance(tr, str):
                tr = tr.strip()
                if not tr:
                    idx = self.timerange_combo.findText('(no timerange)')
                    if idx >= 0:
                        self.timerange_combo.setCurrentIndex(idx)
                else:
                    idx = -1
                    for i in range(self.timerange_combo.count()):
                        d = self.timerange_combo.itemData(i)
                        if isinstance(d, str) and d.strip() == tr:
                            idx = i
                            break
                    if idx >= 0:
                        self.timerange_combo.setCurrentIndex(idx)
                    else:
                        if self.timerange_combo.findText(tr) == -1:
                            self.timerange_combo.addItem(tr, tr)
                        self.timerange_combo.setCurrentText(tr)
        except Exception:
            return

    def _load_defaults_from_bot_config(self):
        try:
            with open(BOT_CONFIG_PATH, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            if not isinstance(cfg, dict):
                return

            timeframe = cfg.get('timeframe')
            if isinstance(timeframe, str) and timeframe.strip():
                self.timeframe_combo.setCurrentText(timeframe.strip())

            ex = cfg.get('exchange')
            if isinstance(ex, dict):
                whitelist = ex.get('pair_whitelist')
                if isinstance(whitelist, list) and whitelist:
                    cleaned = [str(p).strip() for p in whitelist if str(p).strip()]
                    self._known_pairs = cleaned
                    joined = ",".join(cleaned)

                    if joined:
                        label = f"Whitelist ({len(cleaned)} pairs)"
                        if self.pairs_combo.findText(label) == -1:
                            self.pairs_combo.addItem(label, joined)

                    for p in cleaned:
                        if self.pairs_combo.findText(p) == -1:
                            self.pairs_combo.addItem(p, p)

                    if joined:
                        self.pairs_combo.setCurrentIndex(self.pairs_combo.findText(label))

            self._load_timerange_history()
        except Exception:
            return

    def open_timerange_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("Select Timerange")
        layout = QVBoxLayout(dlg)

        row = QHBoxLayout()
        start_edit = QDateEdit()
        start_edit.setCalendarPopup(True)
        end_edit = QDateEdit()
        end_edit.setCalendarPopup(True)

        today = date.today()
        default_start = today - timedelta(days=30)
        default_end = today

        current = self._get_current_timerange_value()
        if current:
            m = re.match(r"^(\d{8})-(\d{8})$", current)
            if m:
                try:
                    ys, ms, ds = int(m.group(1)[0:4]), int(m.group(1)[4:6]), int(m.group(1)[6:8])
                    ye, me, de = int(m.group(2)[0:4]), int(m.group(2)[4:6]), int(m.group(2)[6:8])
                    default_start = date(ys, ms, ds)
                    default_end = date(ye, me, de)
                except Exception:
                    pass

        start_edit.setDate(QDate(default_start.year, default_start.month, default_start.day))
        end_edit.setDate(QDate(default_end.year, default_end.month, default_end.day))

        row.addWidget(QLabel("Start:"))
        row.addWidget(start_edit)
        row.addWidget(QLabel("End:"))
        row.addWidget(end_edit)
        layout.addLayout(row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        s = start_edit.date().toPyDate()
        e = end_edit.date().toPyDate()
        if s > e:
            QMessageBox.warning(self, "Warning", "Start date must be before end date.")
            return

        tr = f"{s.strftime('%Y%m%d')}-{e.strftime('%Y%m%d')}"
        idx = -1
        for i in range(self.timerange_combo.count()):
            d = self.timerange_combo.itemData(i)
            if isinstance(d, str) and d.strip() == tr:
                idx = i
                break
        if idx == -1:
            self.timerange_combo.addItem(f"Custom ({tr})", tr)
            idx = self.timerange_combo.count() - 1
        self.timerange_combo.setCurrentIndex(idx)
        self._schedule_save_prefs()

    def open_pairs_dialog(self):
        pairs = list(dict.fromkeys([p for p in self._known_pairs if isinstance(p, str) and p.strip()]))

        if not pairs:
            QMessageBox.warning(self, "Warning", "No pairs available. Add exchange.pair_whitelist in userdata/config.json.")
            return

        current_raw = self._get_current_pairs_value()
        current_set = set([p.strip() for p in current_raw.replace(",", " ").split() if p.strip()]) if current_raw else set()

        dlg = QDialog(self)
        dlg.setWindowTitle("Select Pairs")
        layout = QVBoxLayout(dlg)

        filter_edit = QLineEdit()
        filter_edit.setPlaceholderText("Filter pairs...")
        layout.addWidget(filter_edit)

        listw = QListWidget()
        layout.addWidget(listw)

        items = []
        for p in pairs:
            it = QListWidgetItem(p)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if p in current_set else Qt.CheckState.Unchecked)
            listw.addItem(it)
            items.append(it)

        def _apply_filter(text: str):
            t = (text or "").strip().lower()
            for it in items:
                it.setHidden(bool(t) and t not in it.text().lower())

        filter_edit.textChanged.connect(_apply_filter)

        btn_row = QHBoxLayout()
        btn_all = QPushButton("All")
        btn_none = QPushButton("None")
        btn_row.addWidget(btn_all)
        btn_row.addWidget(btn_none)
        layout.addLayout(btn_row)

        def _set_all(state: bool):
            for it in items:
                it.setCheckState(Qt.CheckState.Checked if state else Qt.CheckState.Unchecked)

        btn_all.clicked.connect(lambda: _set_all(True))
        btn_none.clicked.connect(lambda: _set_all(False))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        chosen = []
        for it in items:
            if it.checkState() == Qt.CheckState.Checked:
                chosen.append(it.text())

        if not chosen:
            idx = self.pairs_combo.findText('(no override)')
            if idx >= 0:
                self.pairs_combo.setCurrentIndex(idx)
            else:
                self.pairs_combo.setCurrentText('')
            self._schedule_save_prefs()
            return

        joined = ",".join(chosen)

        idx = -1
        for i in range(self.pairs_combo.count()):
            d = self.pairs_combo.itemData(i)
            if isinstance(d, str) and d.strip() == joined:
                idx = i
                break

        if idx == -1:
            label = f"Custom ({len(chosen)} pairs)"
            self.pairs_combo.addItem(label, joined)
            idx = self.pairs_combo.count() - 1

        self.pairs_combo.setCurrentIndex(idx)
        self._schedule_save_prefs()

    def _load_timerange_history(self):
        try:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            out_dir = os.path.join(root, "data", "backtest_results")
            if not os.path.isdir(out_dir):
                return

            timeranges = set()
            files = []
            for name in os.listdir(out_dir):
                if name.lower().endswith('.json'):
                    files.append(os.path.join(out_dir, name))

            files.sort(key=lambda p: os.path.getmtime(p), reverse=True)
            for path in files[:30]:
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if not isinstance(data, dict):
                        continue

                    meta = data.get('metadata')
                    if isinstance(meta, dict):
                        tr = meta.get('timerange')
                        if isinstance(tr, str) and tr.strip():
                            timeranges.add(tr.strip())

                    tr2 = data.get('timerange')
                    if isinstance(tr2, str) and tr2.strip():
                        timeranges.add(tr2.strip())
                except Exception:
                    continue

            for tr in sorted(timeranges):
                if self.timerange_combo.findText(tr) == -1:
                    self.timerange_combo.addItem(tr, tr)
        except Exception:
            return

    def _set_running(self, running: bool):
        self._running = running
        self.btn_run.setEnabled(not running)
        self.btn_load_file.setEnabled(not running)
        if hasattr(self, 'btn_pairs_custom'):
            self.btn_pairs_custom.setEnabled(not running)
        if hasattr(self, 'btn_timerange_custom'):
            self.btn_timerange_custom.setEnabled(not running)
        if hasattr(self, 'btn_download'):
            self.btn_download.setEnabled(not running)

    def _get_current_timeframe_value(self):
        tf = self.timeframe_combo.currentText().strip()
        return tf or ""

    def load_strategy_file(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Strategy File", "", "Python Files (*.py)")
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.txt_strategy.setText(f.read())
            self.lbl_status.setText(f"Loaded: {file_path} | Config: {BOT_CONFIG_PATH}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to load file: {e}")

    def run_backtest_async(self):
        if self._running:
            return

        strategy_code = self.txt_strategy.toPlainText()
        if not strategy_code or not strategy_code.strip():
            QMessageBox.warning(self, "Warning", "Please paste strategy code or load a strategy file.")
            return

        timerange_data = self.timerange_combo.currentData()
        if isinstance(timerange_data, str) and timerange_data.strip():
            timerange = timerange_data.strip()
        else:
            timerange_text = self.timerange_combo.currentText().strip()
            timerange = self._extract_timerange(timerange_text) if timerange_text else None

        timeframe = self.timeframe_combo.currentText().strip() or None

        pairs_data = self.pairs_combo.currentData()
        if isinstance(pairs_data, str) and pairs_data.strip():
            pairs = pairs_data.strip()
        else:
            pairs_text = self.pairs_combo.currentText().strip()
            pairs = pairs_text if pairs_text and not pairs_text.startswith('(') else None

        self._set_running(True)
        self.txt_summary.setText("Running backtest... (this may take a while)")
        self.txt_raw.setText("")

        worker = Worker(run_backtest, strategy_code, BOT_CONFIG_PATH, timerange, timeframe, pairs)

        def _on_result(result: dict):
            if not isinstance(result, dict):
                QMessageBox.critical(self, "Error", "Unexpected backtest result format")
                return

            data = result.get("data")
            stdout = result.get("stdout", "")
            stderr = result.get("stderr", "")
            result_file = result.get("result_file")
            strategy_class = result.get("strategy_class")

            summary_lines = []
            summary_lines.append(f"Strategy: {strategy_class}")
            summary_lines.append(f"Result file: {result_file}")

            if isinstance(data, dict):
                for key in ["strategy", "strategy_comparison", "results", "backtest", "metadata"]:
                    if key in data:
                        summary_lines.append(f"Contains: {key}")

            self.txt_summary.setText("\n".join(summary_lines))

            raw_payload = {
                "result_file": result_file,
                "strategy_class": strategy_class,
                "stdout": stdout,
                "stderr": stderr,
                "data": data,
            }
            self.txt_raw.setText(json.dumps(raw_payload, indent=2, ensure_ascii=False))

        def _on_error(msg: str):
            self.txt_summary.setText(f"Backtest failed: {msg}")

        def _on_finished():
            self._set_running(False)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)

    def download_data_async(self):
        if self._running:
            return

        timerange = self._get_current_timerange_value().strip() or None
        timeframe = self._get_current_timeframe_value().strip() or None
        pairs = self._get_current_pairs_value().strip() or None

        self._set_running(True)
        self.txt_summary.setText("Downloading data... (this may take a while)")
        self.txt_raw.setText("")

        worker = Worker(download_data, BOT_CONFIG_PATH, timerange, timeframe, pairs)

        def _on_result(result: dict):
            if not isinstance(result, dict):
                QMessageBox.critical(self, "Error", "Unexpected download result format")
                return
            self.txt_summary.setText("Data download completed.")
            self.txt_raw.setText(json.dumps(result, indent=2, ensure_ascii=False))

        def _on_error(msg: str):
            self.txt_summary.setText(f"Data download failed: {msg}")

        def _on_finished():
            self._set_running(False)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)
