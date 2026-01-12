import { useEffect, useMemo, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost, formatApiError } from "../lib/api";
import { useLocalStorageState } from "../lib/storage";
import { useSelectedStrategy } from "../lib/strategy-context";
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

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  ts: number;
};

type ShowConfig = {
  strategy?: string;
  timeframe?: string;
  exchange?: string;
  stake_currency?: string;
};

export function StrategyNavigator() {
  const nav = useNavigate();
  const { selectedFilename, selectStrategy, strategyCode } = useSelectedStrategy();

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
  const [showChat, setShowChat] = useLocalStorageState<boolean>("st_sidebar_show_chat", false);
  const [chatMessages, setChatMessages] = useLocalStorageState<ChatMessage[]>("st_sidebar_chat_messages", []);
  const [chatDraft, setChatDraft] = useState<string>("");
  const [chatErr, setChatErr] = useState<string>("");
  const [chatSending, setChatSending] = useState<boolean>(false);
  const chatScrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!showChat) return;
    const el = chatScrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [showChat, chatMessages]);

  async function sendChat() {
    const msg = chatDraft.trim();
    if (!msg) return;
    if (chatSending) return;

    setChatErr("");
    setChatDraft("");
    setChatSending(true);

    const userMsg: ChatMessage = { role: "user", content: msg, ts: Date.now() };
    const nextMsgs = [...chatMessages, userMsg].slice(-200);
    setChatMessages(nextMsgs);

    try {
      const res = await apiPost<{ reply: string; model_used?: string }>("/api/ai/chat", {
        message: msg,
        history: nextMsgs.map((m) => ({ role: m.role, content: m.content })),
        strategy_code: strategyCode?.trim() ? strategyCode : undefined,
        context: {
          selected_filename: selectedFilename || "",
          active_strategy: activeStrategyName || "",
          timeframe: cfgQ.data?.timeframe || "",
          last_backtest_profit_pct: selectedRun?.backtest_summary?.metrics?.profit_total_pct ?? null,
          last_backtest_max_dd_pct:
            selectedRun?.backtest_summary?.metrics?.max_drawdown_pct ?? selectedRun?.trade_forensics?.risk_adjusted?.max_drawdown_pct ?? null,
        },
      });

      const reply = String(res?.reply || "").trim();
      if (!reply) throw new Error("AI returned empty reply");

      const assistantMsg: ChatMessage = { role: "assistant", content: reply, ts: Date.now() };
      setChatMessages((prev) => [...prev, assistantMsg].slice(-200));
    } catch (e) {
      setChatErr(formatApiError(e));
    } finally {
      setChatSending(false);
    }
  }

  const strategiesQ = useQuery({
    queryKey: ["strategies"],
    queryFn: () => apiGet<StrategiesResponse>("/api/strategies"),
    refetchInterval: 15000,
  });

  const cfgQ = useQuery({
    queryKey: ["show_config"],
    queryFn: () => apiGet<ShowConfig>("/api/bot/show_config"),
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

  const selectedStrategyEntry = useMemo(() => {
    if (!selectedFilename) return null;
    const found = strategies.find((s) => s.filename === selectedFilename);
    return found || null;
  }, [strategies, selectedFilename]);

  const selectedRun = useMemo(() => {
    const h = selectedStrategyEntry?.strategy_hash;
    if (!h) return null;
    return runByHash.get(h) || null;
  }, [runByHash, selectedStrategyEntry]);

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
        <div className="mt-2 text-xs text-fg-400">Selected (editor)</div>
        <div className="mt-1 font-mono text-sm text-fg-200 truncate">{(selectedFilename || "").trim() || "(none)"}</div>
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

        <div className="mt-2 grid grid-cols-4 gap-1 px-1">
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
          <button
            type="button"
            onClick={() => setShowChat((s) => !s)}
            className={[
              "rounded-md px-2 py-1 text-[11px] font-mono text-center",
              showChat ? "bg-panel-750 text-fg-100" : "text-fg-400 hover:bg-panel-800 hover:text-fg-200",
            ].join(" ")}
          >
            4tiee
          </button>
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

      <div className={["flex-1 min-h-0 flex flex-col", showChat ? "overflow-hidden" : "overflow-auto"].join(" ")}>
        <div className="px-4 pt-4 pb-2 flex items-center justify-between">
          <div className="text-xs text-fg-400">{showChat ? "4tiee" : "Strategies"}</div>
          {!showChat ? (
            <button
              type="button"
              onClick={() => setShowStrategies((s) => !s)}
              className="text-[11px] font-mono text-fg-400 hover:text-fg-200"
            >
              {showStrategies ? "Hide" : "Show"}
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setShowChat(false)}
              className="text-[11px] font-mono text-fg-400 hover:text-fg-200"
            >
              Close
            </button>
          )}
        </div>

        {showChat ? (
          <div className="px-2 pb-4 flex-1 min-h-0 flex flex-col">
            <div className="rounded-md border border-border-700 bg-panel-800 p-2 flex-1 min-h-0 flex flex-col">
              {chatErr ? <div className="text-[11px] text-semantic-neg">{chatErr}</div> : null}

              <div
                ref={chatScrollRef}
                className="mt-2 flex-1 min-h-0 overflow-auto rounded-md border border-border-700 bg-bg-950 p-2"
              >
                {chatMessages.length ? (
                  <div className="space-y-2">
                    {chatMessages.map((m) => (
                      <div key={`${m.role}:${m.ts}:${m.content.slice(0, 16)}`} className="text-[11px] font-mono">
                        <div className="text-fg-400">{m.role === "user" ? "YOU" : "4tiee"}</div>
                        <div className="whitespace-pre-wrap break-words text-fg-100">{m.content}</div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-[11px] text-fg-500">Ask 4tiee about your strategy/backtests.</div>
                )}
              </div>

              <div className="mt-2 flex items-center gap-2 flex-shrink-0">
                <input
                  value={chatDraft}
                  onChange={(e) => setChatDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      sendChat();
                    }
                  }}
                  placeholder="Type a message…"
                  className="flex-1 rounded-md border border-border-700 bg-bg-950 px-2 py-1 text-[11px] font-mono text-fg-100 placeholder:text-fg-500"
                  disabled={chatSending}
                />
                <button
                  type="button"
                  onClick={sendChat}
                  disabled={chatSending || !chatDraft.trim()}
                  className="rounded-md border border-border-700 bg-panel-800 px-2 py-1 text-[11px] font-mono text-fg-200 hover:bg-panel-750 disabled:opacity-50"
                >
                  Send
                </button>
              </div>
            </div>
          </div>
        ) : showStrategies ? (
          <>
            {!strategiesQ.isLoading && strategies.length === 0 ? (
              <div className="px-4 pb-4 text-xs text-fg-400">No strategy files found.</div>
            ) : null}

            <div className="px-2 pb-4 space-y-1">
              {strategies.map((s) => {
                const isActiveFile =
                  activeStrategyName && s.filename.toLowerCase() === `${activeStrategyName}.py`.toLowerCase();
                const isSelected = selectedFilename === s.filename;

                const run = s.strategy_hash ? runByHash.get(s.strategy_hash) : undefined;
                const profit = run?.backtest_summary?.metrics?.profit_total_pct;
                const dd = run?.backtest_summary?.metrics?.max_drawdown_pct;

                let statusColor = "bg-panel-800";
                if (typeof profit === "number") {
                  statusColor = profit >= 0 ? "bg-[#0b2a1a]" : "bg-[#2a0b0b]";
                }

                return (
                  <button
                    key={s.filename}
                    type="button"
                    onClick={() => selectStrategy(s.filename)}
                    className={[
                      "w-full block rounded-md px-3 py-2 border transition-all hover:border-border-650",
                      isActiveFile ? "border-semantic-info" : isSelected ? "border-semantic-warn" : "border-border-700",
                      statusColor,
                    ].join(" ")}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0">
                        <div className="text-sm font-mono truncate text-fg-100 text-left">{s.filename}</div>
                        <div className="text-[11px] text-fg-400 font-mono truncate text-left">{s.strategy_hash || ""}</div>
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
                  </button>
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
