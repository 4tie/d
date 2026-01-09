import json
import logging
import math
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, Optional, List, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _detect_strategy_class(strategy_code: str) -> str:
    m = re.search(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(.*IStrategy.*\)\s*:", strategy_code, re.MULTILINE)
    if not m:
        raise RuntimeError("Could not detect strategy class name inheriting from IStrategy.")
    return m.group(1)


def _deep_find_first(obj: Any, predicate) -> Optional[Any]:
    if predicate(obj):
        return obj
    if isinstance(obj, dict):
        for v in obj.values():
            found = _deep_find_first(v, predicate)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _deep_find_first(v, predicate)
            if found is not None:
                return found
    return None


def _extract_trade_profit_pct(trade: Dict[str, Any]) -> Optional[float]:
    for k in ("profit_pct", "close_profit_pct", "profit_percent", "profit_ratio"):
        v = trade.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except Exception:
            continue
    return None


def summarize_backtest_data(backtest_json: Dict[str, Any], max_trades: int = 30) -> Dict[str, Any]:
    if not isinstance(backtest_json, dict):
        raise ValueError("backtest_json must be a dict")

    meta = backtest_json.get("metadata") if isinstance(backtest_json.get("metadata"), dict) else {}

    # Find trades list in a schema-agnostic way.
    trades_any = _deep_find_first(
        backtest_json,
        lambda x: isinstance(x, list)
        and len(x) > 0
        and all(isinstance(i, dict) for i in x[: min(3, len(x))])
        and any(
            isinstance(x[0].get(k), (int, float, str))
            for k in ("pair", "open_date", "close_date", "profit_pct", "profit_ratio")
        ),
    )

    trades: List[Dict[str, Any]] = []
    if isinstance(trades_any, list):
        trades = [t for t in trades_any if isinstance(t, dict)]

    # Pull a few stable metrics if present.
    metrics: Dict[str, Any] = {}
    for k in (
        "profit_total_pct",
        "profit_total_abs",
        "profit_total",
        "max_drawdown",
        "max_drawdown_pct",
        "winrate",
        "win_rate",
        "wins",
        "losses",
        "total_trades",
        "trade_count",
        "trades",
        "starting_balance",
        "final_balance",
        "sharpe",
        "sharpe_ratio",
        "sortino",
        "calmar",
    ):
        v = _deep_find_first(backtest_json, lambda x: isinstance(x, dict) and k in x)
        if isinstance(v, dict) and k in v:
            metrics[k] = v.get(k)

    # Build top/worst trades from the detected trade list.
    ranked: List[Tuple[float, Dict[str, Any]]] = []
    for t in trades:
        p = _extract_trade_profit_pct(t)
        if p is None:
            continue
        ranked.append((p, t))
    ranked.sort(key=lambda x: x[0])

    worst = [t for _p, t in ranked[: max_trades // 2]]
    best = [t for _p, t in ranked[-(max_trades // 2) :]] if ranked else []

    def _compact_trade(t: Dict[str, Any]) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        for k in (
            "pair",
            "open_date",
            "close_date",
            "open_rate",
            "close_rate",
            "enter_tag",
            "exit_reason",
            "profit_pct",
            "profit_ratio",
            "duration",
        ):
            if k in t:
                out[k] = t.get(k)
        return out

    summary = {
        "metadata": {
            "timerange": meta.get("timerange"),
            "timeframe": meta.get("timeframe"),
            "exchange": meta.get("exchange"),
        },
        "metrics": metrics,
        "trades_detected": len(trades),
        "worst_trades": [_compact_trade(t) for t in worst],
        "best_trades": [_compact_trade(t) for t in best],
    }

    return summary


def _safe_float(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _safe_str(v: Any) -> Optional[str]:
    if isinstance(v, str) and v.strip():
        return v.strip()
    return None


def build_trade_forensics(backtest_json: Dict[str, Any], max_groups: int = 8) -> Dict[str, Any]:
    """Build a deterministic quant forensics report from a backtest result.

    This intentionally does NOT rely on a single fixed freqtrade schema.
    It will best-effort find the trades list and then compute stable metrics.
    """
    if not isinstance(backtest_json, dict):
        raise ValueError("backtest_json must be a dict")

    summary = summarize_backtest_data(backtest_json, max_trades=0)
    trades_any = _deep_find_first(
        backtest_json,
        lambda x: isinstance(x, list)
        and len(x) > 0
        and all(isinstance(i, dict) for i in x[: min(3, len(x))])
        and any(
            isinstance(x[0].get(k), (int, float, str))
            for k in ("pair", "open_date", "close_date", "profit_pct", "profit_ratio", "profit_abs")
        ),
    )

    trades: List[Dict[str, Any]] = []
    if isinstance(trades_any, list):
        trades = [t for t in trades_any if isinstance(t, dict)]

    # Extract per-trade profit in pct terms (best-effort)
    profits: List[float] = []
    profit_abs: List[float] = []
    tiny_edge_count = 0
    win_count = 0
    loss_count = 0

    per_pair: Dict[str, List[float]] = {}
    per_exit: Dict[str, List[float]] = {}
    per_enter: Dict[str, List[float]] = {}

    for t in trades:
        p = _extract_trade_profit_pct(t)
        if p is None:
            # Some exports store only profit_abs
            pa = _safe_float(t.get("profit_abs"))
            if pa is not None:
                profit_abs.append(pa)
            continue

        profits.append(p)
        if p > 0:
            win_count += 1
        elif p < 0:
            loss_count += 1

        if abs(p) <= 0.10:
            tiny_edge_count += 1

        pair = _safe_str(t.get("pair"))
        if pair:
            per_pair.setdefault(pair, []).append(p)

        exit_reason = _safe_str(t.get("exit_reason")) or _safe_str(t.get("exit_tag"))
        if exit_reason:
            per_exit.setdefault(exit_reason, []).append(p)

        enter_tag = _safe_str(t.get("enter_tag")) or _safe_str(t.get("buy_tag"))
        if enter_tag:
            per_enter.setdefault(enter_tag, []).append(p)

        pa2 = _safe_float(t.get("profit_abs"))
        if pa2 is not None:
            profit_abs.append(pa2)

    n = len(profits)
    if n == 0:
        return {
            "metadata": summary.get("metadata"),
            "trades_detected": len(trades),
            "error": "No profit_pct values detected in trades. Cannot compute detailed forensics.",
        }

    profits_sorted = sorted(profits)

    def _std(xs: List[float]) -> Optional[float]:
        if len(xs) < 2:
            return None
        m = sum(xs) / len(xs)
        v = sum((x - m) ** 2 for x in xs) / (len(xs) - 1)
        if v <= 0:
            return 0.0
        return math.sqrt(v)

    def _compute_equity_curve_metrics() -> Dict[str, Any]:
        equity = 1.0
        peak = 1.0
        max_dd = 0.0

        for p in profits:
            r = p / 100.0
            equity *= (1.0 + r)
            if equity > peak:
                peak = equity
            dd = (equity - peak) / peak
            if dd < max_dd:
                max_dd = dd

        total_return = equity - 1.0
        max_dd_abs = abs(max_dd)
        calmar = (total_return / max_dd_abs) if max_dd_abs > 0 else None

        return {
            "total_return_fraction": total_return,
            "total_return_pct": total_return * 100.0,
            "max_drawdown_fraction": max_dd_abs,
            "max_drawdown_pct": max_dd_abs * 100.0,
            "calmar_trade": calmar,
        }

    def _compute_risk_adjusted_ratios() -> Dict[str, Any]:
        rs = [p / 100.0 for p in profits]
        nrs = len(rs)
        if nrs < 2:
            return {"sharpe_trade": None, "sortino_trade": None, "volatility_trade": None}

        mean_r = sum(rs) / nrs
        std_r = _std(rs)
        if std_r is None:
            return {"sharpe_trade": None, "sortino_trade": None, "volatility_trade": None}

        downside = [min(0.0, r) for r in rs]
        dd = math.sqrt(sum((r ** 2) for r in downside) / nrs) if nrs else 0.0

        vol = std_r
        sharpe = (mean_r / std_r) * math.sqrt(nrs) if std_r and std_r > 0 else None
        sortino = (mean_r / dd) * math.sqrt(nrs) if dd and dd > 0 else None

        return {
            "sharpe_trade": sharpe,
            "sortino_trade": sortino,
            "volatility_trade": vol,
        }

    def _max_streak(sign: int) -> int:
        best = 0
        cur = 0
        for p in profits:
            if (p > 0 and sign > 0) or (p < 0 and sign < 0):
                cur += 1
                if cur > best:
                    best = cur
            else:
                cur = 0
        return best

    def _distribution_bins() -> Dict[str, Any]:
        # Percentage profit bins (trade-level). Stable and interpretable for AI.
        bins = [
            (-float("inf"), -5.0, "<= -5%"),
            (-5.0, -2.0, "-5% .. -2%"),
            (-2.0, -1.0, "-2% .. -1%"),
            (-1.0, -0.5, "-1% .. -0.5%"),
            (-0.5, -0.1, "-0.5% .. -0.1%"),
            (-0.1, 0.1, "-0.1% .. +0.1%"),
            (0.1, 0.5, "+0.1% .. +0.5%"),
            (0.5, 1.0, "+0.5% .. +1%"),
            (1.0, 2.0, "+1% .. +2%"),
            (2.0, 5.0, "+2% .. +5%"),
            (5.0, float("inf"), ">= +5%"),
        ]

        counts: Dict[str, int] = {label: 0 for _a, _b, label in bins}
        for p in profits:
            for a, b, label in bins:
                if a < p <= b:
                    counts[label] += 1
                    break

        return {
            "n": len(profits),
            "counts": counts,
        }

    def _mean(xs: List[float]) -> float:
        return sum(xs) / max(1, len(xs))

    def _median(xs: List[float]) -> float:
        m = len(xs)
        if m == 0:
            return 0.0
        mid = m // 2
        if m % 2:
            return xs[mid]
        return (xs[mid - 1] + xs[mid]) / 2.0

    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p < 0]
    winrate = (len(wins) / n) if n else 0.0

    avg_win = _mean(wins) if wins else 0.0
    avg_loss = _mean(losses) if losses else 0.0  # negative

    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else None

    expectancy = (winrate * avg_win) + ((1.0 - winrate) * avg_loss)
    expectancy_ratio = (expectancy / abs(avg_loss)) if avg_loss < 0 else None

    p05 = profits_sorted[max(0, int(0.05 * (n - 1)))]
    p95 = profits_sorted[max(0, int(0.95 * (n - 1)))]

    # Heuristics to explain paradoxes ("profit but losing")
    diagnostics: List[str] = []
    if winrate > 0.55 and expectancy < 0:
        diagnostics.append("High winrate but negative expectancy: average loss magnitude dominates average win.")
    if winrate < 0.45 and expectancy > 0:
        diagnostics.append("Low winrate but positive expectancy: winners outweigh losers (trend-following profile).")
    if tiny_edge_count / n > 0.60:
        diagnostics.append("Most trades are tiny outcomes (<= 0.10%): strategy edge may be fee/slippage dominated.")
    if profit_factor is not None and profit_factor < 1.0:
        diagnostics.append("Profit factor < 1: gross losses exceed gross gains.")
    if p05 < -5:
        diagnostics.append("Heavy left tail: worst 5% of trades are very negative (tail risk).")

    def _group_stats(values: List[float]) -> Dict[str, Any]:
        vs = sorted(values)
        w = [p for p in values if p > 0]
        l = [p for p in values if p < 0]
        nr = len(values)
        wr = len(w) / nr if nr else 0.0
        exp = (wr * (_mean(w) if w else 0.0)) + ((1.0 - wr) * (_mean(l) if l else 0.0))
        return {
            "n": nr,
            "winrate": wr,
            "avg": _mean(values),
            "median": _median(vs),
            "p05": vs[max(0, int(0.05 * (nr - 1)))],
            "p95": vs[max(0, int(0.95 * (nr - 1)))],
            "expectancy": exp,
        }

    def _top_groups(groups: Dict[str, List[float]], reverse: bool) -> List[Dict[str, Any]]:
        rows = []
        for k, vs in groups.items():
            st = _group_stats(vs)
            rows.append({"key": k, **st})
        rows.sort(key=lambda r: r.get("expectancy", 0.0), reverse=reverse)
        return rows[:max_groups]

    report = {
        "metadata": summary.get("metadata"),
        "trades_detected": len(trades),
        "trades_scored": n,
        "winrate": winrate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": profit_factor,
        "expectancy_pct": expectancy,
        "expectancy_ratio": expectancy_ratio,
        "median_profit_pct": _median(profits_sorted),
        "p05_profit_pct": p05,
        "p95_profit_pct": p95,
        "tiny_edge_fraction": tiny_edge_count / n,
        "max_win_streak": _max_streak(+1),
        "max_loss_streak": _max_streak(-1),
        "profit_pct_distribution": _distribution_bins(),
        "risk_adjusted": {
            **_compute_equity_curve_metrics(),
            **_compute_risk_adjusted_ratios(),
        },
        "diagnostics": diagnostics,
        "best_pairs": _top_groups(per_pair, reverse=True),
        "worst_pairs": _top_groups(per_pair, reverse=False),
        "best_exit_reasons": _top_groups(per_exit, reverse=True),
        "worst_exit_reasons": _top_groups(per_exit, reverse=False),
        "best_enter_tags": _top_groups(per_enter, reverse=True),
        "worst_enter_tags": _top_groups(per_enter, reverse=False),
    }

    # Optional absolute profit info if present
    if profit_abs:
        report["profit_abs_summary"] = {
            "count": len(profit_abs),
            "total": sum(profit_abs),
            "avg": sum(profit_abs) / max(1, len(profit_abs)),
        }

    return report


def _cleanup_temp_files(tmp_strat_dir: str, max_age_hours: int = 24) -> int:
    """Clean up temporary strategy files older than max_age_hours. Returns count of deleted files."""
    deleted_count = 0
    try:
        tmp_path = Path(tmp_strat_dir)
        if not tmp_path.exists():
            return 0
        
        current_time = time.time()
        for file_path in tmp_path.glob("analysis_strategy_*.py"):
            try:
                file_mtime = file_path.stat().st_mtime
                if (current_time - file_mtime) > (max_age_hours * 3600):
                    file_path.unlink()
                    deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to clean up temp file {file_path}: {e}")
    except Exception as e:
        logger.warning(f"Failed to clean up temp directory {tmp_strat_dir}: {e}")
    
    return deleted_count


def _cleanup_backtest_results(out_dir: str, max_files: int = 20) -> int:
    """Clean up old backtest result files, keeping only the most recent ones. Returns count of deleted files."""
    deleted_count = 0
    try:
        out_path = Path(out_dir)
        if not out_path.exists():
            return 0
        
        result_files = sorted(
            [f for f in out_path.glob("backtest_*.json")],
            key=lambda f: f.stat().st_mtime,
            reverse=True
        )
        
        # Keep only the most recent files
        for file_path in result_files[max_files:]:
            try:
                file_path.unlink()
                deleted_count += 1
            except Exception as e:
                logger.warning(f"Failed to clean up backtest result {file_path}: {e}")
    except Exception as e:
        logger.warning(f"Failed to clean up backtest directory {out_dir}: {e}")
    
    return deleted_count


def download_data(
    config_path: str,
    timerange: Optional[str] = None,
    timeframe: Optional[str] = None,
    pairs: Optional[str] = None,
) -> Dict[str, Any]:
    root = _project_root()

    cmd = [
        sys.executable,
        "-m",
        "freqtrade",
        "download-data",
        "-c",
        config_path,
    ]

    if timerange:
        tr = str(timerange).strip()
        if tr:
            cmd.extend(["--timerange", tr])

    if timeframe:
        tf = str(timeframe).strip()
        if tf:
            cmd.extend(["-t", tf])

    if pairs:
        raw = str(pairs)
        parts = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
        if parts:
            cmd.extend(["-p", *parts])

    logger.info("Downloading data: %s", " ".join(cmd))

    proc = subprocess.run(
        cmd,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60 * 20,
    )

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""

    if proc.returncode != 0:
        raise RuntimeError(
            f"Data download failed (exit={proc.returncode}).\nSTDOUT:\n{stdout[-4000:]}\n\nSTDERR:\n{stderr[-4000:]}"
        )

    return {
        "cmd": cmd,
        "stdout": stdout,
        "stderr": stderr,
    }


def run_backtest(
    strategy_code: str,
    config_path: str,
    timerange: Optional[str] = None,
    timeframe: Optional[str] = None,
    pairs: Optional[str] = None,
) -> Dict[str, Any]:
    if not strategy_code or not strategy_code.strip():
        raise ValueError("Strategy code is empty")

    class_name = _detect_strategy_class(strategy_code)

    root = _project_root()
    data_dir = os.path.join(root, "data")
    tmp_strat_dir = os.path.join(data_dir, "tmp_backtest_strategies")
    out_dir = os.path.join(data_dir, "backtest_results")
    os.makedirs(tmp_strat_dir, exist_ok=True)
    os.makedirs(out_dir, exist_ok=True)

    # Clean up old temp files before creating new ones
    _cleanup_temp_files(tmp_strat_dir)
    _cleanup_backtest_results(out_dir)

    ts = time.strftime("%Y%m%d_%H%M%S")
    strategy_file = os.path.join(tmp_strat_dir, f"analysis_strategy_{ts}.py")
    out_filename = f"backtest_{class_name}_{ts}.json"
    out_file = os.path.join(out_dir, out_filename)

    strategy_file_temp = None
    try:
        with open(strategy_file, "w", encoding="utf-8") as f:
            f.write(strategy_code)
        strategy_file_temp = strategy_file

        cmd = [
            sys.executable,
            "-m",
            "freqtrade",
            "backtesting",
            "-c",
            config_path,
            "-s",
            class_name,
            "--strategy-path",
            tmp_strat_dir,
            "--export",
            "trades",
            "--backtest-directory",
            out_dir,
            "--backtest-filename",
            out_filename,
        ]

        if timeframe:
            tf = str(timeframe).strip()
            if tf:
                cmd.extend(["-i", tf])

        if timerange:
            cmd.extend(["--timerange", timerange])

        if pairs:
            raw = str(pairs)
            parts = [p.strip() for p in raw.replace(",", " ").split() if p.strip()]
            if parts:
                cmd.extend(["-p", *parts])

        logger.info("Running backtest: %s", " ".join(cmd))

        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60 * 20,
        )

        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        if proc.returncode != 0:
            raise RuntimeError(
                f"Backtest failed (exit={proc.returncode}).\nSTDOUT:\n{stdout[-4000:]}\n\nSTDERR:\n{stderr[-4000:]}"
            )

        if not os.path.exists(out_file):
            raise RuntimeError(
                f"Backtest finished but result file not found: {out_file}\nSTDOUT:\n{stdout[-4000:]}\n\nSTDERR:\n{stderr[-4000:]}"
            )

        with open(out_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if not isinstance(data, dict):
            raise RuntimeError("Backtest output JSON has unexpected format (expected object).")

        return {
            "strategy_class": class_name,
            "strategy_file": strategy_file,
            "result_file": out_file,
            "stdout": stdout,
            "stderr": stderr,
            "data": data,
        }
    finally:
        # Clean up the temporary strategy file immediately after use
        if strategy_file_temp and os.path.exists(strategy_file_temp):
            try:
                os.remove(strategy_file_temp)
            except Exception as e:
                logger.warning(f"Failed to remove temp strategy file {strategy_file_temp}: {e}")
