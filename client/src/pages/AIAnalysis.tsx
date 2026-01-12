import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost, formatApiError } from "../lib/api";
import { useLocalStorageState } from "../lib/storage";
import { Button, Card, Input, Textarea, TokenInput } from "../components/primitives";
import { useSelectedStrategy } from "../lib/strategy-context";

type StrategyCurrent = {
  content?: string;
  missing?: boolean;
};

type JobView = {
  job_id: string;
  kind: string;
  status: "queued" | "running" | "succeeded" | "failed";
  logs: string[];
  result?: any;
  error?: string | null;
};

type DiffOp = {
  kind: "equal" | "insert" | "delete";
  line: string;
};

type BacktestSuggestions = {
  timeranges: string[];
  timeframes: string[];
  pairs: string[];
  warnings?: string[];
};

export default function AIAnalysis() {
  const [userGoal, setUserGoal] = useLocalStorageState<string>("st_ai_user_goal", "");
  const [maxIterations, setMaxIterations] = useLocalStorageState<string>("st_ai_max_iterations", "2");
  const [timerange, setTimerange] = useLocalStorageState<string>("st_cfg_timerange", "");
  const [timeframe, setTimeframe] = useLocalStorageState<string>("st_cfg_timeframe", "");
  const [pairTokens, setPairTokens] = useLocalStorageState<string[]>("st_cfg_pair_tokens", []);
  const [pairDraft, setPairDraft] = useLocalStorageState<string>("st_cfg_pair_draft", "");
  const [jobId, setJobId] = useState("");
  const [err, setErr] = useState("");
  const [saveErr, setSaveErr] = useState("");
  const [saving, setSaving] = useState(false);
  const [filename, setFilename] = useLocalStorageState<string>("st_ai_refine_filename", "AIStrategy.py");
  const [runBaseCode, setRunBaseCode] = useState<string>("");

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

  const currentQ = useQuery({
    queryKey: ["strategy_current"],
    queryFn: () => apiGet<StrategyCurrent>("/api/strategy/current"),
    refetchInterval: 15000,
  });

  const initialCode = useMemo(() => {
    const c = currentQ.data?.content;
    return typeof c === "string" ? c : "";
  }, [currentQ.data]);

  const [strategyCode, setStrategyCode] = useLocalStorageState<string>("st_cfg_strategy_code", "");
  const { strategyCode: selectedStrategyCode, selectedFilename } = useSelectedStrategy();

  useEffect(() => {
    if (!strategyCode && initialCode) setStrategyCode(initialCode);
  }, [initialCode, strategyCode]);

  // Auto-populate from selected strategy
  useEffect(() => {
    if (selectedStrategyCode && selectedFilename) {
      setStrategyCode(selectedStrategyCode);
      if (!filename.trim()) setFilename(selectedFilename);
    }
  }, [selectedStrategyCode, selectedFilename, filename, setFilename, setStrategyCode]);

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
            if (dd > 1) {
              if (curX === prevX) {
                ops.push({ kind: "insert", line: b[curY - 1] ?? "" });
                curY--;
              } else {
                ops.push({ kind: "delete", line: a[curX - 1] ?? "" });
                curX--;
              }
            }
          }
          return ops.reverse();
        }
      }
    }

    return [];
  }

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

  async function runRefine() {
    setErr("");
    setSaveErr("");
    try {
      const committedPairs = buildPairsValue();
      if (committedPairs !== pairTokens.join(",")) {
        const next = splitPairs(committedPairs);
        setPairTokens(next);
        setPairDraft("");
      }

      const miRaw = Number(maxIterations);
      const mi = Number.isFinite(miRaw) ? Math.trunc(miRaw) : 2;
      const miClamped = mi >= 1 && mi <= 5 ? mi : 2;
      const res = await apiPost<{ job_id: string }>("/api/ai/refine", {
        strategy_code: strategyCode,
        user_goal: userGoal,
        max_iterations: miClamped,
        timerange: timerange.trim() || undefined,
        timeframe: timeframe.trim() || undefined,
        pairs: committedPairs.trim() || undefined,
      });
      setRunBaseCode(strategyCode);
      setJobId(res.job_id);
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  async function saveCode(code: string) {
    setSaveErr("");
    setSaving(true);
    try {
      const fn = filename.trim();
      if (!fn) throw new Error("filename is required");
      if (!code.trim()) throw new Error("code is empty");
      await apiPost("/api/strategy/save", { code, filename: fn });
    } catch (e) {
      setSaveErr(formatApiError(e));
    } finally {
      setSaving(false);
    }
  }

  const job = jobQ.data;
  const iterations = Array.isArray(job?.result?.iterations) ? (job?.result?.iterations as any[]) : [];
  const [selectedIdx, setSelectedIdx] = useState<number>(0);

  useEffect(() => {
    if (iterations.length > 0 && selectedIdx >= iterations.length) setSelectedIdx(0);
  }, [iterations.length, selectedIdx]);

  const selected = iterations[selectedIdx];
  const selectedInputCode = typeof selected?.input_code === "string" ? String(selected.input_code) : "";
  const selectedRefinedCode = typeof selected?.refined_code === "string" ? String(selected.refined_code) : "";

  const selectedDiffOps = useMemo(() => {
    if (!selectedInputCode.trim() && !selectedRefinedCode.trim()) return [] as DiffOp[];
    return diffLines(selectedInputCode, selectedRefinedCode);
  }, [selectedInputCode, selectedRefinedCode]);

  const selectedDiffChanges = useMemo(() => {
    return selectedDiffOps.filter((op) => op.kind !== "equal");
  }, [selectedDiffOps]);

  const final = job?.result?.final;
  const finalCode = typeof final?.strategy_code === "string" ? String(final.strategy_code) : "";
  const finalSummary = final?.backtest_summary;
  const finalForensics = final?.trade_forensics;

  const finalDiffOps = useMemo(() => {
    if (!runBaseCode.trim() && !finalCode.trim()) return [] as DiffOp[];
    return diffLines(runBaseCode, finalCode);
  }, [runBaseCode, finalCode]);

  const finalDiffChanges = useMemo(() => {
    return finalDiffOps.filter((op) => op.kind !== "equal");
  }, [finalDiffOps]);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div className="lg:col-span-1 space-y-4">
        <Card title="Refine Parameters">
          <div className="space-y-3">
            <div>
              <div className="text-xs text-fg-400">Goal</div>
              <Input value={userGoal} onChange={setUserGoal} placeholder="Enter goal" />
            </div>
            <div>
              <div className="text-xs text-fg-400">Max iterations (1-5)</div>
              <Input value={maxIterations} onChange={setMaxIterations} placeholder="Enter max iterations" />
            </div>
            <div>
              <div className="text-xs text-fg-400">Timerange</div>
              <Input value={timerange} onChange={setTimerange} placeholder="Enter timerange" list="timerange-list" />
              <datalist id="timerange-list">
                {(suggestionsQ.data?.timeranges || []).map((t: string) => (
                  <option key={t} value={t} />
                ))}
              </datalist>
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
            <div className="flex gap-2">
              <Button variant="primary" onClick={runRefine} disabled={!strategyCode.trim() || !userGoal.trim()}>
                Run Refine
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
            <div className="text-sm text-fg-400">No analysis running.</div>
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
          <Textarea value={strategyCode} onChange={setStrategyCode} rows={10} />
          <div className="mt-3">
            <div className="text-xs text-fg-400">Save as</div>
            <Input value={filename} onChange={setFilename} placeholder="AIStrategy.py" />
          </div>
        </Card>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-1">
            <Card title="Iterations">
              {iterations.length === 0 ? (
                <div className="text-sm text-fg-400">No iterations yet.</div>
              ) : (
                <div className="space-y-2">
                  {iterations.map((it, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => setSelectedIdx(idx)}
                      className={`w-full text-left rounded-md border px-3 py-2 text-xs font-mono ${idx === selectedIdx ? "border-semantic-info bg-panel-750" : "border-border-700 bg-panel-800"
                        }`}
                    >
                      Iteration {String(it?.iteration ?? idx + 1)}
                    </button>
                  ))}
                </div>
              )}
            </Card>
          </div>
          <div className="lg:col-span-2">
            <Card title="Detailed Reasoning">
              {!selected ? (
                <div className="text-sm text-fg-400">Select an iteration.</div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <div className="text-xs text-fg-400">Analysis</div>
                    <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-64">
                      {String(selected?.analysis || "")}
                    </pre>
                  </div>
                  <div>
                    <div className="text-xs text-fg-400">Risk</div>
                    <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-3 overflow-auto max-h-64">
                      {String(selected?.risk || "")}
                    </pre>
                  </div>
                </div>
              )}
            </Card>
          </div>
        </div>

        <Card title="Refined Output">
          {!selected ? (
            <div className="text-sm text-fg-400">Select an iteration to view refined output.</div>
          ) : (
            <div className="space-y-4">
              <div>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <div className="text-xs text-fg-400">Iteration {String(selected?.iteration ?? selectedIdx + 1)} diff</div>
                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => setStrategyCode(selectedRefinedCode)} disabled={!selectedRefinedCode.trim()}>
                      Apply to Editor
                    </Button>
                    <Button variant="primary" onClick={() => saveCode(selectedRefinedCode)} disabled={saving || !selectedRefinedCode.trim()}>
                      {saving ? "Saving..." : "Save"}
                    </Button>
                  </div>
                </div>
                {selectedDiffChanges.length ? (
                  <div className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md overflow-auto max-h-64">
                    {selectedDiffChanges.map((op, idx) => {
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
                ) : (
                  <div className="text-sm text-fg-400">No code changes in this iteration.</div>
                )}
              </div>

              <div>
                <div className="text-xs text-fg-400">Iteration refined code</div>
                <Textarea value={selectedRefinedCode} onChange={(_v: string) => { }} rows={10} className="opacity-90" />
              </div>

              {finalCode.trim() ? (
                <div className="space-y-3">
                  <div className="text-xs text-fg-400">Final output diff</div>
                  {finalDiffChanges.length ? (
                    <div className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md overflow-auto max-h-64">
                      {finalDiffChanges.map((op, idx) => {
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
                  ) : (
                    <div className="text-sm text-fg-400">No final code changes.</div>
                  )}

                  <div className="flex gap-2">
                    <Button variant="outline" onClick={() => setStrategyCode(finalCode)} disabled={!finalCode.trim()}>
                      Apply Final to Editor
                    </Button>
                    <Button variant="primary" onClick={() => saveCode(finalCode)} disabled={saving || !finalCode.trim()}>
                      {saving ? "Saving..." : "Save Final"}
                    </Button>
                  </div>

                  <div>
                    <div className="text-xs text-fg-400">Final strategy code</div>
                    <Textarea value={finalCode} onChange={(_v: string) => { }} rows={10} className="opacity-90" />
                  </div>

                  {(finalSummary || finalForensics) ? (
                    <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                      <div>
                        <div className="text-xs text-fg-400">Final summary</div>
                        <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-2 overflow-auto max-h-64">
                          {JSON.stringify(finalSummary ?? {}, null, 2)}
                        </pre>
                      </div>
                      <div>
                        <div className="text-xs text-fg-400">Final trade forensics</div>
                        <pre className="text-xs font-mono bg-bg-900 border border-border-700 rounded-md p-2 overflow-auto max-h-64">
                          {JSON.stringify(finalForensics ?? {}, null, 2)}
                        </pre>
                      </div>
                    </div>
                  ) : null}
                </div>
              ) : null}

              {saveErr ? <div className="text-xs text-semantic-neg font-mono">{saveErr}</div> : null}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
