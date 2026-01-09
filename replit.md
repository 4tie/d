# SmartTrade AI Wrapper

## Overview

SmartTrade AI Wrapper is a PyQt6-based desktop GUI application that provides an intelligent interface for Freqtrade cryptocurrency trading bot. The application enables users to generate trading strategies using natural language descriptions through local Ollama AI models, run backtests, analyze strategy performance, and control their trading bot through a unified dashboard.

Key capabilities:
- AI-powered strategy generation from natural language descriptions
- Real-time bot status monitoring and control
- Backtesting with automated strategy refinement loops
- AI analysis for loss patterns and strategy improvements
- Persistent chat interface for AI assistance

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Application Structure
The application follows a modular architecture with clear separation of concerns:

- **main.py**: Entry point containing the `SmartBotApp` QMainWindow class that orchestrates all UI tabs and background workers
- **core/**: Business logic layer with `StrategyService` as the central orchestrator for AI operations
- **ui/**: PyQt6 widget components for each major feature (dashboard, AI builder, analysis, backtest, settings, chat)
- **api/**: HTTP client for communicating with Freqtrade REST API
- **utils/**: Utility modules for AI clients, file operations, background workers, and data persistence
- **config/**: Settings management with JSON-based configuration

### AI Integration Pattern
The system uses a multi-model approach through Ollama:
- Different AI models can be assigned to different tasks (strategy generation, analysis, risk assessment, chat)
- `OllamaClient` handles all AI communication with retry logic, connection pooling, and streaming support
- `StrategyGenerator` wraps AI calls specifically for code generation with validation and repair loops
- Knowledge base (SQLite-backed) provides context for AI responses

### Threading Model
Background operations use Qt's `QThreadPool` with custom `Worker` runnables:
- All API calls and AI operations run in background threads
- Signal/slot pattern communicates results back to the UI thread
- Prevents UI freezing during long-running operations

### Data Persistence
- **data/config.json**: Application settings (API credentials, Ollama configuration, UI preferences)
- **userdata/config.json**: Freqtrade bot configuration
- **data/ai_performance.sqlite**: SQLite database tracking AI generation runs and backtest results
- **data/knowledge_base.sqlite**: SQLite database for RAG-style context retrieval
- **data/feedback/**: JSON files collecting user feedback on AI responses

### Strategy Workflow
1. User describes strategy in natural language
2. AI generates Freqtrade-compatible Python code
3. Code is validated (AST parsing) and optionally repaired via AI
4. Strategy saved to `user_data/strategies/`
5. Optional backtest-refine loop: run backtest → analyze results → improve strategy

## External Dependencies

### Required Services
- **Freqtrade**: Trading bot with REST API enabled (configurable URL with HTTP Basic Auth)
- **Ollama**: Local LLM server at configurable endpoint (default: http://localhost:11434)

### Python Dependencies
- **PyQt6**: Desktop GUI framework
- **requests**: HTTP client for API communication
- **pandas**: Data manipulation for backtest results
- **freqtrade**: Trading bot library (also used for backtesting subprocess calls)

### Data Storage
- **SQLite**: Used for performance tracking and knowledge base (via standard library sqlite3)
- **JSON files**: Configuration and feedback storage

### AI Models
Configurable per-task in `data/config.json` under `ollama.task_models`:
- `strategy_generation`: Model for generating strategy code
- `strategy_analysis`: Model for analyzing strategy performance
- `risk_assessment`: Model for risk evaluation
- `chat`: Model for interactive chat assistance