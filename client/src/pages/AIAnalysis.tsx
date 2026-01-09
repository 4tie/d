import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost, formatApiError } from "../lib/api";
import { useLocalStorageState } from "../lib/storage";
import { Button, Card, Input, Textarea, TokenInput } from "../components/primitives";

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

  async function runRefine() {
    setErr("");
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
      setJobId(res.job_id);
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  const job = jobQ.data;
  const iterations = Array.isArray(job?.result?.iterations) ? (job?.result?.iterations as any[]) : [];
  const [selectedIdx, setSelectedIdx] = useState<number>(0);

  useEffect(() => {
    if (iterations.length > 0 && selectedIdx >= iterations.length) setSelectedIdx(0);
  }, [iterations.length, selectedIdx]);

  const selected = iterations[selectedIdx];

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
                      className={`w-full text-left rounded-md border px-3 py-2 text-xs font-mono ${
                        idx === selectedIdx ? "border-semantic-info bg-panel-750" : "border-border-700 bg-panel-800"
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
      </div>
    </div>
  );
}
