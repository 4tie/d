import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost, formatApiError } from "../lib/api";
import { useLocalStorageState } from "../lib/storage";
import { Button, Card, Input, Textarea, TokenInput } from "../components/primitives";

type StrategyCurrent = {
  filename: string;
  path: string;
  missing?: boolean;
  content?: string;
  strategy_hash?: string | null;
};

type JobView = {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  created_ts: number;
  updated_ts: number;
  logs: string[];
  result?: any;
  error?: string | null;
};

type BacktestRunResponse = {
  job_id: string;
};

type BacktestSuggestions = {
  timeranges: string[];
  timeframes: string[];
  pairs: string[];
  warnings?: string[];
  defaults?: {
    fee?: number | null;
    dry_run_wallet?: number | null;
    max_open_trades?: number | null;
  };
};

export default function Backtest() {
  const [timerange, setTimerange] = useLocalStorageState<string>("st_cfg_timerange", "");
  const [fromDate, setFromDate] = useLocalStorageState<string>("st_cfg_from_date", "");
  const [toDate, setToDate] = useLocalStorageState<string>("st_cfg_to_date", "");
  const [timeframe, setTimeframe] = useLocalStorageState<string>("st_cfg_timeframe", "");
  const [pairTokens, setPairTokens] = useLocalStorageState<string[]>("st_cfg_pair_tokens", []);
  const [pairDraft, setPairDraft] = useLocalStorageState<string>("st_cfg_pair_draft", "");
  const [fee, setFee] = useLocalStorageState<string>("st_cfg_fee", "");
  const [dryRunWallet, setDryRunWallet] = useLocalStorageState<string>("st_cfg_wallet", "");
  const [maxOpenTrades, setMaxOpenTrades] = useLocalStorageState<string>("st_cfg_max_open_trades", "");
  const [jobId, setJobId] = useState<string>("");
  const [err, setErr] = useState<string>("");

  function splitPairs(s: string): string[] {
    return String(s || "")
      .split(/[,;\n]+/g)
      .map((x) => x.trim())
      .filter(Boolean);
  }

  function buildPairsValue(): string {
    const next = [...pairTokens];
    for (const p of splitPairs(pairDraft)) {
      if (!next.includes(p)) next.push(p);
    }
    return next.join(",");
  }

  const suggestionsQ = useQuery({
    queryKey: ["backtest_suggestions"],
    queryFn: () => apiGet<BacktestSuggestions>("/api/backtest/suggestions"),
    refetchInterval: 60000,
    retry: 1,
  });

  const timeframeSuggestions = useMemo(() => {
    const tfs = suggestionsQ.data?.timeframes || [];
    return tfs.filter((t) => /^\d+[mhdw]$/.test(String(t || "")));
  }, [suggestionsQ.data]);

  useEffect(() => {
    const d = suggestionsQ.data?.defaults;
    if (!d) return;
    if (!fee.trim() && typeof d.fee === "number" && Number.isFinite(d.fee)) setFee(String(d.fee));
    if (!dryRunWallet.trim() && typeof d.dry_run_wallet === "number" && Number.isFinite(d.dry_run_wallet)) {
      setDryRunWallet(String(d.dry_run_wallet));
    }
    if (!maxOpenTrades.trim() && typeof d.max_open_trades === "number" && Number.isFinite(d.max_open_trades)) {
      setMaxOpenTrades(String(d.max_open_trades));
    }
  }, [suggestionsQ.data, fee, dryRunWallet, maxOpenTrades]);

  function formatLocalDate(date: Date): string {
    const y = date.getFullYear();
    const m = String(date.getMonth() + 1).padStart(2, "0");
    const d = String(date.getDate()).padStart(2, "0");
    return `${y}-${m}-${d}`;
  }

  function toTimerange(fromIso: string, toIso: string): string {
    const a = String(fromIso || "").trim();
    const b = String(toIso || "").trim();
    if (!/^\d{4}-\d{2}-\d{2}$/.test(a) || !/^\d{4}-\d{2}-\d{2}$/.test(b)) return "";
    const from = a.replaceAll("-", "");
    const to = b.replaceAll("-", "");
    if (from > to) return "";
    return `${from}-${to}`;
  }

  function applyPreset(days: number) {
    const now = new Date();
    const end = formatLocalDate(now);
    const startDate = new Date(now);
    startDate.setDate(startDate.getDate() - Math.max(1, days));
    const start = formatLocalDate(startDate);
    setFromDate(start);
    setToDate(end);
    const tr = toTimerange(start, end);
    if (tr) setTimerange(tr);
  }

  const currentQ = useQuery({
    queryKey: ["strategy_current"],
    queryFn: () => apiGet<StrategyCurrent>("/api/strategy/current"),
    refetchInterval: 10000,
  });

  const initialCode = useMemo(() => {
    const c = currentQ.data?.content;
    return typeof c === "string" ? c : "";
  }, [currentQ.data]);

  const [strategyCode, setStrategyCode] = useLocalStorageState<string>("st_cfg_strategy_code", "");

  useEffect(() => {
    if (!strategyCode && initialCode) setStrategyCode(initialCode);
  }, [initialCode, strategyCode]);

  const jobQ = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => apiGet<JobView>(`/api/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (q: any) => {
      const st = (q.state.data as any)?.status;
      if (st === "running" || st === "queued") return 1000;
      return false;
    },
  });

  async function run() {
    setErr("");
    try {
      const committedPairs = buildPairsValue();
      if (committedPairs !== pairTokens.join(",")) {
        const next = splitPairs(committedPairs);
        setPairTokens(next);
        setPairDraft("");
      }

      const feeVal = fee.trim() ? Number(fee) : undefined;
      const walletVal = dryRunWallet.trim() ? Number(dryRunWallet) : undefined;
      const motVal = maxOpenTrades.trim() ? Number(maxOpenTrades) : undefined;
      const res = await apiPost<BacktestRunResponse>("/api/backtest/run", {
        strategy_code: strategyCode,
        timerange: timerange.trim() || undefined,
        timeframe: timeframe.trim() || undefined,
        pairs: committedPairs.trim() || undefined,
        fee: Number.isFinite(feeVal as number) ? feeVal : undefined,
        dry_run_wallet: Number.isFinite(walletVal as number) ? walletVal : undefined,
        max_open_trades: Number.isFinite(motVal as number) ? Math.trunc(motVal as number) : undefined,
      });
      setJobId(res.job_id);
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  async function downloadData() {
    setErr("");
    try {
      const committedPairs = buildPairsValue();
      if (committedPairs !== pairTokens.join(",")) {
        const next = splitPairs(committedPairs);
        setPairTokens(next);
        setPairDraft("");
      }

      const res = await apiPost<{ job_id: string }>("/api/data/download", {
        timerange: timerange.trim() || undefined,
        timeframe: timeframe.trim() || undefined,
        pairs: committedPairs.trim() || undefined,
      });
      setJobId(res.job_id);
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  const job = jobQ.data;

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-1 space-y-4">
        <Card title="Configuration">
          <div className="space-y-3">
            <div>
              <div className="text-xs text-fg-400">Timerange</div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <Input
                  value={fromDate}
                  onChange={(v) => {
                    setFromDate(v);
                    const tr = toTimerange(v, toDate);
                    if (tr) setTimerange(tr);
                  }}
                  type="date"
                />
                <Input
                  value={toDate}
                  onChange={(v) => {
                    setToDate(v);
                    const tr = toTimerange(fromDate, v);
                    if (tr) setTimerange(tr);
                  }}
                  type="date"
                />
              </div>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => applyPreset(7)}>
                  7d
                </Button>
                <Button variant="outline" onClick={() => applyPreset(15)}>
                  15d
                </Button>
                <Button variant="outline" onClick={() => applyPreset(30)}>
                  30d
                </Button>
                <Button variant="outline" onClick={() => applyPreset(60)}>
                  60d
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setFromDate("");
                    setToDate("");
                    setTimerange("");
                  }}
                >
                  Clear
                </Button>
              </div>
              <div className="mt-2">
                <Input
                  value={timerange}
                  onChange={(v) => {
                    setTimerange(v);
                    setFromDate("");
                    setToDate("");
                  }}
                  placeholder="Timerange"
                  list="timerange-list"
                />
                <datalist id="timerange-list">
                  {(suggestionsQ.data?.timeranges || []).map((t: string) => (
                    <option key={t} value={t} />
                  ))}
                </datalist>
              </div>
            </div>
            <div>
              <div className="text-xs text-fg-400">Timeframe</div>
              <Input value={timeframe} onChange={setTimeframe} placeholder="Select timeframe" list="timeframe-list" />
              <datalist id="timeframe-list">
                {timeframeSuggestions.map((t: string) => (
                  <option key={t} value={t} />
                ))}
              </datalist>
            </div>
            <div>
              <div className="text-xs text-fg-400">Pairs</div>
              <TokenInput
                tokens={pairTokens}
                onTokensChange={setPairTokens}
                draft={pairDraft}
                onDraftChange={setPairDraft}
                placeholder="Add pair"
                suggestions={suggestionsQ.data?.pairs || []}
              />
            </div>
            <div>
              <div className="text-xs text-fg-400">Fee (ratio)</div>
              <Input value={fee} onChange={setFee} placeholder="Optional fee ratio" type="number" />
            </div>
            <div>
              <div className="text-xs text-fg-400">Starting balance</div>
              <Input value={dryRunWallet} onChange={setDryRunWallet} placeholder="Optional starting balance" type="number" />
            </div>
            <div>
              <div className="text-xs text-fg-400">Max open trades</div>
              <Input value={maxOpenTrades} onChange={setMaxOpenTrades} placeholder="Optional max open trades" type="number" />
            </div>
            <div className="flex gap-2">
              <Button variant="primary" onClick={run} disabled={!strategyCode.trim()}>
                Run Backtest
              </Button>
              <Button variant="outline" onClick={downloadData}>
                Download Data
              </Button>
            </div>
            {(suggestionsQ.data?.warnings || []).length ? (
              <div className="text-xs text-fg-400 font-mono">{(suggestionsQ.data?.warnings || []).join(" | ")}</div>
            ) : null}
            {err ? <div className="text-xs text-semantic-neg font-mono">{err}</div> : null}
          </div>
        </Card>

        <Card title="Job">
          {!jobId ? (
            <div className="text-sm text-fg-400">No job running.</div>
          ) : jobQ.isLoading ? (
            <div className="text-sm text-fg-400">Loading job…</div>
          ) : (
            <div className="space-y-2">
              <div className="text-xs text-fg-400 font-mono">{jobId}</div>
              <div className="text-sm">
                Status: <span className="font-mono text-fg-200">{job?.status}</span>
              </div>
              {job?.error ? <div className="text-xs text-semantic-neg font-mono">{job.error}</div> : null}
              <div className="text-xs text-fg-400">Logs</div>
              <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-2 overflow-auto max-h-48">
                {(job?.logs || []).join("\n")}
              </pre>
            </div>
          )}
        </Card>
      </div>

      <div className="lg:col-span-2 space-y-4">
        <Card title="Strategy Code">
          <Textarea value={strategyCode} onChange={setStrategyCode} rows={18} />
        </Card>

        <Card title="Result">
          {job?.status === "succeeded" && job?.result ? (
            <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[420px]">
              {JSON.stringify(job.result, null, 2)}
            </pre>
          ) : (
            <div className="text-sm text-fg-400">Run a backtest to see results here.</div>
          )}
        </Card>
      </div>
    </div>
  );
}
