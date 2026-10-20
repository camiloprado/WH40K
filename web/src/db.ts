import Dexie, { type Table } from "dexie";

export type BundleRecord = { id: number; savedAt: string; payload: any };
export type MetaRecord = { key: string; bundleId?: number; schema?: number };
export type GameRecord = {
  id: string;
  listVersionId: number;
  bundleEtag: string;
  opponentName: string;
  opponentFaction: string;
  missionName: string;
  firstPlayer: "me" | "opponent";
  cpMe: number;
  cpOpponent: number;
  seq: number;
  status: string;
  result?: "win" | "loss" | "draw" | null;
  listName?: string;
  updatedAt: number;
};
export type EventRecord = {
  id: string;
  game_id: string;
  seq: number;
  device_id: string;
  type: string;
  payload: Record<string, any>;
  undoes_event_id?: string | null;
  created_at: string;
};
export type QueueRecord = { localId?: number; game_id: string; event: EventRecord };

class CompanionDB extends Dexie {
  bundles!: Table<BundleRecord, number>;
  meta!: Table<MetaRecord, string>;
  games!: Table<GameRecord, string>;
  game_events!: Table<EventRecord, string>;
  sync_queue!: Table<QueueRecord, number>;

  constructor() {
    super("list-companion");
    this.version(1).stores({
      bundles: "id",
      meta: "key",
      games: "id, status, updatedAt",
      game_events: "id, game_id",
      sync_queue: "++localId, game_id",
    });
  }
}

export const db = new CompanionDB();
export const SUPPORTED_BUNDLE = 1;

export async function saveBundle(payload: any) {
  if (!payload || payload.bundle_schema_version !== SUPPORTED_BUNDLE) {
    throw new Error("schema");
  }
  await db.transaction("rw", db.bundles, db.meta, async () => {
    await db.bundles.put({ id: payload.version.id, savedAt: new Date().toISOString(), payload });
    await db.meta.put({ key: "active_bundle", bundleId: payload.version.id, schema: payload.bundle_schema_version });
  });
}

export async function storeBundle(payload: any) {
  if (!payload || payload.bundle_schema_version !== SUPPORTED_BUNDLE) throw new Error("schema");
  await db.bundles.put({ id: payload.version.id, savedAt: new Date().toISOString(), payload });
}

export async function bundleFor(versionId: number) {
  const row = await db.bundles.get(versionId);
  return row?.payload ?? null;
}

export async function activeBundle() {
  const pointer = await db.meta.get("active_bundle");
  if (!pointer?.bundleId) return null;
  const row = await db.bundles.get(pointer.bundleId);
  return row?.payload ?? null;
}

export function deviceId() {
  const key = "device_id";
  let value = localStorage.getItem(key);
  if (!value) {
    value = crypto.randomUUID();
    localStorage.setItem(key, value);
  }
  return value;
}
