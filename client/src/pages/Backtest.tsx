import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost, formatApiError } from "../lib/api";
import { useLocalStorageState } from "../lib/storage";
import { Button, Card, Input, Metric, Textarea, TokenInput } from "../components/primitives";
import { useToast } from "../components/toast";
import { useSelectedStrategy } from "../lib/strategy-context";
import { InlineLoading } from "../components/loading";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

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

type OptimizeRunResponse = {
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

type BacktestDetailResponse = {
  run: Record<string, any>;
  ai_payload: Record<string, any>;
  backtest_result?: Record<string, any>;
};

export default function Backtest() {
  const nav = useNavigate();
  const toast = useToast();
  const [timerange, setTimerange] = useLocalStorageState<string>("st_cfg_timerange", "");
  const [fromDate, setFromDate] = useLocalStorageState<string>("st_cfg_from_date", "");
  const [toDate, setToDate] = useLocalStorageState<string>("st_cfg_to_date", "");
  const [timeframe, setTimeframe] = useLocalStorageState<string>("st_cfg_timeframe", "");
  const [pairTokens, setPairTokens] = useLocalStorageState<string[]>("st_cfg_pair_tokens", []);
  const [pairDraft, setPairDraft] = useLocalStorageState<string>("st_cfg_pair_draft", "");
  const [fee, setFee] = useLocalStorageState<string>("st_cfg_fee", "");
  const [dryRunWallet, setDryRunWallet] = useLocalStorageState<string>("st_cfg_wallet", "");
  const [maxOpenTrades, setMaxOpenTrades] = useLocalStorageState<string>("st_cfg_max_open_trades", "");
  const [minTradesPerDay, setMinTradesPerDay] = useLocalStorageState<string>("st_cfg_min_trades_per_day", "");
  const [requireMinTradesPerDay, setRequireMinTradesPerDay] = useLocalStorageState<boolean>("st_cfg_require_min_trades_per_day", false);
  const [maxFeeDominatedFraction, setMaxFeeDominatedFraction] = useLocalStorageState<string>("st_cfg_max_fee_dominated_fraction", "");
  const [minEdgeToFeeRatio, setMinEdgeToFeeRatio] = useLocalStorageState<string>("st_cfg_min_edge_to_fee_ratio", "");
  const [jobId, setJobId] = useState<string>("");
  const [err, setErr] = useState<string>("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [detail, setDetail] = useState<BacktestDetailResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

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
  const { strategyCode: selectedStrategyCode, selectedFilename, selectStrategy } = useSelectedStrategy();

  useEffect(() => {
    if (!strategyCode && initialCode) setStrategyCode(initialCode);
  }, [initialCode, strategyCode]);

  // Auto-populate from selected strategy
  useEffect(() => {
    if (selectedStrategyCode && selectedFilename) {
      setStrategyCode(selectedStrategyCode);
    }
  }, [selectedStrategyCode, selectedFilename]);

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
    setIsSubmitting(true);
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
      toast.success("Backtest job started successfully!");
    } catch (e) {
      const errorMsg = formatApiError(e);
      setErr(errorMsg);
      toast.error(`Failed to start backtest: ${errorMsg}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function optimize() {
    setErr("");
    setIsSubmitting(true);
    try {
      const selected = String(selectedFilename || "").trim();
      if (!selected) throw new Error("Select a strategy file in the sidebar first");

      const committedPairs = buildPairsValue();
      if (committedPairs !== pairTokens.join(",")) {
        const next = splitPairs(committedPairs);
        setPairTokens(next);
        setPairDraft("");
      }

      const feeVal = fee.trim() ? Number(fee) : undefined;
      const walletVal = dryRunWallet.trim() ? Number(dryRunWallet) : undefined;
      const motVal = maxOpenTrades.trim() ? Number(maxOpenTrades) : undefined;

      const minTpdVal = minTradesPerDay.trim() ? Number(minTradesPerDay) : undefined;
      const maxFeeDomVal = maxFeeDominatedFraction.trim() ? Number(maxFeeDominatedFraction) : undefined;
      const minEtfVal = minEdgeToFeeRatio.trim() ? Number(minEdgeToFeeRatio) : undefined;

      const res = await apiPost<OptimizeRunResponse>("/api/ai/strategy/optimize", {
        strategy_code: strategyCode,
        selected_filename: selected,
        timerange: timerange.trim() || undefined,
        timeframe: timeframe.trim() || undefined,
        pairs: committedPairs.trim() || undefined,
        fee: Number.isFinite(feeVal as number) ? feeVal : undefined,
        dry_run_wallet: Number.isFinite(walletVal as number) ? walletVal : undefined,
        max_open_trades: Number.isFinite(motVal as number) ? Math.trunc(motVal as number) : undefined,
        min_trades_per_day: Number.isFinite(minTpdVal as number) ? minTpdVal : undefined,
        require_min_trades_per_day: Boolean(requireMinTradesPerDay),
        max_fee_dominated_fraction: Number.isFinite(maxFeeDomVal as number) ? maxFeeDomVal : undefined,
        min_edge_to_fee_ratio: Number.isFinite(minEtfVal as number) ? minEtfVal : undefined,
      });
      setJobId(res.job_id);
      toast.info("AI optimize job started");
    } catch (e) {
      const errorMsg = formatApiError(e);
      setErr(errorMsg);
      toast.error(`Failed to start AI optimize: ${errorMsg}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function downloadData() {
    setErr("");
    setIsSubmitting(true);
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
      toast.info("Data download job started");
    } catch (e) {
      const errorMsg = formatApiError(e);
      setErr(errorMsg);
      toast.error(`Failed to start download: ${errorMsg}`);
    } finally {
      setIsSubmitting(false);
    }
  }

  const job = jobQ.data;
  const runId = Number(job?.result?.performance_run_id);
  const hasRunId = Number.isFinite(runId) && runId > 0;

  const btSummary = job?.result?.backtest_summary;
  const btMetrics = btSummary?.metrics || {};
  const tradeForensics = job?.result?.trade_forensics;
  const profitDist = tradeForensics?.profit_pct_distribution;

  const optSavedFilename = typeof job?.result?.saved_filename === "string" ? String(job?.result?.saved_filename) : "";
  const optBaselineMetrics = job?.result?.baseline?.backtest_summary?.metrics || {};
  const optBestMetrics = job?.result?.best?.backtest_summary?.metrics || {};

  const distData = useMemo(() => {
    const counts = profitDist?.counts;
    if (!counts || typeof counts !== "object") return [];
    return Object.keys(counts).map((k) => ({
      bin: String(k),
      n: Number((counts as any)[k] ?? 0) || 0,
    }));
  }, [profitDist]);

  async function loadDetail(includeResult: boolean) {
    if (!hasRunId) return;
    setErr("");
    setDetailLoading(true);
    try {
      const res = await apiGet<BacktestDetailResponse>(`/api/backtest/runs/${runId}/detail?include_result=${includeResult ? "true" : "false"}`);
      setDetail(res);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setDetailLoading(false);
    }
  }

  async function copyJson(obj: any, label: string) {
    try {
      await navigator.clipboard.writeText(JSON.stringify(obj ?? {}, null, 2));
      toast.success(`${label} copied`);
    } catch (e) {
      toast.error(`Failed to copy: ${String(e)}`);
    }
  }

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

            <div className="pt-2 border-t border-border-700" />

            <div className="text-xs text-fg-400 font-mono">Optimize goals (optional)</div>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <div className="text-xs text-fg-400">Min trades / day</div>
                <Input value={minTradesPerDay} onChange={setMinTradesPerDay} placeholder="e.g. 10" type="number" />
              </div>
              <div>
                <div className="text-xs text-fg-400">Max fee-dominated fraction (0..1)</div>
                <Input value={maxFeeDominatedFraction} onChange={setMaxFeeDominatedFraction} placeholder="e.g. 0.6" type="number" />
              </div>
              <div>
                <div className="text-xs text-fg-400">Min edge/fee ratio</div>
                <Input value={minEdgeToFeeRatio} onChange={setMinEdgeToFeeRatio} placeholder="e.g. 2" type="number" />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 text-xs text-fg-200 select-none">
                  <input
                    type="checkbox"
                    checked={Boolean(requireMinTradesPerDay)}
                    onChange={(e) => setRequireMinTradesPerDay(e.target.checked)}
                    className="h-4 w-4 rounded border-border-700 bg-bg-900 text-semantic-info focus:ring-semantic-info/30"
                  />
                  Strict min trades/day gate
                </label>
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="primary" onClick={run} disabled={!strategyCode.trim() || isSubmitting} loading={isSubmitting}>
                Run Backtest
              </Button>
              <Button
                variant="outline"
                onClick={optimize}
                disabled={!strategyCode.trim() || !String(selectedFilename || "").trim() || isSubmitting}
                loading={isSubmitting}
              >
                AI Optimize
              </Button>
              <Button variant="outline" onClick={downloadData} disabled={isSubmitting} loading={isSubmitting}>
                Download Data
              </Button>
            </div>
            {(suggestionsQ.data?.warnings || []).length ? (
              <div className="text-xs text-fg-400 font-mono">{(suggestionsQ.data?.warnings || []).join(" | ")}</div>
            ) : null}
            {err ? <div className="text-xs text-semantic-neg font-mono">{err}</div> : null}
          </div>
        </Card>

        <Card title="Job Status">
          {!jobId ? (
            <div className="text-sm text-fg-400">No job running.</div>
          ) : jobQ.isLoading ? (
            <InlineLoading message="Loading job status…" />
          ) : (
            <div className="space-y-2 animate-fade-in">
              <div className="text-xs text-fg-400 font-mono">{jobId}</div>
              <div className="text-sm flex items-center gap-2">
                <span>Status:</span>
                <span className={`font-mono font-medium ${job?.status === "succeeded" ? "text-semantic-pos" :
                  job?.status === "failed" ? "text-semantic-neg" :
                    job?.status === "running" ? "text-semantic-info" :
                      "text-fg-200"
                  }`}>
                  {job?.status}
                </span>
                {(job?.status === "running" || job?.status === "queued") && (
                  <div className="w-2 h-2 rounded-full bg-semantic-info animate-pulse-glow" />
                )}
              </div>
              {job?.error ? <div className="text-xs text-semantic-neg font-mono animate-slide-down">{job.error}</div> : null}
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
            job?.kind === "backtest" ? (
              <div className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                <Metric
                  label="Profit %"
                  value={typeof btMetrics?.profit_total_pct === "number" ? `${btMetrics.profit_total_pct >= 0 ? "+" : ""}${Number(btMetrics.profit_total_pct).toFixed(2)}%` : "-"}
                  tone={typeof btMetrics?.profit_total_pct === "number" ? (Number(btMetrics.profit_total_pct) >= 0 ? "pos" : "neg") : "neutral"}
                />
                <Metric
                  label="Max DD %"
                  value={typeof btMetrics?.max_drawdown_pct === "number" ? `${Number(btMetrics.max_drawdown_pct).toFixed(2)}%` : "-"}
                  tone={typeof btMetrics?.max_drawdown_pct === "number" ? "warn" : "neutral"}
                />
                <Metric
                  label="Trades"
                  value={typeof btMetrics?.total_trades === "number" ? String(btMetrics.total_trades) : typeof btMetrics?.trades === "number" ? String(btMetrics.trades) : "-"}
                  tone="neutral"
                />
              </div>

              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => loadDetail(false)} disabled={!hasRunId || detailLoading}>
                  Load AI payload
                </Button>
                <Button variant="outline" onClick={() => loadDetail(true)} disabled={!hasRunId || detailLoading}>
                  Load full detail JSON
                </Button>
                <Button variant="outline" onClick={() => copyJson(job.result, "Compact result")}>
                  Copy compact
                </Button>
                <Button variant="outline" onClick={() => copyJson(detail?.ai_payload, "AI payload")} disabled={!detail?.ai_payload}>
                  Copy AI payload
                </Button>
                <Button variant="outline" onClick={() => copyJson(detail?.backtest_result, "Full detail JSON")} disabled={!detail?.backtest_result}>
                  Copy full detail
                </Button>
              </div>

              {detailLoading ? <InlineLoading message="Loading detail…" /> : null}

              {distData.length ? (
                <div>
                  <div className="text-xs text-fg-400 font-mono">Profit distribution (trade % bins)</div>
                  <div className="mt-2 h-[260px]">
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={distData}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="rgb(var(--border-700))" />
                        <XAxis dataKey="bin" tick={{ fill: "rgb(var(--fg-400))", fontSize: 10 }} interval={0} angle={-30} height={70} />
                        <YAxis tick={{ fill: "rgb(var(--fg-400))", fontSize: 12 }} allowDecimals={false} />
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "rgb(var(--bg-900))",
                            border: "1px solid rgb(var(--border-700))",
                            borderRadius: "8px",
                          }}
                          itemStyle={{ color: "rgb(var(--fg-100))" }}
                        />
                        <Bar dataKey="n" fill="rgb(var(--semantic-info))" />
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              ) : null}

              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <div className="text-xs text-fg-400 font-mono">Summary</div>
                  <pre className="mt-2 text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[260px]">
                    {JSON.stringify(btSummary || {}, null, 2)}
                  </pre>
                </div>
                <div>
                  <div className="text-xs text-fg-400 font-mono">Forensics</div>
                  <pre className="mt-2 text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[260px]">
                    {JSON.stringify(tradeForensics || {}, null, 2)}
                  </pre>
                </div>
              </div>

              {detail?.ai_payload ? (
                <div>
                  <div className="text-xs text-fg-400 font-mono">AI payload (compact)</div>
                  <pre className="mt-2 text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[260px]">
                    {JSON.stringify(detail.ai_payload, null, 2)}
                  </pre>
                </div>
              ) : null}

              {detail?.backtest_result ? (
                <div>
                  <div className="text-xs text-fg-400 font-mono">Full backtest JSON (detailed)</div>
                  <pre className="mt-2 text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[420px]">
                    {JSON.stringify(detail.backtest_result, null, 2)}
                  </pre>
                </div>
              ) : null}

              <div>
                <div className="text-xs text-fg-400 font-mono">Raw output</div>
                <pre className="mt-2 text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[220px]">
                  {String(job.result?.stdout_tail || "")}
                </pre>
              </div>
              </div>
            ) : job?.kind === "ai_optimize" ? (
              <div className="space-y-4">
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                  <Metric
                    label="Baseline Profit %"
                    value={typeof optBaselineMetrics?.profit_total_pct === "number" ? `${Number(optBaselineMetrics.profit_total_pct).toFixed(2)}%` : "-"}
                    tone={typeof optBaselineMetrics?.profit_total_pct === "number" ? (Number(optBaselineMetrics.profit_total_pct) >= 0 ? "pos" : "neg") : "neutral"}
                  />
                  <Metric
                    label="Best Profit %"
                    value={typeof optBestMetrics?.profit_total_pct === "number" ? `${Number(optBestMetrics.profit_total_pct).toFixed(2)}%` : "-"}
                    tone={typeof optBestMetrics?.profit_total_pct === "number" ? (Number(optBestMetrics.profit_total_pct) >= 0 ? "pos" : "neg") : "neutral"}
                  />
                  <Metric
                    label="Best Max DD %"
                    value={typeof optBestMetrics?.max_drawdown_pct === "number" ? `${Number(optBestMetrics.max_drawdown_pct).toFixed(2)}%` : "-"}
                    tone={typeof optBestMetrics?.max_drawdown_pct === "number" ? "warn" : "neutral"}
                  />
                </div>

                <div className="space-y-2">
                  <div className="text-xs text-fg-400 font-mono">Saved as</div>
                  <div className="font-mono text-sm text-fg-200">{optSavedFilename || "-"}</div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      variant="outline"
                      onClick={() => {
                        if (!optSavedFilename.trim()) return;
                        nav(`/strategy-editor?file=${encodeURIComponent(optSavedFilename)}`);
                      }}
                      disabled={!optSavedFilename.trim()}
                    >
                      Open in editor
                    </Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        if (!optSavedFilename.trim()) return;
                        selectStrategy(optSavedFilename);
                      }}
                      disabled={!optSavedFilename.trim()}
                    >
                      Promote (select)
                    </Button>
                  </div>
                </div>

                <div>
                  <div className="text-xs text-fg-400 font-mono">Optimize result (compact)</div>
                  <pre className="mt-2 text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[420px]">
                    {JSON.stringify(job.result || {}, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[420px]">
                {JSON.stringify(job.result || {}, null, 2)}
              </pre>
            )
          ) : job?.status === "failed" ? (
            <div className="space-y-2">
              <div className="text-sm text-fg-400">Backtest failed. See error above and logs in Job Status.</div>
              <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-[420px]">
                {JSON.stringify(job, null, 2)}
              </pre>
            </div>
          ) : (
            <div className="text-sm text-fg-400">Run a backtest to see results here.</div>
          )}
        </Card>
      </div>
    </div>
  );
}
