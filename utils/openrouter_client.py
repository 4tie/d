import os
import time
import json
import re
import logging
from typing import Any, Dict, List, Optional

import requests

from utils.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)


class OpenRouterClient:
    MAX_RETRIES = 2
    RETRY_DELAY = 1.0
    RETRY_BACKOFF = 2.0
    CONNECTION_TIMEOUT = 10
    READ_TIMEOUT = 120

    def __init__(
        self,
        *,
        api_key: str = "",
        model: str = "",
        base_url: str = "https://openrouter.ai/api/v1",
        options: Optional[Dict[str, Any]] = None,
    ):
        self.api_key = str(api_key or "")
        self.base_url = str(base_url or "https://openrouter.ai/api/v1").rstrip("/")
        self.model = str(model or "")
        self.options: Dict[str, Any] = options if isinstance(options, dict) else {}

        self.session = requests.Session()

        self._kb: KnowledgeBase | None = None

        self._last_model_check = 0.0
        self._available_models: List[str] = []

        self._cache: Dict[str, Dict[str, Any]] = {}

    def _get_kb(self) -> KnowledgeBase:
        if self._kb is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self._kb = KnowledgeBase(base_dir=base_dir)
        return self._kb

    def _build_kb_context(self, query: str) -> str:
        try:
            kb = self._get_kb()
            try:
                kb.refresh_if_stale(max_age_seconds=900)
            except Exception:
                pass

            hits = kb.retrieve(query=query, top_k=4, max_chars=2600)
            if not hits:
                return ""

            parts: List[str] = []
            for h in hits:
                src = h.get("source") if isinstance(h, dict) else None
                content = h.get("content") if isinstance(h, dict) else None
                if not isinstance(content, str) or not content.strip():
                    continue
                if isinstance(src, str) and src.strip():
                    parts.append(f"SOURCE: {src.strip()}\n{content.strip()}")
                else:
                    parts.append(content.strip())
            return "\n\n".join(parts).strip()
        except Exception:
            return ""

    def update_settings(
        self,
        *,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        if api_key is not None:
            self.api_key = str(api_key or "")
        if model is not None:
            self.model = str(model or "")
        if base_url is not None:
            self.base_url = str(base_url or "https://openrouter.ai/api/v1").rstrip("/")
        if options is not None:
            if not isinstance(options, dict):
                raise ValueError("options must be a dict")
            self.options = options

        # invalidate model cache on settings changes
        self._last_model_check = 0.0
        self._available_models = []

    def is_configured(self) -> bool:
        return bool(str(self.api_key or "").strip()) and bool(str(self.model or "").strip())

    def _auth_headers(self) -> Dict[str, str]:
        key = str(self.api_key or "").strip()
        if not key:
            return {}
        return {"Authorization": f"Bearer {key}"}

    @staticmethod
    def _parse_money_str(v: Any) -> Optional[float]:
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if not s:
            return None
        try:
            return float(s)
        except Exception:
            return None

    @classmethod
    def _is_free_pricing(cls, pricing: Any) -> bool:
        if not isinstance(pricing, dict):
            return False

        required = ("prompt", "completion", "request")
        for k in required:
            if k not in pricing:
                return False
            f = cls._parse_money_str(pricing.get(k))
            if f is None or f != 0.0:
                return False

        for k, v in pricing.items():
            f = cls._parse_money_str(v)
            if f is None:
                return False
            if f != 0.0:
                return False

        return True

    def _get_cache_key(self, prompt: str) -> str:
        import hashlib

        s = f"openrouter:{self.model}:{prompt[:120]}"
        return hashlib.md5(s.encode("utf-8")).hexdigest()

    def _check_cache(self, prompt: str) -> Optional[str]:
        k = self._get_cache_key(prompt)
        cached = self._cache.get(k)
        if not isinstance(cached, dict):
            return None
        ts = cached.get("timestamp")
        if not isinstance(ts, (int, float)):
            return None
        if time.time() - float(ts) > 3600:
            return None
        txt = cached.get("response")
        if isinstance(txt, str) and txt.strip():
            return txt
        return None

    def _cache_response(self, prompt: str, response: str) -> None:
        k = self._get_cache_key(prompt)
        self._cache[k] = {"response": response, "timestamp": time.time(), "model": self.model}
        if len(self._cache) > 100:
            items = sorted(self._cache.items(), key=lambda kv: kv[1].get("timestamp", 0))
            self._cache = dict(items[-50:])

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = self.base_url.rstrip("/") + "/" + path.lstrip("/")
        headers = kwargs.pop("headers", {})
        if not isinstance(headers, dict):
            headers = {}

        headers.setdefault("Content-Type", "application/json")
        headers.update(self._auth_headers())

        kwargs.setdefault("timeout", (self.CONNECTION_TIMEOUT, self.READ_TIMEOUT))

        last_exception: Exception | None = None
        delay = self.RETRY_DELAY

        for attempt in range(self.MAX_RETRIES + 1):
            try:
                if method.upper() == "GET":
                    resp = self.session.get(url, headers=headers, **kwargs)
                elif method.upper() == "POST":
                    resp = self.session.post(url, headers=headers, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                resp.raise_for_status()
                return resp
            except requests.exceptions.HTTPError:
                raise
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                last_exception = e
                if attempt < self.MAX_RETRIES:
                    time.sleep(delay)
                    delay *= self.RETRY_BACKOFF
                    continue
                break
            except Exception as e:
                last_exception = e
                break

        raise RuntimeError(f"OpenRouter request failed: {type(last_exception).__name__}: {last_exception}")

    def list_free_models(self, *, force_refresh: bool = False) -> List[str]:
        now = time.time()
        if not force_refresh and self._available_models and (now - self._last_model_check) < 3600:
            return list(self._available_models)

        if not str(self.api_key or "").strip():
            raise RuntimeError("OpenRouter API key is not configured")

        resp = self._request("GET", "/models")
        data = resp.json()
        if not isinstance(data, dict) or not isinstance(data.get("data"), list):
            raise RuntimeError("Unexpected OpenRouter /models response format")

        out: List[str] = []
        for m in data.get("data"):
            if not isinstance(m, dict):
                continue
            mid = m.get("id")
            if not isinstance(mid, str) or not mid.strip():
                continue
            pricing = m.get("pricing")
            if not self._is_free_pricing(pricing):
                continue
            out.append(mid.strip())

        out = sorted(set(out))
        self._available_models = out
        self._last_model_check = now
        return list(out)

    def is_available(self) -> bool:
        try:
            if not str(self.api_key or "").strip():
                return False
            # Models endpoint is edge-cached and cheap; verify auth + connectivity.
            self.list_free_models(force_refresh=False)
            return True
        except Exception:
            return False

    def ensure_selected_model_is_free(self) -> None:
        self._ensure_selected_model_is_free()

    def _ensure_selected_model_is_free(self) -> None:
        model = str(self.model or "").strip()
        if not model:
            raise RuntimeError("OpenRouter model is not configured")

        models = self.list_free_models(force_refresh=False)
        if model in models:
            return

        models = self.list_free_models(force_refresh=True)
        if model in models:
            return

        raise RuntimeError(
            "Selected OpenRouter model is not free (or not available). "
            "Only free models are allowed."
        )

    def generate_text(self, prompt: str, use_cache: bool = True) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt is empty")

        if use_cache:
            cached = self._check_cache(prompt)
            if cached is not None:
                return cached

        self._ensure_selected_model_is_free()

        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }

        if isinstance(self.options, dict) and self.options:
            for k, v in self.options.items():
                if k in payload:
                    continue
                payload[k] = v

        resp = self._request("POST", "/chat/completions", data=json.dumps(payload))

        result = resp.json()
        if not isinstance(result, dict):
            raise RuntimeError("Unexpected OpenRouter chat response format")

        choices = result.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("OpenRouter returned empty choices")

        msg = choices[0]
        if not isinstance(msg, dict):
            raise RuntimeError("Unexpected OpenRouter chat response format (choice)")

        message = msg.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Unexpected OpenRouter chat response format (message)")

        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("OpenRouter returned empty response")

        text = content.strip()
        if use_cache:
            self._cache_response(prompt, text)

        return text

    def analyze_strategy_with_backtest(self, strategy_code: str, backtest_result: Dict) -> str:
        if not isinstance(backtest_result, dict):
            raise ValueError("Invalid backtest result format")

        backtest_json = json.dumps(backtest_result, indent=2, ensure_ascii=False)

        kb_context = self._build_kb_context(
            "strategy backtest analysis\n" + (strategy_code or "")[:2000] + "\n" + backtest_json[:2000]
        )

        prompt = f"""
You are a senior quantitative trading engineer and Freqtrade expert.

You will receive:
1) Freqtrade strategy code
2) A compact backtest summary + deterministic trade forensics

CRITICAL:
- Base your conclusions on the provided forensics and the strategy logic.
- If something is missing from the data, say exactly what is missing.
- Provide causal analysis: tie observed outcomes to concrete code logic and market regime conditions.
- Risk-adjusted reasoning is mandatory: discuss Sharpe/Sortino/max drawdown/Calmar if present.
- If Sharpe/Sortino/MaxDD are missing in the raw backtest summary, use trade_forensics.risk_adjusted.* as deterministic proxies.
- Explain "why losing" even when gross profit seems positive (fees, small edge, tail losses, regime mismatch).
- Keep ANY suggestion to change timeframe/pairs/timerange STRICTLY as the last section.

Output requirements:
- Use clear headings.
- Give concrete, testable recommendations.
- If you suggest code changes, show exact snippets.
- Provide a prioritized action list.

Return format:
1) Summary verdict (1 paragraph)
2) Risk-adjusted scorecard (Sharpe/Sortino/MaxDD/Calmar or proxies) + interpretation
3) Quant forensics interpretation (expectancy, profit factor, win/loss sizing, tail risk, fee/slippage sensitivity)
4) Causal root causes in strategy code (entry/exit/risk logic issues) + market regime linkage
5) Concrete fixes (numbered, with exact parameter/code changes)
6) Validation plan (what to backtest / what to measure next) + scenario ideas
7) Last resort: timeframe/pairs/timerange experiments (ONLY here)

Strategy code:
{strategy_code}

Knowledge base context (retrieved):
{kb_context}

Backtest summary JSON:
{backtest_json}
"""

        return self.generate_text(prompt)

    def assess_risk_with_backtest(self, strategy_code: str, backtest_result: Dict) -> str:
        if not isinstance(backtest_result, dict):
            raise ValueError("Invalid backtest result format")

        backtest_json = json.dumps(backtest_result, indent=2, ensure_ascii=False)

        kb_context = self._build_kb_context(
            "risk assessment\n" + (strategy_code or "")[:2000] + "\n" + backtest_json[:2000]
        )

        prompt = f"""
You are a senior risk manager and Freqtrade strategy reviewer.

You will receive:
1) Strategy code
2) Backtest summary + trade forensics + (optional) market context JSON

Rules:
- Base every claim on the provided JSON and the code.
- Use risk-adjusted metrics if present: Sharpe ratio, Sortino ratio, maximum drawdown, Calmar.
- If those are missing in the raw backtest summary, use the deterministic trade forensics risk_adjusted metrics (trade-based Sharpe/Sortino/max drawdown proxies) if present.
- If a risk-relevant metric is missing, state exactly what's missing.

Output format:
1) Risk rating (Low/Medium/High) + justification grounded in metrics
2) Risk-adjusted profile (Sharpe/Sortino/MaxDD/Calmar or trade-based proxies)
3) Key tail risks (loss tail, streaks, drawdown sensitivity, fee sensitivity)
4) Failure modes (market regimes / volatility / trend vs chop) - tie to market_context if present
5) Risk controls present/missing in code (stoploss, protections, exits, cooldown)
6) Concrete risk mitigations (ordered, testable) + what metric should improve

Strategy code:
{strategy_code}

Knowledge base context (retrieved):
{kb_context}

Backtest JSON:
{backtest_json}
"""

        return self.generate_text(prompt)

    def refine_strategy_with_backtest(self, user_goal: str, current_strategy_code: str, backtest_result: Dict) -> str:
        if not isinstance(backtest_result, dict):
            raise ValueError("Invalid backtest result format")

        goal = (user_goal or "").strip()
        strategy_class = "AIStrategy"
        try:
            m = re.search(
                r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(.*IStrategy.*\)\s*:\s*$",
                str(current_strategy_code or ""),
                flags=re.MULTILINE,
            )
            if m:
                strategy_class = str(m.group(1) or "").strip() or strategy_class
        except Exception:
            strategy_class = "AIStrategy"

        backtest_json = json.dumps(backtest_result, indent=2, ensure_ascii=False)

        kb_context = self._build_kb_context(
            "strategy refinement\n" + (goal or "") + "\n" + (current_strategy_code or "")[:2000] + "\n" + backtest_json[:2000]
        )

        prompt = f"""
You are an expert Freqtrade strategy developer and quantitative trading engineer.

You will improve the strategy based ONLY on:
1) The provided strategy code
2) The provided backtest summary + trade forensics JSON

Hard requirements:
1) Output ONLY Python code (no explanations, no markdown).
2) Keep the strategy class name EXACTLY as: {strategy_class}
3) The strategy class MUST inherit from IStrategy.
4) MUST include: populate_indicators, populate_entry_trend, populate_exit_trend.
5) MUST be syntactically valid Python.
6) Do NOT introduce lookahead bias.
7) Make the smallest set of changes that plausibly improves profitability AND risk-adjusted metrics.
8) If the code uses legacy naming (populate_buy_trend/populate_sell_trend or buy/sell columns), upgrade it to populate_entry_trend/populate_exit_trend and enter_long/exit_long.

Risk-adjusted requirements:
- Explicitly reduce tail risk and drawdown.
- Prefer changes that would improve Sharpe/Sortino and reduce maximum drawdown.
- If Sharpe/Sortino/MaxDD are not available in summary.metrics, use trade_forensics.risk_adjusted.* as proxy targets.

User goal (may be empty):
{goal}

Current strategy code:
{current_strategy_code}

Knowledge base context (retrieved):
{kb_context}

Backtest summary + forensics JSON:
{backtest_json}
"""

        return self.generate_text(prompt)

    def repair_strategy_code(self, user_idea: str, broken_code: str, error: str) -> str:
        strategy_class = "AIStrategy"
        try:
            m = re.search(
                r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(.*IStrategy.*\)\s*:\s*$",
                str(broken_code or ""),
                flags=re.MULTILINE,
            )
            if m:
                strategy_class = str(m.group(1) or "").strip() or strategy_class
        except Exception:
            strategy_class = "AIStrategy"

        kb_context = self._build_kb_context(
            "freqtrade strategy repair\n" + str(error or "")[:1200] + "\n" + str(broken_code or "")[:1800]
        )

        prompt = f"""
You are an expert Freqtrade strategy developer.

The following strategy code is INVALID and fails validation.
Fix it.

Hard requirements:
1) Output ONLY Python code (no explanations, no markdown).
2) Keep the strategy class name EXACTLY as: {strategy_class}
3) The strategy class MUST inherit from IStrategy.
3) MUST include: populate_indicators, populate_entry_trend, populate_exit_trend.
4) MUST be syntactically valid Python.
5) If the code uses legacy naming (populate_buy_trend/populate_sell_trend or buy/sell columns), upgrade it to populate_entry_trend/populate_exit_trend and enter_long/exit_long.
6) Do not use lookahead bias.

User idea:
{user_idea}

Validation error:
{error}

Knowledge base context (retrieved from local docs):
{kb_context}

Broken code:
{broken_code}
"""

        return self.generate_text(prompt)

    def generate_strategy(self, user_idea: str) -> str:
        prompt = f"""
You are an expert Freqtrade strategy developer.

Create a COMPLETE and VALID Python strategy file for Freqtrade.

Hard requirements:
1) Output ONLY Python code (no explanations, no markdown).
2) The strategy class MUST be named AIStrategy and inherit from IStrategy.
3) MUST include: populate_indicators, populate_entry_trend, populate_exit_trend.
4) MUST be syntactically valid Python.
5) Prefer talib.abstract as ta OR pandas_ta, but keep imports correct.
6) Keep parameters realistic (stoploss, minimal_roi) and avoid lookahead.

User idea:
{user_idea}
"""

        return self.generate_text(prompt)
