import { api } from "./api";
import { db, deviceId, type EventRecord, type GameRecord } from "./db";

export async function flushSync() {
  if (!navigator.onLine) return;
  const var_lstQueued = await db.sync_queue.toArray();
  const var_dctByGame = new Map<string, EventRecord[]>();
  for (const var_objItem of var_lstQueued) {
    const var_lstEvents = var_dctByGame.get(var_objItem.game_id) ?? [];
    var_lstEvents.push(var_objItem.event);
    var_dctByGame.set(var_objItem.game_id, var_lstEvents);
  }
  for (const [var_strGameId, var_lstEvents] of var_dctByGame) {
    const var_objGame = await db.games.get(var_strGameId);
    if (!var_objGame) continue;
    try {
      await api("/games", { method: "POST", body: JSON.stringify(gameBody(var_objGame)) });
      const var_objResult = await api<{ accepted: string[]; duplicates: string[] }>("/games/sync", {
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
      await db.sync_queue
        .where("game_id")
        .equals(var_strGameId)
        .filter((item) => var_setDone.has(item.event.id))
        .delete();
    } catch {
      return;
    }
  }
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
