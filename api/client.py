import requests
from requests.auth import HTTPBasicAuth
from typing import List, Dict, Any, Optional
import logging
import time

logger = logging.getLogger(__name__)


class FreqtradeClient:
    """Freqtrade API client with retry logic and connection pooling"""
    
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0  # seconds
    RETRY_BACKOFF = 2.0  # exponential backoff multiplier
    CONNECTION_TIMEOUT = 10
    READ_TIMEOUT = 30
    
    def __init__(self, base_url, username, password):
        self.base_url = base_url
        self.auth = HTTPBasicAuth(username, password)
        
        # Create a session with connection pooling
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=0  # We handle retries manually
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)

        self.token = None
        self._connected = None

    def _build_url(self, path: str) -> str:
        base = self.base_url
        if not isinstance(base, str) or not base.strip():
            raise ValueError("Freqtrade URL is not configured")

        base = base.strip()
        if not (base.startswith("http://") or base.startswith("https://")):
            raise ValueError("Freqtrade URL must start with http:// or https://")

        base = base.rstrip("/")
        p = path if isinstance(path, str) else ""
        if not p.startswith("/"):
            p = "/" + p

        if base.endswith("/api/v1") and p.startswith("/api/v1/"):
            return base + p[len("/api/v1"):]
        if base.endswith("/api") and p.startswith("/api/"):
            return base + p[len("/api"):]

        return base + p

    def _set_connectivity(self, connected: bool) -> None:
        if self._connected is connected:
            return
        self._connected = connected
        if connected:
            logger.info("Freqtrade API connected")
        else:
            logger.info("Freqtrade API unreachable")
    
    def _make_request(self, method: str, url: str, **kwargs) -> Optional[requests.Response]:
        """Make an HTTP request with retry logic"""
        last_exception = None
        delay = self.RETRY_DELAY
        
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                kwargs.setdefault('timeout', (self.CONNECTION_TIMEOUT, self.READ_TIMEOUT))
                
                if method.upper() == 'GET':
                    response = self.session.get(url, auth=self.auth, **kwargs)
                elif method.upper() == 'POST':
                    response = self.session.post(url, auth=self.auth, **kwargs)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                self._set_connectivity(True)
                
                response.raise_for_status()
                return response
                
            except requests.exceptions.ConnectionError as e:
                last_exception = e
                logger.debug(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(delay)
                    delay *= self.RETRY_BACKOFF
                    
            except requests.exceptions.Timeout as e:
                last_exception = e
                logger.debug(f"Timeout on attempt {attempt + 1}: {e}")
                if attempt < self.MAX_RETRIES:
                    time.sleep(delay)
                    delay *= self.RETRY_BACKOFF
                    
            except requests.exceptions.HTTPError as e:
                # Don't retry on HTTP errors (4xx, 5xx)
                raise
                
            except Exception as e:
                logger.error(f"Unexpected error during request: {e}")
                raise
        
        self._set_connectivity(False)
        raise last_exception

    def update_settings(self, base_url: str, username: str, password: str) -> None:
        self.base_url = base_url
        self.auth = HTTPBasicAuth(username, password)
        self.token = None

    def get_status(self):
        """Fetches bot status (running, stopped, etc)."""
        try:
            url = self._build_url("/api/v1/ping")
        except ValueError:
            return "Not configured"
        try:
            response = self._make_request('GET', url)
            return response.json().get('status', 'Unknown')
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return "Error"
        except requests.exceptions.RequestException as e:
            logger.warning("Status Error: %s", e)
            return "Error"
        except Exception:
            logger.exception("Status Error")
            return "Error"

    def get_profit(self):
        """Fetches current profit stats."""
        try:
            url = self._build_url("/api/v1/profit")
        except ValueError:
            return None
        try:
            response = self._make_request('GET', url)
            return response.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return {}
        except requests.exceptions.RequestException as e:
            logger.warning("Profit Error: %s", e)
            return {}
        except Exception:
            logger.exception("Profit Error")
            return {}
    
    def get_trade_history(self, limit: int = 50):
        """Fetches recent trade history."""
        try:
            url = self._build_url("/api/v1/trades")
        except ValueError:
            return []
        try:
            params = {"limit": limit}
            response = self._make_request('GET', url, params=params)
            data = response.json()
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                trades = data.get('trades', [])
                return trades if isinstance(trades, list) else []
            return []
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return []
        except requests.exceptions.RequestException as e:
            logger.warning("Trade History Error: %s", e)
            return []
        except Exception:
            logger.exception("Trade History Error")
            return []
    
    def get_performance_stats(self):
        """Fetches detailed performance statistics."""
        try:
            url = self._build_url("/api/v1/status")
        except ValueError:
            return {}
        try:
            response = self._make_request('GET', url)
            return response.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return {}
        except requests.exceptions.RequestException as e:
            logger.warning("Performance Stats Error: %s", e)
            return {}
        except Exception:
            logger.exception("Performance Stats Error")
            return {}
    
    def get_daily_profit(self, days: int = 30):
        """Fetches daily profit data for analysis."""
        try:
            url = self._build_url("/api/v1/daily")
        except ValueError:
            return []
        try:
            params = {"timescale": days}
            response = self._make_request('GET', url, params=params)
            return response.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return []
        except requests.exceptions.RequestException as e:
            logger.warning("Daily Profit Error: %s", e)
            return []
        except Exception:
            logger.exception("Daily Profit Error")
            return []

    def reload_config(self) -> Dict[str, Any]:
        """Reloads the bot's configuration."""
        try:
            url = self._build_url("/api/v1/reload_config")
        except ValueError as e:
            return {"status": f"error: {e}"}
        try:
            response = self._make_request('POST', url)
            return response.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            return {"status": f"error: {e}"}
        except requests.exceptions.RequestException as e:
            logger.warning("Reload Config Error: %s", e)
            return {"status": f"error: {e}"}
        except Exception as e:
            logger.exception("Reload Config Error")
            return {"status": f"error: {e}"}

    def get_config(self) -> Optional[Dict[str, Any]]:
        """Fetches the bot's current configuration."""
        try:
            url = self._build_url("/api/v1/show_config")
        except ValueError:
            return None
        try:
            response = self._make_request('GET', url)
            return response.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return None
        except requests.exceptions.RequestException as e:
            logger.warning("Get Config Error: %s", e)
            return None
        except Exception:
            logger.exception("Get Config Error")
            return None

    def get_open_trades(self) -> List[Dict[str, Any]]:
        """Fetches the list of open trades."""
        data: Any = None
        try:
            url = self._build_url("/api/v1/status")
        except ValueError:
            return []
        try:
            response = self._make_request('GET', url)
            data = response.json()
            if isinstance(data, list):
                return [t for t in data if isinstance(t, dict)]
            if isinstance(data, dict):
                open_trades = data.get('open_trades')
                if isinstance(open_trades, list):
                    return [t for t in open_trades if isinstance(t, dict)]
                trades = data.get('trades')
                if isinstance(trades, list):
                    return [t for t in trades if isinstance(t, dict)]
                return []
            return []
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return []
        except requests.exceptions.RequestException as e:
            logger.warning("Get Open Trades Error: %s", e)
            return []
        except Exception:
            logger.exception("Get Open Trades Error (%s) [type=%s]", __file__, type(data).__name__)
            return []

    def get_whitelist(self) -> List[str]:
        """Fetches current trading whitelist from the bot."""
        try:
            url = self._build_url("/api/v1/whitelist")
        except ValueError:
            return []
        try:
            response = self._make_request('GET', url)
            data = response.json()
            if isinstance(data, list):
                return [str(p).strip() for p in data if str(p).strip()]
            if isinstance(data, dict):
                wl = data.get('whitelist', data.get('data'))
                if isinstance(wl, list):
                    return [str(p).strip() for p in wl if str(p).strip()]
            return []
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return []
        except requests.exceptions.RequestException as e:
            logger.warning("Whitelist Error: %s", e)
            return []
        except Exception:
            logger.exception("Whitelist Error")
            return []

    def get_pair_candles(
        self,
        pair: str,
        timeframe: str,
        limit: int = 120,
        columns: Optional[List[str]] = None,
    ) -> Any:
        """Fetches candles for a pair from the bot (typically OHLCV and optionally indicators).

        Returns the raw JSON response (schema may differ by freqtrade version).
        """
        if not pair or not str(pair).strip():
            raise ValueError("pair is required")
        if not timeframe or not str(timeframe).strip():
            raise ValueError("timeframe is required")

        try:
            url = self._build_url("/api/v1/pair_candles")
        except ValueError:
            return None

        try:
            params: Dict[str, Any] = {
                "pair": str(pair).strip(),
                "timeframe": str(timeframe).strip(),
                "limit": int(limit),
            }
            if columns:
                params["columns"] = columns
            response = self._make_request('GET', url, params=params)
            return response.json()
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            return None
        except requests.exceptions.RequestException as e:
            logger.warning("Pair candles Error: %s", e)
            return None
        except Exception:
            logger.exception("Pair candles Error")
            return None
