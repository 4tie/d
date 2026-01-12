import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { ApiError, apiGet, apiPost, formatApiError } from "../lib/api";
import { useLocalStorageState } from "../lib/storage";
import { Button, Card, Input, Textarea, TokenInput } from "../components/primitives";
import { useSelectedStrategy } from "../lib/strategy-context";

type StrategyFileView = {
  filename: string;
  path: string;
  missing?: boolean;
  content?: string;
  strategy_hash?: string | null;
};

type ValidateResponse = {
  ok: boolean;
  error: string;
};

type RepairResponse = {
  strategy_code: string;
  repaired: boolean;
  original_error: string;
  validation: ValidateResponse;
};

type DiffOp = {
  kind: "equal" | "insert" | "delete";
  line: string;
};

type JobView = {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  logs: string[];
  result?: any;
  error?: string | null;
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

export default function AIStrategy() {
  const [params] = useSearchParams();
  const selectedFile = (params.get("file") || "AIStrategy.py").trim();
  const fileKey = encodeURIComponent(selectedFile);

  const fileQ = useQuery({
    queryKey: ["strategy_file", selectedFile],
    queryFn: async () => {
      try {
        return await apiGet<StrategyFileView>(`/api/strategies/${encodeURIComponent(selectedFile)}`);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) {
          return { filename: selectedFile, path: "", missing: true, content: "" };
        }
        throw e;
      }
    },
    retry: false,
  });

  const [prompt, setPrompt] = useLocalStorageState<string>(`st_strategy_prompt_${fileKey}`, "");
  const [originalCode, setOriginalCode] = useState("");
  const [proposedCode, setProposedCode] = useLocalStorageState<string>(`st_strategy_proposed_${fileKey}`, "");
  const [filename, setFilename] = useLocalStorageState<string>(`st_strategy_filename_${fileKey}`, selectedFile);
  const [validation, setValidation] = useState<ValidateResponse | null>(null);
  const [err, setErr] = useState<string>("");
  const [repairing, setRepairing] = useState<boolean>(false);
  const [applying, setApplying] = useState<boolean>(false);
  const { strategyCode: selectedStrategyCode, selectedFilename } = useSelectedStrategy();

  const [timerange, setTimerange] = useLocalStorageState<string>("st_cfg_timerange", "");
  const [fromDate, setFromDate] = useLocalStorageState<string>("st_cfg_from_date", "");
  const [toDate, setToDate] = useLocalStorageState<string>("st_cfg_to_date", "");
  const [timeframe, setTimeframe] = useLocalStorageState<string>("st_cfg_timeframe", "");
  const [pairTokens, setPairTokens] = useLocalStorageState<string[]>("st_cfg_pair_tokens", []);
  const [pairDraft, setPairDraft] = useLocalStorageState<string>("st_cfg_pair_draft", "");
  const [fee, setFee] = useLocalStorageState<string>("st_cfg_fee", "");
  const [dryRunWallet, setDryRunWallet] = useLocalStorageState<string>("st_cfg_wallet", "");
  const [maxOpenTrades, setMaxOpenTrades] = useLocalStorageState<string>("st_cfg_max_open_trades", "");

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

  const [jobId, setJobId] = useState<string>("");
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

  useEffect(() => {
    if (!fileQ.data) return;
    if (fileQ.data.missing) {
      setOriginalCode("");
      setProposedCode((prev) => (typeof prev === "string" && prev.trim() ? prev : ""));
      return;
    }
    const c = typeof fileQ.data.content === "string" ? fileQ.data.content : "";
    setOriginalCode(c);
    setProposedCode((prev) => (typeof prev === "string" && prev.trim() ? prev : c));
    setValidation(null);
    setErr("");
    setJobId("");
  }, [fileQ.data]);

  // Auto-populate from selected strategy
  useEffect(() => {
    if (selectedStrategyCode && selectedFilename) {
      setOriginalCode(selectedStrategyCode);
      setProposedCode(selectedStrategyCode);
      setFilename(selectedFilename);
    }
  }, [selectedStrategyCode, selectedFilename]);

  const changeStats = useMemo(() => {
    const a = originalCode.split("\n");
    const b = proposedCode.split("\n");
    const max = Math.max(a.length, b.length);
    let changed = 0;
    for (let i = 0; i < max; i++) {
      if ((a[i] || "") !== (b[i] || "")) changed++;
    }
    return {
      originalLines: a.length,
      proposedLines: b.length,
      changedLines: changed,
    };
  }, [originalCode, proposedCode]);

  function diffLines(aText: string, bText: string): DiffOp[] {
    const a = String(aText || "").split("\n");
    const b = String(bText || "").split("\n");
    const n = a.length;
    const m = b.length;
    const max = n + m;
    const offset = max;

    let v = new Array<number>(2 * max + 1).fill(0);
    const trace: number[][] = [];

    for (let d = 0; d <= max; d++) {
      trace.push(v.slice());
      for (let k = -d; k <= d; k += 2) {
        const kIndex = offset + k;
        let x: number;
        if (k === -d || (k !== d && v[kIndex - 1] < v[kIndex + 1])) {
          x = v[kIndex + 1];
        } else {
          x = v[kIndex - 1] + 1;
        }
        let y = x - k;
        while (x < n && y < m && a[x] === b[y]) {
          x++;
          y++;
        }
        v[kIndex] = x;
        if (x >= n && y >= m) {
          trace.push(v.slice());
          const ops: DiffOp[] = [];
          let curX = n;
          let curY = m;
          for (let dd = trace.length - 1; dd > 0; dd--) {
            const vv = trace[dd - 1];
            const curK = curX - curY;
            let prevK: number;
            if (curK === -dd + 1 || (curK !== dd - 1 && vv[offset + curK - 1] < vv[offset + curK + 1])) {
              prevK = curK + 1;
            } else {
              prevK = curK - 1;
            }
            const prevX = vv[offset + prevK];
            const prevY = prevX - prevK;
            while (curX > prevX && curY > prevY) {
              ops.push({ kind: "equal", line: a[curX - 1] ?? "" });
              curX--;
              curY--;
            }
            if (curX === prevX) {
              ops.push({ kind: "insert", line: b[curY - 1] ?? "" });
              curY--;
            } else {
              ops.push({ kind: "delete", line: a[curX - 1] ?? "" });
              curX--;
            }
          }
          while (curX > 0 && curY > 0) {
            ops.push({ kind: "equal", line: a[curX - 1] ?? "" });
            curX--;
            curY--;
          }
          while (curX > 0) {
            ops.push({ kind: "delete", line: a[curX - 1] ?? "" });
            curX--;
          }
          while (curY > 0) {
            ops.push({ kind: "insert", line: b[curY - 1] ?? "" });
            curY--;
          }
          return ops.reverse();
        }
      }
    }

    return [];
  }

  const diffOps = useMemo(() => {
    if (!originalCode && !proposedCode) return [];
    return diffLines(originalCode, proposedCode);
  }, [originalCode, proposedCode]);

  const diffChangeOps = useMemo(() => {
    return diffOps.filter((op) => op.kind !== "equal");
  }, [diffOps]);

  const hasDiffChanges = diffChangeOps.length > 0;

  async function apply() {
    setErr("");
    setApplying(true);
    try {
      const fn = filename.trim();
      if (!fn) throw new Error("filename is required");
      await apiPost("/api/strategy/save", { code: proposedCode, filename: fn });
      setOriginalCode(proposedCode);
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setApplying(false);
    }
  }

  async function validate() {
    setErr("");
    setValidation(null);
    try {
      const res = await apiPost<ValidateResponse>("/api/strategy/validate", { code: proposedCode });
      setValidation(res);
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  async function repairWithAi() {
    setErr("");
    setRepairing(true);
    try {
      const res = await apiPost<RepairResponse>("/api/ai/strategy/repair", { code: proposedCode, prompt: prompt.trim() || undefined });
      const next = String(res.strategy_code || "");
      if (!next.trim()) throw new Error("AI repair returned empty code");
      setProposedCode(next);
      setValidation(res.validation || null);
      if (res.validation && !res.validation.ok) {
        setErr(res.validation.error || "AI repair returned code that still fails validation");
      }
    } catch (e) {
      setErr(formatApiError(e));
    } finally {
      setRepairing(false);
    }
  }

  async function generate() {
    setErr("");
    try {
      const res = await apiPost<{ strategy_code: string }>("/api/ai/strategy/generate", { prompt });
      setProposedCode(String(res.strategy_code || ""));
      setValidation(null);
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  async function save() {
    setErr("");
    try {
      const fn = filename.trim();
      if (!fn) throw new Error("filename is required");
      await apiPost("/api/strategy/save", { code: proposedCode, filename: fn });
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  async function applyAndBacktest() {
    setErr("");
    setJobId("");
    try {
      const committedPairs = buildPairsValue();
      if (committedPairs !== pairTokens.join(",")) {
        const next = splitPairs(committedPairs);
        setPairTokens(next);
        setPairDraft("");
      }

      const fn = filename.trim();
      if (!fn) throw new Error("filename is required");
      await apiPost("/api/strategy/save", { code: proposedCode, filename: fn });

      const feeVal = fee.trim() ? Number(fee) : undefined;
      const walletVal = dryRunWallet.trim() ? Number(dryRunWallet) : undefined;
      const motVal = maxOpenTrades.trim() ? Number(maxOpenTrades) : undefined;
      const res = await apiPost<{ job_id: string }>("/api/backtest/run", {
        strategy_code: proposedCode,
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

  const job = jobQ.data;

  return (
    <div className="space-y-4">
      <Card title="Change Summary">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div>
            <div className="text-xs text-fg-400">File</div>
            <div className="mt-1 font-mono text-sm text-fg-200">{selectedFile}</div>
            <div className="mt-2">
              <div className="text-xs text-fg-400">Save as</div>
              <Input value={filename} onChange={setFilename} placeholder="AIStrategy.py" />
            </div>
          </div>
          <div>
            <div className="text-xs text-fg-400">Diff stats</div>
            <div className="mt-1 text-sm text-fg-200 font-mono">Lines: {changeStats.originalLines} → {changeStats.proposedLines}</div>
            <div className="mt-1 text-sm text-fg-200 font-mono">Changed lines: {changeStats.changedLines}</div>
            <div className="mt-2 text-xs text-fg-400">Validate</div>
            <div className="mt-1">
              <Button variant="outline" onClick={validate}>
                Validate
              </Button>
              <Button
                variant="outline"
                onClick={repairWithAi}
                disabled={repairing || !proposedCode.trim()}
              >
                {repairing ? "Fixing..." : "Fix with AI"}
              </Button>
              {validation ? (
                <span className={validation.ok ? "ml-3 text-xs font-mono text-semantic-pos" : "ml-3 text-xs font-mono text-semantic-neg"}>
                  {validation.ok ? "OK" : validation.error}
                </span>
              ) : null}
            </div>
          </div>
          <div>
            <div className="text-xs text-fg-400">AI prompt</div>
            <Textarea value={prompt} onChange={setPrompt} rows={5} placeholder="Describe the strategy you want..." className="font-sans" />
            <div className="mt-2 flex gap-2">
              <Button variant="primary" onClick={generate} disabled={!prompt.trim()}>
                Generate
              </Button>
              <Button variant="outline" onClick={save} disabled={!proposedCode.trim()}>
                Save
              </Button>
            </div>
          </div>
        </div>
        {err ? <div className="mt-3 text-xs font-mono text-semantic-neg">{err}</div> : null}
      </Card>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-2 space-y-6">
          <Card title="Original">
            <Textarea value={originalCode} onChange={(_v: string) => { }} rows={18} className="opacity-70" />
          </Card>
        </div>

        <div className="lg:col-span-3 space-y-4">
          <Card title="Proposed">
            {hasDiffChanges ? (
              <div className="mb-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-xs text-fg-400">Diff (Original → Proposed)</div>
                  <Button
                    variant="primary"
                    onClick={apply}
                    disabled={applying || repairing || !proposedCode.trim()}
                  >
                    {applying ? "Applying..." : "Apply"}
                  </Button>
                </div>
                <div className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md overflow-auto max-h-[420px]">
                  {diffChangeOps.map((op, idx) => {
                    const prefix = op.kind === "insert" ? "+" : op.kind === "delete" ? "-" : " ";
                    const rowClass =
                      op.kind === "insert"
                        ? "bg-semantic-pos/10 text-semantic-pos"
                        : op.kind === "delete"
                          ? "bg-semantic-neg/10 text-semantic-neg"
                          : "text-fg-200";
                    return (
                      <div key={idx} className={`px-3 py-0.5 whitespace-pre ${rowClass}`}>
                        <span className="inline-block w-4 select-none opacity-70">{prefix}</span>
                        <span>{op.line}</span>
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : null}

            <Textarea value={proposedCode} onChange={setProposedCode} rows={18} />
          </Card>

          <Card title="Apply & Backtest">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
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
                <div className="text-xs text-fg-400">Fee</div>
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
            </div>
            <div className="mt-3 flex gap-2">
              <Button variant="danger" onClick={applyAndBacktest} disabled={!proposedCode.trim()}>
                Apply & Backtest
              </Button>
            </div>

            {(suggestionsQ.data?.warnings || []).length ? (
              <div className="mt-2 text-xs text-fg-400 font-mono">{(suggestionsQ.data?.warnings || []).join(" | ")}</div>
            ) : null}

            {jobId ? (
              <div className="mt-4 space-y-2">
                <div className="text-xs text-fg-400 font-mono">Job: {jobId}</div>
                <div className="text-sm text-fg-200">Status: <span className="font-mono">{job?.status}</span></div>
                {job?.error ? <div className="text-xs text-semantic-neg font-mono">{job.error}</div> : null}
                <div className="text-xs text-fg-400">Logs</div>
                <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-2 overflow-auto max-h-48">
                  {(job?.logs || []).join("\n")}
                </pre>
                {job?.status === "succeeded" && job?.result ? (
                  <>
                    <div className="text-xs text-fg-400">Result</div>
                    <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-2 overflow-auto max-h-72">
                      {JSON.stringify(job.result, null, 2)}
                    </pre>
                  </>
                ) : null}
              </div>
            ) : null}
          </Card>
        </div>
      </div>
    </div>
  );
}
