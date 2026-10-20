import { create } from "zustand";

type SessionState = { needsAuth: boolean; updateReady: boolean; setNeedsAuth: (value: boolean) => void; setUpdateReady: (value: boolean) => void };
export const useSession = create<SessionState>((set) => ({
  needsAuth: false,
  updateReady: false,
  setNeedsAuth: (needsAuth) => set({ needsAuth }),
  setUpdateReady: (updateReady) => set({ updateReady }),
}));

export class AuthError extends Error {}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  headers.set("X-App", "wh40k");
  const response = await fetch(`/api/v1${path}`, { ...init, headers, credentials: "include" });
  if (response.status === 401) {
    useSession.getState().setNeedsAuth(true);
    throw new AuthError("sessão");
  }
  if (response.status === 304) return null as T;
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: response.statusText, code: "invalid_input" }));
    throw Object.assign(new Error(body.detail || "erro"), { status: response.status, body });
  }
  if (response.status === 204) return null as T;
  const text = await response.text();
  if (!text) return null as T;
  const type = response.headers.get("content-type") || "";
  if (type.includes("application/json")) return JSON.parse(text) as T;
  return text as T;
}

export async function login(token: string) {
  await api("/session", { method: "POST", body: JSON.stringify({ token }) });
  useSession.getState().setNeedsAuth(false);
}

export async function logout() {
  const pending = await import("./db").then(({ db }) => db.sync_queue.count());
  if (pending && !window.confirm("Há eventos pendentes. Sair mesmo assim apaga a cópia local.")) return false;
  await api("/session", { method: "DELETE", body: "{}" }).catch(() => undefined);
  const { db } = await import("./db");
  await db.delete();
  await db.open();
  useSession.getState().setNeedsAuth(true);
  return true;
}
