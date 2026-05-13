import React, { useEffect, useState } from "react";
import "@/App.css";
import {
  BrowserRouter,
  Routes,
  Route,
  useLocation,
  useNavigate,
  Navigate,
} from "react-router-dom";
import { Toaster } from "@/components/ui/sonner";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import { api, setSessionToken, clearSessionToken } from "@/lib/api";

function AuthCallback() {
  const navigate = useNavigate();
  useEffect(() => {
    const hash = window.location.hash || "";
    const match = hash.match(/session_id=([^&]+)/);
    if (!match) {
      navigate("/login", { replace: true });
      return;
    }
    const sessionId = decodeURIComponent(match[1]);

    // Module-level dedup via sessionStorage. Emergent's session_id is single-use;
    // React Strict Mode double-fires effects and would otherwise burn it twice.
    const usedKey = "chartink_session_id_used";
    if (sessionStorage.getItem(usedKey) === sessionId) {
      // Already processed this session_id (e.g. from strict-mode remount). If we
      // already have a token, go to dashboard; otherwise back to login.
      if (localStorage.getItem("chartink_session_token")) {
        navigate("/dashboard", { replace: true });
      } else {
        navigate("/login", { replace: true });
      }
      return;
    }
    sessionStorage.setItem(usedKey, sessionId);

    // Strip the hash from the URL immediately so a hard refresh during the
    // network call doesn't re-trigger this component with the same hash.
    window.history.replaceState(null, "", "/dashboard");

    (async () => {
      try {
        const res = await api.post("/auth/session", { session_id: sessionId });
        if (res.data?.session_token) {
          setSessionToken(res.data.session_token);
        }
        navigate("/dashboard", { replace: true, state: { user: res.data.user } });
      } catch (e) {
        clearSessionToken();
        sessionStorage.removeItem(usedKey);
        navigate("/login", { replace: true, state: { authError: e?.response?.data?.detail || "Login failed" } });
      }
    })();
  }, [navigate]);
  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-1 text-muted-foreground text-sm">
      Signing you in...
    </div>
  );
}

function ProtectedRoute({ children }) {
  const location = useLocation();
  const passedUser = location.state?.user;
  const [auth, setAuth] = useState(passedUser ? true : null);
  const [user, setUser] = useState(passedUser || null);

  useEffect(() => {
    if (passedUser) return;
    (async () => {
      try {
        const res = await api.get("/auth/me");
        setUser(res.data);
        setAuth(true);
      } catch (e) {
        setAuth(false);
      }
    })();
  }, [passedUser]);

  if (auth === null) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-1 text-muted-foreground text-sm">
        Loading...
      </div>
    );
  }
  if (!auth) return <Navigate to="/login" replace />;
  return React.cloneElement(children, { user });
}

function AppRouter() {
  const location = useLocation();
  // Synchronously intercept OAuth redirect callback (session_id in hash)
  if (location.hash?.includes("session_id=")) {
    return <AuthCallback />;
  }
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        path="/dashboard"
        element={
          <ProtectedRoute>
            <Dashboard />
          </ProtectedRoute>
        }
      />
      <Route path="/" element={<Navigate to="/dashboard" replace />} />
      <Route path="*" element={<Navigate to="/dashboard" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AppRouter />
      <Toaster theme="dark" richColors closeButton position="top-right" />
    </BrowserRouter>
  );
}
