import { api } from "./api";
import { db, deviceId, type EventRecord, type GameRecord } from "./db";

export async function flushSync() {
  if (!navigator.onLine) return;
  const queued = await db.sync_queue.toArray();
  const byGame = new Map<string, EventRecord[]>();
  for (const item of queued) {
    const list = byGame.get(item.game_id) ?? [];
    list.push(item.event);
    byGame.set(item.game_id, list);
  }
  for (const [gameId, events] of byGame) {
    const game = await db.games.get(gameId);
    if (!game) continue;
    try {
      await api("/games", { method: "POST", body: JSON.stringify(gameBody(game)) });
      const result = await api<{ accepted: string[]; duplicates: string[] }>("/games/sync", {
        method: "POST",
        body: JSON.stringify({
          game_id: gameId,
          events: events.map((event) => ({
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
      const done = new Set([...(result.accepted || []), ...(result.duplicates || [])]);
      await db.sync_queue.where("game_id").equals(gameId).filter((item) => done.has(item.event.id)).delete();
    } catch {
      return;
    }
  }
}

export async function finishMatch(game: { id: string }, result: "win" | "loss" | "draw", listName: string) {
  const current = await db.games.get(game.id);
  if (current) {
    const event: EventRecord = {
      id: crypto.randomUUID(),
      game_id: game.id,
      seq: current.seq + 1,
      device_id: deviceId(),
      type: "game_ended",
      payload: { status: "finished", result, list_label: listName },
      created_at: new Date().toISOString(),
    };
    await db.transaction("rw", db.games, db.game_events, db.sync_queue, async () => {
      await db.game_events.add(event);
      await db.games.update(game.id, { seq: event.seq, status: "finished", result, listName, updatedAt: Date.now() });
      await db.sync_queue.add({ game_id: game.id, event });
    });
  }
  await flushSync();
  try {
    await api(`/games/${game.id}`, {
      method: "PATCH",
      body: JSON.stringify({ status: "finished", result, list_label: listName }),
    });
  } catch (err) {
    const status = (err as { status?: number }).status;
    if (status !== 404) throw err;
  }
}

export async function deleteMatch(game: { id: string }) {
  try {
    await api(`/games/${game.id}`, { method: "DELETE", body: JSON.stringify({ confirm: "EXCLUIR" }) });
  } catch (err) {
    const status = (err as { status?: number }).status;
    if (status !== 404) throw err;
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
