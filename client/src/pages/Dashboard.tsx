import { useQuery } from "@tanstack/react-query";
import { Bot, Trade } from "@shared/schema";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Activity, TrendingUp, Cpu, ShieldCheck } from "lucide-react";

export default function Dashboard() {
  const { data: bots, isLoading: botsLoading } = useQuery<Bot[]>({ queryKey: ["/api/bots"] });
  const { data: trades, isLoading: tradesLoading } = useQuery<Trade[]>({ queryKey: ["/api/trades"] });

  const stats = [
    { title: "Active Bots", value: bots?.filter(b => b.status === 'running').length || 0, icon: Activity },
    { title: "Total PnL", value: `${bots?.reduce((acc, b) => acc + (b.pnl || 0), 0).toFixed(2)}%`, icon: TrendingUp },
    { title: "Strategies", value: bots?.length || 0, icon: Cpu },
    { title: "Safety Score", value: "94%", icon: ShieldCheck },
  ];

  if (botsLoading || tradesLoading) return <div>Loading dashboard...</div>;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((stat, i) => (
          <Card key={i} className="hover-elevate">
            <CardHeader className="flex flex-row items-center justify-between gap-2 space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{stat.title}</CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold font-mono">{stat.value}</div>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Performance History</CardTitle>
          </CardHeader>
          <CardContent className="h-[300px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trades}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#334155" />
                <XAxis dataKey="timestamp" hide />
                <YAxis stroke="#94a3b8" fontSize={12} tickFormatter={(val) => `${val}%`} />
                <Tooltip 
                  contentStyle={{ backgroundColor: '#1e293b', border: '1px solid #334155' }}
                  itemStyle={{ color: '#3b82f6' }}
                />
                <Line type="monotone" dataKey="pnl" stroke="#3b82f6" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Active Bots</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {bots?.map((bot) => (
                <div key={bot.id} className="flex items-center justify-between p-2 rounded-lg bg-muted/50">
                  <div>
                    <div className="font-medium">{bot.name}</div>
                    <div className="text-xs text-muted-foreground">{bot.strategy}</div>
                  </div>
                  <Badge variant={bot.status === 'running' ? 'default' : 'secondary'}>
                    {bot.status}
                  </Badge>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Recent Trades</CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Pair</TableHead>
                <TableHead>Type</TableHead>
                <TableHead>Price</TableHead>
                <TableHead>PnL</TableHead>
                <TableHead>Time</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {trades?.map((trade) => (
                <TableRow key={trade.id}>
                  <TableCell className="font-mono">{trade.pair}</TableCell>
                  <TableCell>
                    <Badge variant={trade.type === 'buy' ? 'outline' : 'default'}>
                      {trade.type}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono">${trade.price.toFixed(2)}</TableCell>
                  <TableCell className={trade.pnl && trade.pnl > 0 ? "text-green-500" : "text-red-500"}>
                    {trade.pnl ? `${trade.pnl > 0 ? '+' : ''}${trade.pnl}%` : '-'}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {new Date(trade.timestamp!).toLocaleTimeString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
