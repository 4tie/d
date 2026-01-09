import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { apiGet, formatApiError } from "../lib/api";
import { Card, Metric } from "../components/primitives";

type ProfitResponse = Record<string, any>;
type ShowConfig = Record<string, any>;

export default function Dashboard() {
  const pingQ = useQuery({
    queryKey: ["ft_ping"],
    queryFn: () => apiGet<any>("/api/freqtrade/ping"),
    refetchInterval: 5000,
  });

  const profitQ = useQuery({
    queryKey: ["ft_profit"],
    queryFn: () => apiGet<ProfitResponse>("/api/freqtrade/profit"),
    refetchInterval: 15000,
    enabled: pingQ.isSuccess,
  });

  const cfgQ = useQuery({
    queryKey: ["ft_show_config"],
    queryFn: () => apiGet<ShowConfig>("/api/freqtrade/show_config"),
    refetchInterval: 30000,
    enabled: pingQ.isSuccess,
  });

  const dailyQ = useQuery({
    queryKey: ["ft_daily"],
    queryFn: () => apiGet<any>("/api/freqtrade/daily?days=180"),
    refetchInterval: 60000,
    enabled: pingQ.isSuccess,
  });

  const tradesQ = useQuery({
    queryKey: ["ft_trades"],
    queryFn: () => apiGet<any>("/api/freqtrade/trades"),
    refetchInterval: 30000,
    enabled: pingQ.isSuccess,
  });

  const recentTrades = useMemo(() => {
    const d = tradesQ.data;
    const arr = Array.isArray(d) ? d : Array.isArray((d as any)?.trades) ? (d as any).trades : [];
    if (!Array.isArray(arr)) return [];
    return arr.slice(0, 10);
  }, [tradesQ.data]);

  const profitPct = useMemo(() => {
    const p = profitQ.data;
    const v = (p as any)?.profit_all_percent ?? (p as any)?.profit_all_pct ?? (p as any)?.profit_total_pct;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }, [profitQ.data]);

  const ddPct = useMemo(() => {
    const p = profitQ.data;
    const v = (p as any)?.max_drawdown_abs ?? (p as any)?.max_drawdown_pct ?? (p as any)?.max_drawdown;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }, [profitQ.data]);

  const equitySeries = useMemo(() => {
    const d = dailyQ.data;
    const arr = Array.isArray(d) ? d : Array.isArray((d as any)?.data) ? (d as any).data : Array.isArray((d as any)?.daily) ? (d as any).daily : [];
    return arr
      .map((row: any) => {
        const date = String(row?.date || row?.timestamp || row?.day || "");
        const value = Number(row?.profit_pct ?? row?.profit_percent ?? row?.profit ?? row?.profit_total_pct ?? row?.pct);
        return {
          date,
          value: Number.isFinite(value) ? value : null,
        };
      })
      .filter((x: any) => x.value !== null);
  }, [dailyQ.data]);

  const errors = [pingQ.error, profitQ.error, cfgQ.error, dailyQ.error, tradesQ.error].filter(Boolean);

  return (
    <div className="space-y-4">
      {errors.length ? (
        <div className="text-xs font-mono text-semantic-neg">{errors.map((e) => formatApiError(e)).join(" | ")}</div>
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
          label="Net Profit %"
          value={profitPct === null ? "-" : `${profitPct >= 0 ? "+" : ""}${profitPct.toFixed(2)}%`}
          tone={profitPct === null ? "neutral" : profitPct >= 0 ? "pos" : "neg"}
        />
        <Metric
          label="Max Drawdown %"
          value={ddPct === null ? "-" : `${ddPct.toFixed(2)}%`}
          tone={ddPct === null ? "neutral" : "warn"}
        />
        <Metric label="Connection" value={pingQ.isSuccess ? "Online" : "Offline"} tone={pingQ.isSuccess ? "pos" : "neg"} />
      </div>

      <Card title="Equity Curve (Daily %)">
        {equitySeries.length ? (
          <div className="h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={equitySeries}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgb(var(--border-700))" />
                <XAxis dataKey="date" hide />
                <YAxis stroke="rgb(var(--fg-400))" fontSize={12} tickFormatter={(v) => `${v}%`} />
                <Tooltip
                  contentStyle={{ backgroundColor: "rgb(var(--bg-900))", border: "1px solid rgb(var(--border-700))" }}
                  itemStyle={{ color: "rgb(var(--fg-100))" }}
                />
                <Line type="monotone" dataKey="value" stroke="rgb(var(--semantic-info))" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="text-sm text-fg-400">No daily series available.</div>
        )}
      </Card>

      <Card title="Recent Trades">
        {recentTrades.length ? (
          <div className="space-y-2">
            {recentTrades.map((t: any, idx: number) => {
              const pair = String(t?.pair || "");
              const profit = Number(t?.profit_pct ?? t?.close_profit_pct ?? t?.profit_ratio);
              const profitNum = Number.isFinite(profit) ? profit : null;
              const exitReason = String(t?.exit_reason || t?.exit_tag || "");
              return (
                <div
                  key={String(t?.trade_id || t?.id || idx)}
                  className="flex items-center justify-between gap-3 rounded-md border border-border-700 bg-panel-800 px-3 py-2"
                >
                  <div className="min-w-0">
                    <div className="text-sm font-mono text-fg-100 truncate">{pair}</div>
                    <div className="text-[11px] text-fg-400 font-mono truncate">{exitReason}</div>
                  </div>
                  <div className={profitNum !== null && profitNum >= 0 ? "text-semantic-pos font-mono text-xs" : "text-semantic-neg font-mono text-xs"}>
                    {profitNum === null ? "-" : `${profitNum >= 0 ? "+" : ""}${profitNum.toFixed(3)}`}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="text-sm text-fg-400">No trades available.</div>
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
