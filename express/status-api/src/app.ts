import express from "express";

const app = express();
app.get("/health", (_req, res) => res.json({ status: "ok" }));
app.get("/status", (_req, res) => res.status(202).json({ service: "status-api", ready: true, revision: 1 }));
export default app;
