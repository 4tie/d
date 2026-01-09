import type { Express } from "express";
import { createServer, type Server } from "http";
import { storage } from "./storage";
import { insertBotSchema, insertStrategySchema } from "@shared/schema";
import { spawn } from "child_process";
import path from "path";

export async function registerRoutes(app: Express): Promise<Server> {
  app.get("/api/bots", async (_req, res) => {
    res.json(await storage.getBots());
  });

  app.post("/api/bots", async (req, res) => {
    const parsed = insertBotSchema.safeParse(req.body);
    if (!parsed.success) return res.status(400).json({ error: parsed.error });
    res.json(await storage.createBot(parsed.data));
  });

  app.patch("/api/bots/:id", async (req, res) => {
    const id = parseInt(req.params.id);
    res.json(await storage.updateBot(id, req.body));
  });

  app.get("/api/strategies", async (_req, res) => {
    res.json(await storage.getStrategies());
  });

  app.post("/api/strategies", async (req, res) => {
    const parsed = insertStrategySchema.safeParse(req.body);
    if (!parsed.success) return res.status(400).json({ error: parsed.error });
    res.json(await storage.createStrategy(parsed.data));
  });

  app.get("/api/trades", async (req, res) => {
    const botId = req.query.botId ? parseInt(req.query.botId as string) : undefined;
    res.json(await storage.getTrades(botId));
  });

  // Python Bridge Endpoint
  app.post("/api/python/generate", (req, res) => {
    const { prompt } = req.body;
    // Example of calling Python logic
    const pythonProcess = spawn('python3', ['utils/strategy_generator.py', prompt]);
    
    let output = '';
    pythonProcess.stdout.on('data', (data) => {
      output += data.toString();
    });

    pythonProcess.on('close', (code) => {
      if (code === 0) {
        res.json({ success: true, strategy: output });
      } else {
        res.status(500).json({ success: false, error: 'Python process failed' });
      }
    });
  });

  const httpServer = createServer(app);
  return httpServer;
}
