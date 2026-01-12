import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet, formatApiError } from "../lib/api";
import { Card, Metric } from "../components/primitives";
import { SkeletonMetric, SkeletonCard, EmptyState } from "../components/loading";

type ShowConfig = Record<string, any>;

type RunRow = Record<string, any>;

type RunsResponse = {
  runs: RunRow[];
};

export default function Dashboard() {
  const cfgQ = useQuery({
    queryKey: ["bot_show_config"],
    queryFn: () => apiGet<ShowConfig>("/api/bot/show_config"),
    refetchInterval: 30000,
  });
  const runsQ = useQuery({
    queryKey: ["history_runs_dashboard"],
    queryFn: () => apiGet<RunsResponse>("/api/history/runs?limit=80"),
    refetchInterval: 15000,
  });

  const runs = Array.isArray(runsQ.data?.runs) ? runsQ.data?.runs : [];
  const latestRun = runs.length ? runs[0] : null;

  const profitPct = useMemo(() => {
    const v = (latestRun as any)?.backtest_summary?.metrics?.profit_total_pct;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }, [latestRun]);

  const ddPct = useMemo(() => {
    const v = (latestRun as any)?.backtest_summary?.metrics?.max_drawdown_pct ?? (latestRun as any)?.trade_forensics?.risk_adjusted?.max_drawdown_pct;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }, [latestRun]);

  const bestTrades = useMemo(() => {
    const arr = (latestRun as any)?.backtest_summary?.best_trades;
    return Array.isArray(arr) ? arr : [];
  }, [latestRun]);

  const worstTrades = useMemo(() => {
    const arr = (latestRun as any)?.backtest_summary?.worst_trades;
    return Array.isArray(arr) ? arr : [];
  }, [latestRun]);

  const errors = [cfgQ.error, runsQ.error].filter(Boolean);
  const isInitialLoading = cfgQ.isLoading || runsQ.isLoading;

  if (isInitialLoading) {
    return (
      <div className="space-y-4">
        <SkeletonCard />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <SkeletonMetric />
          <SkeletonMetric />
          <SkeletonMetric />
        </div>
        <SkeletonCard />
      </div>
    );
  }

  return (
    <div className="space-y-4 animate-fade-in">
      {errors.length ? (
        <div className="text-xs font-mono text-semantic-neg animate-slide-down">{errors.map((e) => formatApiError(e)).join(" | ")}</div>
      ) : null}

      <Card title="Strategy Identity">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div>
            <div className="text-xs text-fg-400">Strategy</div>
            <div className="mt-1 font-mono text-sm text-fg-200">{String((cfgQ.data as any)?.strategy || "-")}</div>
          </div>
          <div>
            <div className="text-xs text-fg-400">Timeframe</div>
            <div className="mt-1 font-mono text-sm text-fg-200">{String((cfgQ.data as any)?.timeframe || "-")}</div>
          </div>
          <div>
            <div className="text-xs text-fg-400">Exchange</div>
            <div className="mt-1 font-mono text-sm text-fg-200">{String((cfgQ.data as any)?.exchange || "-")}</div>
          </div>
        </div>
      </Card>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Metric
          label="Last Backtest Profit %"
          value={profitPct === null ? "-" : `${profitPct >= 0 ? "+" : ""}${profitPct.toFixed(2)}%`}
          tone={profitPct === null ? "neutral" : profitPct >= 0 ? "pos" : "neg"}
        />
        <Metric
          label="Last Backtest Max DD %"
          value={ddPct === null ? "-" : `${ddPct.toFixed(2)}%`}
          tone={ddPct === null ? "neutral" : "warn"}
        />
        <Metric label="Runs" value={runs.length ? String(runs.length) : "0"} tone={runs.length ? "pos" : "neutral"} />
      </div>

      <Card title="Last Run">
        {!latestRun ? (
          <EmptyState title="No runs yet" description="Run a backtest to populate local history." />
        ) : (
          <div className="space-y-2">
            <div className="text-xs font-mono text-fg-400">Run #{String((latestRun as any).id || "-")}</div>
            <div className="text-xs font-mono text-fg-400">Type: {String((latestRun as any).run_type || "-")}</div>
            <div className="text-xs font-mono text-fg-400">Time: {Number((latestRun as any).ts) ? new Date(Number((latestRun as any).ts) * 1000).toLocaleString() : ""}</div>
          </div>
        )}
      </Card>

      <Card title="Backtest Trades (Best / Worst)">
        {!latestRun ? (
          <EmptyState title="No trades" description="Run a backtest to generate trade samples." />
        ) : (bestTrades.length || worstTrades.length) ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-xs text-fg-400 font-mono">Worst</div>
              <pre className="mt-2 text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[260px]">
                {JSON.stringify(worstTrades.slice(0, 10), null, 2)}
              </pre>
            </div>
            <div>
              <div className="text-xs text-fg-400 font-mono">Best</div>
              <pre className="mt-2 text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[260px]">
                {JSON.stringify(bestTrades.slice(0, 10), null, 2)}
              </pre>
            </div>
          </div>
        ) : (
          <EmptyState title="No trade samples" description="This run did not include trade samples in its summary." />
        )}
      </Card>

      <Card title="Quick Diagnostics">
        <div className="text-sm text-fg-400">
          This panel will surface deterministic checks once backtest/forensics runs exist in History.
        </div>
      </Card>
    </div>
  );
}
