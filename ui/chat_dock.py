import html
from datetime import datetime
from typing import Callable, Optional

from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLineEdit,
    QTextBrowser,
    QDockWidget,
    QMessageBox,
    QSizePolicy,
)
from PyQt6.QtCore import Qt, QThreadPool, QCoreApplication

from utils.ollama_client import OllamaClient
from utils.ai_feedback import AIFeedbackCollector
from utils.qt_worker import Worker


class ChatDock(QDockWidget):
    # Configuration constants for memory management
    MAX_HISTORY_MESSAGES = 100  # Maximum number of messages to keep in history
    MAX_DISPLAYED_MESSAGES = 50  # Maximum messages to display at once
    HTML_SIZE_THRESHOLD = 1000000  # 1MB - trigger cleanup when HTML exceeds this
    MESSAGE_GROUPING_THRESHOLD = 10  # Group messages after this many consecutive messages

    def __init__(
        self,
        threadpool: QThreadPool,
        base_url: str,
        model: str,
        options: dict | None = None,
        context_provider: Optional[Callable[[], str]] = None,
        parent=None,
    ):
        super().__init__("AI Chat", parent)
        self.setObjectName("AIDockChat")
        self.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)
        self.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetClosable
            | QDockWidget.DockWidgetFeature.DockWidgetMovable
            | QDockWidget.DockWidgetFeature.DockWidgetFloatable
        )
        self.setMinimumWidth(260)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.threadpool = threadpool
        self.ollama = OllamaClient(base_url=base_url, model=model, options=options if isinstance(options, dict) else {})
        self._context_provider = context_provider
        self._feedback_collector = AIFeedbackCollector()

        self._running = False
        self._history: list[dict] = []
        self._message_count = 0  # Track total messages for cleanup
        self._consecutive_messages = 0  # Track consecutive messages for grouping

        root = QWidget()
        root.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.chat_view = QTextBrowser()
        self.chat_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.chat_view.setOpenExternalLinks(True)
        self.chat_view.setReadOnly(True)
        self.chat_view.setAccessibleName("Chat messages display")
        self.chat_view.setAccessibleDescription("Displays the conversation history with AI assistant")
        self.chat_view.setStyleSheet(
            "QTextBrowser {"
            "background: #121212;"
            "color: #e0e0e0;"
            "border: 1px solid #333333;"
            "border-radius: 12px;"
            "padding: 12px;"
            "font-family: 'Segoe UI', sans-serif;"
            "font-size: 14px;"
            "}"
        )

        self.input_line = QLineEdit()
        self.input_line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.input_line.setPlaceholderText("Ask about strategies, backtests, risk, or paste code...")
        self.input_line.returnPressed.connect(self.send)
        self.input_line.setAccessibleName("Chat input field")
        self.input_line.setAccessibleDescription("Type your message here and press Enter to send")
        self.input_line.setStyleSheet(
            "QLineEdit {"
            "background: #1e1e1e;"
            "color: #ffffff;"
            "border: 1px solid #444444;"
            "border-radius: 12px;"
            "padding: 12px;"
            "font-family: 'Segoe UI', sans-serif;"
            "font-size: 14px;"
            "}"
        )

        self.btn_send = QPushButton("Send")
        self.btn_send.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.btn_send.clicked.connect(self.send)
        self.btn_send.setAccessibleName("Send message button")
        self.btn_send.setAccessibleDescription("Click to send your message to the AI assistant")
        self.btn_send.setStyleSheet(
            "QPushButton {"
            "background: #4a8cff;"
            "color: white;"
            "font-weight: bold;"
            "border-radius: 12px;"
            "padding: 12px 16px;"
            "font-family: 'Segoe UI', sans-serif;"
            "font-size: 14px;"
            "}"
            "QPushButton:hover {"
            "background: #5a9cff;"
            "}"
            "QPushButton:disabled {"
            "background: #333333;"
            "color: #888888;"
            "}"
        )
        
        # Add AI suggestions button
        self.btn_suggestions = QPushButton("💡")
        self.btn_suggestions.setStyleSheet(
            "QPushButton {"
            "background: #666666;"
            "color: white;"
            "font-weight: bold;"
            "border-radius: 12px;"
            "padding: 12px 16px;"
            "font-family: 'Segoe UI', sans-serif;"
            "font-size: 14px;"
            "}"
            "QPushButton:hover {"
            "background: #777777;"
            "}"
        )
        self.btn_suggestions.setToolTip("Get AI suggestions")
        self.btn_suggestions.clicked.connect(self._show_suggestions)
        
        bottom = QHBoxLayout()
        bottom.addWidget(self.input_line, 1)
        bottom.addWidget(self.btn_suggestions)
        bottom.addWidget(self.btn_send)

        # Feedback buttons
        self.btn_feedback_good = QPushButton("👍")
        self.btn_feedback_good.setStyleSheet("QPushButton { background: #4CAF50; color: white; padding: 4px 8px; }")
        self.btn_feedback_good.setToolTip("Good response")
        self.btn_feedback_good.clicked.connect(lambda: self._submit_feedback(5))
        self.btn_feedback_good.setEnabled(False)
        
        self.btn_feedback_bad = QPushButton("👎")
        self.btn_feedback_bad.setStyleSheet("QPushButton { background: #F44336; color: white; padding: 4px 8px; }")
        self.btn_feedback_bad.setToolTip("Bad response")
        self.btn_feedback_bad.clicked.connect(lambda: self._submit_feedback(1))
        self.btn_feedback_bad.setEnabled(False)
        
        feedback_layout = QHBoxLayout()
        feedback_layout.addWidget(self.btn_feedback_good)
        feedback_layout.addWidget(self.btn_feedback_bad)
        feedback_layout.addStretch()
        
        layout.addWidget(self.chat_view, 1)
        layout.addLayout(bottom)
        layout.addLayout(feedback_layout)

        self._append_system(
            "Chat is ready. Ask questions about strategy logic, backtests, fees, drawdown, and improvements. "
            "Use code fences (```python / ```json) for code or JSON blocks."
        )

    def update_ollama_settings(self, base_url: str, model: str, options: dict | None = None, task_models: dict | None = None) -> None:
        chat_model = model
        if isinstance(task_models, dict):
            chat_model = str(task_models.get("chat") or chat_model)
        self.ollama.update_settings(base_url=base_url, model=chat_model, options=options)

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.btn_send.setEnabled(not running)
        self.input_line.setEnabled(not running)
        self.btn_suggestions.setEnabled(not running)
    
    def keyPressEvent(self, event):
        """Handle keyboard shortcuts for accessibility"""
        if event.key() == Qt.Key.Key_Escape and self.input_line.hasFocus():
            # Clear input on Escape
            self.input_line.clear()
            event.accept()
        elif event.key() == Qt.Key.Key_Return and not self.input_line.hasFocus():
            # Focus input on Enter when not focused
            self.input_line.setFocus()
            event.accept()
        elif event.key() == Qt.Key.Key_S and event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            # Show suggestions with Ctrl+S
            self._show_suggestions()
            event.accept()
        else:
            super().keyPressEvent(event)

    def _create_bubble(self, role: str, text: str) -> str:
        """Create HTML bubble for a message (extracted for reuse)"""
        ts = datetime.now().strftime("%H:%M")
        safe = self._render_text_with_code_blocks(text)

        if role == "user":
            bg = "#1e2a4a"
            align = "right"
            border = "#4a8cff"
            title = f"You · {ts}"
        elif role == "assistant":
            bg = "#1a2e22"
            align = "left"
            border = "#4caf50"
            title = f"AI · {ts}"
        else:
            bg = "#222222"
            align = "center"
            border = "#555555"
            title = f"System · {ts}"

        return (
            f"<div style='margin: 10px 0; text-align: {align};'>"
            f"<div style='display: inline-block; max-width: 95%; background: {bg}; "
            f"border: 1px solid {border}; border-radius: 14px; padding: 12px 14px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
            f"<div style='font-size: 12px; color: #cccccc; margin-bottom: 8px; font-weight: bold;'>{html.escape(title)}</div>"
            f"<div style='font-size: 14px; line-height: 1.4; white-space: normal;'>{safe}</div>"
            f"</div>"
            f"</div>"
        )

    def _append_system(self, text: str) -> None:
        self._history.append({"role": "system", "content": text})
        self._append_bubble("system", text)
        self._check_memory_pressure()

    def _append_user(self, text: str) -> None:
        self._history.append({"role": "user", "content": text})
        self._append_bubble("user", text)
        self._check_memory_pressure()

    def _append_assistant(self, text: str) -> None:
        self._history.append({"role": "assistant", "content": text})
        self._append_bubble("assistant", text)
        self._check_memory_pressure()

    def _check_memory_pressure(self) -> None:
        """Check memory pressure and cleanup if needed"""
        self._message_count += 1
        self._consecutive_messages += 1
        
        # Cleanup every N messages or when history exceeds limit
        if self._message_count % 10 == 0 or len(self._history) > self.MAX_HISTORY_MESSAGES:
            self._trim_history()
        
        # Group messages if consecutive messages exceed threshold
        if self._consecutive_messages >= self.MESSAGE_GROUPING_THRESHOLD:
            self._group_messages()
    
    def _trim_history(self) -> None:
        """Trim history to maximum allowed messages to prevent memory leaks"""
        if len(self._history) <= self.MAX_HISTORY_MESSAGES:
            return
        
        # Keep system message at the start, trim oldest non-system messages
        system_messages = [h for h in self._history if h.get("role") == "system"]
        other_messages = [h for h in self._history if h.get("role") != "system"]
        
        # Keep only the most recent non-system messages
        trimmed_others = other_messages[-self.MAX_HISTORY_MESSAGES:]
        self._history = system_messages + trimmed_others
        
        # Also trim the displayed HTML to match
        self._trim_display()
    
    def _group_messages(self) -> None:
        """Group consecutive messages to optimize display"""
        if len(self._history) < self.MESSAGE_GROUPING_THRESHOLD:
            return
        
        # Reset consecutive message counter
        self._consecutive_messages = 0
        
        # Group messages in the display
        visible_history = self._history[-self.MAX_DISPLAYED_MESSAGES:]
        
        # Build HTML with grouped messages
        html_parts = ["<html><head><meta charset='utf-8'></head><body style='margin:0;'>"]
        
        # Add grouped message indicator
        if len(self._history) > self.MAX_DISPLAYED_MESSAGES:
            html_parts.append("<div style='padding: 10px; color: #888; font-size: 12px; text-align: center;'>")
            html_parts.append("--- Previous messages grouped ---")
            html_parts.append("</div>")
        
        # Group messages by sender
        current_sender = None
        grouped_messages = []
        
        for msg in visible_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            if role != current_sender:
                if grouped_messages:
                    # Add grouped messages
                    grouped_html = self._create_grouped_bubble(current_sender, grouped_messages)
                    html_parts.append(grouped_html)
                    grouped_messages = []
                current_sender = role
            
            grouped_messages.append(content)
        
        # Add any remaining grouped messages
        if grouped_messages:
            grouped_html = self._create_grouped_bubble(current_sender, grouped_messages)
            html_parts.append(grouped_html)
        
        html_parts.append("</body></html>")
        
        self.chat_view.setHtml("".join(html_parts))
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())
    
    def _create_grouped_bubble(self, role: str, messages: list[str]) -> str:
        """Create HTML bubble for grouped messages"""
        ts = datetime.now().strftime("%H:%M")
        
        if role == "user":
            bg = "#1e2a4a"
            align = "right"
            border = "#4a8cff"
            title = f"You · {ts}"
        elif role == "assistant":
            bg = "#1a2e22"
            align = "left"
            border = "#4caf50"
            title = f"AI · {ts}"
        else:
            bg = "#222222"
            align = "center"
            border = "#555555"
            title = f"System · {ts}"
        
        # Combine messages with separators
        combined_content = "<div style='margin: 6px 0; padding: 6px 0; border-top: 1px solid rgba(255,255,255,0.1);'>".join(
            [self._render_text_with_code_blocks(msg) for msg in messages]
        )
        
        return (
            f"<div style='margin: 10px 0; text-align: {align};'>"
            f"<div style='display: inline-block; max-width: 95%; background: {bg}; "
            f"border: 1px solid {border}; border-radius: 14px; padding: 12px 14px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
            f"<div style='font-size: 12px; color: #cccccc; margin-bottom: 8px; font-weight: bold;'>{html.escape(title)}</div>"
            f"<div style='font-size: 14px; line-height: 1.4; white-space: normal;'>{combined_content}</div>"
            f"</div>"
            f"</div>"
        )
    
    def _trim_display(self) -> None:
        """Trim the displayed messages to prevent HTML bloat"""
        # Rebuild HTML with only recent messages
        visible_history = self._history[-self.MAX_DISPLAYED_MESSAGES:]
         
        # Build compact HTML without full history
        html_parts = ["<html><head><meta charset='utf-8'></head><body style='margin:0;'>"]
        html_parts.append("<div style='padding: 10px; color: #888; font-size: 12px; text-align: center;'>")
        html_parts.append("--- Previous messages hidden ---")
        html_parts.append("</div>")
         
        for msg in visible_history:
            role = msg.get("role", "")
            content = msg.get("content", "")
            bubble = self._create_bubble(role, content)
            html_parts.append(bubble)
         
        html_parts.append("</body></html>")
         
        self.chat_view.setHtml("".join(html_parts))
        self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

    def _append_bubble(self, role: str, text: str) -> None:
        """Append a single bubble to the chat view (original behavior)"""
        bubble = self._create_bubble(role, text)
        
        # Reset consecutive messages counter for new messages
        self._consecutive_messages = 0
        
        cur = self.chat_view.toHtml()
        if not cur:
            cur = "<html><head><meta charset='utf-8'></head><body style='margin:0;'></body></html>"
         
        # Check HTML size and rebuild if too large
        if len(cur) > self.HTML_SIZE_THRESHOLD:
            self._trim_display()
        else:
            self.chat_view.setHtml(cur.replace("</body>", bubble + "</body>"))
            self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

    def _render_text_with_code_blocks(self, text: str) -> str:
        t = text or ""
        parts = []
        while True:
            start = t.find("```")
            if start == -1:
                parts.append(self._render_plain(t))
                break
            parts.append(self._render_plain(t[:start]))
            t = t[start + 3 :]
            end = t.find("```")
            if end == -1:
                parts.append(self._render_code(t, lang=""))
                break
            block = t[:end]
            t = t[end + 3 :]

            lang = ""
            first_nl = block.find("\n")
            if first_nl != -1:
                maybe_lang = block[:first_nl].strip()
                if len(maybe_lang) <= 20 and " " not in maybe_lang and "\t" not in maybe_lang:
                    lang = maybe_lang
                    block = block[first_nl + 1 :]

            parts.append(self._render_code(block, lang=lang))

        return "".join(parts)

    def _render_plain(self, text: str) -> str:
        safe = html.escape(text)
        safe = safe.replace("\n", "<br>")
        return safe

    def _render_code(self, code: str, lang: str = "") -> str:
        safe_code = html.escape(code.rstrip("\n"))
        label = html.escape(lang) if lang else "code"
        return (
            "<div style='margin-top: 10px; margin-bottom: 10px;'>"
            f"<div style='font-size: 12px; color: #aad4ff; margin-bottom: 6px; font-weight: bold;'>{label}</div>"
            "<pre style='margin:0; background:#0e1420; border:1px solid #2a4a7a; "
            "border-radius:12px; padding:12px; overflow:auto; box-shadow: 0 2px 4px rgba(0,0,0,0.1);'>"
            f"<code style='font-family: Consolas, Menlo, monospace; font-size:13px; color:#f0f0f0;'>{safe_code}</code>"
            "</pre>"
            "</div>"
        )

    def _build_prompt(self, user_text: str) -> str:
        system = (
            "You are an expert quantitative trading assistant specialized in Freqtrade strategies. "
            "Be precise and actionable. When proposing fixes, prefer code-level changes. "
            "If you include code or JSON, wrap it in fenced code blocks using triple backticks with a language."
        )

        ctx = ""
        if callable(self._context_provider):
            try:
                ctx = self._context_provider() or ""
            except Exception:
                ctx = ""

        history = [h for h in self._history if h.get("role") in ("user", "assistant")]
        history = history[-20:]

        lines = [f"SYSTEM: {system}"]
        if ctx.strip():
            lines.append(f"CONTEXT (real app state):\n{ctx.strip()}")
        for h in history:
            role = h.get("role")
            content = str(h.get("content", ""))
            if role == "user":
                lines.append(f"USER: {content}")
            else:
                lines.append(f"ASSISTANT: {content}")

        lines.append(f"USER: {user_text}")
        lines.append("ASSISTANT:")
        return "\n\n".join(lines)

    def send(self) -> None:
        if self._running:
            return

        text = self.input_line.text().strip()
        if not text:
            return

        if not self.ollama.is_available():
            QMessageBox.critical(self, "Error", "Ollama is not available. Start it with: ollama serve")
            return

        self.input_line.setText("")
        self._append_user(text)
        self._set_running(True)

        prompt = self._build_prompt(text)

        worker = Worker(self.ollama.generate_text, prompt)

        def _on_result(answer: str):
            if not isinstance(answer, str):
                self._append_assistant("Error: unexpected response type")
                return
            self._append_assistant(answer)

        def _on_error(msg: str):
            self._append_assistant(f"Error: {msg}")

        def _on_finished():
            self._set_running(False)
            # Enable feedback buttons after response is received
            self.btn_feedback_good.setEnabled(True)
            self.btn_feedback_bad.setEnabled(True)

        worker.signals.result.connect(_on_result)
        worker.signals.error.connect(_on_error)
        worker.signals.finished.connect(_on_finished)
        self.threadpool.start(worker)
    
    def _submit_feedback(self, rating: int):
        """Submit feedback on the last AI response"""
        if len(self._history) < 2:  # Need at least user question and AI response
            QMessageBox.warning(self, "Feedback", "No AI response available for feedback")
            return
        
        # Get the last user question and AI response
        last_user = None
        last_assistant = None
        
        for msg in reversed(self._history):
            if msg.get("role") == "user" and last_user is None:
                last_user = msg.get("content", "")
            elif msg.get("role") == "assistant" and last_assistant is None:
                last_assistant = msg.get("content", "")
            
            if last_user and last_assistant:
                break
        
        if not last_user or not last_assistant:
            QMessageBox.warning(self, "Feedback", "Could not find matching question/response pair")
            return
        
        # Submit feedback
        try:
            self._feedback_collector.submit_feedback(
                prompt=last_user,
                response=last_assistant,
                rating=rating,
                model=self.ollama.model if hasattr(self.ollama, 'model') else None
            )
            
            # Show confirmation
            self._append_system(f"Feedback submitted: {'Positive' if rating >= 4 else 'Negative'}")
            
            # Disable feedback buttons after submission
            self.btn_feedback_good.setEnabled(False)
            self.btn_feedback_bad.setEnabled(False)
            
        except Exception as e:
            QMessageBox.critical(self, "Feedback Error", f"Failed to submit feedback: {e}")

    def closeEvent(self, event) -> None:
        # If the application is shutting down, allow the dock to close.
        try:
            if QCoreApplication.instance() is not None and QCoreApplication.closingDown():
                event.accept()
                return
        except Exception:
            pass
    
    def _get_ai_suggestions(self) -> list[str]:
        """Generate AI-driven suggestions based on conversation context"""
        if len(self._history) < 2:
            return []
        
        # Get recent conversation context
        recent_messages = self._history[-5:]  # Last 5 messages
        context = "\n".join([f"{msg.get('role', 'unknown')}: {msg.get('content', '')}" for msg in recent_messages])
        
        # Simple suggestion logic based on keywords
        suggestions = []
        
        # Check for strategy-related questions
        if any(keyword in context.lower() for keyword in ['strategy', 'backtest', 'indicator', 'optimize']):
            suggestions.extend([
                "How can I improve my strategy's performance?",
                "What are the best indicators for this market condition?",
                "Can you analyze my backtest results?",
                "Suggest optimizations for my trading strategy"
            ])
        
        # Check for risk-related questions
        if any(keyword in context.lower() for keyword in ['risk', 'drawdown', 'stop loss', 'position size']):
            suggestions.extend([
                "What's the optimal risk management approach?",
                "How can I reduce my drawdown?",
                "Suggest stop-loss strategies",
                "Calculate position size for this trade"
            ])
        
        # Check for code-related questions
        if any(keyword in context.lower() for keyword in ['code', 'python', 'json', 'error']):
            suggestions.extend([
                "Review this code for potential issues",
                "Suggest improvements for this implementation",
                "Explain this error message",
                "Generate sample code for this use case"
            ])
        
        # Remove duplicates and limit to 3 suggestions
        unique_suggestions = list(dict.fromkeys(suggestions))
        return unique_suggestions[:3]
    
    def _show_suggestions(self) -> None:
        """Display AI-driven suggestions in the chat"""
        suggestions = self._get_ai_suggestions()
        if not suggestions:
            return
        
        # Format suggestions as clickable buttons
        suggestion_html = "<div style='margin: 10px 0; padding: 10px; background: #111111; border-radius: 8px;'>"
        suggestion_html += "<div style='font-size: 12px; color: #aaaaaa; margin-bottom: 8px;'>💡 AI Suggestions:</div>"
        
        for suggestion in suggestions:
            # Create a clickable suggestion that fills the input field
            safe_suggestion = html.escape(suggestion)
            suggestion_html += (
                f"<div style='margin: 4px 0; padding: 6px 10px; background: #222222; border-radius: 6px; "
                f"color: #e0e0e0; font-size: 13px; cursor: pointer; display: inline-block; "
                f"margin-right: 8px;' "
                f"onclick='document.getElementById(\"input_line\").value = \"{safe_suggestion}\"; "
                f"document.getElementById(\"input_line\").focus();'>"
                f"{safe_suggestion}</div>"
            )
        
        suggestion_html += "</div>"
        
        # Add suggestions to chat view
        cur = self.chat_view.toHtml()
        if cur:
            self.chat_view.setHtml(cur.replace("</body>", suggestion_html + "</body>"))
            self.chat_view.verticalScrollBar().setValue(self.chat_view.verticalScrollBar().maximum())

        # Otherwise, don't allow closing via the titlebar X.
        # Users can hide/show via View -> AI Chat.
        event.ignore()
        try:
            parent = self.parent()
            if parent is not None and hasattr(parent, "restore_chat_dock"):
                parent.restore_chat_dock()
        except Exception:
            pass
