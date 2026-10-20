import { api } from "./api";
import { db, deviceId, type EventRecord, type GameRecord } from "./db";

export type SyncChip = "offline" | "server_down" | "syncing" | "ok" | "rejected";

let var_intRejected = 0;
let var_boolServerDown = false;
let var_intBackoffMs = 30_000;
let var_intTimer: number | null = null;
const var_lstListeners = new Set<() => void>();

function notify() {
  for (const fn of var_lstListeners) fn();
}

export function syncRejectedCount() {
  return var_intRejected;
}

export function syncServerDown() {
  return var_boolServerDown;
}

export function onSyncStatus(fn: () => void) {
  var_lstListeners.add(fn);
  return () => var_lstListeners.delete(fn);
}

function scheduleRetry() {
  if (var_intTimer != null) return;
  var_intTimer = window.setTimeout(() => {
    var_intTimer = null;
    void flushSync();
  }, var_intBackoffMs);
  var_intBackoffMs = Math.min(300_000, Math.floor(var_intBackoffMs * 1.5));
}

export async function flushSync() {
  if (!navigator.onLine) {
    var_boolServerDown = false;
    notify();
    return;
  }
  const var_lstQueued = await db.sync_queue.toArray();
  if (!var_lstQueued.length) {
    var_boolServerDown = false;
    var_intBackoffMs = 30_000;
    notify();
    return;
  }
  const var_dctByGame = new Map<string, EventRecord[]>();
  for (const var_objItem of var_lstQueued) {
    const var_lstEvents = var_dctByGame.get(var_objItem.game_id) ?? [];
    var_lstEvents.push(var_objItem.event);
    var_dctByGame.set(var_objItem.game_id, var_lstEvents);
  }
  let var_intRejectedTotal = 0;
  for (const [var_strGameId, var_lstEvents] of var_dctByGame) {
    const var_objGame = await db.games.get(var_strGameId);
    if (!var_objGame) continue;
    try {
      await api("/games", { method: "POST", body: JSON.stringify(gameBody(var_objGame)) });
      const var_objResult = await api<{
        accepted: string[];
        duplicates: string[];
        rejected?: { id: string; reason: string }[];
      }>("/games/sync", {
        method: "POST",
        body: JSON.stringify({
          game_id: var_strGameId,
          events: var_lstEvents.map((event) => ({
            id: event.id,
            seq: event.seq,
            device_id: event.device_id,
            type: event.type,
            payload: event.payload,
            undoes_event_id: event.undoes_event_id ?? null,
            created_at: event.created_at,
          })),
        }),
      });
      const var_setDone = new Set([...(var_objResult.accepted || []), ...(var_objResult.duplicates || [])]);
      const var_setRejectedIds = new Set((var_objResult.rejected || []).map((item) => item.id));
      var_intRejectedTotal += var_setRejectedIds.size;
      await db.sync_queue
        .where("game_id")
        .equals(var_strGameId)
        .filter((item) => var_setDone.has(item.event.id) || var_setRejectedIds.has(item.event.id))
        .delete();
      var_boolServerDown = false;
      var_intBackoffMs = 30_000;
      notify();
    } catch (err) {
      const var_intStatus = Number((err as { status?: number }).status || 0);
      // BG2: 4xx de validação → rejeitados (não "Servidor fora").
      if (var_intStatus >= 400 && var_intStatus < 500 && var_intStatus !== 401) {
        var_intRejectedTotal += var_lstEvents.length;
        await db.sync_queue.where("game_id").equals(var_strGameId).delete();
        var_boolServerDown = false;
        notify();
        continue;
      }
      var_boolServerDown = true;
      notify();
      scheduleRetry();
      return;
    }
  }
  var_intRejected = var_intRejectedTotal;
  notify();
  const var_intLeft = await db.sync_queue.count();
  if (var_intLeft) scheduleRetry();
}

if (typeof window !== "undefined") {
  window.addEventListener("online", () => {
    void flushSync();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") void flushSync();
  });
}

export async function finishMatch(game: { id: string }, result: "win" | "loss" | "draw", listName: string) {
  const var_objCurrent = await db.games.get(game.id);
  if (var_objCurrent) {
    const var_objEvent: EventRecord = {
      id: crypto.randomUUID(),
      game_id: game.id,
      seq: var_objCurrent.seq + 1,
      device_id: deviceId(),
      type: "game_ended",
      payload: { status: "finished", result, list_label: listName },
      created_at: new Date().toISOString(),
    };
    await db.transaction("rw", db.games, db.game_events, db.sync_queue, async () => {
      await db.game_events.add(var_objEvent);
      await db.games.update(game.id, {
        seq: var_objEvent.seq,
        status: "finished",
        result,
        listName,
        updatedAt: Date.now(),
      });
      await db.sync_queue.add({ game_id: game.id, event: var_objEvent });
    });
  }
  await flushSync();
  try {
    await api(`/games/${game.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "finished", result, list_label: listName }),
    });
  } catch (err) {
    const var_intStatus = (err as { status?: number }).status;
    if (var_intStatus !== 404) throw err;
  }
}

export async function deleteMatch(game: { id: string }) {
  try {
    await api(`/games/${game.id}`, { method: "DELETE", body: JSON.stringify({ confirm: "EXCLUIR" }) });
  } catch (err) {
    const var_intStatus = (err as { status?: number }).status;
    if (var_intStatus !== 404) throw err;
  }
  await db.transaction("rw", db.games, db.game_events, db.sync_queue, async () => {
    await db.game_events.where("game_id").equals(game.id).delete();
    await db.sync_queue.where("game_id").equals(game.id).delete();
    await db.games.delete(game.id);
  });
}

function gameBody(game: GameRecord) {
  return {
    id: game.id,
    list_version_id: game.listVersionId,
    bundle_etag: game.bundleEtag,
    first_player: game.firstPlayer,
    opponent_name: game.opponentName,
    opponent_faction: game.opponentFaction,
    mission_name: game.missionName,
    cp_me: game.cpMe,
    cp_opponent: game.cpOpponent,
  };
}
