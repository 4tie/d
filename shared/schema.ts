import { pgTable, text, serial, integer, boolean, timestamp, jsonb, real } from "drizzle-orm/pg-core";
import { createInsertSchema } from "drizzle-zod";
import { z } from "zod";

export const bots = pgTable("bots", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  status: text("status").notNull(), // 'running', 'paused', 'stopped'
  strategy: text("strategy").notNull(),
  pnl: real("pnl").default(0),
  winRate: real("win_rate").default(0),
  active: boolean("active").default(true),
  lastUpdated: timestamp("last_updated").defaultNow(),
});

export const strategies = pgTable("strategies", {
  id: serial("id").primaryKey(),
  name: text("name").notNull(),
  description: text("description"),
  code: text("code").notNull(),
  aiGenerated: boolean("ai_generated").default(false),
  createdAt: timestamp("created_at").defaultNow(),
});

export const trades = pgTable("trades", {
  id: serial("id").primaryKey(),
  botId: integer("bot_id").references(() => bots.id),
  pair: text("pair").notNull(),
  type: text("type").notNull(), // 'buy', 'sell'
  amount: real("amount").notNull(),
  price: real("price").notNull(),
  pnl: real("pnl"),
  timestamp: timestamp("timestamp").defaultNow(),
});

export const insertBotSchema = createInsertSchema(bots).omit({ id: true, lastUpdated: true });
export const insertStrategySchema = createInsertSchema(strategies).omit({ id: true, createdAt: true });
export const insertTradeSchema = createInsertSchema(trades).omit({ id: true, timestamp: true });

export type Bot = typeof bots.$inferSelect;
export type InsertBot = z.infer<typeof insertBotSchema>;
export type Strategy = typeof strategies.$inferSelect;
export type InsertStrategy = z.infer<typeof insertStrategySchema>;
export type Trade = typeof trades.$inferSelect;
export type InsertTrade = z.infer<typeof insertTradeSchema>;
