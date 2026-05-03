import React, { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Plug, PowerOff, RotateCcw, Settings2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import KotakSetupDialog from "./KotakSetupDialog";
import KotakOtpDialog from "./KotakOtpDialog";

export default function ConnectionCard({ status, reload }) {
  const [setupOpen, setSetupOpen] = useState(false);
  const [otpOpen, setOtpOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const handleLogin = async () => {
    setBusy(true);
    try {
      await api.post("/kotak/login");
      toast.success("OTP / 2FA challenge initiated");
      setOtpOpen(true);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Kotak login failed");
    } finally {
      setBusy(false);
    }
  };

  const handleDisconnect = async () => {
    setBusy(true);
    try {
      await api.post("/kotak/logout");
      toast.success("Disconnected Kotak session");
      reload?.();
    } catch (e) {
      toast.error("Failed to disconnect");
    } finally {
      setBusy(false);
    }
  };

  const handleWipe = async () => {
    if (!window.confirm("Delete saved Kotak credentials from this account?"))
      return;
    setBusy(true);
    try {
      await api.delete("/kotak/credentials");
      toast.success("Credentials deleted");
      reload?.();
    } catch (e) {
      toast.error("Failed to delete credentials");
    } finally {
      setBusy(false);
    }
  };

  const hasCreds = status?.has_credentials;
  const isAuth = status?.is_authenticated;

  return (
    <Card
      className="bg-surface-2 border-border rounded-sm"
      data-testid="connection-card"
    >
      <CardHeader className="pb-3 flex flex-row items-start justify-between space-y-0">
        <div>
          <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground mb-1 font-semibold">
            / broker
          </div>
          <CardTitle className="text-lg font-medium">Kotak Neo</CardTitle>
        </div>
        <StatusPill isAuth={isAuth} hasCreds={hasCreds} />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 gap-3 pt-1">
          <Stat
            label="Credentials"
            value={hasCreds ? "saved" : "missing"}
            tone={hasCreds ? "ok" : "warn"}
          />
          <Stat
            label="Session"
            value={isAuth ? "active" : "inactive"}
            tone={isAuth ? "ok" : "warn"}
          />
        </div>

        <div className="flex flex-wrap gap-2 pt-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSetupOpen(true)}
            data-testid="edit-credentials-button"
            className="rounded-sm h-8 text-xs border-border bg-surface-1 hover:bg-surface-3"
          >
            <Settings2 className="w-3.5 h-3.5 mr-1.5" />
            {hasCreds ? "Edit creds" : "Add credentials"}
          </Button>
          {hasCreds && !isAuth && (
            <Button
              size="sm"
              onClick={handleLogin}
              disabled={busy}
              data-testid="kotak-login-button"
              className="rounded-sm h-8 text-xs bg-brand hover:bg-brand/90 text-white"
            >
              <Plug className="w-3.5 h-3.5 mr-1.5" />
              Connect
            </Button>
          )}
          {hasCreds && isAuth && (
            <>
              <Button
                size="sm"
                variant="outline"
                onClick={handleLogin}
                disabled={busy}
                data-testid="kotak-relogin-button"
                className="rounded-sm h-8 text-xs border-border bg-surface-1 hover:bg-surface-3"
              >
                <RotateCcw className="w-3.5 h-3.5 mr-1.5" />
                Re-login
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={handleDisconnect}
                disabled={busy}
                data-testid="kotak-disconnect-button"
                className="rounded-sm h-8 text-xs text-muted-foreground hover:text-loss"
              >
                <PowerOff className="w-3.5 h-3.5 mr-1.5" />
                Disconnect
              </Button>
            </>
          )}
          {hasCreds && (
            <Button
              size="sm"
              variant="ghost"
              onClick={handleWipe}
              disabled={busy}
              data-testid="kotak-wipe-button"
              className="rounded-sm h-8 text-xs text-muted-foreground hover:text-loss ml-auto"
            >
              Wipe vault
            </Button>
          )}
        </div>
      </CardContent>

      <KotakSetupDialog
        open={setupOpen}
        onOpenChange={setSetupOpen}
        reload={reload}
      />
      <KotakOtpDialog
        open={otpOpen}
        onOpenChange={setOtpOpen}
        reload={reload}
      />
    </Card>
  );
}

function StatusPill({ isAuth, hasCreds }) {
  let color = "#737373";
  let text = "not configured";
  if (hasCreds && isAuth) {
    color = "#00C805";
    text = "authenticated";
  } else if (hasCreds) {
    color = "#FF9F0A";
    text = "needs login";
  }
  return (
    <div
      className="flex items-center gap-2 border border-border px-2.5 h-7 rounded-sm bg-surface-1 font-mono text-[10px] uppercase tracking-wider"
      data-testid="connection-status-pill"
    >
      <span
        className="w-1.5 h-1.5 rounded-full pulse-dot"
        style={{ backgroundColor: color }}
      />
      <span style={{ color }}>{text}</span>
    </div>
  );
}

function Stat({ label, value, tone = "default" }) {
  const color =
    tone === "ok" ? "text-profit" : tone === "warn" ? "text-warn" : "text-white";
  return (
    <div className="border border-border p-3 bg-surface-1 rounded-sm">
      <div className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
        {label}
      </div>
      <div className={`mt-1 font-mono text-sm ${color}`}>{value}</div>
    </div>
  );
}
