import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

export function ConnectionStatus() {
  const healthQ = useQuery({
    queryKey: ["api_health"],
    queryFn: () => apiGet<{ ok: boolean }>("/api/health"),
    refetchInterval: 10000,
    retry: 1,
  });

  const ollamaQ = useQuery({
    queryKey: ["ollama_ping"],
    queryFn: () => apiGet<{ available: boolean }>("/api/ollama/ping"),
    refetchInterval: 10000,
    retry: 1,
  });

  const apiOk = healthQ.isSuccess && healthQ.data?.ok;
  const aiOk = ollamaQ.isSuccess && !!ollamaQ.data?.available;

  return (
    <div className="flex items-center gap-2 text-xs">
      <div className="flex items-center gap-1.5">
        <div
          className={`w-2 h-2 rounded-full transition-all duration-300 ${apiOk ? "bg-semantic-pos animate-pulse-glow" : "bg-semantic-neg"
            }`}
        />
        <span className={`font-mono transition-colors duration-300 ${apiOk ? "text-semantic-pos" : "text-semantic-neg"
          }`}>
          API
        </span>
      </div>
      <div className="w-px h-3 bg-border-700" />
      <div className="flex items-center gap-1.5">
        <div
          className={`w-2 h-2 rounded-full transition-all duration-300 ${aiOk ? "bg-semantic-pos animate-pulse-glow" : "bg-fg-400"}`}
        />
        <span className={`font-mono transition-colors duration-300 ${aiOk ? "text-semantic-pos" : "text-fg-400"}`}>
          AI
        </span>
      </div>
    </div>
  );
}
