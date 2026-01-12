import json
import os
import re
import threading
import time
import uuid
from typing import Any, Dict, List, Optional

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from api.client import FreqtradeClient
from config.settings import APP_CONFIG_PATH, BOT_CONFIG_PATH, STRATEGY_DIR, load_app_config
from core.strategy_service import StrategyService
from utils.backtest_runner import build_trade_forensics, download_data, load_backtest_result_file, run_backtest, summarize_backtest_data
from utils.performance_store import AIPerformanceStore


class SettingsView(BaseModel):
    freqtrade_url: str = ""
    api_user: str = ""
    has_api_password: bool = False
    ollama_url: str = ""
    ollama_model: str = ""
    ollama_options: Dict[str, Any] = Field(default_factory=dict)
    ollama_task_models: Dict[str, str] = Field(default_factory=dict)


class SettingsUpdate(BaseModel):
    freqtrade_url: Optional[str] = None
    api_user: Optional[str] = None
    api_password: Optional[str] = None
    ollama_url: Optional[str] = None
    ollama_model: Optional[str] = None
    ollama_options: Optional[Dict[str, Any]] = None
    ollama_task_models: Optional[Dict[str, str]] = None


class BacktestRequest(BaseModel):
    strategy_code: str
    timerange: Optional[str] = None
    timeframe: Optional[str] = None
    pairs: Optional[str] = None
    fee: Optional[float] = None
    dry_run_wallet: Optional[float] = None
    max_open_trades: Optional[int] = None


class DownloadDataRequest(BaseModel):
    timerange: Optional[str] = None
    timeframe: Optional[str] = None
    pairs: Optional[str] = None


class GenerateStrategyRequest(BaseModel):
    prompt: str


class RepairStrategyRequest(BaseModel):
    code: str
    prompt: str = ""


class SaveStrategyRequest(BaseModel):
    code: str
    filename: str = "AIStrategy.py"


class RefineStrategyRequest(BaseModel):
    strategy_code: str
    user_goal: str = ""
    max_iterations: int = 2
    timerange: Optional[str] = None
    timeframe: Optional[str] = None
    pairs: Optional[str] = None


class OptimizeStrategyRequest(BaseModel):
    strategy_code: str
    selected_filename: str
    user_goal: str = ""
    max_iterations: int = 3
    timerange: Optional[str] = None
    timeframe: Optional[str] = None
    pairs: Optional[str] = None
    fee: Optional[float] = None
    dry_run_wallet: Optional[float] = None
    max_open_trades: Optional[int] = None
    min_trades_per_day: Optional[float] = None
    require_min_trades_per_day: bool = False
    max_fee_dominated_fraction: Optional[float] = None
    min_edge_to_fee_ratio: Optional[float] = None


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[Dict[str, Any]]] = None
    strategy_code: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class RestoreStrategyRequest(BaseModel):
    run_id: int


class JobView(BaseModel):
    job_id: str
    kind: str
    status: str
    created_ts: int
    updated_ts: int
    logs: List[str]
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class _Job:
    def __init__(self, *, kind: str):
        self.id = str(uuid.uuid4())
        self.kind = kind
        self.status = "queued"
        self.created_ts = int(time.time())
        self.updated_ts = self.created_ts
        self.logs: List[str] = []
        self.result: Optional[Dict[str, Any]] = None
        self.error: Optional[str] = None

    def append_log(self, line: str) -> None:
        if not isinstance(line, str):
            return
        s = line.rstrip("\n")
        if not s:
            return
        self.logs.append(s)
        self.updated_ts = int(time.time())

    def to_view(self) -> JobView:
        return JobView(
            job_id=self.id,
            kind=self.kind,
            status=self.status,
            created_ts=self.created_ts,
            updated_ts=self.updated_ts,
            logs=list(self.logs),
            result=self.result,
            error=self.error,
        )


class _AppState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs_lock = threading.Lock()
        self._jobs: Dict[str, _Job] = {}

        self.freqtrade_client = FreqtradeClient("", "", "")
        self.strategy_service = StrategyService()
        self.performance_store = AIPerformanceStore()

        self._apply_settings_from_disk()

    def _read_settings_from_disk(self) -> Dict[str, Any]:
        cfg = load_app_config()
        if not isinstance(cfg, dict):
            cfg = {}

        api_cfg = cfg.get("api") if isinstance(cfg.get("api"), dict) else {}
        ollama_cfg = cfg.get("ollama") if isinstance(cfg.get("ollama"), dict) else {}

        task_models = ollama_cfg.get("task_models")
        if task_models is None:
            task_models = {}
        if not isinstance(task_models, dict):
            task_models = {}

        return {
            "freqtrade_url": str(api_cfg.get("freqtrade_url") or ""),
            "api_user": str(api_cfg.get("user") or ""),
            "api_password": str(api_cfg.get("password") or ""),
            "ollama_url": str(ollama_cfg.get("base_url") or "http://localhost:11434"),
            "ollama_model": str(ollama_cfg.get("model") or "llama2"),
            "ollama_options": ollama_cfg.get("options") if isinstance(ollama_cfg.get("options"), dict) else {},
            "ollama_task_models": {str(k): str(v) for k, v in task_models.items() if isinstance(k, str) and isinstance(v, str)},
        }

    def _write_settings_to_disk(self, update: SettingsUpdate) -> Dict[str, Any]:
        existing = load_app_config()
        if not isinstance(existing, dict):
            existing = {}

        api_cfg = existing.get("api")
        if not isinstance(api_cfg, dict):
            api_cfg = {}
            existing["api"] = api_cfg

        ollama_cfg = existing.get("ollama")
        if not isinstance(ollama_cfg, dict):
            ollama_cfg = {}
            existing["ollama"] = ollama_cfg

        if update.freqtrade_url is not None:
            api_cfg["freqtrade_url"] = str(update.freqtrade_url)
        if update.api_user is not None:
            api_cfg["user"] = str(update.api_user)
        if update.api_password is not None:
            api_cfg["password"] = str(update.api_password)

        if update.ollama_url is not None:
            ollama_cfg["base_url"] = str(update.ollama_url)
        if update.ollama_model is not None:
            ollama_cfg["model"] = str(update.ollama_model)
        if update.ollama_options is not None:
            if not isinstance(update.ollama_options, dict):
                raise HTTPException(status_code=400, detail="ollama_options must be an object")
            ollama_cfg["options"] = update.ollama_options
        if update.ollama_task_models is not None:
            if not isinstance(update.ollama_task_models, dict):
                raise HTTPException(status_code=400, detail="ollama_task_models must be an object")
            ollama_cfg["task_models"] = {str(k): str(v) for k, v in update.ollama_task_models.items()}

        os.makedirs(os.path.dirname(APP_CONFIG_PATH), exist_ok=True)
        with open(APP_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2)

        return self._read_settings_from_disk()

    def _apply_settings_from_disk(self) -> None:
        s = self._read_settings_from_disk()
        self.freqtrade_client.update_settings(
            base_url=s["freqtrade_url"],
            username=s["api_user"],
            password=s["api_password"],
        )
        self.strategy_service.update_ollama_settings(
            base_url=s["ollama_url"],
            model=s["ollama_model"],
            options=s["ollama_options"],
            task_models=s["ollama_task_models"],
        )

    def get_settings_view(self) -> SettingsView:
        s = self._read_settings_from_disk()
        return SettingsView(
            freqtrade_url=s["freqtrade_url"],
            api_user=s["api_user"],
            has_api_password=bool(s["api_password"]),
            ollama_url=s["ollama_url"],
            ollama_model=s["ollama_model"],
            ollama_options=s["ollama_options"],
            ollama_task_models=s["ollama_task_models"],
        )

    def update_settings(self, update: SettingsUpdate) -> SettingsView:
        with self._lock:
            self._write_settings_to_disk(update)
            self._apply_settings_from_disk()
            return self.get_settings_view()

    def ensure_freqtrade_configured(self) -> None:
        base = str(getattr(self.freqtrade_client, "base_url", "") or "").strip()
        if not base:
            raise HTTPException(status_code=400, detail="Freqtrade URL is not configured")
        if not (base.startswith("http://") or base.startswith("https://")):
            raise HTTPException(status_code=400, detail="Freqtrade URL must start with http:// or https://")

    def ensure_bot_config_exists(self) -> None:
        if not os.path.exists(BOT_CONFIG_PATH):
            raise HTTPException(
                status_code=400,
                detail=(
                    "Bot config not found at user_data/config.json. "
                    "Create it (Freqtrade user_data config) before running backtests or downloads."
                ),
            )

    def _resolve_strategy_dir(self) -> str:
        raw = str(STRATEGY_DIR or "").strip() or "./user_data/strategies"
        base_dir = os.path.dirname(os.path.abspath(__file__))
        root = os.path.abspath(os.path.join(base_dir))
        path = raw
        if not os.path.isabs(path):
            path = os.path.abspath(os.path.join(root, path))
        return path

    def _safe_strategy_filename(self, name: str) -> str:
        if not isinstance(name, str) or not name.strip():
            raise HTTPException(status_code=400, detail="strategy name is required")
        base = os.path.basename(name.strip())
        if base != name.strip():
            raise HTTPException(status_code=400, detail="invalid strategy name")
        if not base.lower().endswith(".py"):
            raise HTTPException(status_code=400, detail="strategy file must end with .py")
        return base

    def read_strategy_file(self, filename: str) -> Dict[str, Any]:
        strategy_dir = self._resolve_strategy_dir()
        filename = self._safe_strategy_filename(filename)
        path = os.path.join(strategy_dir, filename)
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="strategy file not found")
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"failed to read strategy file: {e}")
        st = os.stat(path)
        strategy_hash = None
        try:
            if isinstance(content, str) and content.strip():
                strategy_hash = AIPerformanceStore.compute_strategy_hash(content)
        except Exception:
            strategy_hash = None
        return {
            "filename": filename,
            "path": path,
            "size": int(st.st_size),
            "mtime": int(st.st_mtime),
            "strategy_hash": strategy_hash,
            "content": content,
        }

    def list_strategy_files(self) -> List[Dict[str, Any]]:
        strategy_dir = self._resolve_strategy_dir()
        os.makedirs(strategy_dir, exist_ok=True)
        out: List[Dict[str, Any]] = []
        for name in sorted(os.listdir(strategy_dir)):
            if not name.lower().endswith(".py"):
                continue
            path = os.path.join(strategy_dir, name)
            if not os.path.isfile(path):
                continue
            try:
                st = os.stat(path)
                strategy_hash = None
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if isinstance(content, str) and content.strip():
                        strategy_hash = AIPerformanceStore.compute_strategy_hash(content)
                except Exception:
                    strategy_hash = None

                out.append(
                    {
                        "filename": name,
                        "path": path,
                        "size": int(st.st_size),
                        "mtime": int(st.st_mtime),
                        "strategy_hash": strategy_hash,
                    }
                )
            except Exception:
                continue
        return out

    def _freqtrade_request_json(self, method: str, path: str, *, params: Optional[Dict[str, Any]] = None, payload: Optional[Dict[str, Any]] = None) -> Any:
        self.ensure_freqtrade_configured()
        try:
            url = self.freqtrade_client._build_url(path)
            if method.upper() == "GET":
                resp = self.freqtrade_client._make_request("GET", url, params=params)
            elif method.upper() == "POST":
                resp = self.freqtrade_client._make_request("POST", url, json=payload)
            else:
                raise HTTPException(status_code=500, detail=f"Unsupported method: {method}")

            if resp is None:
                raise HTTPException(status_code=502, detail="Freqtrade returned empty response")

            try:
                return resp.json()
            except Exception:
                content_type = ""
                try:
                    content_type = str(resp.headers.get("content-type") or "")
                except Exception:
                    content_type = ""
                body = ""
                try:
                    body = str(resp.text or "")
                except Exception:
                    body = ""
                body = body.strip()
                if len(body) > 2000:
                    body = body[:2000] + "..."
                raise HTTPException(
                    status_code=502,
                    detail=(
                        f"Freqtrade returned non-JSON response for {path}. "
                        f"url='{url}', content-type='{content_type}'. "
                        f"Body: {body}" if body else f"Freqtrade returned non-JSON response for {path}. url='{url}', content-type='{content_type}'."
                    ),
                )
        except HTTPException:
            raise

        except requests.exceptions.HTTPError as e:
            resp = getattr(e, "response", None)
            if resp is None:
                raise HTTPException(status_code=502, detail=f"Freqtrade HTTP error: {e}")
            status = int(getattr(resp, "status_code", 502) or 502)
            body = ""
            try:
                body = str(getattr(resp, "text", "") or "")
            except Exception:
                body = ""
            body = body.strip()
            if len(body) > 2000:
                body = body[:2000] + "..."
            msg = f"Freqtrade responded with HTTP {status} for {path}"
            if body:
                msg = msg + f": {body}"
            raise HTTPException(status_code=status, detail=msg)

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            base = str(getattr(self.freqtrade_client, "base_url", "") or "").strip()
            raise HTTPException(
                status_code=502,
                detail=f"Freqtrade unreachable ({e}). Check freqtrade_url='{base}', credentials, and that the bot API is running.",
            )

        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Freqtrade request failed: {e}")

    def create_job(self, *, kind: str, target, args: tuple, kwargs: dict) -> _Job:
        job = _Job(kind=kind)
        with self._jobs_lock:
            self._jobs[job.id] = job

        def _runner():
            job.status = "running"
            job.updated_ts = int(time.time())
            try:
                res = target(job, *args, **kwargs)
                if res is not None and not isinstance(res, dict):
                    raise RuntimeError("Job result must be an object")
                job.result = res
                job.status = "succeeded"
                job.updated_ts = int(time.time())
            except Exception as e:
                job.error = str(e)
                job.status = "failed"
                job.updated_ts = int(time.time())

        t = threading.Thread(target=_runner, daemon=True)
        t.start()
        return job

    def get_job(self, job_id: str) -> _Job:
        with self._jobs_lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return job


state = _AppState()

app = FastAPI(title="SmartTrade AI Web API")


@app.get("/", include_in_schema=False)
def root() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width,initial-scale=1" />
    <title>SmartTrade API</title>
  </head>
  <body style="font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; padding: 24px;">
    <h1 style="margin: 0 0 12px;">SmartTrade AI Web API</h1>
    <div style="margin: 0 0 16px;">This is the backend API server. Use the Web UI on <code>http://127.0.0.1:5173</code>.</div>
    <ul>
      <li><a href="/docs">Swagger UI (/docs)</a></li>
      <li><a href="/api/health">Health (/api/health)</a></li>
    </ul>
  </body>
</html>"""
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"] ,
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> Dict[str, Any]:
    return {
        "ok": True,
        "ts": int(time.time()),
        "has_app_config": os.path.exists(APP_CONFIG_PATH),
        "has_bot_config": os.path.exists(BOT_CONFIG_PATH),
    }


@app.get("/api/settings", response_model=SettingsView)
def get_settings() -> SettingsView:
    return state.get_settings_view()


@app.post("/api/settings", response_model=SettingsView)
def post_settings(update: SettingsUpdate) -> SettingsView:
    return state.update_settings(update)


@app.post("/api/strategy/validate")
def strategy_validate(payload: Dict[str, Any]) -> Dict[str, Any]:
    code = payload.get("code") if isinstance(payload, dict) else None
    if not isinstance(code, str) or not code.strip():
        raise HTTPException(status_code=400, detail="code is required")

    try:
        ok, err = state.strategy_service.generator.validate_strategy_code(code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"ok": bool(ok), "error": str(err or "")}


def _job_optimize_strategy(job: _Job, req: OptimizeStrategyRequest) -> Dict[str, Any]:
    if not isinstance(req.strategy_code, str) or not req.strategy_code.strip():
        raise ValueError("strategy_code is required")

    selected = str(req.selected_filename or "").strip()
    if not selected:
        raise ValueError("selected_filename is required")

    file_view = None
    try:
        file_view = state.read_strategy_file(selected)
    except HTTPException as e:
        raise ValueError(f"selected strategy file not found: {selected} ({e.detail})")
    except Exception as e:
        raise ValueError(f"failed to read selected strategy file: {selected} ({e})")

    disk_code = file_view.get("content") if isinstance(file_view, dict) else None
    if not isinstance(disk_code, str) or not disk_code.strip():
        raise ValueError(f"selected strategy file has no content: {selected}")

    if req.max_iterations < 1 or req.max_iterations > 5:
        raise ValueError("max_iterations must be between 1 and 5")

    fee = None
    if req.fee is not None:
        try:
            fee = float(req.fee)
        except Exception:
            raise ValueError("fee must be a number")
        if fee < 0 or fee > 0.05:
            raise ValueError("fee must be between 0 and 0.05")

    dry_run_wallet = None
    if req.dry_run_wallet is not None:
        try:
            dry_run_wallet = float(req.dry_run_wallet)
        except Exception:
            raise ValueError("dry_run_wallet must be a number")
        if dry_run_wallet <= 0:
            raise ValueError("dry_run_wallet must be > 0")

    max_open_trades = None
    if req.max_open_trades is not None:
        try:
            max_open_trades = int(req.max_open_trades)
        except Exception:
            raise ValueError("max_open_trades must be an integer")
        if max_open_trades < 0:
            raise ValueError("max_open_trades must be >= 0")

    min_trades_per_day = None
    if req.min_trades_per_day is not None:
        try:
            min_trades_per_day = float(req.min_trades_per_day)
        except Exception:
            raise ValueError("min_trades_per_day must be a number")
        if min_trades_per_day < 0:
            raise ValueError("min_trades_per_day must be >= 0")

    max_fee_dominated_fraction = None
    if req.max_fee_dominated_fraction is not None:
        try:
            max_fee_dominated_fraction = float(req.max_fee_dominated_fraction)
        except Exception:
            raise ValueError("max_fee_dominated_fraction must be a number")
        if max_fee_dominated_fraction < 0 or max_fee_dominated_fraction > 1:
            raise ValueError("max_fee_dominated_fraction must be between 0 and 1")

    min_edge_to_fee_ratio = None
    if req.min_edge_to_fee_ratio is not None:
        try:
            min_edge_to_fee_ratio = float(req.min_edge_to_fee_ratio)
        except Exception:
            raise ValueError("min_edge_to_fee_ratio must be a number")
        if min_edge_to_fee_ratio < 0:
            raise ValueError("min_edge_to_fee_ratio must be >= 0")

    job.append_log("Starting AI optimize loop")

    res = state.strategy_service.optimize_strategy_with_backtest_loop(
        strategy_code=disk_code,
        selected_filename=selected,
        user_goal=req.user_goal,
        max_iterations=req.max_iterations,
        timerange=req.timerange,
        timeframe=req.timeframe,
        pairs=req.pairs,
        fee=fee,
        dry_run_wallet=dry_run_wallet,
        max_open_trades=max_open_trades,
        min_trades_per_day=min_trades_per_day,
        require_min_trades_per_day=bool(req.require_min_trades_per_day),
        max_fee_dominated_fraction=max_fee_dominated_fraction,
        min_edge_to_fee_ratio=min_edge_to_fee_ratio,
        job=job,
    )
    if not isinstance(res, dict):
        raise RuntimeError("optimize_strategy_with_backtest_loop returned invalid result")
    return res


@app.post("/api/ai/strategy/optimize")
def ai_strategy_optimize(req: OptimizeStrategyRequest) -> Dict[str, Any]:
    if not isinstance(req.strategy_code, str) or not req.strategy_code.strip():
        raise HTTPException(status_code=400, detail="strategy_code is required")
    if not isinstance(req.selected_filename, str) or not req.selected_filename.strip():
        raise HTTPException(status_code=400, detail="selected_filename is required")
    if req.max_iterations < 1 or req.max_iterations > 5:
        raise HTTPException(status_code=400, detail="max_iterations must be between 1 and 5")

    job = state.create_job(kind="ai_optimize", target=_job_optimize_strategy, args=(req,), kwargs={})
    return {"job_id": job.id}


@app.post("/api/ai/chat")
def ai_chat(req: ChatRequest) -> Dict[str, Any]:
    if not isinstance(req.message, str) or not req.message.strip():
        raise HTTPException(status_code=400, detail="message is required")

    ctx_in: Dict[str, Any] = req.context if isinstance(req.context, dict) else {}
    selected = str(ctx_in.get("selected_filename") or "").strip()

    disk_code: str | None = None
    strategy_hash: str | None = None

    if selected:
        try:
            file_view = state.read_strategy_file(selected)
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

        disk_code = file_view.get("content") if isinstance(file_view, dict) else None
        strategy_hash = file_view.get("strategy_hash") if isinstance(file_view, dict) else None

        if not isinstance(disk_code, str) or not disk_code.strip():
            raise HTTPException(status_code=400, detail=f"selected strategy file has no content: {selected}")

    ctx = dict(ctx_in)
    if strategy_hash:
        ctx["strategy_hash"] = strategy_hash
        try:
            latest = state.performance_store.get_latest_run_for_hash(strategy_hash)
            if latest:
                ctx["last_run_type"] = latest.get("run_type")
                ctx["last_run_ts"] = latest.get("ts")
                ctx["last_backtest_summary"] = latest.get("backtest_summary")
                ctx["last_trade_forensics"] = latest.get("trade_forensics")

                metrics = {}
                bt = latest.get("backtest_summary") if isinstance(latest.get("backtest_summary"), dict) else {}
                if isinstance(bt.get("metrics"), dict):
                    metrics = bt.get("metrics")

                profit_pct = metrics.get("profit_total_pct")
                max_dd_pct = metrics.get("max_drawdown_pct")
                if max_dd_pct is None:
                    tf = latest.get("trade_forensics") if isinstance(latest.get("trade_forensics"), dict) else {}
                    ra = tf.get("risk_adjusted") if isinstance(tf.get("risk_adjusted"), dict) else {}
                    max_dd_pct = ra.get("max_drawdown_pct")

                if profit_pct is not None:
                    ctx["last_backtest_profit_pct"] = profit_pct
                if max_dd_pct is not None:
                    ctx["last_backtest_max_dd_pct"] = max_dd_pct

                total_trades = metrics.get("total_trades")
                if total_trades is None:
                    total_trades = metrics.get("trades")
                if total_trades is not None:
                    ctx["last_backtest_total_trades"] = total_trades

                tf = latest.get("trade_forensics") if isinstance(latest.get("trade_forensics"), dict) else {}
                tfreq = tf.get("trade_frequency") if isinstance(tf.get("trade_frequency"), dict) else {}
                avg_tpd = tfreq.get("avg_trades_per_day")
                if avg_tpd is not None:
                    ctx["last_backtest_trades_per_day"] = avg_tpd
        except Exception as e:
            ctx["performance_store_error"] = str(e)

    try:
        return state.strategy_service.chat(
            req.message,
            history=req.history,
            strategy_code=disk_code or req.strategy_code,
            context=ctx,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/ollama/ping")
def ollama_ping() -> Dict[str, Any]:
    try:
        available = bool(state.strategy_service.generator.ollama.is_available())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"available": available}


@app.get("/api/ollama/models")
def ollama_models(force_refresh: bool = False) -> Dict[str, Any]:
    try:
        models = state.strategy_service.generator.ollama.get_available_models(force_refresh=bool(force_refresh))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"models": models}


@app.get("/api/freqtrade/ping")
def freqtrade_ping() -> Any:
    return state._freqtrade_request_json("GET", "/api/v1/ping")


@app.get("/api/freqtrade/profit")
def freqtrade_profit() -> Any:
    return state._freqtrade_request_json("GET", "/api/v1/profit")


@app.get("/api/freqtrade/show_config")
def freqtrade_show_config() -> Any:
    state.ensure_bot_config_exists()
    try:
        with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
            bot_cfg = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to read bot config: {e}")

    if not isinstance(bot_cfg, dict):
        raise HTTPException(status_code=500, detail="user_data/config.json must be a JSON object")

    ex = bot_cfg.get("exchange") if isinstance(bot_cfg.get("exchange"), dict) else {}
    exchange_name = ex.get("name") if isinstance(ex.get("name"), str) else bot_cfg.get("exchange")
    if not isinstance(exchange_name, str):
        exchange_name = ""

    return {
        "strategy": bot_cfg.get("strategy"),
        "timeframe": bot_cfg.get("timeframe"),
        "stake_currency": bot_cfg.get("stake_currency"),
        "dry_run": bot_cfg.get("dry_run"),
        "exchange": exchange_name,
        "pair_whitelist": ex.get("pair_whitelist"),
        "pairs": ex.get("pair_whitelist"),
        "fee": (ex.get("fees") or {}).get("taker") if isinstance(ex.get("fees"), dict) else None,
        "dry_run_wallet": bot_cfg.get("dry_run_wallet"),
        "max_open_trades": bot_cfg.get("max_open_trades"),
    }


@app.get("/api/freqtrade/whitelist")
def freqtrade_whitelist() -> Any:
    state.ensure_bot_config_exists()
    try:
        with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
            bot_cfg = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to read bot config: {e}")

    if not isinstance(bot_cfg, dict):
        raise HTTPException(status_code=500, detail="user_data/config.json must be a JSON object")

    pairs: List[str] = []

    def _add_unique(dst: List[str], v: Any) -> None:
        if not isinstance(v, str):
            return
        s = v.strip()
        if not s:
            return
        if s not in dst:
            dst.append(s)

    def _add_pairs_from_any(val: Any) -> None:
        if isinstance(val, list):
            for it in val:
                if isinstance(it, str):
                    _add_unique(pairs, it)
            return
        if isinstance(val, str):
            for part in val.replace(";", ",").split(","):
                _add_unique(pairs, part)

    ex = bot_cfg.get("exchange") if isinstance(bot_cfg.get("exchange"), dict) else {}
    _add_pairs_from_any(ex.get("pair_whitelist"))

    pls = bot_cfg.get("pairlists")
    if isinstance(pls, list):
        for pl in pls:
            if isinstance(pl, dict):
                _add_pairs_from_any(pl.get("pair_whitelist"))

    return {"whitelist": pairs}


@app.get("/api/bot/show_config")
def bot_show_config() -> Any:
    return freqtrade_show_config()


@app.get("/api/bot/whitelist")
def bot_whitelist() -> Any:
    return freqtrade_whitelist()


@app.get("/api/freqtrade/open_trades")
def freqtrade_open_trades() -> Any:
    return state._freqtrade_request_json("GET", "/api/v1/status")


@app.get("/api/freqtrade/trades")
def freqtrade_trades(limit: int = 200) -> Any:
    if limit < 1 or limit > 2000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")
    return state._freqtrade_request_json("GET", "/api/v1/trades", params={"limit": limit})


@app.get("/api/freqtrade/pair_candles")
def freqtrade_pair_candles(pair: str, timeframe: str, limit: int = 120) -> Any:
    if not pair or not pair.strip():
        raise HTTPException(status_code=400, detail="pair is required")
    if not timeframe or not timeframe.strip():
        raise HTTPException(status_code=400, detail="timeframe is required")
    if limit < 1 or limit > 2000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")
    return state._freqtrade_request_json(
        "GET",
        "/api/v1/pair_candles",
        params={"pair": pair.strip(), "timeframe": timeframe.strip(), "limit": int(limit)},
    )


@app.post("/api/freqtrade/reload_config")
def freqtrade_reload_config() -> Any:
    return state._freqtrade_request_json("POST", "/api/v1/reload_config")


@app.get("/api/freqtrade/daily")
def freqtrade_daily(days: int = 30) -> Any:
    if days < 1 or days > 3650:
        raise HTTPException(status_code=400, detail="days must be between 1 and 3650")
    return state._freqtrade_request_json("GET", "/api/v1/daily", params={"timescale": int(days)})


@app.get("/api/strategies")
def strategies_list() -> Dict[str, Any]:
    return {"strategies": state.list_strategy_files()}


@app.get("/api/strategies/{filename}")
def strategies_read(filename: str) -> Dict[str, Any]:
    return state.read_strategy_file(filename)


@app.get("/api/strategy/current")
def strategy_current() -> Dict[str, Any]:
    # Convention: current strategy is AIStrategy.py
    try:
        return state.read_strategy_file("AIStrategy.py")
    except HTTPException as e:
        if e.status_code == 404:
            # If it doesn't exist yet, expose directory information for UI guidance.
            return {"filename": "AIStrategy.py", "path": os.path.join(state._resolve_strategy_dir(), "AIStrategy.py"), "missing": True}
        raise


@app.get("/api/backtest/suggestions")
def backtest_suggestions(limit: int = 200) -> Dict[str, Any]:
    if limit < 1 or limit > 2000:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 2000")

    timeranges: List[str] = []
    timeframes: List[str] = []
    pairs: List[str] = []
    warnings: List[str] = []

    fee_default: Any = None
    dry_run_wallet_default: Any = None
    max_open_trades_default: Any = None

    def _tf_rank(tf: str) -> int:
        m = re.match(r"^(\d+)([mhdw])$", tf.strip())
        if not m:
            return 10**9
        n = int(m.group(1))
        unit = m.group(2)
        mult = {"m": 1, "h": 60, "d": 1440, "w": 10080}.get(unit, 10**6)
        return n * mult

    def _add_timeframes_from_data_dir(max_files: int = 4000) -> None:
        base = os.path.join(os.path.dirname(BOT_CONFIG_PATH), "data")
        if not os.path.exists(base):
            return

        found: set[str] = set()
        scanned = 0
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if scanned >= max_files:
                    break
                low = fn.lower()
                if not (
                    low.endswith(".feather")
                    or low.endswith(".parquet")
                    or low.endswith(".json")
                    or low.endswith(".jsongz")
                ):
                    continue
                if "-" not in fn:
                    continue
                tail = fn.split("-", 1)[1]
                tf = tail.split(".", 1)[0].strip().split()[0]
                if not tf:
                    continue
                if not re.match(r"^\d+[mhdw]$", tf):
                    continue
                found.add(tf)
                scanned += 1

            if scanned >= max_files:
                break

        for tf in sorted(found, key=_tf_rank):
            _add_unique(timeframes, tf)

    def _add_unique(dst: List[str], v: Any) -> None:
        if not isinstance(v, str):
            return
        s = v.strip()
        if not s:
            return
        if s not in dst:
            dst.append(s)

    def _add_pairs_from_any(val: Any) -> None:
        if isinstance(val, list):
            for it in val:
                if isinstance(it, str):
                    _add_unique(pairs, it)
            return
        if isinstance(val, str):
            for part in val.replace(";", ",").split(","):
                _add_unique(pairs, part)

    try:
        hist = state.performance_store.get_recent_param_suggestions(limit=min(int(limit), 2000))
        for t in hist.get("timeranges", []):
            _add_unique(timeranges, t)
        for tf in hist.get("timeframes", []):
            _add_unique(timeframes, tf)
        for p in hist.get("pairs", []):
            _add_unique(pairs, p)
    except Exception as e:
        warnings.append(f"history suggestions unavailable: {e}")

    if os.path.exists(BOT_CONFIG_PATH):
        try:
            with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
                bot_cfg = json.load(f)
            if not isinstance(bot_cfg, dict):
                raise RuntimeError("user_data/config.json must be a JSON object")

            if isinstance(bot_cfg.get("dry_run_wallet"), (int, float)):
                dry_run_wallet_default = float(bot_cfg.get("dry_run_wallet"))

            if isinstance(bot_cfg.get("max_open_trades"), (int, float)):
                max_open_trades_default = int(bot_cfg.get("max_open_trades"))

            tf = bot_cfg.get("timeframe")
            if isinstance(tf, str):
                _add_unique(timeframes, tf)

            ex = bot_cfg.get("exchange") if isinstance(bot_cfg.get("exchange"), dict) else {}
            _add_pairs_from_any(ex.get("pair_whitelist"))

            fees_cfg = ex.get("fees") if isinstance(ex.get("fees"), dict) else {}
            fee_taker = fees_cfg.get("taker")
            fee_maker = fees_cfg.get("maker")
            if isinstance(fee_taker, (int, float)):
                fee_default = float(fee_taker)
            elif isinstance(fee_maker, (int, float)):
                fee_default = float(fee_maker)

            pls = bot_cfg.get("pairlists")
            if isinstance(pls, list):
                for pl in pls:
                    if isinstance(pl, dict):
                        _add_pairs_from_any(pl.get("pair_whitelist"))

            freqai = bot_cfg.get("freqai") if isinstance(bot_cfg.get("freqai"), dict) else {}
            fp = freqai.get("feature_parameters") if isinstance(freqai.get("feature_parameters"), dict) else {}
            tfs = fp.get("include_timeframes")
            if isinstance(tfs, list):
                for it in tfs:
                    if isinstance(it, str):
                        _add_unique(timeframes, it)
            corr = fp.get("include_corr_pairlist")
            _add_pairs_from_any(corr)
        except Exception as e:
            warnings.append(f"bot config suggestions unavailable: {e}")

    try:
        _add_timeframes_from_data_dir()
    except Exception as e:
        warnings.append(f"data dir timeframes unavailable: {e}")

    return {
        "timeranges": timeranges,
        "timeframes": timeframes,
        "pairs": pairs,
        "warnings": warnings,
        "defaults": {
            "fee": fee_default,
            "dry_run_wallet": dry_run_wallet_default,
            "max_open_trades": max_open_trades_default,
        },
    }


def _job_backtest(job: _Job, req: BacktestRequest) -> Dict[str, Any]:
    state.ensure_bot_config_exists()
    if req.fee is not None:
        try:
            fee = float(req.fee)
        except Exception:
            raise ValueError("fee must be a number")
        if fee < 0 or fee > 0.05:
            raise ValueError("fee must be between 0 and 0.05")
    else:
        fee = None

    if req.dry_run_wallet is not None:
        try:
            dry_run_wallet = float(req.dry_run_wallet)
        except Exception:
            raise ValueError("dry_run_wallet must be a number")
        if dry_run_wallet <= 0:
            raise ValueError("dry_run_wallet must be > 0")
    else:
        dry_run_wallet = None

    if req.max_open_trades is not None:
        try:
            max_open_trades = int(req.max_open_trades)
        except Exception:
            raise ValueError("max_open_trades must be an integer")
        if max_open_trades < 0:
            raise ValueError("max_open_trades must be >= 0")
    else:
        max_open_trades = None

    job.append_log("Starting backtest")
    bt = run_backtest(
        strategy_code=req.strategy_code,
        config_path=BOT_CONFIG_PATH,
        timerange=req.timerange,
        timeframe=req.timeframe,
        pairs=req.pairs,
        fee=fee,
        dry_run_wallet=dry_run_wallet,
        max_open_trades=max_open_trades,
    )
    data = bt.get("data")
    if not isinstance(data, dict):
        raise RuntimeError("Backtest output missing JSON data")

    job.append_log("Summarizing results")
    summary = summarize_backtest_data(data)
    forensics = build_trade_forensics(data)

    result_kind = bt.get("result_kind")
    zip_member = bt.get("zip_member")

    run_id = state.performance_store.record_run(
        run_type="manual_backtest",
        strategy_code=req.strategy_code,
        user_goal=None,
        iteration=None,
        timerange=req.timerange,
        timeframe=req.timeframe,
        pairs=req.pairs,
        result_file=str(bt.get("result_file") or "") or None,
        model_analysis=None,
        model_risk=None,
        analysis_text=None,
        risk_text=None,
        backtest_summary=summary,
        trade_forensics=forensics,
        market_context=None,
        extra={
            "strategy_class": bt.get("strategy_class"),
            "stdout_tail": str(bt.get("stdout", ""))[-4000:],
            "stderr_tail": str(bt.get("stderr", ""))[-4000:],
            "fee": fee,
            "dry_run_wallet": dry_run_wallet,
            "max_open_trades": max_open_trades,
            "result_kind": result_kind,
            "zip_member": zip_member,
        },
    )

    return {
        "performance_run_id": run_id,
        "strategy_class": bt.get("strategy_class"),
        "result_file": bt.get("result_file"),
        "result_kind": result_kind,
        "zip_member": zip_member,
        "backtest_summary": summary,
        "trade_forensics": forensics,
        "stdout_tail": str(bt.get("stdout", ""))[-8000:],
        "stderr_tail": str(bt.get("stderr", ""))[-8000:],
    }


@app.get("/api/backtest/runs/{run_id}/detail")
def backtest_run_detail(run_id: int, include_result: bool = True) -> Dict[str, Any]:
    if not isinstance(run_id, int) or run_id <= 0:
        raise HTTPException(status_code=400, detail="run_id must be a positive integer")

    try:
        r = state.performance_store.get_run_by_id(int(run_id))
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

    result_file = str(r.get("result_file") or "").strip()
    extra = r.get("extra") if isinstance(r.get("extra"), dict) else {}
    result_kind = str(extra.get("result_kind") or "").strip() or None
    zip_member = str(extra.get("zip_member") or "").strip() or None

    if not result_file:
        raise HTTPException(status_code=400, detail="selected run has no result_file")

    detail = None
    if include_result:
        try:
            detail = load_backtest_result_file(result_file, result_kind=result_kind, zip_member=zip_member)
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    ai_payload = {
        "strategy_code": r.get("strategy_code"),
        "timerange": r.get("timerange"),
        "timeframe": r.get("timeframe"),
        "pairs": r.get("pairs"),
        "backtest_summary": r.get("backtest_summary"),
        "trade_forensics": r.get("trade_forensics"),
        "market_context": r.get("market_context"),
    }

    out = {
        "run": {
            "id": r.get("id"),
            "ts": r.get("ts"),
            "run_type": r.get("run_type"),
            "strategy_hash": r.get("strategy_hash"),
            "timerange": r.get("timerange"),
            "timeframe": r.get("timeframe"),
            "pairs": r.get("pairs"),
            "result_file": result_file,
            "result_kind": result_kind,
            "zip_member": zip_member,
        },
        "ai_payload": ai_payload,
    }
    if include_result:
        out["backtest_result"] = detail
    return out


@app.post("/api/backtest/run")
def backtest_run(req: BacktestRequest) -> Dict[str, Any]:
    if not isinstance(req.strategy_code, str) or not req.strategy_code.strip():
        raise HTTPException(status_code=400, detail="strategy_code is required")

    job = state.create_job(kind="backtest", target=_job_backtest, args=(req,), kwargs={})
    return {"job_id": job.id}


def _job_download_data(job: _Job, req: DownloadDataRequest) -> Dict[str, Any]:
    state.ensure_bot_config_exists()
    job.append_log("Starting data download")
    res = download_data(
        config_path=BOT_CONFIG_PATH,
        timerange=req.timerange,
        timeframe=req.timeframe,
        pairs=req.pairs,
    )
    return {
        "cmd": res.get("cmd"),
        "stdout_tail": str(res.get("stdout", ""))[-8000:],
        "stderr_tail": str(res.get("stderr", ""))[-8000:],
    }


@app.post("/api/data/download")
def data_download(req: DownloadDataRequest) -> Dict[str, Any]:
    job = state.create_job(kind="download_data", target=_job_download_data, args=(req,), kwargs={})
    return {"job_id": job.id}


@app.get("/api/jobs/{job_id}", response_model=JobView)
def jobs_get(job_id: str) -> JobView:
    return state.get_job(job_id).to_view()


@app.post("/api/ai/strategy/generate")
def ai_strategy_generate(req: GenerateStrategyRequest) -> Dict[str, Any]:
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt is required")

    try:
        code = state.strategy_service.generate_strategy_code(req.prompt)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"strategy_code": code}


@app.post("/api/ai/strategy/repair")
def ai_strategy_repair(req: RepairStrategyRequest) -> Dict[str, Any]:
    if not isinstance(req.code, str) or not req.code.strip():
        raise HTTPException(status_code=400, detail="code is required")

    user_idea = str(req.prompt or "").strip() or "repair"
    try:
        return state.strategy_service.repair_strategy_code(req.code, user_idea)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/strategy/save")
def strategy_save(req: SaveStrategyRequest) -> Dict[str, Any]:
    if not req.code or not req.code.strip():
        raise HTTPException(status_code=400, detail="code is required")
    if not req.filename or not req.filename.strip():
        raise HTTPException(status_code=400, detail="filename is required")

    try:
        ok = state.strategy_service.save_strategy_code(req.code, filename=req.filename.strip())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save strategy")

    return {"ok": True, "filename": req.filename.strip()}


@app.get("/api/history/runs")
def history_runs(limit: int = 40) -> Dict[str, Any]:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=400, detail="limit must be between 1 and 200")
    return {"runs": state.performance_store.get_recent_runs(limit=limit)}


@app.post("/api/history/restore")
def history_restore(req: RestoreStrategyRequest) -> Dict[str, Any]:
    if not isinstance(req.run_id, int) or req.run_id <= 0:
        raise HTTPException(status_code=400, detail="run_id must be a positive integer")

    runs = state.performance_store.get_recent_runs(limit=200)
    target = None
    for r in runs:
        if isinstance(r, dict) and r.get("id") == req.run_id:
            target = r
            break

    if not isinstance(target, dict):
        raise HTTPException(status_code=404, detail="run_id not found in recent runs")

    code = target.get("strategy_code")
    if not isinstance(code, str) or not code.strip():
        raise HTTPException(status_code=500, detail="selected run has no strategy_code")

    ok = state.strategy_service.save_strategy_code(code, filename="AIStrategy.py")
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to restore strategy")

    return {"ok": True, "restored_run_id": req.run_id}


def _job_refine(job: _Job, req: RefineStrategyRequest) -> Dict[str, Any]:
    job.append_log("Starting refine loop")
    market_context = {}
    try:
        state.ensure_bot_config_exists()
        with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            raise RuntimeError("user_data/config.json must be a JSON object")

        market_context["bot_config"] = {
            "strategy": cfg.get("strategy"),
            "timeframe": cfg.get("timeframe"),
            "stake_currency": cfg.get("stake_currency"),
            "dry_run": cfg.get("dry_run"),
        }
    except Exception as e:
        market_context["bot_config_error"] = str(e)

    try:
        state.ensure_bot_config_exists()
        with open(BOT_CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg2 = json.load(f)
        if not isinstance(cfg2, dict):
            raise RuntimeError("user_data/config.json must be a JSON object")

        ex = cfg2.get("exchange") if isinstance(cfg2.get("exchange"), dict) else {}
        wl_pairs = []
        if isinstance(ex, dict):
            v = ex.get("pair_whitelist")
            if isinstance(v, list):
                wl_pairs = [str(p).strip() for p in v if isinstance(p, str) and str(p).strip()]
        market_context["whitelist"] = {"whitelist": wl_pairs}
    except Exception as e:
        market_context["whitelist_error"] = str(e)

    res = state.strategy_service.refine_strategy_with_backtest_loop(
        strategy_code=req.strategy_code,
        user_goal=req.user_goal,
        max_iterations=req.max_iterations,
        timerange=req.timerange,
        timeframe=req.timeframe,
        pairs=req.pairs,
        market_context=market_context,
    )

    return res if isinstance(res, dict) else {"result": res}


@app.post("/api/ai/refine")
def ai_refine(req: RefineStrategyRequest) -> Dict[str, Any]:
    if not isinstance(req.strategy_code, str) or not req.strategy_code.strip():
        raise HTTPException(status_code=400, detail="strategy_code is required")
    if req.max_iterations < 1 or req.max_iterations > 5:
        raise HTTPException(status_code=400, detail="max_iterations must be between 1 and 5")

    job = state.create_job(kind="ai_refine", target=_job_refine, args=(req,), kwargs={})
    return {"job_id": job.id}
