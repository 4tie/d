import { useQuery } from "@tanstack/react-query";
import { apiGet } from "../lib/api";

type HealthResponse = {
  ok: boolean;
  ts: number;
  has_app_config: boolean;
  has_bot_config: boolean;
};

export function ConnectionStatus() {
  const q = useQuery({
    queryKey: ["health"],
    queryFn: () => apiGet<HealthResponse>("/api/health"),
    refetchInterval: 5000,
  });

  const ok = q.data?.ok === true;

  const dotClass = ok ? "bg-semantic-pos" : "bg-semantic-neg";
  const text = ok ? "API: Online" : "API: Offline";

  return (
    <div className="flex items-center gap-2 text-xs text-fg-400">
      <span className={`h-2.5 w-2.5 rounded-full ${dotClass}`} />
      <span className="font-mono">{text}</span>
    </div>
  );
}
