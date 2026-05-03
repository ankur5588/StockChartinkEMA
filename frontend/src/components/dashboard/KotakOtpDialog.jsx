import React, { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import {
  InputOTP,
  InputOTPGroup,
  InputOTPSlot,
} from "@/components/ui/input-otp";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import { api } from "@/lib/api";

export default function KotakOtpDialog({ open, onOpenChange, reload }) {
  const [otp, setOtp] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e?.preventDefault?.();
    if (otp.length < 4) {
      toast.error("Enter your OTP / MPIN");
      return;
    }
    setBusy(true);
    try {
      await api.post("/kotak/verify-otp", { otp });
      toast.success("Kotak Neo session established");
      onOpenChange(false);
      setOtp("");
      reload?.();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "OTP verification failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="bg-surface-2 border-border rounded-sm sm:max-w-md"
        data-testid="kotak-otp-dialog"
      >
        <DialogHeader>
          <DialogTitle className="font-medium tracking-tight">
            2-Factor Authentication
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            Enter the OTP sent to your registered mobile, or your MPIN,
            depending on your Kotak Neo account 2FA setup.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4 pt-2">
          <div className="space-y-2">
            <Label className="text-[10px] uppercase tracking-[0.15em] text-muted-foreground font-semibold">
              Code
            </Label>
            <InputOTP
              maxLength={6}
              value={otp}
              onChange={setOtp}
              data-testid="kotak-otp-input"
            >
              <InputOTPGroup>
                {Array.from({ length: 6 }).map((_, i) => (
                  <InputOTPSlot
                    key={i}
                    index={i}
                    className="rounded-sm border-border font-mono bg-surface-1"
                  />
                ))}
              </InputOTPGroup>
            </InputOTP>
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              className="rounded-sm h-9 text-xs"
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={busy}
              data-testid="verify-otp-button"
              className="rounded-sm h-9 text-xs bg-brand hover:bg-brand/90 text-white"
            >
              {busy ? "Verifying..." : "Verify"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
