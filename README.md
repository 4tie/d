# SmartTrade AI Wrapper

A PyQt6-based GUI application for Freqtrade that provides an AI-powered strategy builder, real-time trading dashboard, and advanced AI analysis capabilities using Ollama.

## Features

- **Dashboard Tab**: Real-time bot status and profit monitoring
- **AI Strategy Builder**: Generate trading strategies using natural language descriptions
- **AI Analysis Tab**: Advanced AI-powered analysis including:
  - Strategy analysis and insights
  - Loss pattern analysis and recommendations
  - Strategy improvement suggestions
- **Modular Architecture**: Clean separation of concerns with organized folder structure
- **Ollama Integration**: Local AI processing for privacy and speed

## Project Structure

```
py_freqtrade/
├── main.py                # Main application entry point
├── core/                  # Core application logic
│   ├── __init__.py
│   └── strategy_service.py # Strategy orchestration service
├── ui/                    # UI components
│   ├── __init__.py
│   ├── dashboard_tab.py   # Dashboard tab widget
│   ├── ai_builder_tab.py  # AI strategy builder tab
│   └── ai_analysis_tab.py # AI analysis and insights tab
├── api/                   # API client and communication
│   ├── __init__.py
│   └── client.py          # Enhanced Freqtrade API client
├── utils/                 # Utility functions
│   ├── __init__.py
│   ├── strategy_generator.py # AI strategy generation
│   ├── strategy_saver.py   # Strategy file management
│   └── ollama_client.py  # Ollama AI client
├── config/                # Configuration files
│   ├── __init__.py
│   └── settings.py        # Application settings
├── data/                  # Data and configuration
│   └── config.json        # JSON configuration file
├── user_data/             # Freqtrade user data
├── requirements.txt       # Python dependencies
└── README.md             # This file
```

## Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Install and setup Ollama for AI features:
 
Install Ollama following the official instructions, then:

- **Start the Ollama server**: `ollama serve`
- **Ensure a model is available**: `ollama list` (pull one if needed)

3. Ensure Freqtrade is running with API access enabled, then configure its URL and credentials in the app Settings.

4. Run the application:
```bash
python main.py
# or
python -m main
```

## Configuration

Use the **Settings** tab in the application to configure:

- **Freqtrade API** (URL, username, password)
- **Ollama** (URL, model, and options)

Settings are stored in `data/config.json` (intended to be local-only and not committed).

## Usage

### Dashboard Tab
- Monitor your bot's status and profit in real-time
- View current performance metrics
- Automatic updates every 5 seconds

### AI Strategy Builder
- Describe your trading strategy in natural language
- Generate complete Freqtrade strategy code
- Save strategies directly to your strategies folder

### AI Analysis Tab
- **Strategy Analysis**: Paste strategy code for detailed AI analysis
- **Loss Analysis**: Analyze recent trades to understand loss patterns
- **Strategy Improvement**: Get AI-generated improvements for existing strategies

## AI Features

The application integrates with Ollama to provide:

1. **Strategy Analysis**
   - Logic effectiveness evaluation
   - Risk assessment
   - Market condition recommendations
   - Optimization suggestions

2. **Loss Analysis**
   - Pattern recognition in losing trades
   - Drawdown analysis
   - Recovery recommendations
   - Risk management insights

3. **Strategy Improvement**
   - Parameter optimization
   - Additional indicator suggestions
   - Enhanced risk management
   - Performance-based improvements

## Development

The application follows a modular architecture:
- **Core**: Main application logic and orchestration
- **UI**: Reusable GUI components with clear separation
- **API**: Enhanced Freqtrade communication
- **Utils**: Specialized utility classes
- **Config**: Centralized JSON-based configuration

## Requirements

- Python 3.11+
- PyQt6
- requests
- pandas
- Ollama (for AI features)
- Freqtrade with API enabled

## Troubleshooting

**Ollama Connection Issues**:
- Ensure Ollama is installed and running: `ollama serve`
- Check if model is pulled: `ollama list`
- Verify port 11434 is accessible

**Freqtrade Connection Issues**:
- Verify Freqtrade is running with API enabled
- Check the URL and credentials in the app Settings
- Ensure API port 8080 is accessible

**Import Errors**:
- Run from project root directory
- Ensure all dependencies are installed
- Check Python path configuration
