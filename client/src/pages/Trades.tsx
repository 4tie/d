import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";
import { useLocalStorageState } from "../lib/storage";
import { Card, Input } from "../components/primitives";

type Trade = Record<string, any>;

type RunRow = Record<string, any>;

type RunsResponse = {
  runs: RunRow[];
};

export default function Trades() {
  const [pairFilter, setPairFilter] = useLocalStorageState<string>("st_trades_pair_filter", "");

  const q = useQuery({
    queryKey: ["history_runs_trades"],
    queryFn: () => apiGet<RunsResponse>("/api/history/runs?limit=40"),
    refetchInterval: 15000,
  });

  const trades: Trade[] = useMemo(() => {
    const runs = Array.isArray(q.data?.runs) ? q.data?.runs : [];
    const latest = runs.length ? runs[0] : null;
    if (!latest) return [];
    const best = (latest as any)?.backtest_summary?.best_trades;
    const worst = (latest as any)?.backtest_summary?.worst_trades;
    const out: Trade[] = [];
    if (Array.isArray(worst)) out.push(...(worst as Trade[]));
    if (Array.isArray(best)) out.push(...(best as Trade[]));
    return out;
  }, [q.data]);

  const filtered = useMemo(() => {
    const pf = pairFilter.trim().toLowerCase();
    if (!pf) return trades;
    return trades.filter((t) => String(t.pair || "").toLowerCase().includes(pf));
  }, [trades, pairFilter]);

  const [selected, setSelected] = useState<Trade | null>(null);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 space-y-4">
        <Card title="Filters">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <div>
              <div className="text-xs text-fg-400">Pair</div>
              <Input value={pairFilter} onChange={setPairFilter} placeholder="Filter by pair" />
            </div>
          </div>
        </Card>

        <Card title={`Backtest Trade Samples (${filtered.length})`}>
          {q.isLoading ? (
            <div className="text-sm text-fg-400">Loading…</div>
          ) : !trades.length ? (
            <div className="text-sm text-fg-400">No backtest trade samples yet. Run a backtest to populate History.</div>
          ) : (
            <div className="overflow-auto max-h-[620px] border border-border-700 rounded-md">
              <table className="w-full text-xs font-mono">
                <thead className="sticky top-0 bg-bg-900 border-b border-border-700">
                  <tr>
                    <th className="text-left p-2">Pair</th>
                    <th className="text-left p-2">Open</th>
                    <th className="text-left p-2">Close</th>
                    <th className="text-right p-2">Profit %</th>
                    <th className="text-left p-2">Exit</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((t, i) => {
                    const profit = Number((t as any).profit_pct ?? (t as any).close_profit_pct ?? (t as any).profit_ratio);
                    const profitNum = Number.isFinite(profit) ? profit : null;
                    return (
                      <tr
                        key={String((t as any).trade_id || (t as any).id || i)}
                        className="border-b border-border-700 hover:bg-panel-750 cursor-pointer"
                        onClick={() => setSelected(t)}
                      >
                        <td className="p-2">{String((t as any).pair || "")}</td>
                        <td className="p-2">{String((t as any).open_date || (t as any).open_time || "")}</td>
                        <td className="p-2">{String((t as any).close_date || (t as any).close_time || "")}</td>
                        <td className={`p-2 text-right ${profitNum !== null && profitNum >= 0 ? "text-semantic-pos" : "text-semantic-neg"}`}>
                          {profitNum === null ? "-" : profitNum.toFixed(3)}
                        </td>
                        <td className="p-2">{String((t as any).exit_reason || (t as any).exit_tag || "")}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>

      <div className="lg:col-span-1 space-y-4">
        <Card title="Trade Inspector">
          {!selected ? (
            <div className="text-sm text-fg-400">Select a trade to inspect.</div>
          ) : (
            <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[760px]">
              {JSON.stringify(selected, null, 2)}
            </pre>
          )}
        </Card>
      </div>
    </div>
  );
}
