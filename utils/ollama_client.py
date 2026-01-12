"""
Ollama AI client for strategy analysis and trading insights
"""
import os
import requests
import json
import re
from typing import Dict, List, Optional, Any
import time
import logging
import threading
from queue import Queue

from utils.knowledge_base import KnowledgeBase

logger = logging.getLogger(__name__)

# Session will be created per instance to allow custom configuration


class OllamaClient:
    """Client for interacting with Ollama models with retry logic"""
    
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds
    RETRY_BACKOFF = 2.0  # exponential backoff multiplier
    CONNECTION_TIMEOUT = 10
    READ_TIMEOUT = 90  # Longer timeout for AI responses
    STREAM_TIMEOUT = 120  # Timeout for streaming responses
    MAX_CONCURRENT_REQUESTS = 3  # Maximum concurrent AI requests
    REQUEST_QUEUE_SIZE = 10  # Maximum queued requests
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama2", options: Optional[Dict] = None):
        self.base_url = base_url
        self.model = model
        self.options = options if isinstance(options, dict) else {}
        self._active_requests = 0
        self._request_queue = []
        self._cache = {}
        self._performance_metrics = {}
        self._last_model_check = 0
        self._available_models = []
        self._kb: KnowledgeBase | None = None
        
        # Create a session with connection pooling
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=5,
            pool_maxsize=5,
            max_retries=0  # We handle retries manually
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

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

    def update_settings(self, base_url: str, model: str, options: Optional[Dict] = None) -> None:
        self.base_url = base_url
        self.model = model
        if options is not None:
            if not isinstance(options, dict):
                raise ValueError("options must be a dict")
            self.options = options

    def update_options(self, options: Dict) -> None:
        if not isinstance(options, dict):
            raise ValueError("options must be a dict")
        self.options = options
    
    def set_model(self, model: str) -> None:
        """Switch to a different model"""
        if not model or not isinstance(model, str):
            raise ValueError("Model name must be a non-empty string")
        self.model = model
        
    def get_available_models(self, force_refresh: bool = False) -> List[str]:
        """Get list of available models with caching"""
        current_time = time.time()
        if not force_refresh and self._available_models and (current_time - self._last_model_check) < 3600:
            return self._available_models
        
        try:
            self._available_models = self.list_models()
            self._last_model_check = current_time
            return self._available_models
        except Exception:
            return self._available_models if self._available_models else []
    
    def get_model_info(self, model_name: str = None) -> Dict:
        """Get information about a specific model"""
        model = model_name or self.model
        try:
            response = self._make_request('GET', f"{self.base_url}/api/show", params={'name': model})
            return response.json()
        except Exception:
            return {}
    
    def generate_text_stream(self, prompt: str, callback: callable) -> str:
        """Generate text with streaming response"""
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt is empty")
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True
        }
        
        if isinstance(self.options, dict) and self.options:
            payload["options"] = self.options
        
        try:
            response = self._make_request(
                'POST',
                f"{self.base_url}/api/generate",
                json=payload,
                stream=True,
                timeout=(self.CONNECTION_TIMEOUT, self.STREAM_TIMEOUT)
            )
            
            full_response = ""
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        data_str = decoded_line[6:].strip()
                        if data_str == '[DONE]':
                            break
                        try:
                            data = json.loads(data_str)
                            if isinstance(data, dict):
                                text = data.get('response', '')
                                if text:
                                    full_response += text
                                    if callable(callback):
                                        callback(text)
                        except json.JSONDecodeError:
                            continue
            
            return full_response
            
        except Exception as e:
            raise RuntimeError(f"Streaming request failed: {e}")
    
    def _get_cache_key(self, prompt: str, method: str = "generate") -> str:
        """Generate a cache key for the given prompt"""
        import hashlib
        cache_key = f"{method}:{self.model}:{prompt[:100]}"  # Use first 100 chars for key
        return hashlib.md5(cache_key.encode('utf-8')).hexdigest()
    
    def _check_cache(self, prompt: str, method: str = "generate") -> Optional[str]:
        """Check if response is cached"""
        cache_key = self._get_cache_key(prompt, method)
        cached = self._cache.get(cache_key)
        if cached and isinstance(cached, dict):
            # Check if cache is still valid (1 hour)
            if time.time() - cached.get('timestamp', 0) < 3600:
                return cached.get('response')
        return None
    
    def _cache_response(self, prompt: str, response: str, method: str = "generate") -> None:
        """Cache the response"""
        cache_key = self._get_cache_key(prompt, method)
        self._cache[cache_key] = {
            'response': response,
            'timestamp': time.time(),
            'model': self.model
        }
        # Limit cache size
        if len(self._cache) > 100:
            # Remove oldest entries
            sorted_cache = sorted(self._cache.items(), key=lambda x: x[1]['timestamp'])
            self._cache = dict(sorted_cache[-50:])
    
    def _track_performance(self, method: str, success: bool, duration: float, prompt_length: int) -> None:
        """Track performance metrics"""
        key = f"{method}:{self.model}"
        if key not in self._performance_metrics:
            self._performance_metrics[key] = {
                'total_requests': 0,
                'successful_requests': 0,
                'total_duration': 0.0,
                'total_prompt_length': 0,
                'last_request_time': time.time()
            }
        
        metrics = self._performance_metrics[key]
        metrics['total_requests'] += 1
        if success:
            metrics['successful_requests'] += 1
        metrics['total_duration'] += duration
        metrics['total_prompt_length'] += prompt_length
        metrics['last_request_time'] = time.time()
    
    def get_performance_metrics(self) -> Dict:
        """Get performance metrics for all models"""
        return self._performance_metrics.copy()
    
    def _can_make_request(self) -> bool:
        """Check if we can make another request based on concurrency limits"""
        if self._active_requests >= self.MAX_CONCURRENT_REQUESTS:
            return False
        return True
    
    def _queue_request(self, method: str, url: str, **kwargs) -> Any:
        """Queue a request if we're at concurrency limit"""
        if len(self._request_queue) >= self.REQUEST_QUEUE_SIZE:
            raise RuntimeError("Request queue is full")
        
        # Create a future-like object for the queued request
        import threading
        from queue import Queue
        
        result_queue = Queue()
        
        def _process_queue():
            while self._request_queue:
                if self._can_make_request():
                    queued_method, queued_url, queued_kwargs, queued_result_queue = self._request_queue.pop(0)
                    self._active_requests += 1
                    try:
                        response = self._make_request(queued_method, queued_url, **queued_kwargs)
                        queued_result_queue.put({'success': True, 'response': response})
                    except Exception as e:
                        queued_result_queue.put({'success': False, 'error': e})
                    finally:
                        self._active_requests -= 1
                else:
                    time.sleep(0.05)
        
        self._request_queue.append((method, url, kwargs, result_queue))
        
        # Start processing thread if not already running
        if not hasattr(self, '_queue_thread') or not self._queue_thread.is_alive():
            self._queue_thread = threading.Thread(target=_process_queue, daemon=True)
            self._queue_thread.start()
        
        # Wait for result
        result = result_queue.get()
        if result['success']:
            return result['response']
        else:
            err = result.get('error')
            if isinstance(err, Exception):
                raise err
            raise RuntimeError(str(err))

    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make an HTTP request with retry logic"""
        last_exception = None
        delay = self.RETRY_DELAY
        
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                kwargs.setdefault('timeout', (self.CONNECTION_TIMEOUT, self.READ_TIMEOUT))
                
                if method.upper() == 'GET':
                    response = self.session.get(url, **kwargs)
                elif method.upper() == 'POST':
                    response = self.session.post(url, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                break
                    
            except requests.exceptions.Timeout as e:
                last_exception = e
                break
                    
            except requests.exceptions.HTTPError as e:
                # Don't retry on HTTP errors
                raise
                
            except Exception as e:
                raise
        
        raise last_exception

    def list_models(self) -> List[str]:
        response = self._make_request('GET', f"{self.base_url}/api/tags")
        data = response.json()

        if not isinstance(data, dict):
            raise RuntimeError("Unexpected Ollama /api/tags response format")

        models = data.get("models")
        if not isinstance(models, list):
            raise RuntimeError("Unexpected Ollama /api/tags response format (missing models)")

        names: List[str] = []
        for m in models:
            if isinstance(m, dict):
                name = m.get("name")
                if isinstance(name, str) and name.strip():
                    names.append(name.strip())

        if not names:
            raise RuntimeError("No models returned by Ollama. Pull a model (e.g. ollama pull llama2).")

        return sorted(set(names))
    
    def is_available(self) -> bool:
        """Check if Ollama service is available"""
        try:
            response = self._make_request('GET', f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception:
            return False
    
    def analyze_strategy(self, strategy_code: str, market_data: Optional[Dict] = None) -> str:
        """
        Analyze trading strategy and provide insights
        
        Args:
            strategy_code: The strategy code to analyze
            market_data: Optional market data for context
            
        Returns:
            AI analysis of the strategy
        """
        prompt = f"""
        As a trading expert, analyze this Freqtrade strategy and provide detailed insights:

        Strategy Code:
        {strategy_code}

        Please analyze:
        1. Strategy logic and potential effectiveness
        2. Risk factors and potential weaknesses
        3. Market conditions where this strategy would perform well/poorly
        4. Suggested improvements or optimizations
        5. Overall risk assessment (Low/Medium/High)

        Provide a comprehensive analysis in a structured format.
        """
        
        return self._generate_response(prompt)

    def analyze_strategy_with_backtest_contract(self, strategy_code: str, backtest_result: Dict) -> str:
        if not isinstance(backtest_result, dict):
            raise ValueError("Invalid backtest result format")

        backtest_json = json.dumps(backtest_result, indent=2, ensure_ascii=False)

        kb_context = self._build_kb_context(
            "contract strategy review\n" + (strategy_code or "")[:2000] + "\n" + backtest_json[:2000]
        )

        prompt = f"""
You are a quantitative trading strategy reviewer.

Your objective is to maximize risk-adjusted profitability.
You prioritize:
- Avoiding drawdowns
- Avoiding trend counter-trades
- Avoiding overfitting
- Practical execution on real exchanges

You do NOT explain basic indicators.
You focus on failure modes and improvements.

You will receive:
1) Freqtrade strategy code
2) Backtest summary + deterministic trade forensics JSON

Rules (non-negotiable):
- Base every claim on the provided JSON and the code. If data is missing, say what is missing.
- Propose EXACTLY ONE change (one hypothesis). Do not stack multiple modifications.
- Do not tune parameters without a concrete causal reason grounded in the code + results.
- The code change must be minimal and testable.

Reasoning framework (follow in order):
Step 1: Identify the primary loss mechanism.
Step 2: Identify market regimes where it fails.
Step 3: Propose one constraint/change to reduce losses.
Step 4: Explain why this constraint improves profitability.
Step 5: Output the exact code change as a complete strategy file.

Output format (MUST follow exactly):

LOSS_MECHANISM:
<text>

FAILURE_REGIME:
<text>

PROPOSED_FIX:
<text>

WHY_IT_WORKS:
<text>

CODE_CHANGE:
<python code>

After CODE_CHANGE, output nothing else.

CODE_CHANGE requirements:
- Provide a COMPLETE strategy file.
- Output raw Python code (no markdown fences).
- The class MUST be named AIStrategy and inherit from IStrategy.
- Must be syntactically valid.
- Must include populate_indicators, populate_entry_trend, populate_exit_trend.

Strategy code:
{strategy_code}

Knowledge base context (retrieved):
{kb_context}

Backtest JSON:
{backtest_json}
"""

        return self._generate_response(prompt)

    def analyze_strategy_with_scenarios(self, strategy_code: str, scenarios_payload: Dict) -> str:
        if not isinstance(scenarios_payload, dict):
            raise ValueError("Invalid scenarios payload format")

        payload_json = json.dumps(scenarios_payload, indent=2, ensure_ascii=False)

        kb_context = self._build_kb_context(
            "strategy scenario analysis\n" + (strategy_code or "")[:2000] + "\n" + payload_json[:2000]
        )

        prompt = f"""
You are a senior quantitative trading engineer and Freqtrade expert.

Task:
Analyze the SAME strategy across MULTIPLE backtest scenarios and explain regime sensitivity.

Rules:
- Base every claim on the provided JSON and the code.
- Provide causal analysis: tie performance differences to concrete entry/exit/risk logic.
- Risk-adjusted reasoning is mandatory: Sharpe/Sortino/max drawdown/Calmar if present.
- If those are missing in backtest_summary.metrics, use trade_forensics.risk_adjusted.* as deterministic proxies.
- Identify which scenario characteristics likely caused improvements/degradation (timeframe, timerange, pair set).
- Do NOT invent candle patterns or indicators outside the provided data/code.

Output format:
1) Scenario scorecard table (per scenario: profit/expectancy/profit_factor + Sharpe/Sortino + MaxDD)
2) Regime sensitivity summary (what changes across scenarios and why)
3) Failure modes & their triggers (scenario-linked)
4) Concrete strategy changes to reduce sensitivity (testable)
5) Validation plan: next scenario grid to run

Strategy code:
{strategy_code}

Knowledge base context (retrieved):
{kb_context}

Scenarios JSON:
{payload_json}
"""

        return self._generate_response(prompt)

    def assess_risk_with_scenarios(self, strategy_code: str, scenarios_payload: Dict) -> str:
        if not isinstance(scenarios_payload, dict):
            raise ValueError("Invalid scenarios payload format")

        payload_json = json.dumps(scenarios_payload, indent=2, ensure_ascii=False)

        kb_context = self._build_kb_context(
            "scenario risk assessment\n" + (strategy_code or "")[:2000] + "\n" + payload_json[:2000]
        )

        prompt = f"""
You are a senior risk manager and Freqtrade strategy reviewer.

Task:
Assess risk across MULTIPLE backtest scenarios for the SAME strategy.

Rules:
- Base every claim on the provided JSON and the code.
- Risk-adjusted reasoning is mandatory (Sharpe/Sortino/MaxDD/Calmar or trade_forensics.risk_adjusted proxies).
- Focus on tail risk, drawdown sensitivity, and scenario-to-scenario stability.
- If a risk-relevant metric is missing, state exactly what's missing.

Output format:
1) Overall risk rating (Low/Medium/High) based on worst-case scenario
2) Worst-case scenario identification + metric evidence
3) Drawdown and tail risk drivers (code + scenario linkage)
4) Risk controls present/missing in code
5) Concrete mitigations (ordered) + what metric should improve

Strategy code:
{strategy_code}

Knowledge base context (retrieved):
{kb_context}

Scenarios JSON:
{payload_json}
"""

        return self._generate_response(prompt)

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

        return self._generate_response(prompt)

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

        return self._generate_response(prompt)

    def generate_text(self, prompt: str, use_cache: bool = True) -> str:
        if not isinstance(prompt, str) or not prompt.strip():
            raise ValueError("Prompt is empty")
        return self._generate_response(prompt, use_cache=use_cache)
    
    def get_queue_status(self) -> Dict:
        """Get current request queue status"""
        return {
            'active_requests': self._active_requests,
            'queued_requests': len(self._request_queue),
            'max_concurrent': self.MAX_CONCURRENT_REQUESTS,
            'max_queue_size': self.REQUEST_QUEUE_SIZE
        }
    
    def clear_cache(self) -> None:
        """Clear the response cache"""
        self._cache = {}
    
    def set_concurrency_limits(self, max_concurrent: int, max_queue: int) -> None:
        """Set concurrency limits"""
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be at least 1")
        if max_queue < 0:
            raise ValueError("max_queue must be non-negative")
        
        self.MAX_CONCURRENT_REQUESTS = max_concurrent
        self.REQUEST_QUEUE_SIZE = max_queue

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

        return self._generate_response(prompt)

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

        return self._generate_response(prompt)

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

        return self._generate_response(prompt)
    
    def analyze_losses(self, trade_history: List[Dict], current_drawdown: float) -> str:
        """
        Analyze trading losses and provide insights on why trades are losing
        
        Args:
            trade_history: List of recent trades with details
            current_drawdown: Current portfolio drawdown percentage
            
        Returns:
            AI analysis of losses and recommendations
        """
        trades_text = "\n".join([
            f"Trade {i+1}: {trade.get('pair', 'Unknown')} - "
            f"Entry: {trade.get('enter_price', 0)}, "
            f"Exit: {trade.get('exit_price', 0)}, "
            f"Profit: {trade.get('profit_pct', 0)}%, "
            f"Duration: {trade.get('duration', 'Unknown')}"
            for i, trade in enumerate(trade_history[-10:])  # Last 10 trades
        ])
        
        prompt = f"""
        As a trading analyst, analyze these recent trading losses and provide insights:

        Current Drawdown: {current_drawdown:.2f}%

        Recent Trades:
        {trades_text}

        Please analyze:
        1. Common patterns in losing trades
        2. Potential reasons for the current drawdown
        3. Market conditions affecting performance
        4. Strategy adjustments needed
        5. Risk management recommendations
        6. When to expect recovery

        Provide actionable insights to improve trading performance.
        """
        
        return self._generate_response(prompt)
    
    def generate_strategy_improvements(self, current_strategy: str, performance_metrics: Dict) -> str:
        """
        Generate improvements for an existing strategy based on performance
        
        Args:
            current_strategy: Current strategy code
            performance_metrics: Strategy performance data
            
        Returns:
            AI-generated strategy improvements
        """
        prompt = f"""
        As a quantitative trading expert, improve this Freqtrade strategy based on its performance:

        Current Strategy:
        {current_strategy}

        Performance Metrics:
        - Total Profit: {performance_metrics.get('profit_pct', 0)}%
        - Win Rate: {performance_metrics.get('win_rate', 0)}%
        - Max Drawdown: {performance_metrics.get('max_drawdown', 0)}%
        - Sharpe Ratio: {performance_metrics.get('sharpe', 0)}
        - Total Trades: {performance_metrics.get('total_trades', 0)}

        Please provide:
        1. Specific code improvements
        2. Parameter optimizations
        3. Additional indicators that could help
        4. Risk management enhancements
        5. Market condition filters

        Return the complete improved strategy code with explanations.
        """
        
        return self._generate_response(prompt)

    def generate_strategy_improvements_contract(self, current_strategy: str, performance_metrics: Dict) -> str:
        if not isinstance(performance_metrics, dict):
            raise ValueError("performance_metrics must be a dict")

        metrics_json = json.dumps(performance_metrics, indent=2, ensure_ascii=False)

        kb_context = self._build_kb_context(
            "contract improvements\n" + (current_strategy or "")[:2000] + "\n" + metrics_json[:2000]
        )

        prompt = f"""
You are a quantitative trading strategy reviewer.

Your objective is to maximize risk-adjusted profitability.
You prioritize:
- Avoiding drawdowns
- Avoiding trend counter-trades
- Avoiding overfitting
- Practical execution on real exchanges

You do NOT explain basic indicators.
You focus on failure modes and improvements.

Rules (non-negotiable):
- Propose EXACTLY ONE change (one hypothesis). Do not stack multiple modifications.
- Do not optimize blindly.
- Do not tune parameters without a causal justification grounded in the provided metrics + code.

Reasoning framework (follow in order):
Step 1: Identify the primary loss mechanism.
Step 2: Identify market regimes where it fails.
Step 3: Propose one constraint/change to reduce losses.
Step 4: Explain why this constraint improves profitability.
Step 5: Output the exact code change as a complete strategy file.

Output format (MUST follow exactly):

LOSS_MECHANISM:
<text>

FAILURE_REGIME:
<text>

PROPOSED_FIX:
<text>

WHY_IT_WORKS:
<text>

CODE_CHANGE:
<python code>

After CODE_CHANGE, output nothing else.

CODE_CHANGE requirements:
- Provide a COMPLETE strategy file.
- Output raw Python code (no markdown fences).
- The class MUST be named AIStrategy and inherit from IStrategy.
- Must be syntactically valid.
- Must include populate_indicators, populate_entry_trend, populate_exit_trend.

Current strategy code:
{current_strategy}

Performance metrics JSON:
{metrics_json}

Knowledge base context (retrieved):
{kb_context}
"""

        return self._generate_response(prompt)
    
    def _generate_response(self, prompt: str, use_cache: bool = True) -> str:
        """Generate response from Ollama model with retry logic"""
        # Check cache first
        if use_cache:
            cached_response = self._check_cache(prompt)
            if cached_response:
                return cached_response
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False
        }
        
        if isinstance(self.options, dict) and self.options:
            payload["options"] = self.options
        
        last_exception = None
        delay = self.RETRY_DELAY
        start_time = time.time()
        
        # Check if we can make the request or need to queue it
        if not self._can_make_request():
            try:
                response = self._queue_request('POST', f"{self.base_url}/api/generate", json=payload)
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                self._track_performance('generate', False, time.time() - start_time, len(prompt))
                endpoint = f"{self.base_url}/api/generate"
                err_name = type(e).__name__
                hint = (
                    "Hint: ensure Ollama is running ('ollama serve'), the Ollama URL/model in Settings are correct, "
                    "and the model is pulled ('ollama pull <model>')."
                )
                raise RuntimeError(
                    f"Ollama request failed (model='{self.model}', url='{endpoint}', "
                    f"timeouts=({self.CONNECTION_TIMEOUT},{self.READ_TIMEOUT})s, attempts=1): "
                    f"{err_name}: {e}. {hint}"
                ) from e

            result: Any = response.json()
            if not isinstance(result, dict):
                self._track_performance('generate', False, time.time() - start_time, len(prompt))
                raise RuntimeError("Unexpected Ollama response format")

            text = result.get('response')
            if not isinstance(text, str) or not text.strip():
                self._track_performance('generate', False, time.time() - start_time, len(prompt))
                raise RuntimeError("Ollama returned empty response")

            if use_cache:
                self._cache_response(prompt, text)

            duration = time.time() - start_time
            self._track_performance('generate', True, duration, len(prompt))
            return text
        
        self._active_requests += 1
        
        try:
            for attempt in range(self.MAX_RETRIES + 1):
                try:
                    response = self._make_request(
                        'POST',
                        f"{self.base_url}/api/generate",
                        json=payload
                    )
                    
                    result: Any = response.json()
                    if not isinstance(result, dict):
                        raise RuntimeError("Unexpected Ollama response format")
                    
                    text = result.get('response')
                    if not isinstance(text, str) or not text.strip():
                        raise RuntimeError("Ollama returned empty response")
                    
                    # Cache the successful response
                    if use_cache:
                        self._cache_response(prompt, text)
                    
                    # Track performance
                    duration = time.time() - start_time
                    self._track_performance('generate', True, duration, len(prompt))
                    
                    return text
                    
                except requests.exceptions.ConnectionError as e:
                    last_exception = e
                    logger.warning(f"Ollama connection attempt {attempt + 1} failed: {e}")
                    break
                        
                except requests.exceptions.Timeout as e:
                    last_exception = e
                    logger.warning(f"Ollama timeout on attempt {attempt + 1}: {e}")
                    break
                        
                except RuntimeError as e:
                    # Don't retry on validation errors
                    self._track_performance('generate', False, time.time() - start_time, len(prompt))
                    raise
                    
                except Exception as e:
                    last_exception = e
                    if attempt < self.MAX_RETRIES:
                        time.sleep(delay)
                        delay *= self.RETRY_BACKOFF
            
            self._track_performance('generate', False, time.time() - start_time, len(prompt))
            endpoint = f"{self.base_url}/api/generate"
            err_name = type(last_exception).__name__ if last_exception is not None else "UnknownError"
            attempts = attempt + 1
            hint = (
                "Hint: ensure Ollama is running ('ollama serve'), the Ollama URL/model in Settings are correct, "
                "and the model is pulled ('ollama pull <model>')."
            )
            raise RuntimeError(
                f"Ollama request failed (model='{self.model}', url='{endpoint}', "
                f"timeouts=({self.CONNECTION_TIMEOUT},{self.READ_TIMEOUT})s, attempts={attempts}): "
                f"{err_name}: {last_exception}. {hint}"
            )
            
        finally:
            self._active_requests -= 1
            # Process any queued requests
            pass
