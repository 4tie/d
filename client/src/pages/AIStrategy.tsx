import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { apiRequest } from "@/lib/queryClient";
import { useToast } from "@/hooks/use-toast";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Loader2, Send, Cpu, Save } from "lucide-react";

export default function AIStrategy() {
  const [prompt, setPrompt] = useState("");
  const { toast } = useToast();

  const mutation = useMutation({
    mutationFn: async (prompt: string) => {
      const res = await apiRequest("POST", "/api/python/generate", { prompt });
      return res.json();
    },
    onSuccess: (data) => {
      toast({
        title: "Strategy Generated",
        description: "AI has successfully generated your trading strategy.",
      });
    },
    onError: () => {
      toast({
        variant: "destructive",
        title: "Error",
        description: "Failed to generate strategy. Ensure Python backend is responsive.",
      });
    }
  });

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Cpu className="h-5 w-5 text-primary" />
            AI Strategy Generator
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            Describe your trading strategy in plain English. Our AI will translate it into high-performance Python code for your bot.
          </p>
          <Textarea
            placeholder="e.g. Scalp BTC on 5m timeframe using RSI oversold and EMA crossover..."
            className="min-h-[150px] font-sans text-base"
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
          <div className="flex justify-end">
            <Button 
              onClick={() => mutation.mutate(prompt)}
              disabled={mutation.isPending || !prompt}
              className="gap-2"
            >
              {mutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <Send className="h-4 w-4" />
                  Generate Strategy
                </>
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {mutation.data?.strategy && (
        <Card className="animate-in fade-in slide-in-from-bottom-4 duration-500">
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Generated Python Code</CardTitle>
            <Button variant="outline" size="sm" className="gap-2">
              <Save className="h-4 w-4" />
              Save to Strategies
            </Button>
          </CardHeader>
          <CardContent>
            <pre className="p-4 rounded-lg bg-muted font-mono text-sm overflow-x-auto">
              <code>{mutation.data.strategy}</code>
            </pre>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
