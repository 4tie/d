import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost, formatApiError } from "../lib/api";
import { Button, Card } from "../components/primitives";

type RunRow = Record<string, any>;

type RunsResponse = {
  runs: RunRow[];
};

export default function History() {
  const [err, setErr] = useState("");

  const q = useQuery({
    queryKey: ["history_runs"],
    queryFn: () => apiGet<RunsResponse>("/api/history/runs?limit=80"),
    refetchInterval: 15000,
  });

  const runs = q.data?.runs || [];
  const [selected, setSelected] = useState<RunRow | null>(null);

  const rows = useMemo(() => {
    return Array.isArray(runs) ? runs : [];
  }, [runs]);

  async function restore(runId: number) {
    setErr("");
    try {
      await apiPost("/api/history/restore", { run_id: runId });
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-2 space-y-4">
        <Card title="Timeline">
          {q.isLoading ? (
            <div className="text-sm text-fg-400">Loading…</div>
          ) : (
            <div className="space-y-2">
              {rows.map((r, idx) => {
                const id = Number((r as any).id);
                const ts = Number((r as any).ts);
                const profit = (r as any).backtest_summary?.metrics?.profit_total_pct;
                const dd = (r as any).backtest_summary?.metrics?.max_drawdown_pct;
                return (
                  <button
                    key={String(id || idx)}
                    type="button"
                    onClick={() => setSelected(r)}
                    className="w-full text-left rounded-md border border-border-700 bg-panel-800 hover:bg-panel-750 px-3 py-2"
                  >
                    <div className="flex items-center justify-between">
                      <div className="text-sm font-mono text-fg-100">Run #{String(id || "-")}</div>
                      <div className="text-xs font-mono text-fg-400">{ts ? new Date(ts * 1000).toLocaleString() : ""}</div>
                    </div>
                    <div className="mt-1 text-xs font-mono text-fg-400">{String((r as any).run_type || "")}</div>
                    <div className="mt-1 text-xs font-mono">
                      <span className={typeof profit === "number" && profit >= 0 ? "text-semantic-pos" : "text-semantic-neg"}>
                        {typeof profit === "number" ? `${profit >= 0 ? "+" : ""}${profit.toFixed(2)}%` : "-"}
                      </span>
                      <span className="text-fg-400">  DD </span>
                      <span className="text-fg-400">{typeof dd === "number" ? `${dd.toFixed(2)}%` : "-"}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </Card>
      </div>

      <div className="lg:col-span-1 space-y-4">
        <Card title="Run Inspector">
          {!selected ? (
            <div className="text-sm text-fg-400">Select a run.</div>
          ) : (
            <div className="space-y-3">
              <div className="text-xs text-fg-400 font-mono">id: {String((selected as any).id)}</div>
              <div className="flex gap-2">
                <Button
                  variant="danger"
                  onClick={() => restore(Number((selected as any).id))}
                  disabled={!Number.isFinite(Number((selected as any).id))}
                >
                  Restore
                </Button>
              </div>
              {err ? <div className="text-xs text-semantic-neg font-mono">{err}</div> : null}
              <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[680px]">
                {JSON.stringify(selected, null, 2)}
              </pre>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
