import { useCallback, useEffect, useMemo, useRef, useState, type DragEvent, type ReactNode } from "react";
import { useLiveQuery } from "dexie-react-hooks";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "./api";
import { askConfirm } from "./confirm";
import { bundleFor, db, deviceId, storeBundle, type EventRecord } from "./db";
import {
  activeChoice,
  applyEvents,
  isChoiceActive,
  LANES,
  PHASES,
  PHASES_V2,
  shadowNow,
  zoneOf,
  type Choice,
  type Lane,
  type LiveUnit,
  type LogEntry,
  type Projection,
  type Zone,
} from "./engine/project";
import {
  canStartAction,
  conditionLabel,
  evaluateUnit,
  guideMatch,
  type Eligibility,
  type Moved,
} from "./engine/eligibility";
import { flushSync, onSyncStatus, syncRejectedCount, syncServerDown } from "./sync";
import { ConditionalBadge, HypothesisBadge } from "./components";

const PHASE_NAMES: Record<string, string> = {
  round_start: "Início",
  command: "Command",
  battle_shock: "Battle-shock",
  movement: "Movement",
  shooting: "Shooting",
  charge: "Charge",
  fight: "Fight",
  end_of_turn: "Fim do turno",
  end_of_round: "Fim da rodada",
};

const MOVES: [Moved, string][] = [
  ["normal", "Normal"],
  ["advanced", "Avançou"],
  ["fell_back", "Recuou"],
  ["remained", "Parado"],
];

const MOVE_LETTER: Record<string, string> = { none: "·", normal: "N", advanced: "A", fell_back: "R", remained: "P" };
const OBJECTIVES = ["1", "2", "3", "4", "5", "6"];
const LANE_NAMES: Record<Lane, string> = { left: "Esquerda", center: "Centro", right: "Direita", home: "Home" };
const FRONT_LANES: Lane[] = ["left", "center", "right"];
const PERSONAL_KINDS = new Set(["unit", "leader", "enhancement"]);
const TIMING_NAMES: Record<string, string> = { start: "Início", during: "Durante", end: "Fim" };
const SCOPE_NAMES: Record<string, string> = {
  turn: "neste turno",
  round: "nesta rodada",
  battle: "na batalha",
  until_own_command: "até seu próximo Command",
};

type Place = Lane | "reserves" | "destroyed";
const PLACES: Place[] = [...LANES, "reserves", "destroyed"];
const PLACE_NAMES: Record<Place, string> = { ...LANE_NAMES, reserves: "Reserva", destroyed: "Destruídas" };

export type PhaseEffect = {
  id: number;
  ability_id: number;
  ability_name: string;
  owner_label: string;
  effect_text: string;
  timing: string;
  is_hypothesis: boolean;
  is_conditional?: boolean;
  condition_text?: string;
  unit_ids: number[];
  choice_options: string[];
  choice_count: number | null;
  choice_scope: "turn" | "round" | "battle" | "until_own_command";
};

type Card = { unit: any; live: LiveUnit; result: Eligibility; zone: Zone; place: Place; order: number; effects: PhaseEffect[]; chosen: string[] };
type ChoiceLookup = (effect: PhaseEffect, unitId: number | null) => Choice | undefined;

function phaseEffects(
  bundle: any,
  phase: string,
  mine: boolean,
  shadowAreas: string[],
  shadowComplete: boolean,
): PhaseEffect[] {
  const abilities = new Map<number, any>((bundle.abilities || []).map((item: any) => [item.id, item]));
  const units: any[] = bundle.units || [];
  const facts = {
    shadow_areas: shadowAreas.length ? shadowAreas : ["own_dz"],
    shadow_areas_complete: shadowComplete,
    turn_owner: mine ? "own" : "opponent",
    phase,
  };
  return (bundle.rule_effects || [])
    .filter((effect: any) => effect.effect_kind !== "stratagem")
    .filter((effect: any) => effect.phase === phase || effect.phase === "any")
    .filter((effect: any) => effect.turn_owner === "both" || (effect.turn_owner === "opponent") !== mine)
    .map((effect: any) => {
      const ability = abilities.get(effect.ability_id);
      const gate = guideMatch(effect.condition_json || {}, facts);
      if (!gate.include) return null;
      let unitIds: number[] = effect.unit_ids || [];
      if (!unitIds.length && ability && PERSONAL_KINDS.has(ability.kind) && ability.datasheet_id) {
        unitIds = units.filter((unit) => unit.datasheet_id === ability.datasheet_id).map((unit) => unit.id);
      }
      return {
        id: effect.id,
        ability_id: effect.ability_id,
        ability_name: ability?.name || effect.owner_label,
        owner_label: effect.owner_label,
        effect_text: effect.effect_text,
        timing: effect.timing || "during",
        is_hypothesis: Boolean(effect.is_hypothesis || ability?.is_hypothesis),
        is_conditional: gate.conditional,
        condition_text: gate.conditional ? conditionLabel(effect.condition_json || {}) : "",
        unit_ids: unitIds,
        choice_options: effect.choice_options || [],
        choice_count: effect.choice_count ?? null,
        choice_scope: effect.choice_scope || "turn",
      } as PhaseEffect;
    })
    .filter(Boolean)
    .sort((a: PhaseEffect, b: PhaseEffect) => ["start", "during", "end"].indexOf(a.timing) - ["start", "during", "end"].indexOf(b.timing)) as PhaseEffect[];
}
type Menu = { x: number; y: number; unitId: number } | null;

const BLANK: LiveUnit = {
  list_unit_id: 0,
  name: "",
  round: 1,
  moved: "none",
  shot: false,
  charged: false,
  fought: false,
  engaged: false,
  engaged_at_fight_start: false,
  on_action: false,
  action_name: null,
  battle_shocked: false,
  below_half: false,
  destroyed: false,
  in_reserves: false,
  must_ingress: false,
  action_started_moved: null,
  snap_shooting: false,
  fall_back_mode: null,
  lane: "center",
  overrides: [],
};

export function GameScreen() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const events = useLiveQuery(() => db.game_events.where("game_id").equals(id).toArray(), [id], []);
  const game = useLiveQuery(() => db.games.get(id), [id]);
  const pending = useLiveQuery(() => db.sync_queue.where("game_id").equals(id).count(), [id], 0);
  const [bundle, setBundle] = useState<any>(null);
  const [missing, setMissing] = useState(false);
  const [online, setOnline] = useState(navigator.onLine);
  const [rejected, setRejected] = useState(0);
  const [serverDown, setServerDown] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [menu, setMenu] = useState<Menu>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [advanceConfirm, setAdvanceConfirm] = useState<string[] | null>(null);
  const [wake, setWake] = useState(typeof navigator.wakeLock?.request === "function");
  const toastTimer = useRef<number>();

  useEffect(() => {
    if (!game) return;
    let alive = true;
    bundleFor(game.listVersionId).then(async (stored) => {
      if (stored && alive) setBundle(stored);
      try {
        const fetched = await api<any>(`/versions/${game.listVersionId}/bundle`);
        await storeBundle(fetched);
        if (alive) setBundle(fetched);
      } catch {
        if (alive && !stored) setMissing(true);
      }
    });
    return () => {
      alive = false;
    };
  }, [game?.listVersionId]);

  useEffect(() => {
    const on = () => setOnline(navigator.onLine);
    window.addEventListener("online", on);
    window.addEventListener("offline", on);
    const refresh = () => {
      setRejected(syncRejectedCount());
      setServerDown(syncServerDown());
    };
    refresh();
    const off = onSyncStatus(refresh);
    let lock: { release: () => Promise<void> } | null = null;
    const requestWake = () => {
      navigator.wakeLock
        ?.request("screen")
        .then((value) => {
          lock = value;
          setWake(true);
          value.addEventListener("release", () => setWake(false));
        })
        .catch(() => setWake(false));
    };
    requestWake();
    const onVis = () => {
      if (document.visibilityState === "visible") requestWake();
    };
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", on);
      document.removeEventListener("visibilitychange", onVis);
      off();
      lock?.release();
    };
  }, []);

  const projection = useMemo(() => applyEvents(events || []), [events]);
  const phase = projection.phase;
  const phaseList = projection.phasesV >= 2 ? [...PHASES_V2] : [...PHASES];
  const effectsNow = useMemo(() => {
    if (!bundle) return [];
    const shadow = shadowNow(projection);
    const areas = ["own_dz", ...(shadow.nml ? ["nml"] : []), ...(shadow.opp_dz ? ["opp_dz"] : [])];
    return phaseEffects(bundle, phase, projection.player === "me", areas, shadow.known);
  }, [bundle, phase, projection]);

  const cards: Card[] = useMemo(() => {
    if (!bundle) return [];
    return (bundle.units as any[]).map((unit, order) => {
      const live = projection.live[unit.id] || { ...BLANK, list_unit_id: unit.id, name: unit.datasheet_name };
      const var_objShadow = shadowNow(projection);
      const var_boolLeading = (bundle.attachments || []).some((item: any) => item.leader_list_unit_id === unit.id);
      const result = evaluateUnit({
        phase,
        unit: live,
        weapons: (unit.wargear || []).map((item: any) => ({ name: item.weapon_name, keywords: item.keywords || [], kind: item.kind })),
        unitKeywords: unit.keywords || [],
        effects: bundle.rule_effects || [],
        activePlayer: projection.player === "opponent" ? "opponent" : "me",
        game: {
          round: projection.round,
          firstPlayer: projection.firstPlayer === "opponent" ? "opponent" : "me",
          turnOwner: projection.player === "me" ? "own" : "opponent",
          isLeading: var_boolLeading,
          hasDeepStrike: (unit.keywords || []).some((item: string) => item.toUpperCase() === "DEEP STRIKE"),
          hasWarpRifts: (unit.keywords || []).some((item: string) => item.toUpperCase() === "WARP RIFTS"),
          shadow: [
            "own_dz",
            ...(var_objShadow.nml ? ["nml"] : []),
            ...(var_objShadow.opp_dz ? ["opp_dz"] : []),
          ],
        },
      });
      const zone = zoneOf(live);
      const place: Place = zone === "table" ? live.lane || "center" : zone;
      const effects = effectsNow.filter((effect) => effect.unit_ids.includes(unit.id));
      const chosen = projection.choices
        .filter((item) =>
          item.list_unit_id === unit.id &&
          isChoiceActive(item, projection.round, projection.player, projection.phase, projection.firstPlayer),
        )
        .flatMap((item) => item.options);
      return { unit, live, result, zone, place, order, effects, chosen };
    });
  }, [bundle, projection, phase, effectsNow]);

  const flash = useCallback((message: string) => {
    setToast(message);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 6000);
  }, []);

  useEffect(() => {
    if (projection.warnings.includes("reserves_destroyed")) {
      flash("Reserva ainda fora na R3: marque como destruída (reserves_destroyed)");
    }
  }, [projection.warnings, flash]);

  const push = useCallback(
    async (type: string, payload: Record<string, unknown>, label?: string) => {
      const event: EventRecord = {
        id: crypto.randomUUID(),
        game_id: id,
        seq: 0,
        device_id: deviceId(),
        type,
        payload,
        undoes_event_id: typeof payload.undoes_event_id === "string" ? payload.undoes_event_id : null,
        created_at: new Date().toISOString(),
      };
      await db.transaction("rw", db.game_events, db.games, db.sync_queue, async () => {
        const current = await db.games.get(id);
        event.seq = (current?.seq || 0) + 1;
        await db.game_events.add(event);
        await db.games.update(id, { seq: event.seq, updatedAt: Date.now() });
        await db.sync_queue.add({ game_id: id, event });
      });
      if (label) flash(label);
      flushSync();
    },
    [id, flash],
  );

  const lastAction = useMemo(
    () => [...projection.log].reverse().find((item) => !item.undone && item.type !== "undo" && item.type !== "game_started"),
    [projection.log],
  );

  const undo = useCallback(() => {
    if (lastAction) push("undo", { undoes_event_id: lastAction.id }, "Desfeito");
  }, [lastAction, push]);

  const doAdvance = useCallback(() => {
    setAdvanceConfirm(null);
    return push("phase_advanced", {});
  }, [push]);

  const pendingUnits = useMemo(() => {
    const actionPhases = new Set(["movement", "shooting", "charge", "fight"]);
    if (!actionPhases.has(phase) || projection.player !== "me") return [];
    return cards.filter(
      (item) => item.zone === "table" && (item.result.status === "active" || item.result.status === "warn"),
    );
  }, [cards, phase, projection.player]);

  const advance = useCallback(() => {
    if (pendingUnits.length) {
      setAdvanceConfirm(pendingUnits.map((item) => item.unit.datasheet_name));
      return;
    }
    void doAdvance();
  }, [pendingUnits, doAdvance]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
      if (event.key === "Escape") {
        setMenu(null);
        setSelected(null);
        setAdvanceConfirm(null);
      } else if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
        event.preventDefault();
        undo();
      } else if (event.key.toLowerCase() === "n" && !event.ctrlKey && !event.metaKey) {
        advance();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, advance]);

  if (missing) {
    return (
      <main className="screen stack">
        <p className="card">Esta partida usa uma lista que não está neste aparelho. Conecte e prepare a cópia offline.</p>
        {game?.listVersionId != null && (
          <Link className="btn primary" to={`/versions/${game.listVersionId}`}>
            Preparar agora
          </Link>
        )}
      </main>
    );
  }
  if (!game || !bundle) return <main className="screen">Carregando partida…</main>;

  const names = new Map<number, string>((bundle.units as any[]).map((unit) => [unit.id, unit.datasheet_name]));
  const leaderOf = new Map<number, number>();
  const ledBy = new Map<number, number>();
  for (const pair of bundle.attachments || []) {
    leaderOf.set(pair.leader_list_unit_id, pair.bodyguard_list_unit_id);
    ledBy.set(pair.bodyguard_list_unit_id, pair.leader_list_unit_id);
  }
  const mine = projection.player === "me";
  const selectedCard = cards.find((item) => item.unit.id === selected) || null;

  function setUnit(unitId: number, patch: Record<string, unknown>, label: string, overrides?: { key: string }[]) {
    push("unit_state_set", overrides ? { list_unit_id: unitId, patch, overrides } : { list_unit_id: unitId, patch }, `${names.get(unitId)}: ${label}`);
  }

  function overrideKeys(card: Card): { key: string }[] {
    const keys: string[] = [];
    if (!mine) {
      // Fire Overwatch: fim da Movement do oponente (Core 15.08), não no Shooting (C11).
      if (phase === "movement") keys.push("overwatch", "rapid_ingress", "reactive_move");
      if (phase === "charge") keys.push("heroic_intervention");
    }
    if (phase === "shooting") {
      if (card.live.moved === "advanced") keys.push("shoot_after_advance");
      if (card.live.moved === "fell_back") keys.push("shoot_after_fall_back");
      if (card.live.engaged) keys.push("shoot_engaged");
      if (card.live.on_action) keys.push("shoot_on_action");
    }
    if (phase === "charge") {
      if (card.live.moved === "advanced") keys.push("charge_after_advance");
      if (card.live.moved === "fell_back") keys.push("charge_after_fall_back");
    }
    if (phase === "movement") {
      if (card.live.moved === "advanced") keys.push("action_after_advance");
      if (card.live.moved === "fell_back") keys.push("action_after_fall_back");
    }
    if (phase === "fight") keys.push("fight_again");
    return keys.map((key) => ({ key }));
  }

  async function primary(card: Card) {
    const flag = phase === "shooting" ? "shot" : phase === "charge" ? "charged" : phase === "fight" ? "fought" : null;
    if (!flag) {
      setSelected(card.unit.id);
      return;
    }
    const label = flag === "shot" ? "Atirou" : flag === "charged" ? "Carregou" : "Lutou";
    if (card.live[flag as keyof LiveUnit]) {
      setUnit(card.unit.id, { [flag]: false }, `${label} desmarcado`);
      return;
    }
    if (card.result.status === "inactive") {
      if (!(await askConfirm(`${card.result.reasons.join(" · ")}. Registrar mesmo assim?`))) return;
      setUnit(card.unit.id, { [flag]: true }, `${label} (override)`, overrideKeys(card));
      return;
    }
    setUnit(card.unit.id, { [flag]: true }, label);
  }

  function moveTo(unitId: number, place: Place) {
    const live = projection.live[unitId];
    if (live?.in_reserves && place !== "reserves" && place !== "destroyed" && live.engaged) {
      flash("Engajada em reserva: Realm of Chaos / Warp Rifts — resolva engajamento antes do ingress");
    }
    const patch =
      place === "destroyed"
        ? { destroyed: true, in_reserves: false }
        : place === "reserves"
          ? { destroyed: false, in_reserves: true }
          : { destroyed: false, in_reserves: false, lane: place };
    setUnit(unitId, patch, `para ${PLACE_NAMES[place]}`);
  }

  const choiceFor = (effect: PhaseEffect, unitId: number | null) =>
    activeChoice(
      projection.choices,
      effect.id,
      unitId,
      effect.choice_scope,
      projection.round,
      projection.player,
      projection.phase,
      projection.firstPlayer,
    );

  function choose(effect: PhaseEffect, unitId: number | null, options: string[]) {
    const who = unitId ? `${names.get(unitId)} · ` : "";
    push(
      "effect_chosen",
      { effect_id: effect.id, ability_id: effect.ability_id, list_unit_id: unitId, options, count: effect.choice_count, scope: effect.choice_scope, player: projection.player },
      `${who}${effect.ability_name}: ${options.join(", ")}`,
    );
  }

  const generalEffects = effectsNow.filter((effect) => !effect.unit_ids.length);
  const abilityName = new Map<number, string>((bundle.abilities || []).map((item: any) => [item.id, item.name]));
  const effectName = new Map<number, string>((bundle.rule_effects || []).map((item: any) => [item.id, abilityName.get(item.ability_id) || item.owner_label]));
  const generalActive = projection.choices.filter(
    (item) =>
      item.list_unit_id == null &&
      isChoiceActive(item, projection.round, projection.player, projection.phase, projection.firstPlayer) &&
      !generalEffects.some((effect) => effect.id === item.effect_id),
  );

  async function jumpTo(target: string) {
    const from = phaseList.indexOf(phase as (typeof phaseList)[number]);
    const to = phaseList.indexOf(target as (typeof phaseList)[number]);
    if (to <= from) return;
    for (let step = from; step < to; step += 1) await push("phase_advanced", {});
  }

  const pendingIds = new Set(pendingUnits.map((item) => item.unit.id));
  const byPlace = (place: Place) =>
    cards
      .filter((item) => item.place === place)
      .sort((a, b) => {
        const ap = pendingIds.has(a.unit.id) ? 0 : 1;
        const bp = pendingIds.has(b.unit.id) ? 0 : 1;
        if (ap !== bp) return ap - bp;
        return a.order - b.order;
      });
  const byZone = (zone: Zone) => cards.filter((item) => item.zone === zone);

  const renderLane = (lane: Lane) => (
    <ZoneArea key={lane} place={lane} count={byPlace(lane).length} onDropUnit={moveTo} lane>
      {byPlace(lane).map((card) => (
        <UnitCard
          key={card.unit.id}
          card={card}
          phase={phase}
          mine={mine}
          selected={selected === card.unit.id}
          choiceFor={choiceFor}
          leads={leaderOf.has(card.unit.id) ? names.get(leaderOf.get(card.unit.id)!) : undefined}
          ledBy={ledBy.has(card.unit.id) ? names.get(ledBy.get(card.unit.id)!) : undefined}
          onSelect={() => setSelected(card.unit.id)}
          onPrimary={() => primary(card)}
          onMenu={(x, y) => setMenu({ x, y, unitId: card.unit.id })}
        />
      ))}
    </ZoneArea>
  );

  const unmoved = cards.filter((item) => item.zone === "table" && item.live.moved === "none").length;

  return (
    <div
      className="table-app"
      style={{
        ["--phase" as string]: `var(--${phase})`,
        ["--on-phase" as string]: `var(--on-${phase})`,
        ["--accent" as string]: bundle.list?.accent_color,
      }}
      onClick={() => setMenu(null)}
    >
      <PhaseRail
        phase={phase}
        phases={phaseList}
        mine={mine}
        pendingCount={pendingUnits.length}
        onPick={jumpTo}
        onNext={advance}
        onPending={() => {
          const first = pendingUnits[0];
          if (!first) return;
          setSelected(first.unit.id);
          requestAnimationFrame(() => {
            document.querySelector(`[data-unit="${first.unit.id}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
          });
        }}
      />
      {advanceConfirm && (
        <div className="sheet-confirm" role="dialog" aria-modal>
          <p>
            {advanceConfirm.length} unidade{advanceConfirm.length > 1 ? "s" : ""} ainda pode
            {advanceConfirm.length > 1 ? "m" : ""} agir: {advanceConfirm.slice(0, 5).join(", ")}
            {advanceConfirm.length > 5 ? "…" : ""}
          </p>
          <div className="row">
            <button className="ghost" onClick={() => setAdvanceConfirm(null)}>
              Voltar
            </button>
            <button className="primary" onClick={() => void doAdvance()}>
              Avançar mesmo assim
            </button>
          </div>
        </div>
      )}

      <section className="board">
        <PlayerBar
          side="opponent"
          title={game.opponentName ? `Oponente · ${game.opponentName}` : "Oponente"}
          active={!mine}
          cp={projection.cp.opponent}
          vp={projection.vp.opponent}
          onCp={(delta) =>
            push("cp_changed", { delta, player: "opponent", reason: "manual", event_rules: false }, `CP do oponente ${delta > 0 ? "+1" : "−1"}`)
          }
          onVp={(delta) => push("vp_scored", { player: "opponent", kind: "other", label: "Ajuste", vp: delta }, `VP do oponente ${delta > 0 ? "+1" : "−1"}`)}
        />

        <div className="board-scroll">
        <section className="zone zone-table" aria-label="Mesa">
          <div className="zone-head">
            <span>
              Mesa <span className="muted mono">{byZone("table").length}</span>
            </span>
            {phase === "movement" && mine && unmoved > 0 && (
              <button className="ghost" onClick={() => byZone("table").filter((item) => item.live.moved === "none").forEach((item) => setUnit(item.unit.id, { moved: "remained" }, "Parado"))}>
                {unmoved} sem mover · marcar como Parado
              </button>
            )}
          </div>
          <div className="lanes">
            {FRONT_LANES.map(renderLane)}
          </div>
          <div className="home-lane">{renderLane("home")}</div>
        </section>

        <div className="zone-row">
          {(["reserves", "destroyed"] as Place[]).map((zone) => (
            <ZoneArea key={zone} place={zone} count={byPlace(zone).length} onDropUnit={moveTo} compact>
              {byPlace(zone).map((card) => (
                <UnitCard
                  key={card.unit.id}
                  card={card}
                  phase={phase}
                  compact
                  choiceFor={choiceFor}
                  selected={selected === card.unit.id}
                  onSelect={() => setSelected(card.unit.id)}
                  onPrimary={() => setSelected(card.unit.id)}
                  onMenu={(x, y) => setMenu({ x, y, unitId: card.unit.id })}
                />
              ))}
            </ZoneArea>
          ))}
        </div>
        </div>

        <PlayerBar
          side="me"
          title="Você"
          active={mine}
          cp={projection.cp.me}
          vp={projection.vp.me}
          onCp={(delta) => push("cp_changed", { delta, player: "me", reason: "manual" }, `Seu CP ${delta > 0 ? "+1" : "−1"}`)}
          onVp={(delta) => push("vp_scored", { player: "me", kind: "other", label: "Ajuste", vp: delta }, `Seu VP ${delta > 0 ? "+1" : "−1"}`)}
          footer={
            <>
              <span className="round mono">Rodada {projection.round}</span>
              <span className={`chip ${!online || serverDown || rejected ? "chip-warn" : ""}`}>
                {!online
                  ? `Offline · ${pending}`
                  : rejected
                    ? `${rejected} rejeitados`
                    : serverDown
                      ? `Servidor fora · ${pending}`
                      : pending
                        ? `Sync ${pending}`
                        : "Sincronizado"}
              </span>
              {!wake && (
                <button
                  type="button"
                  className="chip chip-warn"
                  onClick={() =>
                    flash("Seu navegador não mantém a tela acesa. Ajuste o bloqueio automático do celular.")
                  }
                >
                  Tela pode apagar
                </button>
              )}
              <button className="ghost" onClick={undo} disabled={!lastAction} title="Ctrl+Z">
                Desfazer
              </button>
              <button className="ghost" onClick={() => navigate(`/games/${id}/summary`)}>
                Resumo
              </button>
            </>
          }
        />
      </section>

      <aside className={`side ${selectedCard ? "has-unit" : ""}`}>
        {selectedCard && (
          <Inspector
            card={selectedCard}
            phase={phase}
            mine={mine}
            leads={leaderOf.has(selectedCard.unit.id) ? names.get(leaderOf.get(selectedCard.unit.id)!) : undefined}
            ledBy={ledBy.has(selectedCard.unit.id) ? names.get(ledBy.get(selectedCard.unit.id)!) : undefined}
            onClose={() => setSelected(null)}
            onPatch={(patch, label, overrides) => setUnit(selectedCard.unit.id, patch, label, overrides)}
            onPrimary={() => primary(selectedCard)}
            onBattleShock={(passed) => push("battleshock_result", { list_unit_id: selectedCard.unit.id, passed }, `${selectedCard.unit.datasheet_name}: ${passed ? "passou" : "falhou"}`)}
            onClearBattleShockAbility={() =>
              push(
                "battleshock_result",
                { list_unit_id: selectedCard.unit.id, passed: true, source: "ability" },
                `${selectedCard.unit.datasheet_name}: battle-shock removido (habilidade)`,
              )
            }
            onFlash={flash}
            onZone={(place) => moveTo(selectedCard.unit.id, place)}
            overrides={overrideKeys(selectedCard)}
            effects={
              <EffectList
                title="Efeitos desta unidade"
                effects={selectedCard.effects}
                unitId={selectedCard.unit.id}
                choiceFor={choiceFor}
                onChoose={choose}
                empty={`Nada cadastrado para ${PHASE_NAMES[phase] || phase}.`}
              />
            }
          />
        )}
        <section className="panel">
          <EffectList
            title={`Efeitos gerais · ${PHASE_NAMES[phase] || phase}`}
            effects={generalEffects}
            unitId={null}
            choiceFor={choiceFor}
            onChoose={choose}
            empty={generalActive.length ? "" : "Nenhum efeito geral nesta fase. Cadastre no Catálogo."}
            heading
          >
            {generalActive.map((item) => (
              <p key={`${item.effect_id}-${item.round}-${item.player}`} className="chosen-line">
                Ativo {SCOPE_NAMES[item.scope]} · {effectName.get(item.effect_id) || "Efeito"}: {item.options.join(" · ")}
              </p>
            ))}
          </EffectList>
        </section>
        <PhaseTools phase={phase} mine={mine} projection={projection} bundle={bundle} cards={cards} push={push} />
        <Stratagems
          bundle={bundle}
          projection={projection}
          cards={cards}
          selectedUnitId={selected}
          push={push}
        />
        <GameLog log={projection.log} names={names} />
      </aside>

      {menu && (
        <ContextMenu
          menu={menu}
          card={cards.find((item) => item.unit.id === menu.unitId)!}
          phase={phase}
          mine={mine}
          onClose={() => setMenu(null)}
          onPatch={(patch, label, overrides) => setUnit(menu.unitId, patch, label, overrides)}
          onZone={(place) => moveTo(menu.unitId, place)}
          onBattleShock={(passed) => push("battleshock_result", { list_unit_id: menu.unitId, passed }, `${names.get(menu.unitId)}: ${passed ? "passou" : "falhou"}`)}
          overrides={overrideKeys(cards.find((item) => item.unit.id === menu.unitId)!)}
        />
      )}

      {toast && (
        <div className="toast" role="status">
          {toast}
          <button className="ghost" onClick={undo}>
            Desfazer
          </button>
        </div>
      )}
      <Link className="sr-only" to="/">
        Início
      </Link>
    </div>
  );
}

function PhaseRail({
  phase,
  phases = [...PHASES],
  mine,
  pendingCount,
  onPick,
  onNext,
  onPending,
}: {
  phase: string;
  phases?: string[];
  mine: boolean;
  pendingCount: number;
  onPick: (phase: string) => void;
  onNext: () => void;
  onPending?: () => void;
}) {
  const current = phases.indexOf(phase);
  const short = {
    round_start: "INI",
    command: "CMD",
    battle_shock: "BS",
    movement: "MOV",
    shooting: "SHT",
    charge: "CHG",
    fight: "FGT",
    end_of_turn: "END",
    end_of_round: "Rd",
  } as Record<string, string>;
  return (
    <nav className="phase-rail" aria-label="Fases">
      <div className="turn-tag">{mine ? "Seu turno" : "Turno do oponente"}</div>
      <div className="phase-current mono">{short[phase] || phase}</div>
      {pendingCount > 0 && mine && (
        <button className="ghost pending-chip" type="button" onClick={() => onPending?.()}>
          Faltam {pendingCount} · {short[phase] || phase}
        </button>
      )}
      <details className="phase-menu">
        <summary>Fases</summary>
        <div className="phase-menu-list">
          {phases.map((id, index) => (
            <button
              key={id}
              className={`phase-step ${id === phase ? "on" : ""} ${index < current ? "past" : ""}`}
              style={{ ["--c" as string]: `var(--${id})` }}
              disabled={index < current}
              onClick={() => onPick(id)}
            >
              {PHASE_NAMES[id]}
            </button>
          ))}
        </div>
      </details>
      <button className="primary next" onClick={onNext} title="Atalho: N">
        Próxima fase
      </button>
    </nav>
  );
}

function PlayerBar({
  side,
  title,
  active,
  cp,
  vp,
  onCp,
  onVp,
  footer,
}: {
  side: "me" | "opponent";
  title: string;
  active: boolean;
  cp: number;
  vp: number;
  onCp: (delta: number) => void;
  onVp: (delta: number) => void;
  footer?: ReactNode;
}) {
  return (
    <header className={`player-bar ${side} ${active ? "active" : ""}`}>
      <strong className="player-name">{title}</strong>
      <Counter label="CP" value={cp} onChange={onCp} min={0} />
      <Counter label="VP" value={vp} onChange={onVp} />
      <div className="player-extra">{footer}</div>
    </header>
  );
}

function Counter({ label, value, onChange, min }: { label: string; value: number; onChange: (delta: number) => void; min?: number }) {
  return (
    <div className="counter" aria-label={`${label} ${value}`}>
      <button className="step" onClick={() => onChange(-1)} disabled={min !== undefined && value <= min} aria-label={`${label} menos um`}>
        −
      </button>
      <span className="counter-value mono">
        <small>{label}</small>
        {value}
      </span>
      <button className="step" onClick={() => onChange(1)} aria-label={`${label} mais um`}>
        +
      </button>
    </div>
  );
}

function ZoneArea({
  place,
  count,
  children,
  onDropUnit,
  compact,
  lane,
}: {
  place: Place;
  count: number;
  children: ReactNode;
  onDropUnit: (unitId: number, place: Place) => void;
  compact?: boolean;
  lane?: boolean;
}) {
  const [over, setOver] = useState(false);
  const zone = place;
  return (
    <section
      className={`zone zone-${place} ${lane ? "lane" : ""} ${compact ? "compact" : ""} ${over ? "over" : ""}`}
      aria-label={PLACE_NAMES[place]}
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(event: DragEvent) => {
        event.preventDefault();
        setOver(false);
        const unitId = Number(event.dataTransfer.getData("text/unit"));
        if (unitId) onDropUnit(unitId, zone);
      }}
    >
      <div className="zone-head">
        <span>
          {PLACE_NAMES[zone]} <span className="muted mono">{count}</span>
        </span>
      </div>
      <div className="zone-body">{count ? children : <p className="muted empty">Nenhuma unidade aqui.</p>}</div>
    </section>
  );
}

function UnitCard({
  card,
  phase,
  mine = true,
  selected,
  compact,
  leads,
  ledBy,
  onSelect,
  onPrimary,
  onMenu,
  choiceFor,
}: {
  card: Card;
  phase: string;
  mine?: boolean;
  selected: boolean;
  compact?: boolean;
  choiceFor: ChoiceLookup;
  leads?: string;
  ledBy?: string;
  onSelect: () => void;
  onPrimary: () => void;
  onMenu: (x: number, y: number) => void;
}) {
  const { unit, live, result } = card;
  const tapped = result.status === "done";
  const state = card.zone === "destroyed" ? "destroyed" : result.status;
  const onTable = card.zone === "table";
  const actionPhase = ["movement", "shooting", "charge", "fight"].includes(phase);
  // Só o turno do Camilo destaca pendentes (F1); Fight do oponente não brilha.
  const pending = Boolean(mine) && onTable && actionPhase && (result.status === "active" || result.status === "warn");
  const pendingChoices = onTable ? card.effects.filter((effect) => effect.choice_options.length && !choiceFor(effect, unit.id)) : [];
  return (
    <div className={`card-cell ${compact ? "compact" : ""}`}>
      <button
        className={`unit-card ${state} ${pending ? "pending" : ""} ${tapped ? "tapped" : ""} ${selected ? "selected" : ""}`}
        data-unit={unit.id}
        aria-label={`${unit.datasheet_name}, ${statusLabel(card)}${result.reasons.length ? `: ${result.reasons[0]}` : ""}`}
        draggable
        onDragStart={(event) => {
          event.dataTransfer.setData("text/unit", String(unit.id));
          event.dataTransfer.effectAllowed = "move";
        }}
        onClick={(event) => {
          event.stopPropagation();
          onSelect();
        }}
        onDoubleClick={(event) => {
          event.stopPropagation();
          onPrimary();
        }}
        onContextMenu={(event) => {
          event.preventDefault();
          event.stopPropagation();
          onMenu(event.clientX, event.clientY);
        }}
      >
        <span className="done-seal" aria-hidden>
          ✓
        </span>
        <span className="card-top">
          <span className="card-name">{unit.datasheet_name}</span>
          {unit.is_warlord && <span className="crown" title="Warlord">★</span>}
        </span>
        {!compact && (
          <span className="card-meta mono">
            {unit.model_count} mod · {unit.points} pts
          </span>
        )}
        {!compact && (leads || ledBy) && <span className="card-link">{leads ? `Lidera ${leads}` : `Com ${ledBy}`}</span>}
        {!compact && (
          <span className="pips" aria-hidden>
            <Pip on={live.moved !== "none"} label={MOVE_LETTER[live.moved]} c="movement" title="Movimento" />
            <Pip on={live.shot} label="T" c="shooting" title="Atirou" />
            <Pip on={live.charged} label="C" c="charge" title="Carregou" />
            <Pip on={live.fought} label="L" c="fight" title="Lutou" />
            {live.engaged && <Pip on label="E" c="fight" title="Engajada" />}
            {live.battle_shocked && <Pip on label="BS" c="battle_shock" title="Battle-shock" />}
          </span>
        )}
        {result.reasons.length > 0 && card.zone !== "destroyed" && <span className="card-reason">{result.reasons.join(" · ")}</span>}
        {phase === "shooting" && result.allowedWeapons.length > 0 && result.reasons.includes("Só armas ASSAULT") && (
          <span className="card-weapons">{result.allowedWeapons.join(", ")}</span>
        )}
        {!compact && onTable && pendingChoices.length > 0 && <span className="card-effects pending">Escolher: {pendingChoices[0].ability_name}</span>}
        {!compact && onTable && !pendingChoices.length && card.chosen.length > 0 && <span className="card-effects chosen">{card.chosen.join(" · ")}</span>}
        {!compact && onTable && !pendingChoices.length && !card.chosen.length && card.effects.length > 0 && (
          <span className="card-effects">
            ✦ {card.effects.length} efeito{card.effects.length > 1 ? "s" : ""} nesta fase
          </span>
        )}
      </button>
      {["shooting", "charge", "fight"].includes(phase) && onTable && (
        <button
          type="button"
          className="primary card-action"
          aria-label={phase === "shooting" ? "Marcar tiro" : phase === "charge" ? "Marcar carga" : "Marcar luta"}
          onClick={(event) => {
            event.stopPropagation();
            onPrimary();
          }}
        >
          {phase === "shooting"
            ? live.shot
              ? "Desmarcar"
              : "Atirou"
            : phase === "charge"
              ? live.charged
                ? "Desmarcar"
                : "Carregou"
              : live.fought
                ? "Desmarcar"
                : "Lutou"}
        </button>
      )}
    </div>
  );
}

function Pip({ on, label, c, title }: { on: boolean; label: string; c: string; title: string }) {
  return (
    <span className={`pip ${on ? "on" : ""}`} style={{ ["--c" as string]: `var(--${c})` }} title={title}>
      {label}
    </span>
  );
}

type PatchFn = (patch: Record<string, unknown>, label: string, overrides?: { key: string }[]) => void;

function Inspector({
  card,
  phase,
  mine,
  leads,
  ledBy,
  onClose,
  onPatch,
  onPrimary,
  onBattleShock,
  onClearBattleShockAbility,
  onFlash,
  onZone,
  overrides,
  effects,
}: {
  card: Card;
  phase: string;
  mine: boolean;
  leads?: string;
  ledBy?: string;
  onClose: () => void;
  onPatch: PatchFn;
  onPrimary: () => void;
  onBattleShock: (passed: boolean) => void;
  onClearBattleShockAbility: () => void;
  onFlash: (message: string) => void;
  onZone: (place: Place) => void;
  overrides: { key: string }[];
  effects: ReactNode;
}) {
  const { unit, live, result } = card;
  const primaryLabel = phase === "shooting" ? (live.shot ? "Desmarcar tiro" : "Atirou") : phase === "charge" ? (live.charged ? "Desmarcar carga" : "Carregou") : phase === "fight" ? (live.fought ? "Desmarcar luta" : "Lutou") : null;
  return (
    <section className="panel inspector" aria-label="Unidade selecionada">
      <div className="panel-head">
        <h2>{unit.datasheet_name}</h2>
        <button className="ghost close" onClick={onClose} aria-label="Fechar">
          ×
        </button>
      </div>
      <p className="muted mono">
        {unit.model_count} modelos · {unit.points} pts{unit.is_warlord ? " · Warlord" : ""}
      </p>
      {unit.enhancement_name && <p className="muted">Enhancement: {unit.enhancement_name}</p>}
      {(leads || ledBy) && <p className="muted">{leads ? `Lidera ${leads}` : `Liderada por ${ledBy}`}</p>}
      <p className={`status-line ${result.status}`}>
        {statusLabel(card)}
        {result.reasons.length > 0 && ` — ${result.reasons.join(" · ")}`}
      </p>
      {card.chosen.length > 0 && <p className="chosen-line">Ativo: {card.chosen.join(" · ")}</p>}

      {effects}

      {phase === "movement" && (
        <div className="action-grid">
          {MOVES.map(([move, label]) => (
            <button
              key={move}
              className={live.moved === move ? "primary" : ""}
              onClick={async () => {
                if (move === "fell_back" && live.engaged && !live.battle_shocked) {
                  const ordered = await askConfirm(
                    "Ordered Retreat ou Desperate Escape?\n\nConfirmar = Ordered Retreat. Cancelar = escolher Desperate Escape.",
                    { confirmLabel: "Ordered Retreat", cancelLabel: "Desperate Escape" },
                  );
                  const mode = ordered ? "ordered" : "desperate";
                  onPatch(
                    { moved: move, fall_back_mode: mode },
                    mode === "desperate" ? "Recuou (Desperate Escape)" : "Recuou (Ordered Retreat)",
                  );
                  if (mode === "desperate") {
                    onFlash("Hazard roll por modelo (1–2 = ferida mortal). Em seguida registre o teste de battle-shock.");
                  }
                  return;
                }
                onPatch({ moved: move, fall_back_mode: null }, label);
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}
      {primaryLabel && (
        <button className="primary wide" onClick={onPrimary}>
          {primaryLabel}
        </button>
      )}
      {phase === "battle_shock" && mine && (
        <div className="action-grid">
          <button onClick={() => onBattleShock(true)}>Passou</button>
          <button onClick={() => onBattleShock(false)}>Falhou</button>
        </div>
      )}
      {live.moved === "fell_back" &&
        live.fall_back_mode === "desperate" &&
        live.engaged &&
        !live.battle_shocked &&
        phase === "movement" && (
        <div className="action-grid">
          <button onClick={() => onBattleShock(true)}>Desperate Escape: passou BS</button>
          <button onClick={() => onBattleShock(false)}>Desperate Escape: falhou BS</button>
        </div>
      )}
      {result.status === "inactive" && overrides.length > 0 && (
        <button className="ghost wide" onClick={() => onPatch({}, "restrição ignorada", overrides)}>
          Ignorar restrição nesta fase
        </button>
      )}
      {live.battle_shocked && phase !== "battle_shock" && (
        <button className="ghost wide" type="button" onClick={onClearBattleShockAbility}>
          Remover battle-shock (habilidade)
        </button>
      )}

      <div className="toggles">
        <Toggle on={live.engaged} label="Engajada" onClick={() => onPatch({ engaged: !live.engaged }, live.engaged ? "fora de combate" : "engajada")} />
        <Toggle
          on={live.on_action}
          label="Em ação"
          title="Unidade fazendo uma Action, como uma missão. Enquanto isso, não atira nem carrega."
          onClick={async () => {
            if (!live.on_action) {
              const reasons = canStartAction(live, unit.keywords || [], {
                oc: unit.oc ?? unit.objective_control,
                snapShooting: Boolean(live.snap_shooting),
              });
              if (reasons.length && !(await askConfirm(`${reasons.join(" · ")}. Registrar ação mesmo assim?`))) return;
            }
            onPatch({ on_action: !live.on_action }, live.on_action ? "saiu da ação" : "em ação");
          }}
        />
        <Toggle on={live.below_half} label="Abaixo da metade" onClick={() => onPatch({ below_half: !live.below_half }, live.below_half ? "acima da metade" : "abaixo da metade")} />
        <Toggle on={live.battle_shocked} label="Battle-shock" onClick={() => onPatch({ battle_shocked: !live.battle_shocked }, live.battle_shocked ? "sem battle-shock" : "battle-shock")} />
      </div>

      {(unit.wargear || []).length > 0 && (
        <ul className="weapons">
          {unit.wargear.map((item: any, index: number) => {
            const allowed = phase !== "shooting" || result.allowedWeapons.includes(item.weapon_name);
            return (
              <li key={index} className={allowed ? "" : "dim"}>
                <span>
                  {item.count > 1 ? `${item.count}× ` : ""}
                  {item.weapon_name}
                </span>
                {(item.keywords || []).length > 0 && <span className="kw">{item.keywords.join(" ")}</span>}
              </li>
            );
          })}
        </ul>
      )}

      <p className="muted small-title">Onde está</p>
      <div className="zone-buttons">
        {PLACES.map((place) => (
          <button key={place} className={place === card.place ? "primary" : "ghost"} aria-pressed={place === card.place} onClick={() => place !== card.place && onZone(place)}>
            {PLACE_NAMES[place]}
          </button>
        ))}
      </div>
    </section>
  );
}

function Toggle({ on, label, title, onClick }: { on: boolean; label: string; title?: string; onClick: () => void }) {
  return (
    <button className={`toggle ${on ? "on" : ""}`} aria-pressed={on} title={title} onClick={onClick}>
      {label}
    </button>
  );
}

function statusLabel(card: Card) {
  if (card.zone === "destroyed") return "Destruída";
  if (card.zone === "reserves") return "Na reserva";
  return { active: "Pode agir", inactive: "Não pode agir", done: "Já agiu", warn: "Atenção" }[card.result.status];
}

function ContextMenu({
  menu,
  card,
  phase,
  mine,
  onClose,
  onPatch,
  onZone,
  onBattleShock,
  overrides,
}: {
  menu: NonNullable<Menu>;
  card: Card;
  phase: string;
  mine: boolean;
  onClose: () => void;
  onPatch: PatchFn;
  onZone: (place: Place) => void;
  onBattleShock: (passed: boolean) => void;
  overrides: { key: string }[];
}) {
  const run = (fn: () => void) => () => {
    fn();
    onClose();
  };
  const left = Math.min(menu.x, window.innerWidth - 240);
  const top = Math.min(menu.y, window.innerHeight - 420);
  const { live } = card;
  return (
    <div className="context-menu" style={{ left, top }} role="menu" onClick={(event) => event.stopPropagation()}>
      <p className="menu-title">{card.unit.datasheet_name}</p>
      {MOVES.map(([move, label]) => (
        <button key={move} role="menuitem" onClick={run(() => onPatch({ moved: move }, label))}>
          Movimento: {label}
        </button>
      ))}
      <hr />
      <button role="menuitem" onClick={run(() => onPatch({ shot: !live.shot }, live.shot ? "tiro desmarcado" : "Atirou"))}>
        {live.shot ? "Desmarcar tiro" : "Atirou"}
      </button>
      <button role="menuitem" onClick={run(() => onPatch({ charged: !live.charged }, live.charged ? "carga desmarcada" : "Carregou"))}>
        {live.charged ? "Desmarcar carga" : "Carregou"}
      </button>
      <button role="menuitem" onClick={run(() => onPatch({ fought: !live.fought }, live.fought ? "luta desmarcada" : "Lutou"))}>
        {live.fought ? "Desmarcar luta" : "Lutou"}
      </button>
      <button role="menuitem" onClick={run(() => onPatch({ engaged: !live.engaged }, live.engaged ? "fora de combate" : "engajada"))}>
        {live.engaged ? "Sair do combate" : "Engajada"}
      </button>
      {phase === "battle_shock" && mine && (
        <>
          <button role="menuitem" onClick={run(() => onBattleShock(true))}>
            Battle-shock: passou
          </button>
          <button role="menuitem" onClick={run(() => onBattleShock(false))}>
            Battle-shock: falhou
          </button>
        </>
      )}
      {overrides.length > 0 && card.result.status === "inactive" && (
        <button role="menuitem" onClick={run(() => onPatch({}, "restrição ignorada", overrides))}>
          Ignorar restrição nesta fase
        </button>
      )}
      <hr />
      {PLACES.filter((place) => place !== card.place).map((place) => (
        <button key={place} role="menuitem" onClick={run(() => onZone(place))}>
          Mover para {PLACE_NAMES[place]}
        </button>
      ))}
    </div>
  );
}

function EffectList({
  title,
  effects,
  unitId,
  choiceFor,
  onChoose,
  empty,
  heading,
  children,
}: {
  title: string;
  effects: PhaseEffect[];
  unitId: number | null;
  choiceFor: ChoiceLookup;
  onChoose: (effect: PhaseEffect, unitId: number | null, options: string[]) => void;
  empty: string;
  heading?: boolean;
  children?: ReactNode;
}) {
  return (
    <div className="effects" aria-label={title}>
      {heading ? <h2>{title}</h2> : <p className="muted small-title">{title}</p>}
      {!effects.length && empty && <p className="muted">{empty}</p>}
      {effects.map((effect) => (
        <EffectRowLive key={effect.id} effect={effect} chosen={choiceFor(effect, unitId)} onChoose={(options) => onChoose(effect, unitId, options)} />
      ))}
      {children}
    </div>
  );
}

function EffectRowLive({ effect, chosen, onChoose }: { effect: PhaseEffect; chosen?: Choice; onChoose: (options: string[]) => void }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [editing, setEditing] = useState(false);
  const count = effect.choice_count || 1;
  const hasChoice = effect.choice_options.length > 0;
  const open = hasChoice && (!chosen || editing);
  return (
    <article className={`effect ${hasChoice && !chosen ? "needs-choice" : ""}`}>
      <header className="effect-head">
        <strong>{effect.ability_name}</strong>
        <span className="muted mono">{TIMING_NAMES[effect.timing] || effect.timing}</span>
        <HypothesisBadge on={effect.is_hypothesis} />
        <ConditionalBadge on={effect.is_conditional} text={effect.condition_text} />
      </header>
      <p>{effect.effect_text}</p>
      {hasChoice && chosen && !editing && (
        <p className="chosen-line">
          Escolhido {SCOPE_NAMES[chosen.scope]}: {chosen.options.join(" · ")}{" "}
          <button
            className="ghost link"
            onClick={() => {
              setPicked(chosen.options);
              setEditing(true);
            }}
          >
            Trocar
          </button>
        </p>
      )}
      {open && (
        <div className="choice">
          <p className="muted">
            Escolha {count} de {effect.choice_options.length} · vale {SCOPE_NAMES[effect.choice_scope]}
          </p>
          <div className="choice-options">
            {effect.choice_options.map((option) => {
              const on = picked.includes(option);
              return (
                <button
                  key={option}
                  className={`toggle ${on ? "on" : ""}`}
                  aria-pressed={on}
                  disabled={!on && picked.length >= count}
                  onClick={() => setPicked(on ? picked.filter((item) => item !== option) : [...picked, option])}
                >
                  {option}
                </button>
              );
            })}
          </div>
          <button
            className="primary wide"
            disabled={picked.length !== count}
            onClick={() => {
              onChoose(picked);
              setEditing(false);
              setPicked([]);
            }}
          >
            Confirmar ({picked.length}/{count})
          </button>
        </div>
      )}
    </article>
  );
}

type PushFn = (type: string, payload: Record<string, unknown>, label?: string) => Promise<void>;

function isDaemonsArmy(factionName: string | undefined): boolean {
  const var_strName = (factionName || "").toLowerCase();
  if (var_strName.includes("heretic astartes") || var_strName.includes("chaos knights")) return false;
  return var_strName.includes("chaos daemons") || var_strName.includes("legiones daemonica");
}

function ShadowPhaseCard({ projection, push }: { projection: Projection; push: PushFn }) {
  const var_objNow = shadowNow(projection);
  const [nml, setNml] = useState(var_objNow.nml);
  const [opp, setOpp] = useState(var_objNow.opp_dz);
  useEffect(() => {
    setNml(var_objNow.nml);
    setOpp(var_objNow.opp_dz);
  }, [projection.round, projection.player, projection.phase, var_objNow.known, var_objNow.nml, var_objNow.opp_dz]);
  const var_objPrev = [...projection.shadow]
    .reverse()
    .find(
      (item) =>
        !(item.round === projection.round && item.turn_player === projection.player && item.phase === projection.phase),
    );
  return (
    <div className="shadow">
      <p>
        Shadow nesta fase
        {!var_objNow.known && <span className="warn"> — não informado nesta fase</span>}
      </p>
      <p className="muted">Minha zona: sempre</p>
      <label className="row">
        <input type="checkbox" checked={nml} onChange={(event) => setNml(event.target.checked)} />
        Terra de Ninguém no Shadow
      </label>
      <label className="row">
        <input type="checkbox" checked={opp} onChange={(event) => setOpp(event.target.checked)} />
        Zona do oponente no Shadow
      </label>
      <div className="row">
        <button
          onClick={() =>
            push(
              "shadow_set",
              {
                player: "me",
                turn_player: projection.player,
                phase: projection.phase,
                nml_in_shadow: nml,
                opp_dz_in_shadow: opp,
              },
              "Shadow da fase registrado",
            )
          }
        >
          Registrar Shadow
        </button>
        {var_objPrev && (
          <button
            onClick={() => {
              setNml(var_objPrev.nml_in_shadow);
              setOpp(var_objPrev.opp_dz_in_shadow);
              push(
                "shadow_set",
                {
                  player: "me",
                  turn_player: projection.player,
                  phase: projection.phase,
                  nml_in_shadow: var_objPrev.nml_in_shadow,
                  opp_dz_in_shadow: var_objPrev.opp_dz_in_shadow,
                },
                "Shadow igual à fase anterior",
              );
            }}
          >
            Igual à fase anterior
          </button>
        )}
      </div>
    </div>
  );
}

function PhaseTools({ phase, mine, projection, bundle, cards, push }: { phase: string; mine: boolean; projection: Projection; bundle: any; cards: Card[]; push: PushFn }) {
  const [vp, setVp] = useState(5);
  const [kind, setKind] = useState<"primary" | "secondary">("primary");
  const eventRules = projection.eventRules;
  const showShadow = isDaemonsArmy(bundle?.version?.faction_name);
  const pendingShock = cards.filter(
    (item) => item.zone === "table" && (item.live.below_half || item.live.battle_shocked),
  );

  if (phase === "round_start") {
    return (
      <section className="panel">
        <h2>Início da rodada</h2>
        <p className="muted">Antes da Command: efeitos de começo de battle round. O CP entra na fase seguinte.</p>
        {showShadow && <ShadowPhaseCard projection={projection} push={push} />}
      </section>
    );
  }
  if (phase === "command") {
    return (
      <section className="panel">
        <h2>Command {mine ? "(seu turno)" : "(turno do oponente)"}</h2>
        <button
          className="primary wide"
          onClick={async () => {
            await push("cp_changed", { delta: 1, reason: "core_cp", player: "me" }, "Core CP +1 (você)");
            await push("cp_changed", { delta: 1, reason: "core_cp", player: "opponent" }, "Core CP +1 (oponente)");
          }}
        >
          Gain Core CP (+1 para cada)
        </button>
        <label className="row">
          <input
            type="checkbox"
            checked={eventRules}
            onChange={(event) =>
              push("game_settings_set", { event_rules: event.target.checked }, event.target.checked ? "regras de evento ligadas" : "regras de evento desligadas")
            }
          />
          Regras de evento (aviso se passar de 1 CP extra na rodada)
        </label>
        {projection.warnings.includes("core_cp_twice") && (
          <p className="confirm-warn">Core CP já foi marcado nesta Command.</p>
        )}
        {eventRules && projection.warnings.includes("extra_cp_cap") && (
          <p className="confirm-warn">Mais de 1 CP extra nesta rodada (Event Companion).</p>
        )}
        {showShadow && <ShadowPhaseCard projection={projection} push={push} />}
      </section>
    );
  }
  if (phase === "battle_shock") {
    const var_objShadow = shadowNow(projection);
    return (
      <section className="panel">
        <h2>Battle-shock {mine ? "" : "(turno do oponente)"}</h2>
        {mine ? (
          <p className="muted">Lista quem está em battle-shock ou na metade da força ou abaixo. Marque Passou ou Falhou.</p>
        ) : (
          <p className="muted">Testes do oponente — você não marca Passou/Falhou nas suas unidades.</p>
        )}
        {showShadow && !var_objShadow.known && (
          <p className="confirm-warn">Shadow não informado nesta fase — registre antes de Manifestation/Terror.</p>
        )}
        {showShadow && <ShadowPhaseCard projection={projection} push={push} />}
        {mine &&
          pendingShock.map((item) => (
            <div key={item.unit.id} className="row between">
              <span>
                {item.unit.datasheet_name}
                {item.live.battle_shocked ? " (já em battle-shock)" : ""}
                {item.live.below_half ? " (metade ou abaixo)" : ""}
              </span>
              <span className="row">
                <button onClick={() => push("battleshock_result", { list_unit_id: item.unit.id, passed: true }, `${item.unit.datasheet_name}: passou`)}>Passou</button>
                <button onClick={() => push("battleshock_result", { list_unit_id: item.unit.id, passed: false }, `${item.unit.datasheet_name}: falhou`)}>Falhou</button>
              </span>
            </div>
          ))}
      </section>
    );
  }
  if (phase === "end_of_turn") {
    const owner = projection.player as "me" | "opponent";
    const checked = (key: string) =>
      projection.checklist.some(
        (item) => item.round === projection.round && item.player === owner && item.key === key && item.done,
      );
    const toggleCheck = (key: string) =>
      push("checklist_set", { key, done: !checked(key), player: owner }, `Checklist: ${key}`);
    const ctrlLabel: Record<string, string> = { me: "Você", opponent: "Op", contested: "Disputado", none: "—" };
    return (
      <section className="panel">
        <h2>Fim do turno</h2>
        <div className="checklist">
          <label className="row">
            <input type="checkbox" checked={checked("primary")} onChange={() => toggleCheck("primary")} /> Primária
          </label>
          {(bundle.version?.secondaries || []).map((item: string) => (
            <label key={item} className="row">
              <input type="checkbox" checked={checked(`sec:${item}`)} onChange={() => toggleCheck(`sec:${item}`)} /> {item}
            </label>
          ))}
          <label className="row">
            <input type="checkbox" checked={checked("actions")} onChange={() => toggleCheck("actions")} /> Ações concluídas
          </label>
        </div>
        <p className="muted">Objetivos</p>
        <div className="objectives" role="group" aria-label="Controle de objetivos">
          {OBJECTIVES.map((label) => {
            const controller = projection.objectives.find((item) => item.objective_label === label && item.round === projection.round)?.controller || "none";
            const next = controller === "none" ? "me" : controller === "me" ? "opponent" : controller === "opponent" ? "contested" : "none";
            return (
              <button
                key={label}
                className={`objective ${controller}`}
                onClick={() => push("objective_set", { objective_label: label, controller: next, player_turn: owner })}
                title="Toque para trocar: você → oponente → disputado → ninguém"
              >
                {label} · {ctrlLabel[controller] || controller}
              </button>
            );
          })}
        </div>
        <div className="row">
          <select value={kind} onChange={(event) => setKind(event.target.value as "primary" | "secondary")}>
            <option value="primary">Primária</option>
            <option value="secondary">Secundária</option>
          </select>
          <input className="mono narrow" type="number" value={vp} onChange={(event) => setVp(Number(event.target.value))} />
          <button className="primary" onClick={() => push("vp_scored", { player: owner, kind, label: kind === "primary" ? "Primária" : "Secundária", vp }, `+${vp} VP`)}>
            Anotar VP
          </button>
        </div>
      </section>
    );
  }
  if (showShadow) {
    return (
      <section className="panel">
        <h2>{PHASE_NAMES[phase] || phase}</h2>
        <ShadowPhaseCard projection={projection} push={push} />
      </section>
    );
  }
  return null;
}

function Stratagems({
  bundle,
  projection,
  cards,
  selectedUnitId,
  push,
}: {
  bundle: any;
  projection: Projection;
  cards: Card[];
  selectedUnitId: number | null;
  push: PushFn;
}) {
  const [picking, setPicking] = useState<{ item: any; used: boolean; short: boolean } | null>(null);
  const [targetId, setTargetId] = useState<number | null>(null);
  const mineTurn = projection.player === "me";
  const effects = (bundle.rule_effects || []).filter((effect: any) => effect.effect_kind === "stratagem");
  const abilityIds = new Set(
    effects
      .filter((effect: any) => effect.phase === projection.phase || effect.phase === "any")
      .filter((effect: any) => {
        if (!effect.turn_owner || effect.turn_owner === "both") return true;
        if (effect.turn_owner === "own") return mineTurn;
        if (effect.turn_owner === "opponent") return !mineTurn;
        return true;
      })
      .map((effect: any) => effect.ability_id),
  );
  const all = (bundle.abilities || []).filter((item: any) => item.kind === "stratagem");
  const now = all.filter((item: any) => abilityIds.has(item.id) || !effects.some((effect: any) => effect.ability_id === item.id));
  const later = all.filter((item: any) => !now.includes(item));
  if (!all.length) return null;
  const cp = projection.cp.me;
  const onTable = cards.filter((card) => !card.live.destroyed && !card.live.in_reserves);
  const targets = [
    ...onTable.filter((card) => card.result.status === "active" || card.result.status === "warn"),
    ...onTable.filter((card) => card.result.status !== "active" && card.result.status !== "warn"),
  ];
  const confirm = (item: any, used: boolean, short: boolean, target: number | null) => {
    push(
      "stratagem_used",
      {
        ability_id: item.id,
        stratagem_name: item.name,
        cp_spent: item.cp_cost || 0,
        use_limit: item.use_limit || "per_phase",
        player: "me",
        limit_overridden: used,
        cp_override: short,
        target_list_unit_id: target,
      },
      `${item.name} (−${item.cp_cost || 0} CP)`,
    );
    setPicking(null);
  };
  const openPick = async (item: any, used: boolean, short: boolean) => {
    if (used && !(await askConfirm("Já usado nesta fase. Usar mesmo assim?"))) return;
    if (short && !(await askConfirm("CP insuficiente. Registrar mesmo assim?"))) return;
    const preset = selectedUnitId && targets.some((card) => card.unit.id === selectedUnitId) ? selectedUnitId : null;
    setTargetId(preset);
    setPicking({ item, used, short });
  };
  const render = (item: any, markUsed: boolean) => {
    const used = projection.stratagem_uses.some(
      (use) =>
        use.stratagem_name === item.name &&
        use.phase === projection.phase &&
        use.round === projection.round &&
        use.turn_player === projection.player &&
        use.player === "me",
    );
    const cost = item.cp_cost || 0;
    return (
      <button
        key={item.id}
        className={`stratagem ${used ? "used" : ""} ${cost > cp ? "short" : ""}`}
        onClick={() => openPick(item, used, cost > cp)}
      >
        <span>
          {item.name}
          {markUsed && used ? " · Usado nesta fase" : ""}
        </span>
        <span className="mono">{cost} CP</span>
      </button>
    );
  };
  return (
    <section className="panel">
      <h2>Stratagems</h2>
      {now.map((item: any) => render(item, true))}
      {later.length > 0 && (
        <details>
          <summary>Outras fases ({later.length})</summary>
          {later.map((item: any) => render(item, false))}
        </details>
      )}
      {picking && (
        <div className="sheet-confirm" role="dialog" aria-label="Alvo do stratagem">
          <h3>{picking.item.name}</h3>
          <p className="muted">Escolha o alvo (opcional)</p>
          <div className="action-grid">
            <button className={targetId == null ? "primary" : ""} onClick={() => setTargetId(null)}>
              Sem alvo
            </button>
            {targets.map((card) => (
              <button
                key={card.unit.id}
                className={targetId === card.unit.id ? "primary" : ""}
                onClick={() => setTargetId(card.unit.id)}
              >
                {card.unit.datasheet_name}
                {card.live.battle_shocked ? " · BS" : ""}
              </button>
            ))}
          </div>
          <div className="action-grid" style={{ marginTop: 12 }}>
            <button className="ghost" onClick={() => setPicking(null)}>
              Cancelar
            </button>
            <button className="primary" onClick={() => confirm(picking.item, picking.used, picking.short, targetId)}>
              Confirmar
            </button>
          </div>
        </div>
      )}
    </section>
  );
}

function GameLog({ log, names }: { log: LogEntry[]; names: Map<number, string> }) {
  const ref = useRef<HTMLOListElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight });
  }, [log.length]);
  return (
    <section className="panel log-panel">
      <h2>Log</h2>
      <ol className="log" ref={ref}>
        {log.map((entry) => (
          <li key={entry.id} className={entry.undone ? "undone" : ""}>
            <span className="log-meta mono" style={{ color: `var(--${entry.phase})` }}>
              R{entry.round} {entry.player === "me" ? "Você" : "Op"}
            </span>
            {describe(entry, names)}
          </li>
        ))}
      </ol>
    </section>
  );
}

export function describe(entry: LogEntry, names: Map<number, string>) {
  const p = entry.payload;
  const unit = names.get(Number(p.list_unit_id)) || "Unidade";
  switch (entry.type) {
    case "game_started":
      return "Partida começou";
    case "phase_advanced":
      return `→ ${PHASE_NAMES[entry.phase] || entry.phase}`;
    case "unit_state_set": {
      const parts = Object.entries(p.patch || {}).map(([key, value]) => {
        if (key === "moved") return MOVES.find(([move]) => move === value)?.[1] || String(value);
        if (key === "destroyed") return value ? "destruída" : "voltou";
        if (key === "in_reserves") return value ? "reserva" : "mesa";
        if (key === "lane") return LANE_NAMES[value as Lane] || String(value);
        return `${key}=${value}`;
      });
      if (p.overrides?.length) parts.push("override");
      return `${unit}: ${parts.join(", ")}`;
    }
    case "cp_changed":
      return `CP ${p.player === "opponent" ? "do oponente " : ""}${p.delta > 0 ? "+" : ""}${p.delta}`;
    case "vp_scored":
      return `VP ${p.player === "opponent" ? "do oponente " : ""}${p.vp > 0 ? "+" : ""}${p.vp} (${p.label})`;
    case "stratagem_used":
      return `Stratagem: ${p.stratagem_name} (−${p.cp_spent} CP)`;
    case "objective_set":
      return `Objetivo ${p.objective_label}: ${p.controller}`;
    case "shadow_set":
      if (p.nml_in_shadow !== undefined || p.opp_dz_in_shadow !== undefined) {
        return `Shadow fase ${p.phase || ""}: TdN ${p.nml_in_shadow ? "sim" : "não"}, zona oponente ${p.opp_dz_in_shadow ? "sim" : "não"}`;
      }
      return `Shadow (legado): ${p.objectives_controlled} objetivos${p.whole_board ? ", tabuleiro todo" : ""}`;
    case "battleshock_result":
      return `${unit}: battle-shock ${p.passed ? "passou" : "falhou"}`;
    case "effect_chosen":
      return `${p.list_unit_id ? `${unit} · ` : ""}escolheu ${(p.options || []).join(", ")}`;
    case "undo":
      return "Desfazer";
    case "game_ended":
      return "Fim de jogo";
    default:
      return entry.type;
  }
}

export function EventTimeline({ events, names }: { events: EventRecord[]; names?: Map<number, string> }) {
  const projection = applyEvents(events);
  return <GameLog log={projection.log} names={names || new Map()} />;
}
