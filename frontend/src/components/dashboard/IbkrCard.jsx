import React, { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Plug, PowerOff, Settings2, DollarSign } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

export default function IbkrCard({ status, reload }) {
  const [setupOpen, setSetupOpen] = useState(false);
  const [form, setForm] = useState({ host: "127.0.0.1", port: "4001", client_id: "2" });
  const [busy, setBusy] = useState(false);

  const hasCreds = status?.has_credentials;
  const isAuth = status?.is_authenticated;
  const accountValue = status?.account_value;

  useEffect(() => {
    if (hasCreds && status?.last_login_at) {
      setForm((s) => ({ ...s }));
    }
  }, [hasCreds, status?.last_login_at]);

  useEffect(() => {
    if (status?.host) setForm((s) => ({ ...s, host: status.host }));
    if (status?.port) setForm((s) => ({ ...s, port: String(status.port) }));
    if (status?.client_id) setForm((s) => ({ ...s, client_id: String(status.client_id) }));
  }, [status?.host, status?.port, status?.client_id]);

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/ib/credentials", {
        host: form.host,
        port: parseInt(form.port, 10),
        client_id: parseInt(form.client_id, 10),
      });
      toast.success("IB Gateway settings saved");
      setSetupOpen(false);
      reload?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Failed to save");
    } finally {
      setBusy(false);
    }
  };

  const connect = async () => {
    setBusy(true);
    try {
      await api.post("/ib/connect");
      toast.success("IB Gateway connected");
      reload?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "IB connect failed");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await api.post("/ib/disconnect");
      toast.success("IB Gateway disconnected");
      reload?.();
    } catch (err) {
      toast.error("Disconnect failed");
    } finally {
      setBusy(false);
    }
  };

  const wipe = async () => {
    if (!window.confirm("Delete saved IB Gateway settings?")) return;
    try {
      await api.delete("/ib/credentials");
      toast.success("IB settings wiped");
      reload?.();
    } catch (err) {
      toast.error("Wipe failed");
    }
  };

  return (
    <Card className="bg-surface-2 border-border rounded-sm" data-testid="ibkr-card">
      <CardHeader className="pb-3 flex flex-row items-start justify-between space-y-0">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground mb-1 font-semibold">
            / broker
          </div>
          <CardTitle className="text-lg font-medium">Interactive Brokers</CardTitle>
        </div>
        <StatusPill isAuth={isAuth} hasCreds={hasCreds} />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-3 gap-3 pt-1">
          <Stat label="Gateway" value={hasCreds ? "configured" : "not set"} tone={hasCreds ? "ok" : "warn"} />
          <Stat label="Session" value={isAuth ? "active" : "inactive"} tone={isAuth ? "ok" : "warn"} />
          <Stat
            label="Account"
            value={accountValue != null ? `$${Number(accountValue).toLocaleString()}` : "—"}
            tone={accountValue != null ? "ok" : "default"}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSetupOpen(true)}
            data-testid="ibkr-edit-settings"
            className="rounded-sm h-8 text-xs border-border bg-surface-1 hover:bg-surface-3"
          >
            <Settings2 className="w-3.5 h-3.5 mr-1.5" />
            {hasCreds ? "Edit settings" : "Add settings"}
          </Button>
          {hasCreds && !isAuth && (
            <Button
              size="sm"
              onClick={connect}
              disabled={busy}
              data-testid="ibkr-connect-btn"
              className="rounded-sm h-8 text-xs bg-brand hover:bg-brand/90 text-white"
            >
              <Plug className="w-3.5 h-3.5 mr-1.5" />
              Connect
            </Button>
          )}
          {isAuth && (
            <Button
              size="sm"
              variant="ghost"
              onClick={disconnect}
              disabled={busy}
              data-testid="ibkr-disconnect-btn"
              className="rounded-sm h-8 text-xs text-muted-foreground hover:text-loss"
            >
              <PowerOff className="w-3.5 h-3.5 mr-1.5" />
              Disconnect
            </Button>
          )}
          {hasCreds && (
            <Button
              size="sm"
              variant="ghost"
              onClick={wipe}
              disabled={busy}
              data-testid="ibkr-wipe-btn"
              className="rounded-sm h-8 text-xs text-muted-foreground hover:text-loss ml-auto"
            >
              Wipe
            </Button>
          )}
        </div>
        {isAuth && accountValue != null && (
          <div className="border border-dashed border-border rounded-sm p-3 bg-surface-1 text-[11px] text-muted-foreground">
            <DollarSign className="w-3.5 h-3.5 inline mr-1 text-profit" />
            Available capital: <span className="text-white font-mono">${Number(accountValue).toLocaleString()}</span>
            <span className="block mt-1">
              S&P 500 stocks allocate 10%, others 5% per signal.
            </span>
          </div>
        )}
      </CardContent>

      <Dialog open={setupOpen} onOpenChange={setSetupOpen}>
        <DialogContent className="bg-surface-2 border-border rounded-sm sm:max-w-lg" data-testid="ibkr-setup-dialog">
          <DialogHeader>
            <DialogTitle className="font-medium tracking-tight">IB Gateway Connection</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Configure the local IB Gateway instance. Gateway must be running
              on the EC2 server under Xvfb. Default port is 4001 for Gateway, 7497 for TWS.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={save} className="space-y-3 pt-2">
            <div className="grid grid-cols-3 gap-3">
              <div className="space-y-1.5">
                <Label className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-semibold">
                  Host
                </Label>
                <Input
                  required
                  value={form.host}
                  onChange={(e) => setForm((s) => ({ ...s, host: e.target.value }))}
                  data-testid="ibkr-host-input"
                  placeholder="127.0.0.1"
                  className="h-9 rounded-sm bg-surface-1 border-border font-mono text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-semibold">
                  Port
                </Label>
                <Input
                  required
                  type="number"
                  value={form.port}
                  onChange={(e) => setForm((s) => ({ ...s, port: e.target.value }))}
                  data-testid="ibkr-port-input"
                  placeholder="4001"
                  className="h-9 rounded-sm bg-surface-1 border-border font-mono text-xs"
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-semibold">
                  Client ID
                </Label>
                <Input
                  required
                  type="number"
                  value={form.client_id}
                  onChange={(e) => setForm((s) => ({ ...s, client_id: e.target.value }))}
                  data-testid="ibkr-client-id-input"
                  placeholder="2"
                  className="h-9 rounded-sm bg-surface-1 border-border font-mono text-xs"
                />
              </div>
            </div>
            <DialogFooter className="pt-3">
              <Button type="button" variant="ghost" onClick={() => setSetupOpen(false)} className="rounded-sm h-9 text-xs">
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={busy}
                data-testid="ibkr-save-btn"
                className="rounded-sm h-9 text-xs bg-brand hover:bg-brand/90 text-white"
              >
                {busy ? "Saving..." : "Save"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  );
}

function StatusPill({ isAuth, hasCreds }) {
  let color = "#737373", text = "not configured";
  if (hasCreds && isAuth) { color = "#00C805"; text = "connected"; }
  else if (hasCreds) { color = "#FF9F0A"; text = "needs connect"; }
  return (
    <div className="flex items-center gap-2 border border-border px-2.5 h-7 rounded-sm bg-surface-1 font-mono text-[10px] uppercase tracking-wider">
      <span className="w-1.5 h-1.5 rounded-full pulse-dot" style={{ backgroundColor: color }} />
      <span style={{ color }}>{text}</span>
    </div>
  );
}

function Stat({ label, value, tone = "default" }) {
  const color = tone === "ok" ? "text-profit" : tone === "warn" ? "text-warn" : "text-white";
  return (
    <div className="border border-border p-3 bg-surface-1 rounded-sm">
      <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">{label}</div>
      <div className={`mt-1 font-mono text-sm ${color}`}>{value}</div>
    </div>
  );
}
