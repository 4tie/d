import { Route, Routes } from "react-router-dom";
import { StrategyNavigator } from "./components/app-sidebar";
import Overview from "./pages/Dashboard";
import StrategyEditor from "./pages/AIStrategy";
import Backtest from "./pages/Backtest";
import Trades from "./pages/Trades";
import AIAnalysis from "./pages/AIAnalysis";
import History from "./pages/History";
import Settings from "./pages/Settings";
import NotFound from "./pages/NotFound";

export default function App() {
  return (
    <div className="h-screen w-screen bg-bg-950 text-fg-100 flex overflow-hidden">
      <StrategyNavigator />
      <main className="flex-1 min-w-0 overflow-auto p-4">
        <Routes>
          <Route path="/" element={<Backtest />} />
          <Route path="/overview" element={<Overview />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/trades" element={<Trades />} />
          <Route path="/ai-analysis" element={<AIAnalysis />} />
          <Route path="/strategy-editor" element={<StrategyEditor />} />
          <Route path="/history" element={<History />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="*" element={<NotFound />} />
        </Routes>
      </main>
    </div>
  );
}
