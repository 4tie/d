import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiGet, apiPost, formatApiError } from "../lib/api";
import { useLocalStorageState } from "../lib/storage";
import { Button, Card, Input } from "../components/primitives";

type SettingsView = {
  freqtrade_url: string;
  api_user: string;
  has_api_password: boolean;
  ollama_url: string;
  ollama_model: string;
  ollama_options: Record<string, any>;
  ollama_task_models: Record<string, string>;
};

export default function Settings() {
  const [err, setErr] = useState("");
  const q = useQuery({
    queryKey: ["settings"],
    queryFn: () => apiGet<SettingsView>("/api/settings"),
  });

  const [freqtradeUrl, setFreqtradeUrl] = useLocalStorageState<string>("st_settings_freqtrade_url", "");
  const [apiUser, setApiUser] = useLocalStorageState<string>("st_settings_api_user", "");
  const [apiPass, setApiPass] = useState("");
  const [ollamaUrl, setOllamaUrl] = useLocalStorageState<string>("st_settings_ollama_url", "");
  const [ollamaModel, setOllamaModel] = useLocalStorageState<string>("st_settings_ollama_model", "");
  const [didInitFromApi, setDidInitFromApi] = useState(false);

  useEffect(() => {
    if (!q.data) return;
    if (didInitFromApi) return;

    if (!freqtradeUrl.trim()) setFreqtradeUrl(q.data.freqtrade_url || "");
    if (!apiUser.trim()) setApiUser(q.data.api_user || "");
    if (!ollamaUrl.trim()) setOllamaUrl(q.data.ollama_url || "");
    if (!ollamaModel.trim()) setOllamaModel(q.data.ollama_model || "");

    setDidInitFromApi(true);
  }, [q.data, didInitFromApi, freqtradeUrl, apiUser, ollamaUrl, ollamaModel]);

  async function save() {
    setErr("");
    try {
      await apiPost<SettingsView>("/api/settings", {
        freqtrade_url: freqtradeUrl,
        api_user: apiUser,
        api_password: apiPass ? apiPass : undefined,
        ollama_url: ollamaUrl,
        ollama_model: ollamaModel,
      });
      setApiPass("");
    } catch (e) {
      setErr(formatApiError(e));
    }
  }

  return (
    <div className="max-w-3xl space-y-4">
      <Card title="API Settings">
        {q.isLoading ? (
          <div className="text-sm text-fg-400">Loading…</div>
        ) : (
          <div className="space-y-3">
            <div>
              <div className="text-xs text-fg-400">Freqtrade URL</div>
              <Input value={freqtradeUrl} onChange={setFreqtradeUrl} placeholder="http://127.0.0.1:8080" />
            </div>
            <div>
              <div className="text-xs text-fg-400">API User</div>
              <Input value={apiUser} onChange={setApiUser} placeholder="user" />
            </div>
            <div>
              <div className="text-xs text-fg-400">API Password</div>
              <Input value={apiPass} onChange={setApiPass} placeholder={q.data?.has_api_password ? "(saved)" : ""} type="password" />
            </div>
            <div>
              <div className="text-xs text-fg-400">Ollama URL</div>
              <Input value={ollamaUrl} onChange={setOllamaUrl} placeholder="http://localhost:11434" />
            </div>
            <div>
              <div className="text-xs text-fg-400">Ollama Model</div>
              <Input value={ollamaModel} onChange={setOllamaModel} placeholder="llama2" />
            </div>
            <div className="flex gap-2">
              <Button variant="primary" onClick={save}>
                Save & Apply
              </Button>
            </div>
            {err ? <div className="text-xs text-semantic-neg font-mono">{err}</div> : null}
          </div>
        )}
      </Card>
    </div>
  );
}
