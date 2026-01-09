import { Bot, InsertBot, Strategy, InsertStrategy, Trade, InsertTrade } from "@shared/schema.ts";

export interface IStorage {
  // Bots
  getBots(): Promise<Bot[]>;
  getBot(id: number): Promise<Bot | undefined>;
  createBot(bot: InsertBot): Promise<Bot>;
  updateBot(id: number, bot: Partial<Bot>): Promise<Bot>;
  
  // Strategies
  getStrategies(): Promise<Strategy[]>;
  getStrategy(id: number): Promise<Strategy | undefined>;
  createStrategy(strategy: InsertStrategy): Promise<Strategy>;

  // Trades
  getTrades(botId?: number): Promise<Trade[]>;
  addTrade(trade: InsertTrade): Promise<Trade>;
}

export class MemStorage implements IStorage {
  private bots: Map<number, Bot>;
  private strategies: Map<number, Strategy>;
  private trades: Map<number, Trade>;
  private currentId: { [key: string]: number };

  constructor() {
    this.bots = new Map();
    this.strategies = new Map();
    this.trades = new Map();
    this.currentId = { bots: 1, strategies: 1, trades: 1 };
    
    // Seed some data
    this.createBot({ name: "BTC Trend Follower", status: "running", strategy: "TrendV1", pnl: 2.5, winRate: 65, active: true });
    this.createStrategy({ name: "TrendV1", description: "Standard trend following", code: "class TrendV1...", aiGenerated: false });
  }

  async getBots(): Promise<Bot[]> {
    return Array.from(this.bots.values());
  }

  async getBot(id: number): Promise<Bot | undefined> {
    return this.bots.get(id);
  }

  async createBot(insertBot: InsertBot): Promise<Bot> {
    const id = this.currentId.bots++;
    const bot: Bot = { ...insertBot, id, lastUpdated: new Date(), pnl: insertBot.pnl ?? 0, winRate: insertBot.winRate ?? 0, active: insertBot.active ?? true };
    this.bots.set(id, bot);
    return bot;
  }

  async updateBot(id: number, update: Partial<Bot>): Promise<Bot> {
    const bot = this.bots.get(id);
    if (!bot) throw new Error("Bot not found");
    const updated = { ...bot, ...update, lastUpdated: new Date() };
    this.bots.set(id, updated);
    return updated;
  }

  async getStrategies(): Promise<Strategy[]> {
    return Array.from(this.strategies.values());
  }

  async getStrategy(id: number): Promise<Strategy | undefined> {
    return this.strategies.get(id);
  }

  async createStrategy(insertStrategy: InsertStrategy): Promise<Strategy> {
    const id = this.currentId.strategies++;
    const strategy: Strategy = { ...insertStrategy, id, createdAt: new Date() };
    this.strategies.set(id, strategy);
    return strategy;
  }

  async getTrades(botId?: number): Promise<Trade[]> {
    const all = Array.from(this.trades.values());
    if (botId) return all.filter(t => t.botId === botId);
    return all;
  }

  async addTrade(insertTrade: InsertTrade): Promise<Trade> {
    const id = this.currentId.trades++;
    const trade: Trade = { ...insertTrade, id, timestamp: new Date() };
    this.trades.set(id, trade);
    return trade;
  }
}

export const storage = new MemStorage();
