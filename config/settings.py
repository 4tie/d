"""
Application configuration settings
"""
import json
import os

# --- Paths ---
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_CONFIG_PATH = os.path.join(_base_dir, "data", "config.json")
BOT_CONFIG_PATH = os.path.join(_base_dir, "userdata", "config.json")


def load_app_config():
    """Load application configuration from data/config.json"""
    if not os.path.exists(APP_CONFIG_PATH):
        return {}
    try:
        with open(APP_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _default_app_config() -> dict:
    return {
        "api": {
            "freqtrade_url": "",
            "user": "",
            "password": "",
        },
        "strategy": {
            "directory": "./userdata/strategies",
        },
        "ui": {
            "window_title": "4tie",
            "window_geometry": [100, 100, 1000, 700],
            "update_interval": 5000,
        },
        "ollama": {
            "base_url": "http://localhost:11434",
            "model": "llama2",
            "options": {},
        },
    }


def _merge_defaults(cfg: dict) -> dict:
    base = _default_app_config()
    if not isinstance(cfg, dict):
        return base

    out = base
    for k, v in cfg.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k].update(v)
        else:
            out[k] = v
    return out


# Load application configuration
config = _merge_defaults(load_app_config())

APP_CONFIG_ERRORS: list[str] = []

api_cfg = config.get("api")
ui_cfg = config.get("ui")
strategy_cfg = config.get("strategy")
ollama_cfg = config.get("ollama", {})

if not isinstance(api_cfg, dict):
    api_cfg = {}
    APP_CONFIG_ERRORS.append("Invalid config.api (expected object)")
if not isinstance(ui_cfg, dict):
    ui_cfg = {}
    APP_CONFIG_ERRORS.append("Invalid config.ui (expected object)")
if not isinstance(strategy_cfg, dict):
    strategy_cfg = {}
    APP_CONFIG_ERRORS.append("Invalid config.strategy (expected object)")
if not isinstance(ollama_cfg, dict):
    ollama_cfg = {}
    APP_CONFIG_ERRORS.append("Invalid config.ollama (expected object)")

# API Configuration
FREQTRADE_URL = api_cfg.get("freqtrade_url")
API_USER = api_cfg.get("user")
API_PASS = api_cfg.get("password")

if not FREQTRADE_URL or not API_USER or not API_PASS:
    APP_CONFIG_ERRORS.append(
        "Missing api fields (freqtrade_url/user/password). Configure them in Settings."
    )

# Strategy Configuration
STRATEGY_DIR = strategy_cfg.get("directory")

if not STRATEGY_DIR:
    STRATEGY_DIR = "./userdata/strategies"
    APP_CONFIG_ERRORS.append(
        "Missing strategy.directory. Using default ./userdata/strategies.")

# UI Configuration
WINDOW_TITLE = ui_cfg.get("window_title")
WINDOW_GEOMETRY = list(ui_cfg.get("window_geometry", [100, 100, 1000, 700]))
UPDATE_INTERVAL = ui_cfg.get("update_interval")

if not WINDOW_TITLE:
    WINDOW_TITLE = "SmartTrade AI Wrapper"
    APP_CONFIG_ERRORS.append("Missing ui.window_title. Using default.")
if len(WINDOW_GEOMETRY) != 4:
    WINDOW_GEOMETRY = [100, 100, 1000, 700]
    APP_CONFIG_ERRORS.append(
        "Missing/invalid ui.window_geometry. Using default.")
if not isinstance(UPDATE_INTERVAL, int):
    UPDATE_INTERVAL = 5000
    APP_CONFIG_ERRORS.append(
        "Missing/invalid ui.update_interval. Using default.")

# Ollama Configuration
OLLAMA_BASE_URL = ollama_cfg.get("base_url", "http://localhost:11434")
OLLAMA_MODEL = ollama_cfg.get("model", "llama2")

_task_models = ollama_cfg.get("task_models", {})
if _task_models is None:
    _task_models = {}
if not isinstance(_task_models, dict):
    _task_models = {}
    APP_CONFIG_ERRORS.append(
        "Invalid ollama.task_models (expected object). Ignoring.")

OLLAMA_TASK_MODELS = _task_models
OLLAMA_MODEL_GENERATION = str(
    _task_models.get("strategy_generation") or OLLAMA_MODEL)
OLLAMA_MODEL_ANALYSIS = str(
    _task_models.get("strategy_analysis") or OLLAMA_MODEL)
OLLAMA_MODEL_RISK = str(_task_models.get("risk_assessment") or OLLAMA_MODEL)
OLLAMA_MODEL_CHAT = str(_task_models.get("chat") or OLLAMA_MODEL)

OLLAMA_OPTIONS = ollama_cfg.get("options", {})
if OLLAMA_OPTIONS is None:
    OLLAMA_OPTIONS = {}
if not isinstance(OLLAMA_OPTIONS, dict):
    OLLAMA_OPTIONS = {}
    APP_CONFIG_ERRORS.append(
        "Invalid ollama.options (expected object). Ignoring.")

APP_CONFIG_VALID = len(APP_CONFIG_ERRORS) == 0
