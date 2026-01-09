import { useEffect, useMemo, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import { useLocalStorageState } from "../lib/storage";
import { ConnectionStatus } from "./connection-status";

type StrategyFile = {
  filename: string;
  path: string;
  size: number;
  mtime: number;
  strategy_hash?: string | null;
};

type StrategiesResponse = {
  strategies: StrategyFile[];
};

type HistoryRun = {
  id?: number;
  ts?: number;
  run_type?: string;
  strategy_hash?: string;
  backtest_summary?: any;
  trade_forensics?: any;
};

type HistoryRunsResponse = {
  runs: HistoryRun[];
};

type ShowConfig = {
  strategy?: string;
  timeframe?: string;
  exchange?: string;
  stake_currency?: string;
};

export function StrategyNavigator() {
  const nav = useNavigate();

  const [theme, setTheme] = useState<string>(() => {
    if (typeof document === "undefined") return "";
    return document.documentElement.dataset.theme || "";
  });

  useEffect(() => {
    if (typeof document === "undefined") return;
    const t = theme.trim();
    if (t) {
      document.documentElement.dataset.theme = t;
      try {
        localStorage.setItem("st_theme", t);
      } catch {
        return;
      }
    } else {
      delete document.documentElement.dataset.theme;
      try {
        localStorage.removeItem("st_theme");
      } catch {
        return;
      }
    }
  }, [theme]);

  const [showStrategies, setShowStrategies] = useLocalStorageState<boolean>("st_sidebar_show_strategies", true);

  const strategiesQ = useQuery({
    queryKey: ["strategies"],
    queryFn: () => apiGet<StrategiesResponse>("/api/strategies"),
    refetchInterval: 15000,
  });

  const cfgQ = useQuery({
    queryKey: ["show_config"],
    queryFn: () => apiGet<ShowConfig>("/api/freqtrade/show_config"),
    refetchInterval: 15000,
  });

  const runsQ = useQuery({
    queryKey: ["history_runs_sidebar"],
    queryFn: () => apiGet<HistoryRunsResponse>("/api/history/runs?limit=40"),
    refetchInterval: 15000,
  });

  const activeStrategyName = (cfgQ.data?.strategy || "").trim();

  const runByHash = useMemo(() => {
    const m = new Map<string, HistoryRun>();
    const runs = runsQ.data?.runs;
    if (!Array.isArray(runs)) return m;
    for (const r of runs) {
      const h = typeof r?.strategy_hash === "string" ? r.strategy_hash : "";
      if (h && !m.has(h)) m.set(h, r);
    }
    return m;
  }, [runsQ.data]);

  const strategies = strategiesQ.data?.strategies || [];

  return (
    <aside className="w-72 shrink-0 border-r border-border-700 bg-bg-900 flex flex-col">
      <div className="px-4 py-3 border-b border-border-700">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-sm font-semibold tracking-wide text-fg-200 truncate">SmartTrade AI</div>
            <div className="mt-1">
              <ConnectionStatus />
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setTheme((t) => (t === "midnight" ? "" : "midnight"))}
              className="rounded-md border border-border-700 bg-panel-800 px-2 py-1 text-[11px] font-mono text-fg-200 hover:bg-panel-750"
              title="Toggle dark theme style"
            >
              {theme === "midnight" ? "Midnight" : "Slate"}
            </button>
            <button
              className="rounded-md border border-border-700 bg-panel-800 px-2 py-1 text-[11px] font-mono text-fg-200 hover:bg-panel-750"
              onClick={() => nav("/settings")}
              type="button"
            >
              Settings
            </button>
          </div>
        </div>
      </div>

      <div className="px-4 py-3 border-b border-border-700">
        <div className="text-xs text-fg-400">Active (bot config)</div>
        <div className="mt-1 font-mono text-sm text-fg-200 truncate">{activeStrategyName || "(unknown)"}</div>
        <div className="mt-1 text-xs text-fg-400 font-mono">TF: {cfgQ.data?.timeframe || "-"}</div>
      </div>

      <div className="px-2 py-2 border-b border-border-700">
        <NavLink
          to="/backtest"
          className={({ isActive }: { isActive: boolean }) =>
            [
              "block rounded-md px-3 py-2 text-sm font-medium",
              isActive ? "bg-panel-750 text-fg-100" : "text-fg-200 hover:bg-panel-800",
            ].join(" ")
          }
        >
          Backtest
        </NavLink>
        <NavLink
          to="/ai-analysis"
          className={({ isActive }: { isActive: boolean }) =>
            [
              "mt-1 block rounded-md px-3 py-2 text-sm font-medium",
              isActive ? "bg-panel-750 text-fg-100" : "text-fg-200 hover:bg-panel-800",
            ].join(" ")
          }
        >
          AI Refine
        </NavLink>
        <NavLink
          to="/strategy-editor"
          className={({ isActive }: { isActive: boolean }) =>
            [
              "mt-1 block rounded-md px-3 py-2 text-sm font-medium",
              isActive ? "bg-panel-750 text-fg-100" : "text-fg-200 hover:bg-panel-800",
            ].join(" ")
          }
        >
          AI Strategy
        </NavLink>

        <div className="mt-2 grid grid-cols-3 gap-1 px-1">
          <NavLink
            to="/overview"
            className={({ isActive }: { isActive: boolean }) =>
              [
                "rounded-md px-2 py-1 text-[11px] font-mono text-center",
                isActive ? "bg-panel-750 text-fg-100" : "text-fg-400 hover:bg-panel-800 hover:text-fg-200",
              ].join(" ")
            }
          >
            Overview
          </NavLink>
          <NavLink
            to="/trades"
            className={({ isActive }: { isActive: boolean }) =>
              [
                "rounded-md px-2 py-1 text-[11px] font-mono text-center",
                isActive ? "bg-panel-750 text-fg-100" : "text-fg-400 hover:bg-panel-800 hover:text-fg-200",
              ].join(" ")
            }
          >
            Trades
          </NavLink>
          <NavLink
            to="/history"
            className={({ isActive }: { isActive: boolean }) =>
              [
                "rounded-md px-2 py-1 text-[11px] font-mono text-center",
                isActive ? "bg-panel-750 text-fg-100" : "text-fg-400 hover:bg-panel-800 hover:text-fg-200",
              ].join(" ")
            }
          >
            History
          </NavLink>
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        <div className="px-4 pt-4 pb-2 flex items-center justify-between">
          <div className="text-xs text-fg-400">Strategies</div>
          <button
            type="button"
            onClick={() => setShowStrategies((s) => !s)}
            className="text-[11px] font-mono text-fg-400 hover:text-fg-200"
          >
            {showStrategies ? "Hide" : "Show"}
          </button>
        </div>

        {showStrategies ? (
          <>
            {!strategiesQ.isLoading && strategies.length === 0 ? (
              <div className="px-4 pb-4 text-xs text-fg-400">No strategy files found.</div>
            ) : null}

            <div className="px-2 pb-4 space-y-1">
              {strategies.map((s) => {
                const isActiveFile =
                  activeStrategyName && s.filename.toLowerCase() === `${activeStrategyName}.py`.toLowerCase();

                const run = s.strategy_hash ? runByHash.get(s.strategy_hash) : undefined;
                const profit = run?.backtest_summary?.metrics?.profit_total_pct;
                const dd = run?.backtest_summary?.metrics?.max_drawdown_pct;

                let statusColor = "bg-panel-800";
                if (typeof profit === "number") {
                  statusColor = profit >= 0 ? "bg-[#0b2a1a]" : "bg-[#2a0b0b]";
                }

                return (
                  <NavLink
                    key={s.filename}
                    to={`/strategy-editor?file=${encodeURIComponent(s.filename)}`}
                    className={() =>
                      [
                        "block rounded-md px-3 py-2 border",
                        isActiveFile ? "border-semantic-info" : "border-border-700",
                        statusColor,
                      ].join(" ")
                    }
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-sm font-mono truncate text-fg-100">{s.filename}</div>
                        <div className="text-[11px] text-fg-400 font-mono truncate">{s.strategy_hash || ""}</div>
                      </div>
                      <div className="text-right text-[11px] font-mono text-fg-400">
                        {typeof profit === "number" ? (
                          <div className={profit >= 0 ? "text-semantic-pos" : "text-semantic-neg"}>
                            {profit >= 0 ? "+" : ""}
                            {profit.toFixed(2)}%
                          </div>
                        ) : (
                          <div>-</div>
                        )}
                        {typeof dd === "number" ? <div>DD {dd.toFixed(2)}%</div> : <div />}
                      </div>
                    </div>
                  </NavLink>
                );
              })}
            </div>
          </>
        ) : null}
      </div>
    </aside>
  );
}

 export const AppSidebar = StrategyNavigator;
