import React, { useCallback, useEffect, useState } from "react";
import Header from "@/components/layout/Header";
import LiveBanner from "@/components/layout/LiveBanner";
import IbkrCard from "@/components/dashboard/IbkrCard";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";
import {
  LayoutDashboard,
  RefreshCw,
  TrendingDown,
  Loader2,
  BarChart3,
  ScrollText,
  ShieldAlert,
} from "lucide-react";

export default function IbkrDashboard({ user }) {
  const [status, setStatus] = useState(null);
  const [positions, setPositions] = useState([]);
  const [positionsLoading, setPositionsLoading] = useState(false);
  const [emaLogs, setEmaLogs] = useState([]);
  const [emaRunning, setEmaRunning] = useState(false);
  const [emaConfirming, setEmaConfirming] = useState(false);
  const [emaResults, setEmaResults] = useState(null);
  const [tradeLogs, setTradeLogs] = useState([]);
  const [tradeLogsLoading, setTradeLogsLoading] = useState(false);

  const loadStatus = useCallback(async () => {
    try {
      const res = await api.get("/brokers/status");
      setStatus(res.data);
    } catch (e) {
      setStatus(null);
    }
  }, []);

  const loadPositions = useCallback(async () => {
    setPositionsLoading(true);
    try {
      const res = await api.get("/ib/positions");
      setPositions(res.data?.positions || []);
    } catch (e) {
      setPositions([]);
    } finally {
      setPositionsLoading(false);
    }
  }, []);

  const loadEmaLogs = useCallback(async () => {
    try {
      const res = await api.get("/ib/ema-sl/logs?limit=20");
      setEmaLogs(res.data?.logs || []);
    } catch (e) {
      setEmaLogs([]);
    }
  }, []);

  const loadTradeLogs = useCallback(async () => {
    setTradeLogsLoading(true);
    try {
      const res = await api.get("/trades/logs?limit=30");
      const all = res.data?.logs || [];
      setTradeLogs(all.filter((l) => l.source === "ib_ema_sl" || l.source === "us_signal"));
    } catch (e) {
      setTradeLogs([]);
    } finally {
      setTradeLogsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    loadPositions();
    loadEmaLogs();
    loadTradeLogs();
    const t = setInterval(() => {
      loadPositions();
      loadTradeLogs();
    }, 30000);
    return () => clearInterval(t);
  }, [loadStatus, loadPositions, loadEmaLogs, loadTradeLogs]);

  const isAuth = status?.interactive_brokers?.is_authenticated;

  const runEmaSl = async () => {
    setEmaConfirming(false);
    setEmaRunning(true);
    setEmaResults(null);
    try {
      const res = await api.post("/ib/ema-sl/run");
      setEmaResults(res.data);
      toast.success(`EMA SL ran on ${res.data.total} positions`);
      loadPositions();
      loadEmaLogs();
      loadTradeLogs();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "EMA SL run failed");
    } finally {
      setEmaRunning(false);
    }
  };

  return (
    <div className="min-h-screen bg-surface-1 text-foreground" data-testid="ibkr-dashboard-page">
      <LiveBanner />
      <Header user={user} />

      <main className="max-w-[1600px] mx-auto px-6 py-6 space-y-5">
        {/* Heading */}
        <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-2 pb-2">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold">
              / interactive brokers
            </div>
            <h1 className="text-2xl sm:text-3xl font-medium tracking-tight mt-1">
              US Stocks Terminal
            </h1>
          </div>
          <div className="font-mono text-[10px] text-muted-foreground tracking-wider">
            {new Date().toLocaleString("en-US", { hour12: false })}
          </div>
        </div>

        {/* Connection */}
        <section>
          <div className="text-[10px] uppercase tracking-[0.2em] text-muted-foreground font-semibold mb-3">
            / connection
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="md:col-span-2 lg:col-span-2">
              <IbkrCard status={status?.interactive_brokers} reload={loadStatus} />
            </div>
            {isAuth && status?.interactive_brokers?.account_value != null && (
              <Card className="bg-surface-2 border-border rounded-sm">
                <CardHeader className="pb-3">
                  <CardTitle className="text-sm font-medium flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-brand" />
                    Account Overview
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    <div>
                      <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
                        Net Liquidation
                      </div>
                      <div className="text-2xl font-mono text-profit mt-1">
                        ${Number(status.interactive_brokers.account_value).toLocaleString()}
                      </div>
                    </div>
                    <div className="grid grid-cols-2 gap-2 pt-1">
                      <div className="border border-border p-2 rounded-sm bg-surface-1">
                        <div className="text-[9px] uppercase tracking-[0.15em] text-muted-foreground">
                          S&P 500 allocation
                        </div>
                        <div className="text-sm font-mono mt-0.5">10%</div>
                      </div>
                      <div className="border border-border p-2 rounded-sm bg-surface-1">
                        <div className="text-[9px] uppercase tracking-[0.15em] text-muted-foreground">
                          Other stocks
                        </div>
                        <div className="text-sm font-mono mt-0.5">5%</div>
                      </div>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}
          </div>
        </section>

        {/* Open Positions */}
        <Card className="bg-surface-2 border-border rounded-sm" data-testid="ibkr-positions-section">
          <CardHeader className="pb-3 flex flex-row items-center justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground mb-1 font-semibold">
                / positions
              </div>
              <CardTitle className="text-lg font-medium flex items-center gap-2">
                <BarChart3 className="w-4 h-4 text-brand" />
                Open Positions
              </CardTitle>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadPositions}
              disabled={positionsLoading}
              className="rounded-sm h-8 text-xs border-border bg-surface-1"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${positionsLoading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </CardHeader>
          <CardContent>
            {!isAuth ? (
              <div className="py-10 text-center text-xs text-muted-foreground">
                Connect Interactive Brokers to view positions
              </div>
            ) : positions.length === 0 ? (
              <div className="py-10 text-center text-xs text-muted-foreground">
                No open positions
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow className="border-border">
                    <TableHead className="text-[10px] uppercase tracking-wider font-semibold">Symbol</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider font-semibold text-right">Qty</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider font-semibold text-right">Avg Price</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider font-semibold text-right">LTP</TableHead>
                    <TableHead className="text-[10px] uppercase tracking-wider font-semibold text-right">P&L</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {positions.map((p, i) => (
                    <TableRow key={`${p.symbol}-${i}`} className="border-border">
                      <TableCell className="font-mono text-xs">{p.symbol}</TableCell>
                      <TableCell className="font-mono text-xs text-right">{p.quantity}</TableCell>
                      <TableCell className="font-mono text-xs text-right">${p.avg_price?.toFixed(2)}</TableCell>
                      <TableCell className="font-mono text-xs text-right">
                        {p.ltp != null ? `$${p.ltp.toFixed(2)}` : "—"}
                      </TableCell>
                      <TableCell className={`font-mono text-xs text-right ${(p.pnl || 0) >= 0 ? "text-profit" : "text-loss"}`}>
                        {p.pnl != null ? `$${p.pnl.toFixed(2)}` : "—"}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>

        {/* EMA Trailing Stop */}
        <Card className="bg-surface-2 border-border rounded-sm" data-testid="ibkr-ema-section">
          <CardHeader className="pb-3">
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground mb-1 font-semibold">
              / risk management
            </div>
            <CardTitle className="text-lg font-medium flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-brand" />
              EMA10 Trailing Stop
            </CardTitle>
            <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">
              Computes the daily EMA10 for each open position and places a sell-stop
              at 98% of EMA10 to protect against downside moves.
            </p>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap items-center gap-3">
              {!emaConfirming ? (
                <Button
                  size="sm"
                  onClick={() => setEmaConfirming(true)}
                  disabled={!isAuth || emaRunning}
                  data-testid="ibkr-ema-run-btn"
                  className="rounded-sm h-9 text-xs bg-loss hover:bg-loss/90 text-white"
                >
                  <TrendingDown className="w-3.5 h-3.5 mr-1.5" />
                  Run EMA10 Stop Loss
                </Button>
              ) : (
                <div className="flex items-center gap-2 border border-loss/50 rounded-sm p-2 bg-loss/10">
                  <span className="text-xs text-loss font-medium">Place stop-losses on all positions?</span>
                  <Button
                    size="sm"
                    onClick={runEmaSl}
                    disabled={emaRunning}
                    className="rounded-sm h-8 text-xs bg-loss hover:bg-loss/90 text-white"
                  >
                    {emaRunning ? (
                      <><Loader2 className="w-3 h-3 mr-1 animate-spin" />Running...</>
                    ) : "Confirm"}
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setEmaConfirming(false)}
                    className="rounded-sm h-8 text-xs text-muted-foreground"
                  >
                    Cancel
                  </Button>
                </div>
              )}
            </div>

            {/* EMA Results */}
            {emaResults && (
              <div className="border border-border rounded-sm divide-y divide-border">
                {emaResults.results?.map((r, i) => (
                  <div key={i} className="flex items-center justify-between px-3 py-2 text-xs font-mono">
                    <span className="font-semibold">{r.symbol}</span>
                    <span className={r.status === "placed" ? "text-profit" : "text-warn"}>
                      {r.status === "placed"
                        ? `SL @ $${r.sl_trigger} (EMA10: $${r.ema10})`
                        : r.message}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {/* Recent EMA SL Logs */}
            <div>
              <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-semibold mb-2">
                Recent EMA SL Runs
              </div>
              {emaLogs.length === 0 ? (
                <div className="py-4 text-center text-[11px] text-muted-foreground">
                  No EMA SL runs yet
                </div>
              ) : (
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {emaLogs.map((l, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between text-[11px] font-mono border-b border-border/50 py-1.5 px-1"
                    >
                      <div className="flex items-center gap-2">
                        <span className="text-muted-foreground">
                          {new Date(l.created_at).toLocaleTimeString("en-US", { hour12: false })}
                        </span>
                        <span className="font-semibold">{l.symbol}</span>
                      </div>
                      <div className="text-right">
                        <span className={l.status === "placed" ? "text-profit" : "text-warn"}>
                          {l.status}
                        </span>
                        <span className="text-muted-foreground ml-2">
                          SL @ ${l.sl_trigger}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Trade Log */}
        <Card className="bg-surface-2 border-border rounded-sm" data-testid="ibkr-trade-log-section">
          <CardHeader className="pb-3 flex flex-row items-center justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground mb-1 font-semibold">
                / logs
              </div>
              <CardTitle className="text-lg font-medium flex items-center gap-2">
                <ScrollText className="w-4 h-4 text-brand" />
                IB Trade Log
              </CardTitle>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={loadTradeLogs}
              disabled={tradeLogsLoading}
              className="rounded-sm h-8 text-xs border-border bg-surface-1"
            >
              <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${tradeLogsLoading ? "animate-spin" : ""}`} />
              Refresh
            </Button>
          </CardHeader>
          <CardContent>
            {!isAuth ? (
              <div className="py-10 text-center text-xs text-muted-foreground">
                Connect Interactive Brokers to view trade logs
              </div>
            ) : tradeLogs.length === 0 ? (
              <div className="py-10 text-center text-xs text-muted-foreground">
                No IB trade activity yet
              </div>
            ) : (
              <div className="space-y-1 max-h-80 overflow-y-auto">
                {tradeLogs.map((l, i) => (
                  <div
                    key={l.id || i}
                    className="flex items-center justify-between text-[11px] font-mono border-b border-border/50 py-2 px-1"
                  >
                    <div className="flex items-center gap-3 flex-1 min-w-0">
                      <span className="text-muted-foreground shrink-0 w-16">
                        {new Date(l.created_at).toLocaleTimeString("en-US", { hour12: false })}
                      </span>
                      <span
                        className={`shrink-0 text-[10px] font-semibold uppercase px-1.5 py-0.5 rounded-sm ${
                          l.transaction_type === "B"
                            ? "bg-profit/20 text-profit"
                            : "bg-loss/20 text-loss"
                        }`}
                      >
                        {l.transaction_type === "B" ? "BUY" : "SELL"}
                      </span>
                      <span className="font-semibold shrink-0">{l.symbol}</span>
                      <span className="text-muted-foreground">{l.quantity} @ ${l.price?.toFixed(2)}</span>
                    </div>
                    <div className="text-right shrink-0 ml-3">
                      <span
                        className={`text-[10px] ${
                          l.status === "filled" || l.status === "success"
                            ? "text-profit"
                            : l.status === "error" || l.status === "rejected"
                            ? "text-loss"
                            : "text-warn"
                        }`}
                      >
                        {l.status}
                      </span>
                      {l.message && (
                        <div className="text-[9px] text-muted-foreground truncate max-w-[200px]">
                          {l.message}
                        </div>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Nav back to main dashboard */}
        <div className="pt-2 pb-8">
          <a
            href="/dashboard"
            className="inline-flex items-center gap-1.5 text-[11px] font-mono text-brand hover:text-brand/80 transition-colors"
          >
            <LayoutDashboard className="w-3.5 h-3.5" />
            ← Back to main dashboard
          </a>
        </div>

        <footer className="pt-4 pb-8 text-[10px] font-mono text-muted-foreground tracking-wider flex items-center justify-between">
          <span>
            chartink-trade · v1.1 ·{" "}
            <span className="text-brand">interactive-brokers</span>
          </span>
          <span>NASDAQ / NYSE · US-stocks</span>
        </footer>
      </main>
    </div>
  );
}
