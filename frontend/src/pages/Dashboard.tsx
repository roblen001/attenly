// src/pages/Dashboard.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../libs/https";

type User = {
  id: string;
  email: string;
  full_name?: string;
  is_active?: boolean;
  is_verified?: boolean;
  created_at?: string; // ISO
};

function errorMessage(err: unknown): string {
  if (err instanceof Error) return err.message;
  if (typeof err === "string") return err;
  try {
    return JSON.stringify(err);
  } catch {
    return String(err);
  }
}

export default function Dashboard() {
  const navigate = useNavigate();
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  const loadMe = async (signal?: AbortSignal): Promise<void> => {
    setLoading(true);
    setErr(null);
    try {
      const res = await api("/api/auth/me", {
        method: "GET",
        credentials: "include",
        headers: { Accept: "application/json" },
        signal,
      });

      if (res.status === 401 || res.status === 403) {
        navigate("/");
        return;
      }
      if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(`${res.status} ${text}`);
      }

      const me: User = await res.json();
      setUser(me);
    } catch (e: unknown) {
      if ((e as { name?: string })?.name !== "AbortError") {
        setErr(errorMessage(e) || "Failed to load user");
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    void loadMe(controller.signal);
    return () => controller.abort();
  }, []);

  if (loading) return <div style={{ padding: 24 }}>Loading…</div>;

  if (err) {
    return (
      <div style={{ padding: 24 }}>
        <p style={{ color: "crimson", marginBottom: 12 }}>{err}</p>
        <button onClick={() => void loadMe()} style={{ marginRight: 8 }}>
          Retry
        </button>
        <button onClick={() => navigate("/")}>Go to Home</button>
      </div>
    );
  }

  if (!user) return null;

  const created = user.created_at
    ? new Date(user.created_at).toLocaleString()
    : "—";

  return (
    <div style={{ padding: 24 }}>
      <h1>Dashboard</h1>
      <ul>
        <li>
          <b>ID:</b> {user.id}
        </li>
        <li>
          <b>Email:</b> {user.email}
        </li>
        <li>
          <b>Name:</b> {user.full_name || "—"}
        </li>
        <li>
          <b>Active:</b> {user.is_active ? "Yes" : "No"}
        </li>
        <li>
          <b>Verified:</b> {user.is_verified ? "Yes" : "No"}
        </li>
        <li>
          <b>Created:</b> {created}
        </li>
      </ul>

      <div style={{ marginTop: 16, display: "flex", gap: 8 }}>
        <button onClick={() => void loadMe()}>Refresh</button>
        <button
          onClick={async () => {
            try {
              await api("/api/auth/logout", {
                method: "POST",
                credentials: "include",
              });
            } finally {
              navigate("/");
            }
          }}
        >
          Sign out
        </button>
      </div>
    </div>
  );
}
