# SmartTrade AI Wrapper: PySide6 Version Specification

This document details the functional options and logic found in the PySide6 implementation of the SmartTrade AI Wrapper.

## 1. Settings Tab (`ui/settings_tab.py`)

### Options
- **Freqtrade API:**
  - `Freqtrade URL`: Endpoint for the trading bot (e.g., `http://127.0.0.1:8080/`).
  - `API User`: Username for authentication.
  - `API Password`: Password (masked input).
- **Ollama AI:**
  - `Ollama URL`: Endpoint for the local LLM server (default: `http://localhost:11434`).
  - `Default Model`: Global default model (e.g., `llama2`).
- **Advanced AI Options (Collapsible Group):**
  - `Temperature`: Control randomness (0.0 to 2.0).
  - `Top_p`: Nucleus sampling (0.0 to 1.0).
  - `Num_predict`: Max tokens to generate (16 to 8192).
- **Task Models / Ensemble (Collapsible Group):**
  - `Strategy generation`: Specific model for coding.
  - `Strategy analysis`: Specific model for performance review.
  - `Risk assessment`: Specific model for safety checks.
  - `Chat`: Specific model for interactive assistance.
- **AI Performance Monitoring:**
  - `Show stats`: Displays queue status, success rates, duration, and feedback metrics.
  - `Clear cache`: Clears the `OllamaClient` internal response cache.

### Logic
- **Connection Testing**: Asynchronous testing for both Freqtrade and Ollama endpoints using `Worker` threads.
- **Model Discovery**: Fetches available models from Ollama to populate dropdowns.
- **Configuration Sync**: Saves to `data/config.json`. (Note: Updated in Tkinter version to also sync credentials to `user_data/config.json`).

---

## 2. AI Builder Tab (`ui/ai_builder_tab.py`)

### Options
- **Prompt Input**: Multi-line text area for natural language strategy descriptions.
- **Templates**: Dropdown with presets (RSI, EMA Crossover, Bollinger Bands, MACD).
- **Code Preview**: Editable area for the generated Python code.

### Logic
- **Generation Loop**: Triggers `StrategyService` to call Ollama.
- **Validation**: AST-based verification of the generated Python code.
- **Save Strategy**: Writes the code to `user_data/strategies/AIStrategy.py`.

---

## 3. Backtest Tab (`ui/backtest_tab.py`)

### Options
- **Timeframe**: Selectable (1m to 1d). Defaults to bot config or 5m.
- **Pairs**: 
  - Manual entry (comma/space separated).
  - Custom Dialog: Filterable list of known pairs from bot whitelist.
- **Timerange**: 
  - Presets (7d, 30d, 90d, 180d, 365d, YTD).
  - Custom Dialog: Date pickers for start and end dates.
- **Load File**: Open existing `.py` strategy files.

### Logic
- **Preference Persistence**: Saves the last used timeframe, pairs, and timerange to `data/config.json` under a `backtest` key.
- **Timerange History**: Scans `data/backtest_results` to populate the dropdown with recently used ranges.
- **Async Execution**: Runs `freqtrade backtesting` as a subprocess via a background worker to keep UI responsive.

---

## 4. AI Analysis Tab (`ui/ai_analysis_tab.py`)

### Sub-Tabs
- **Strategy Analysis**: 
  - Analyze code for bugs/inefficiencies.
  - **Refine Mode**: Multi-iteration loop (AI generates -> Backtest -> AI fixes -> Repeat).
  - **Scenario Analysis**: Run strategy against multiple timeranges (e.g., bull vs. bear markets).
- **Loss Analysis**:
  - Fetches recent trades from Freqtrade API.
  - Identifies patterns in losing trades (time, pair, exit reason).
- **Strategy Improvement**:
  - Compares "Current" vs "Improved" code side-by-side.

### Logic
- **Market Context**: Injects real-time bot state (whitelist, open trades, recent candles) into AI prompts for "market-aware" analysis.
- **Backtest Comparison**: Logic to compare baseline results vs. improved strategy results in a markdown table.
- **Feedback Loop**: Users can rate AI suggestions (1-5 stars) and add comments, stored in SQLite for future RAG/fine-tuning context.

---

## 5. Bot Control Tab (`ui/bot_control_tab.py`)

### Options
- **Config Editor**: Update Strategy name, Timeframe, Pairs, and Max Open Trades.
- **Open Trades Table**: Live view of Pair, Type, Amount, Rates, and Profit %.

### Logic
- **Hot Reload**: Calls `/reload_config` on the Freqtrade API after saving changes.
- **Live Sync**: Periodically refreshes open trades (every 5 seconds).

---

## 6. Chat Dock (`ui/chat_dock.py`)

### Options
- **Input**: Persistent chat bar.
- **Suggestions (💡)**: Quick-access buttons for common tasks.
- **Feedback (👍/👎)**: Quick rating for each AI response.

### Logic
- **Context Injection**: Uses a `context_provider` to feed the current strategy or backtest results into the chat memory.
- **Memory Management**: Trims history to 100 messages and groups consecutive bubbles to prevent UI lag.
- **Markdown Rendering**: Converts AI responses (with code blocks) into rich HTML bubbles.
