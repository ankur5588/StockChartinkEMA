import React, { useState } from "react";
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
import { Plug, PowerOff, Settings2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";

const ENVIRONMENTS = [
  { value: "india_prod", label: "India Production" },
  { value: "global_prod", label: "Global Production" },
  { value: "india_testnet", label: "India Testnet" },
  { value: "global_testnet", label: "Global Testnet" },
];

export default function DeltaCard({ status, reload }) {
  const [setupOpen, setSetupOpen] = useState(false);
  const [form, setForm] = useState({ api_key: "", api_secret: "", environment: "india_prod" });
  const [busy, setBusy] = useState(false);

  const hasCreds = status?.has_credentials;
  const isAuth = status?.is_authenticated;

  const save = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/delta/credentials", form);
      toast.success("Delta Exchange credentials saved");
      setSetupOpen(false);
      setForm({ api_key: "", api_secret: "", environment: "india_prod" });
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
      await api.post("/delta/connect");
      toast.success("Delta Exchange session created");
      reload?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Delta connect failed");
    } finally {
      setBusy(false);
    }
  };

  const disconnect = async () => {
    setBusy(true);
    try {
      await api.post("/delta/disconnect");
      toast.success("Delta Exchange disconnected");
      reload?.();
    } catch (err) {
      toast.error("Disconnect failed");
    } finally {
      setBusy(false);
    }
  };

  const wipe = async () => {
    if (!window.confirm("Delete saved Delta Exchange credentials?")) return;
    try {
      await api.delete("/delta/credentials");
      toast.success("Delta credentials wiped");
      reload?.();
    } catch (err) {
      toast.error("Wipe failed");
    }
  };

  return (
    <Card className="bg-surface-2 border-border rounded-sm" data-testid="delta-card">
      <CardHeader className="pb-3 flex flex-row items-start justify-between space-y-0">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground mb-1 font-semibold">
            / broker
          </div>
          <CardTitle className="text-lg font-medium">Delta Exchange</CardTitle>
        </div>
        <StatusPill isAuth={isAuth} hasCreds={hasCreds} />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3 pt-1">
          <Stat label="Credentials" value={hasCreds ? "saved" : "missing"} tone={hasCreds ? "ok" : "warn"} />
          <Stat label="Session" value={isAuth ? "active" : "inactive"} tone={isAuth ? "ok" : "warn"} />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSetupOpen(true)}
            data-testid="delta-edit-creds"
            className="rounded-sm h-8 text-xs border-border bg-surface-1 hover:bg-surface-3"
          >
            <Settings2 className="w-3.5 h-3.5 mr-1.5" />
            {hasCreds ? "Edit keys" : "Add keys"}
          </Button>
          {hasCreds && !isAuth && (
            <Button
              size="sm"
              onClick={connect}
              disabled={busy}
              data-testid="delta-connect-btn"
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
              data-testid="delta-disconnect-btn"
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
              data-testid="delta-wipe-btn"
              className="rounded-sm h-8 text-xs text-muted-foreground hover:text-loss ml-auto"
            >
              Wipe
            </Button>
          )}
        </div>
        <p className="text-[10px] text-muted-foreground leading-relaxed">
          Crypto derivatives (BTC, ETH futures &amp; options). Get API keys from{" "}
          <span className="text-white">delta.exchange → API</span>.
        </p>
      </CardContent>

      <Dialog open={setupOpen} onOpenChange={setSetupOpen}>
        <DialogContent className="bg-surface-2 border-border rounded-sm sm:max-w-lg" data-testid="delta-setup-dialog">
          <DialogHeader>
            <DialogTitle className="font-medium tracking-tight">Delta Exchange API Keys</DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              Generate API Key and Secret at{" "}
              <span className="text-white">delta.exchange → Dashboard → API</span>.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={save} className="space-y-3 pt-2">
            <div className="space-y-1.5">
              <Label className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-semibold">
                API Key <span className="text-loss">*</span>
              </Label>
              <Input
                required
                type="password"
                value={form.api_key}
                onChange={(e) => setForm((s) => ({ ...s, api_key: e.target.value }))}
                data-testid="delta-api-key-input"
                placeholder="paste your Delta API key"
                className="h-9 rounded-sm bg-surface-1 border-border font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-semibold">
                API Secret <span className="text-loss">*</span>
              </Label>
              <Input
                required
                type="password"
                value={form.api_secret}
                onChange={(e) => setForm((s) => ({ ...s, api_secret: e.target.value }))}
                data-testid="delta-api-secret-input"
                placeholder="paste your Delta API secret"
                className="h-9 rounded-sm bg-surface-1 border-border font-mono text-xs"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-semibold">
                Environment
              </Label>
              <Select
                value={form.environment}
                onValueChange={(v) => setForm((s) => ({ ...s, environment: v }))}
              >
                <SelectTrigger className="h-9 rounded-sm bg-surface-1 border-border text-xs">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-surface-2 border-border">
                  {ENVIRONMENTS.map((env) => (
                    <SelectItem key={env.value} value={env.value} className="text-xs">
                      {env.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <DialogFooter className="pt-3">
              <Button type="button" variant="ghost" onClick={() => setSetupOpen(false)} className="rounded-sm h-9 text-xs">
                Cancel
              </Button>
              <Button
                type="submit"
                disabled={busy}
                data-testid="delta-save-btn"
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
