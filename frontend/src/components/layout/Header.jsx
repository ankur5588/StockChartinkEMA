import React from "react";
import { Activity, LogOut, LayoutDashboard, TrendingUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, clearSessionToken } from "@/lib/api";
import { useNavigate, useLocation } from "react-router-dom";

export default function Header({ user }) {
  const navigate = useNavigate();
  const location = useLocation();
  const handleLogout = async () => {
    try {
      await api.post("/auth/logout");
    } catch (e) {}
    clearSessionToken();
    navigate("/login", { replace: true });
  };
  const isIb = location.pathname === "/ib";
  return (
    <header
      className="sticky top-0 z-40 bg-surface-1/95 backdrop-blur border-b border-border"
      data-testid="app-header"
    >
      <div className="max-w-[1600px] mx-auto px-6 h-14 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-7 h-7 rounded-sm bg-brand flex items-center justify-center">
            <Activity className="w-4 h-4 text-white" strokeWidth={2.2} />
          </div>
          <span className="font-mono text-xs tracking-[0.18em] uppercase">
            CHARTINK<span className="text-brand">•</span>TRADE
          </span>
          <nav className="hidden sm:flex items-center gap-1 ml-4">
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/dashboard")}
              className={`h-7 text-[10px] rounded-sm uppercase tracking-wider ${
                !isIb ? "text-white bg-surface-2" : "text-muted-foreground"
              }`}
            >
              <LayoutDashboard className="w-3 h-3 mr-1" />
              Dashboard
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => navigate("/ib")}
              className={`h-7 text-[10px] rounded-sm uppercase tracking-wider ${
                isIb ? "text-white bg-surface-2" : "text-muted-foreground"
              }`}
            >
              <TrendingUp className="w-3 h-3 mr-1" />
              US Stocks
            </Button>
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {user && (
            <div
              className="hidden sm:flex items-center gap-3 border border-border px-3 h-8 rounded-sm bg-surface-2"
              data-testid="user-badge"
            >
              {user.picture && (
                <img
                  src={user.picture}
                  alt=""
                  className="w-5 h-5 rounded-full"
                />
              )}
              <span className="text-xs text-muted-foreground truncate max-w-[140px]">
                {user.email}
              </span>
            </div>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleLogout}
            data-testid="logout-button"
            className="h-8 text-xs rounded-sm"
          >
            <LogOut className="w-3.5 h-3.5 mr-1.5" />
            Sign out
          </Button>
        </div>
      </div>
    </header>
  );
}
