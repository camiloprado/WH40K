import { create } from "zustand";

type SessionState = {
  needsAuth: boolean;
  updateReady: boolean;
  setNeedsAuth: (value: boolean) => void;
  setUpdateReady: (value: boolean) => void;
};
export const useSession = create<SessionState>((set) => ({
  needsAuth: false,
  updateReady: false,
  setNeedsAuth: (needsAuth) => set({ needsAuth }),
  setUpdateReady: (updateReady) => set({ updateReady }),
}));

export class AuthError extends Error {}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const var_objHeaders = new Headers(init.headers);
  if (init.body && !var_objHeaders.has("Content-Type")) var_objHeaders.set("Content-Type", "application/json");
  var_objHeaders.set("X-App", "wh40k");
  const var_objResponse = await fetch(`/api/v1${path}`, { ...init, headers: var_objHeaders, credentials: "include" });
  if (var_objResponse.status === 401) {
    useSession.getState().setNeedsAuth(true);
    throw new AuthError("sessão");
  }
  if (var_objResponse.status === 304) return null as T;
  if (!var_objResponse.ok) {
    const var_objBody = await var_objResponse.json().catch(() => ({
      detail: var_objResponse.statusText,
      code: "invalid_input",
    }));
    throw Object.assign(new Error(var_objBody.detail || "erro"), { status: var_objResponse.status, body: var_objBody });
  }
  if (var_objResponse.status === 204) return null as T;
  const var_strText = await var_objResponse.text();
  if (!var_strText) return null as T;
  const var_strType = var_objResponse.headers.get("content-type") || "";
  if (var_strType.includes("application/json")) return JSON.parse(var_strText) as T;
  return var_strText as T;
}

export async function login(token: string) {
  await api("/session", { method: "POST", body: JSON.stringify({ token }) });
  useSession.getState().setNeedsAuth(false);
}

export async function logout() {
  const var_intPending = await import("./db").then(({ db }) => db.sync_queue.count());
  if (var_intPending) {
    const { askConfirm } = await import("./confirm");
    if (!(await askConfirm("Há eventos pendentes. Sair mesmo assim apaga a cópia local."))) return false;
  }
  await api("/session", { method: "DELETE", body: "{}" }).catch(() => undefined);
  const { db } = await import("./db");
  await db.delete();
  await db.open();
  useSession.getState().setNeedsAuth(true);
  return true;
}
