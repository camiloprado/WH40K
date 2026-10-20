import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLiveQuery } from "dexie-react-hooks";
import { Link, NavLink, Navigate, useNavigate, useParams } from "react-router-dom";
import { Stage, Layer, Circle, Rect, Text, Line } from "react-konva";
import { api, login, logout } from "./api";
import { bundleFor, db, deviceId, saveBundle } from "./db";
import { expectedDamage } from "./engine/damage";
import { conditionLabel, guideMatch } from "./engine/eligibility";
import { applyEvents } from "./engine/project";
import { deleteMatch, finishMatch, flushSync } from "./sync";
import { EffectRow, ParseWarnings } from "./components";
import { EventTimeline } from "./GameScreen";

const con_dctResultLabel: Record<string, string> = { win: "Vitória", loss: "Derrota", draw: "Empate" };
const RESULT_LABEL = con_dctResultLabel;

const PHASE_LABEL: Record<string, string> = {
  round_start: "Início da rodada",
  command: "Command",
  battle_shock: "Battle-shock",
  movement: "Movement",
  shooting: "Shooting",
  charge: "Charge",
  fight: "Fight",
  end_of_turn: "Fim do turno",
  deployment: "Deployment",
  any: "Qualquer fase",
};

function StatLine({ unit }: { unit: any }) {
  if (!unit) return null;
  const bits = [
    unit.movement != null ? `M${unit.movement}"` : "",
    unit.toughness != null ? `T${unit.toughness}` : "",
    unit.save != null ? `Sv${unit.save}+` : "",
    unit.invuln != null ? `inv${unit.invuln}+` : "",
    unit.wounds != null ? `W${unit.wounds}` : "",
    unit.leadership != null ? `Ld${unit.leadership}+` : "",
    unit.oc != null ? `OC${unit.oc}` : "",
    unit.fnp != null ? `FNP${unit.fnp}+` : "",
    unit.base_size_mm || "",
  ].filter(Boolean);
  if (!bits.length) return null;
  return <span className="muted mono stat-line">{bits.join(" · ")}</span>;
}

function pointsState(sum: number, declared: number | null | undefined) {
  if (declared == null || sum === declared) return "exact";
  return sum < declared ? "under" : "over";
}

const STATE_LABEL: Record<string, string> = { under: "abaixo", exact: "exato", over: "acima" };

export function LoginScreen() {
  const [token, setToken] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  return (
    <main className="page" style={{ maxWidth: 420, paddingTop: "18vh" }}>
      <form
        className="card stack"
        onSubmit={async (event) => {
          event.preventDefault();
          try {
            await login(token);
            navigate("/");
          } catch (err) {
            setError(err instanceof Error ? err.message : "Não deu para entrar");
          }
        }}
      >
        <h1>List Companion</h1>
        <p className="muted">Entre com o token gerado na instalação.</p>
        <input type="password" value={token} placeholder="Token" aria-label="Token" onChange={(event) => setToken(event.target.value)} autoFocus />
        {error && <p className="warn">{error}</p>}
        <button className="primary" type="submit">
          Entrar
        </button>
      </form>
    </main>
  );
}

export function HomeScreen() {
  const lists = useQuery({ queryKey: ["lists"], queryFn: () => api<any[]>("/lists"), retry: false });
  const serverGames = useQuery({ queryKey: ["games"], queryFn: () => api<any[]>("/games"), retry: false });
  const games = useLiveQuery(() => db.games.orderBy("updatedAt").reverse().toArray(), [], []);
  const bundles = useLiveQuery(() => db.bundles.toArray(), [], []);
  const offline = !lists.data && bundles.length > 0;
  const [query, setQuery] = useState("");
  const [faction, setFaction] = useState("");
  const [notice, setNotice] = useState("");
  const [cardErrors, setCardErrors] = useState<Record<number, string>>({});
  const [picked, setPicked] = useState<number[]>([]);
  const [choosing, setChoosing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [matchAction, setMatchAction] = useState<{ id: string; mode: "finish" | "delete" } | null>(null);
  const [outcome, setOutcome] = useState<"win" | "loss" | "draw" | "">("");
  const armies = (lists.data || []).filter((list) => list.current_version && !list.archived);
  const factions = [...new Set(armies.map((list) => list.current_version.faction_name).filter(Boolean))] as string[];
  const needle = query.trim().toLowerCase();
  const visible = armies.filter((list) => {
    const version = list.current_version;
    const haystack = `${list.name} ${version.faction_name || ""} ${version.battle_size || ""}`.toLowerCase();
    return (!needle || haystack.includes(needle)) && (!faction || version.faction_name === faction);
  });

  function togglePick(id: number, on: boolean) {
    setPicked((current) => (on ? [...new Set([...current, id])] : current.filter((item) => item !== id)));
  }

  function closeDelete() {
    setConfirming(false);
    setChoosing(false);
    setPicked([]);
  }

  function gamesOf(list: any) {
    const versionId = list.current_version?.id;
    return (games || []).filter((game) => game.listVersionId === versionId);
  }

  async function commitDelete() {
    const targets = armies.filter((list) => picked.includes(list.id));
    if (!targets.length || busy) return;
    setBusy(true);
    setNotice("");
    const blocked: Record<number, string> = {};
    for (const list of targets) {
      try {
        await api(`/lists/${list.id}`, { method: "DELETE", body: JSON.stringify({ confirm: "EXCLUIR" }) });
        if (list.current_version?.id) await db.bundles.delete(list.current_version.id);
      } catch (err) {
        blocked[list.id] = err instanceof Error ? err.message : "Não deu para apagar";
      }
    }
    await lists.refetch();
    await serverGames.refetch();
    setBusy(false);
    closeDelete();
    setCardErrors(blocked);
  }

  useEffect(() => {
    if (!choosing && !confirming) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (confirming) setConfirming(false);
      else closeDelete();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [choosing, confirming]);

  const chosen = armies.filter((list) => picked.includes(list.id));
  const match =
    (games || []).find((game) => game.id === matchAction?.id) ||
    (serverGames.data || [])
      .filter((game) => game.id === matchAction?.id)
      .map((game) => ({
        id: game.id,
        opponentName: game.opponent_name || "",
        missionName: game.mission_name || "",
        listVersionId: game.list_version_id,
        listName: game.list_label || "",
        status: game.status,
        result: game.result,
        updatedAt: Date.now(),
      }))[0] ||
    null;
  const matchList = armies.find((list) => list.current_version?.id === match?.listVersionId);

  async function commitMatch() {
    if (!match || !matchAction || busy) return;
    setBusy(true);
    setNotice("");
    try {
      if (matchAction.mode === "delete") await deleteMatch(match);
      else {
        if (!outcome) return;
        await finishMatch(match, outcome, match.listName || matchList?.name || "Lista");
      }
      setMatchAction(null);
      await serverGames.refetch();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Não deu para atualizar a partida");
    } finally {
      setBusy(false);
    }
  }

  const localIds = new Set((games || []).map((game) => game.id));
  const openGames = [
    ...(games || []).filter((game) => {
      const remote = (serverGames.data || []).find((item) => item.id === game.id);
      return remote ? remote.status === "active" : game.status === "active";
    }),
    ...(serverGames.data || [])
      .filter((game) => game.status === "active" && !localIds.has(game.id))
      .map((game) => ({
        id: game.id,
        opponentName: game.opponent_name || "",
        missionName: game.mission_name || "",
        listVersionId: game.list_version_id,
        status: "active",
        result: game.result,
        listName: game.list_label || "",
        updatedAt: Date.now(),
      })),
  ];
  const pastGames = [
    ...(games || []).filter((game) => game.status === "finished"),
    ...(serverGames.data || [])
      .filter((game) => game.status === "finished" && !localIds.has(game.id))
      .map((game) => ({
        id: game.id,
        opponentName: game.opponent_name || "",
        missionName: game.mission_name || "",
        listName: game.list_label || "",
        result: game.result,
        status: "finished",
      })),
  ];
  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1>Listas</h1>
          <p className="muted">Exércitos importados do New Recruit. Abrir um card mostra as unidades dessa lista.</p>
        </div>
        <Link className="btn primary" to="/import">
          Importar lista
        </Link>
      </div>

      {openGames.length > 0 && (
        <section className="stack home-block" aria-label="Partidas abertas">
          <div>
            <h2>Partidas abertas</h2>
            <p className="muted">Mesa em andamento. Finalizar guarda o resultado e não impede apagar a lista. Apagar tira a partida.</p>
          </div>
          <div className="grid-cards">
            {openGames.map((game) => (
                <article key={game.id} className="card list-tile game-tile">
                  <Link to={`/games/${game.id}`} className="tile-open">
                    <span className="tile-kind">Partida</span>
                    <strong>Contra {game.opponentName || "oponente"}</strong>
                    <dl className="tile-facts">
                      <div>
                        <dt>Missão</dt>
                        <dd>{game.missionName || "Não informada"}</dd>
                      </div>
                      <div>
                        <dt>Atualizada</dt>
                        <dd className="mono">{new Date(game.updatedAt).toLocaleString("pt-BR")}</dd>
                      </div>
                    </dl>
                  </Link>
                  <div className="row">
                    <button onClick={() => (setOutcome(""), setMatchAction({ id: game.id, mode: "finish" }))}>Finalizar</button>
                    <button className="ghost" onClick={() => setMatchAction({ id: game.id, mode: "delete" })}>
                      Apagar
                    </button>
                  </div>
                </article>
              ))}
          </div>
        </section>
      )}
      {pastGames.length > 0 && (
        <section className="stack home-block" aria-label="Histórico de partidas">
          <div>
            <h2>Histórico</h2>
            <p className="muted">Partidas finalizadas com resultado. Não travam a exclusão da lista.</p>
          </div>
          <div className="grid-cards">
            {pastGames
              .filter((game) => !openGames.some((open) => open.id === game.id))
              .map((game) => (
                <article key={game.id} className="card list-tile game-tile">
                  <span className="tile-kind">Histórico</span>
                  <strong>
                    {con_dctResultLabel[game.result || ""] || "Resultado"} — contra {game.opponentName || "oponente"}
                  </strong>
                  <dl className="tile-facts">
                    <div>
                      <dt>Resultado</dt>
                      <dd>{con_dctResultLabel[game.result || ""] || "Não informado"}</dd>
                    </div>
                    <div>
                      <dt>Lista</dt>
                      <dd>{game.listName || "Lista apagada"}</dd>
                    </div>
                    <div>
                      <dt>Missão</dt>
                      <dd>{game.missionName || "Não informada"}</dd>
                    </div>
                  </dl>
                </article>
              ))}
          </div>
        </section>
      )}

      <section className="stack home-block" aria-label="Exércitos importados">
        <div>
          <h2>Exércitos</h2>
          <p className="muted">Uma lista por card. Facção, tamanho do jogo e pontos são da versão atual.</p>
        </div>
        {lists.data && armies.length === 0 && (
          <div className="card stack">
            <p>Nenhuma lista ainda.</p>
            <Link to="/import">Importe o JSON do New Recruit para criar a primeira.</Link>
          </div>
        )}
        {armies.length > 0 && (
          <div className="card row catalog-filter">
            <input aria-label="Filtrar listas" placeholder="Nome, facção ou jogo" value={query} onChange={(event) => setQuery(event.target.value)} />
            <select aria-label="Filtrar por facção" value={faction} onChange={(event) => setFaction(event.target.value)}>
              <option value="">Todas as facções</option>
              {factions.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
            <span className="muted mono">
              {visible.length} de {armies.length}
            </span>
            {choosing && (
              <>
                <label className="row">
                  <input
                    type="checkbox"
                    aria-label="Marcar as listas filtradas"
                    checked={visible.length > 0 && visible.every((list) => picked.includes(list.id))}
                    onChange={(event) => {
                      const ids = visible.map((list) => list.id as number);
                      setPicked((current) => (event.target.checked ? [...new Set([...current, ...ids])] : current.filter((id) => !ids.includes(id))));
                    }}
                  />
                  Marcar estas
                </label>
                <button className="ghost" disabled={!chosen.length} onClick={() => setConfirming(true)}>
                  Apagar selecionadas{chosen.length ? ` (${chosen.length})` : ""}
                </button>
                <button onClick={closeDelete}>Cancelar</button>
              </>
            )}
          </div>
        )}
        {notice && <p className="error">{notice}</p>}
        {armies.length > 0 && visible.length === 0 && <p className="muted">Nenhuma lista com esse filtro.</p>}
        <div className="grid-cards">
          {visible.map((list) => {
              const version = list.current_version;
              const onDevice = bundles.some((item) => item.id === version.id);
              const points = `${version.total_points_declared ?? "—"}${version.points_limit ? ` / ${version.points_limit}` : ""} pts`;
              return (
                <article key={list.id} className={`card list-tile ${choosing && picked.includes(list.id) ? "picked" : ""}`}>
                  {choosing && (
                    <label className="row tile-select">
                      <input
                        type="checkbox"
                        aria-label={`Selecionar ${list.name}`}
                        checked={picked.includes(list.id)}
                        onChange={(event) => togglePick(list.id, event.target.checked)}
                      />
                      Selecionar
                    </label>
                  )}
                  <Link to={`/versions/${version.id}`} className="tile-open">
                    <span className="tile-kind">Lista</span>
                    <strong>{list.name}</strong>
                    <dl className="tile-facts">
                      <div>
                        <dt>Facção</dt>
                        <dd>{version.faction_name || "Não informada"}</dd>
                      </div>
                      <div>
                        <dt>Jogo</dt>
                        <dd>{version.battle_size || "Tamanho não veio no import"}</dd>
                      </div>
                      <div>
                        <dt>Pontos</dt>
                        <dd className="mono">{points}</dd>
                      </div>
                      <div>
                        <dt>Versão</dt>
                        <dd className="mono">v{version.version_no}</dd>
                      </div>
                    </dl>
                    <span className="chip" title={onDevice ? "Esta versão está salva neste aparelho e abre sem rede." : "Abre com a API ligada. Use Preparar pra mesa dentro da lista para guardar aqui."}>
                      {onDevice ? "Neste aparelho" : "Só com a API ligada"}
                    </span>
                  </Link>
                  {cardErrors[list.id] && <p className="confirm-warn">{cardErrors[list.id]}</p>}
                  {!choosing && (
                    <button className="ghost" onClick={() => (setChoosing(true), setPicked([list.id]), setCardErrors((current) => { const next = { ...current }; delete next[list.id]; return next; }))}>
                      Apagar
                    </button>
                  )}
                </article>
              );
            })}
          {offline &&
            bundles.map((item) => (
              <Link key={item.id} to={`/versions/${item.id}`} className="card list-tile">
                <span className="tile-kind">Lista</span>
                <strong>{item.payload.list?.name}</strong>
                <dl className="tile-facts">
                  <div>
                    <dt>Facção</dt>
                    <dd>{item.payload.version?.faction_name || "Não informada"}</dd>
                  </div>
                </dl>
                <span className="chip">Cópia offline</span>
              </Link>
            ))}
        </div>
      </section>
      {match && matchAction && (
        <div className="confirm-backdrop" onClick={() => setMatchAction(null)}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="match-action-title"
            className="card confirm-panel stack"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="match-action-title" style={{ margin: 0 }}>
              {matchAction.mode === "delete" ? "Apagar partida" : "Finalizar partida"}
            </h2>
            <dl className="tile-facts">
              <div>
                <dt>Oponente</dt>
                <dd>{match.opponentName || "Não informado"}</dd>
              </div>
              <div>
                <dt>Missão</dt>
                <dd>{match.missionName || "Não informada"}</dd>
              </div>
              <div>
                <dt>Lista</dt>
                <dd>{matchList?.name || match.listName || "Não informada"}</dd>
              </div>
            </dl>
            {matchAction.mode === "finish" ? (
              <>
                <p className="confirm-warn">Finalizar guarda a partida no histórico. Ela não impede apagar a lista.</p>
                <div className="row" role="group" aria-label="Resultado">
                  {(
                    [
                      ["win", "Vitória"],
                      ["loss", "Derrota"],
                      ["draw", "Empate"],
                    ] as const
                  ).map(([id, label]) => (
                    <button key={id} className={outcome === id ? "primary" : ""} aria-pressed={outcome === id} onClick={() => setOutcome(id)}>
                      {label}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <p className="confirm-warn">Apagar tira a partida deste aparelho e do servidor. Ela não entra no histórico.</p>
            )}
            <div className="row">
              <button onClick={() => setMatchAction(null)}>Cancelar</button>
              <button className="primary" disabled={busy || (matchAction.mode === "finish" && !outcome)} onClick={commitMatch}>
                {matchAction.mode === "delete" ? "Apagar partida" : "Guardar resultado"}
              </button>
            </div>
          </section>
        </div>
      )}
      {confirming && (
        <div className="confirm-backdrop" onClick={() => setConfirming(false)}>
          <section
            role="dialog"
            aria-modal="true"
            aria-labelledby="delete-lists-title"
            className="card confirm-panel stack"
            onClick={(event) => event.stopPropagation()}
          >
            <h2 id="delete-lists-title" style={{ margin: 0 }}>
              Confirmar exclusão
            </h2>
            <p className="confirm-warn">
              Apague antes as partidas e os mapas ligados a essas listas. Se ainda existir partida ou mapa no servidor, a lista não sai.
            </p>
            <ul className="delete-choices">
              {chosen.map((list) => {
                const version = list.current_version;
                const linked = gamesOf(list);
                return (
                  <li key={list.id}>
                    <strong>{list.name}</strong>
                    <dl className="tile-facts">
                      <div>
                        <dt>Facção</dt>
                        <dd>{version.faction_name || "Não informada"}</dd>
                      </div>
                      <div>
                        <dt>Jogo</dt>
                        <dd>{version.battle_size || "Tamanho não veio no import"}</dd>
                      </div>
                      <div>
                        <dt>Pontos</dt>
                        <dd className="mono">
                          {version.total_points_declared ?? "—"}
                          {version.points_limit ? ` / ${version.points_limit}` : ""} pts
                        </dd>
                      </div>
                      <div>
                        <dt>Versão</dt>
                        <dd className="mono">v{version.version_no}</dd>
                      </div>
                    </dl>
                    {linked.length > 0 && (
                      <p className="confirm-warn">
                        Neste aparelho: {linked.map((game) => `contra ${game.opponentName || "oponente"}`).join(", ")}. Apague essa partida antes.
                      </p>
                    )}
                  </li>
                );
              })}
            </ul>
            <div className="row">
              <button onClick={() => setConfirming(false)}>Voltar</button>
              <button className="primary" disabled={!chosen.length || busy} onClick={commitDelete}>
                Excluir {chosen.length === 1 ? "1 lista" : `${chosen.length} listas`}
              </button>
            </div>
          </section>
        </div>
      )}
    </main>
  );
}

export function ImportScreen() {
  const [tab, setTab] = useState<"json" | "text">("json");
  const [raw, setRaw] = useState("");
  const [name, setName] = useState("");
  const [preview, setPreview] = useState<any>(null);
  const [faction, setFaction] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  async function analyse() {
    setBusy(true);
    try {
      const result = await api<any>("/imports/parse", {
        method: "POST",
        body: JSON.stringify({ raw_text: raw, format_hint: tab === "json" ? "nr_json" : null }),
      });
      setPreview(result);
      setFaction(result.header?.faction_name || "");
      setName((current) => current || result.header?.list_name || result.header?.faction_name || "");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não deu para analisar");
    } finally {
      setBusy(false);
    }
  }

  async function confirm() {
    setBusy(true);
    try {
      const created = await api<any>("/imports", {
        method: "POST",
        body: JSON.stringify({
          raw_text: raw,
          parse_hash: preview.parse_hash,
          target: { new_list_name: name || faction || "Lista" },
          resolutions: { faction_name: faction || null, leader_pairs: [] },
        }),
      });
      navigate(`/versions/${created.version_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Não deu para importar");
      setBusy(false);
    }
  }

  const cap = preview ? preview.header.points_limit ?? preview.header.total_points_declared : null;
  const state = preview ? pointsState(preview.header.points_sum, cap) : "exact";
  return (
    <main className="page">
      <div className="page-head">
        <h1>Importar lista</h1>
        <div className="seg" role="tablist">
          <button role="tab" className={tab === "json" ? "on" : ""} onClick={() => setTab("json")}>
            JSON (recomendado)
          </button>
          <button role="tab" className={tab === "text" ? "on" : ""} onClick={() => setTab("text")}>
            Texto
          </button>
        </div>
      </div>
      <div className="split-even">
        <section className="card stack">
          <p className="muted">{tab === "json" ? "No New Recruit: Exportar → JSON. Cole o conteúdo inteiro aqui." : "No New Recruit: Exportar → texto Simple ou WTC."}</p>
          <textarea value={raw} onChange={(event) => setRaw(event.target.value)} placeholder={tab === "json" ? "Cole o JSON" : "Cole o texto"} aria-label={tab === "json" ? "Cole o JSON" : "Cole o texto"} />
          <button className="primary" onClick={analyse} disabled={!raw.trim() || busy}>
            Analisar
          </button>
          {error && <p className="warn">{error}</p>}
        </section>

        <section className="card stack" aria-label="Prévia">
          {!preview && <p className="muted">A prévia aparece aqui: unidades, pontos e quem lidera quem.</p>}
          {preview && (
            <>
              <div className="row between">
                <div>
                  <h2 style={{ margin: 0 }}>{preview.header.list_name || preview.header.faction_name || "Sem facção"}</h2>
                  <span className="muted">
                    {[preview.header.battle_size, ...(preview.header.detachments || []).map((item: any) => item.name)].filter(Boolean).join(" · ")}
                  </span>
                </div>
                <span className={`pts-badge mono ${state}`}>
                  {preview.header.points_sum} / {cap ?? "—"}
                </span>
              </div>
              <ParseWarnings warnings={preview.warnings} />
              {!preview.header.faction_name && <input value={faction} placeholder="Facção" aria-label="Facção" onChange={(event) => setFaction(event.target.value)} />}
              <label className="stack" style={{ gap: 4 }}>
                <span className="muted">Nome da lista</span>
                <input value={name} onChange={(event) => setName(event.target.value)} />
              </label>
              <table className="units">
                <thead>
                  <tr>
                    <th>Unidade</th>
                    <th className="num">Mod</th>
                    <th className="num">Pts</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.units.map((unit: any, index: number) => (
                    <tr key={unit.line_no ?? unit.json_path ?? index}>
                      <td>
                        {unit.name}
                        {unit.is_warlord && <span className="tag gold">Warlord</span>}
                        {unit.enhancement_name && <span className="tag">{unit.enhancement_name}</span>}
                        <StatLine unit={unit} />
                      </td>
                      <td className="num mono">{unit.model_count}</td>
                      <td className="num mono">{unit.points}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="muted">
                Líderes: {preview.leader_pairs.map((pair: any) => `${pair.leader_name} → ${pair.bodyguard_name}`).join(", ") || "nenhum par encontrado"}
              </p>
              <button className="primary" onClick={confirm} disabled={busy}>
                Confirmar import
              </button>
            </>
          )}
        </section>
      </div>
    </main>
  );
}

function useVersion(vid: string) {
  const offline = useLiveQuery(() => bundleFor(Number(vid)), [vid]);
  const query = useQuery({ queryKey: ["version", vid], queryFn: () => api<any>(`/versions/${vid}`), retry: false });
  const data = useMemo(() => {
    if (query.data) return query.data;
    if (!offline) return null;
    const sum = offline.units.reduce((total: number, unit: any) => total + unit.points, 0);
    return {
      version: offline.version,
      units: offline.units,
      attachments: offline.attachments,
      points_sum: sum,
      points_declared: offline.version.total_points_declared,
      points_state: pointsState(sum, offline.version.total_points_declared),
    };
  }, [query.data, offline]);
  return { data, refetch: query.refetch, offline: !query.data && Boolean(offline), ready: Boolean(offline) };
}

function VersionShell({ vid, title, children, actions }: { vid: string; title?: string; children: ReactNode; actions?: ReactNode }) {
  const { data } = useVersion(vid);
  const tabs: [string, string][] = [
    ["", "Lista"],
    ["/guide", "Guia de turno"],
    ["/cheatsheet", "Colinha"],
    ["/weapons", "Armas"],
    ["/map", "Mapa"],
    ["/diff", "Versões"],
  ];
  return (
    <main className="page">
      <div className="page-head">
        <div>
          <h1 style={{ marginBottom: 2 }}>{title || data?.version?.faction_name || "Lista"}</h1>
          {data && (
            <span className="muted">
              {[`v${data.version.version_no}`, data.version.battle_size, ...(data.version.detachment_names || [])].filter(Boolean).join(" · ")}
            </span>
          )}
        </div>
        {actions}
      </div>
      <nav className="seg" style={{ marginBottom: 16 }} aria-label="Seções da lista">
        {tabs.map(([path, label]) => (
          <NavLink key={path} end to={`/versions/${vid}${path}`} className={({ isActive }) => `tab ${isActive ? "active" : ""}`}>
            {label}
          </NavLink>
        ))}
      </nav>
      {children}
    </main>
  );
}

export function VersionScreen() {
  const { vid = "" } = useParams();
  const { data, refetch, offline, ready } = useVersion(vid);
  const [selected, setSelected] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  const navigate = useNavigate();

  if (!data) return <main className="page">Carregando lista…</main>;

  const units = data.units as any[];
  const names = new Map<number, string>(units.map((unit) => [unit.id, unit.datasheet_name]));
  const leading = new Map<number, number>((data.attachments || []).map((item: any) => [item.leader_list_unit_id, item.bodyguard_list_unit_id]));
  const led = new Map<number, number>((data.attachments || []).map((item: any) => [item.bodyguard_list_unit_id, item.leader_list_unit_id]));
  const unit = units.find((item) => item.id === selected) || null;
  const state = data.points_state || pointsState(data.points_sum, data.points_declared);

  async function prepare() {
    try {
      const payload = await api<any>(`/versions/${vid}/bundle`);
      await saveBundle(payload);
      setNotice("Pronto pra mesa: a lista funciona sem rede.");
    } catch {
      setNotice(ready ? "Rede caiu. A cópia anterior continua no aparelho." : "Não deu para baixar a lista.");
    }
  }

  async function savePairs(pairs: { leader_list_unit_id: number; bodyguard_list_unit_id: number }[]) {
    try {
      await api(`/versions/${vid}/attachments`, { method: "PUT", body: JSON.stringify({ pairs }) });
      await refetch();
      setNotice("Líderes salvos.");
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Não deu para salvar");
    }
  }

  const currentPairs = (data.attachments || []).map((item: any) => ({ leader_list_unit_id: item.leader_list_unit_id, bodyguard_list_unit_id: item.bodyguard_list_unit_id }));

  return (
    <VersionShell
      vid={vid}
      actions={
        <div className="row">
          <span className={`pts-badge mono ${state}`}>
            {data.points_sum}
            {data.points_limit ? ` / ${data.points_limit}` : ""} pts · {STATE_LABEL[state]}
          </span>
          <button onClick={prepare} disabled={offline}>
            Preparar pra mesa
          </button>
          <button className="primary" onClick={() => navigate(`/versions/${vid}/game/new`)}>
            Nova partida
          </button>
        </div>
      }
    >
      {notice && <p className="card" role="status" style={{ marginBottom: 12 }}>{notice}</p>}
      <div className="split">
        <section className="card">
          <table className="units">
            <thead>
              <tr>
                <th>Unidade</th>
                <th>Líder</th>
                <th className="num">Mod</th>
                <th className="num">Pts</th>
              </tr>
            </thead>
            <tbody>
              {units.map((item) => (
                <tr key={item.id} className={`clickable ${selected === item.id ? "on" : ""}`} onClick={() => setSelected(item.id)}>
                  <td>
                    {item.datasheet_name}
                    {item.is_warlord && <span className="tag gold">Warlord</span>}
                    {item.enhancement_name && <span className="tag">{item.enhancement_name}</span>}
                  </td>
                  <td className="muted">{leading.has(item.id) ? `→ ${names.get(leading.get(item.id)!)}` : led.has(item.id) ? `← ${names.get(led.get(item.id)!)}` : ""}</td>
                  <td className="num mono">{item.model_count}</td>
                  <td className="num mono">{item.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        <aside className="card stack">
          {!unit && <p className="muted">Selecione uma unidade para ver modelos, armas e líder.</p>}
          {unit && (
            <>
              <h2 style={{ margin: 0 }}>{unit.datasheet_name}</h2>
              <p className="muted mono" style={{ margin: 0 }}>
                {unit.model_count} modelos · {unit.points} pts
              </p>
              <StatLine unit={unit.stats} />
              {(unit.ability_names || []).length > 0 && (
                <p className="muted" style={{ margin: 0 }}>
                  Habilidades: {unit.ability_names.join(" · ")}
                </p>
              )}
              {unit.enhancement_name && <p style={{ margin: 0 }}>Enhancement: {unit.enhancement_name}</p>}
              {(unit.models || []).length > 0 && (
                <ul className="weapons">
                  {unit.models.map((model: any) => (
                    <li key={model.id}>
                      <span>{model.model_name}</span>
                      <span className="mono">×{model.count}</span>
                    </li>
                  ))}
                </ul>
              )}
              <ul className="weapons">
                {(unit.wargear || []).map((item: any, index: number) => (
                  <li key={index}>
                    <span>
                      {item.count > 1 ? `${item.count}× ` : ""}
                      {item.weapon_name}
                    </span>
                    {(item.keywords || []).length > 0 && <span className="kw">{item.keywords.join(" ")}</span>}
                  </li>
                ))}
              </ul>
              {!offline && (
                <label className="stack" style={{ gap: 4 }}>
                  <span className="muted">Lidera</span>
                  <select
                    value={leading.get(unit.id) ?? ""}
                    onChange={(event) => {
                      const target = Number(event.target.value);
                      const rest = currentPairs.filter((pair: any) => pair.leader_list_unit_id !== unit.id);
                      savePairs(target ? [...rest, { leader_list_unit_id: unit.id, bodyguard_list_unit_id: target }] : rest);
                    }}
                  >
                    <option value="">Ninguém</option>
                    {units
                      .filter((item) => item.id !== unit.id)
                      .map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.datasheet_name}
                        </option>
                      ))}
                  </select>
                </label>
              )}
            </>
          )}
        </aside>
      </div>
    </VersionShell>
  );
}

export function LeadersScreen() {
  const { vid = "" } = useParams();
  return <Navigate to={`/versions/${vid}`} replace />;
}

export function GuideScreen() {
  const { vid = "" } = useParams();
  const [owner, setOwner] = useState("own");
  const offline = useLiveQuery(() => bundleFor(Number(vid)), [vid]);
  const query = useQuery({
    queryKey: ["guide", vid, owner],
    queryFn: () => api<any>(`/versions/${vid}/turn-guide?turn_owner=${owner}`),
    retry: false,
  });
  const data = query.data || (offline && offlineGuide(offline, owner));
  return (
    <VersionShell
      vid={vid}
      actions={
        <div className="row">
          <div className="seg">
            <button className={owner === "own" ? "on" : ""} onClick={() => setOwner("own")}>
              Meu turno
            </button>
            <button className={owner === "opponent" ? "on" : ""} onClick={() => setOwner("opponent")}>
              Turno do oponente
            </button>
          </div>
          <a className="btn" href={`/api/v1/versions/${vid}/turn-guide/export.md`}>
            Exportar Markdown
          </a>
        </div>
      }
    >
      <div className="grid-cards" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(320px, 1fr))" }}>
        {(data?.phases || []).map((phase: any) => (
          <section key={phase.phase} className="card stack" style={{ borderTop: `3px solid var(--${phase.phase}, var(--line))` }}>
            <h2 style={{ margin: 0 }}>{PHASE_LABEL[phase.phase] || phase.phase}</h2>
            {phase.groups
              .flatMap((group: any) => group.rows)
              .map((row: any, index: number) => (
                <EffectRow
                  key={index}
                  text={row.effect_text}
                  name={row.ability_name}
                  owner={row.owner_label}
                  hypothesis={row.is_hypothesis}
                  conditional={row.is_conditional}
                  conditionText={row.condition_text}
                />
              ))}
          </section>
        ))}
      </div>
    </VersionShell>
  );
}

function offlineGuide(bundle: any, owner: string) {
  const phases: Record<string, any[]> = {};
  for (const effect of bundle.rule_effects || []) {
    if (owner && effect.turn_owner && !["both", owner].includes(effect.turn_owner)) continue;
    const ability = (bundle.abilities || []).find((item: any) => item.id === effect.ability_id);
    const gate = guideMatch(effect.condition_json || {}, {
      shadow_areas: ["own_dz"],
      shadow_areas_complete: false,
      turn_owner: owner,
      phase: effect.phase,
    });
    if (!gate.include) continue;
    phases[effect.phase] = phases[effect.phase] || [];
    phases[effect.phase].push({
      ...effect,
      ability_name: ability?.name || "",
      is_conditional: gate.conditional,
      condition_text: gate.conditional ? conditionLabel(effect.condition_json || {}) : "",
    });
  }
  return {
    phases: Object.entries(phases).map(([phase, rows]) => ({ phase, groups: [{ timing: "during", rows }] })),
  };
}

export function CheatsheetScreen() {
  const { vid = "" } = useParams();
  const [text, setText] = useState("");
  const [rows, setRows] = useState<any[]>([]);
  const [notice, setNotice] = useState("");
  return (
    <VersionShell vid={vid}>
      <div className="split-even">
        <section className="card stack">
          <p className="muted">Uma linha de cabeçalho por fase, como "Command (Be'lakor)", e os lembretes embaixo.</p>
          <textarea value={text} onChange={(event) => setText(event.target.value)} placeholder={"Command (Be'lakor)\nconferir Shadow antes de gastar CP"} />
          <button
            className="primary"
            disabled={!text.trim()}
            onClick={async () => setRows((await api<any>("/cheatsheet/parse", { method: "POST", body: JSON.stringify({ text }) })).rows)}
          >
            Revisar
          </button>
        </section>
        <section className="card stack">
          {notice && <p role="status">{notice}</p>}
          {!rows.length && !notice && <p className="muted">A revisão aparece aqui antes de gravar.</p>}
          {rows.map((row, index) => (
            <div key={index} className="row between" style={{ borderTop: `3px solid var(--${row.phase}, var(--line))`, paddingTop: 6 }}>
              <span>{row.text}</span>
              <span className="muted">
                {PHASE_LABEL[row.phase] || row.phase} · {row.owner_label}
              </span>
            </div>
          ))}
          {rows.length > 0 && (
            <button
              className="primary"
              onClick={async () => {
                await api("/cheatsheet/commit", {
                  method: "POST",
                  body: JSON.stringify({
                    version_id: Number(vid),
                    rows: rows.map((row) => ({ ...row, owner: { kind: "general", name: row.owner_label } })),
                  }),
                });
                setRows([]);
                setText("");
                setNotice(`Colinha gravada. Ela aparece no guia de turno.`);
              }}
            >
              Gravar {rows.length} lembretes
            </button>
          )}
        </section>
      </div>
    </VersionShell>
  );
}

export function NewGameScreen() {
  const { vid = "" } = useParams();
  const [opponent, setOpponent] = useState("");
  const [faction, setFaction] = useState("");
  const [mission, setMission] = useState("");
  const [first, setFirst] = useState<"me" | "opponent">("me");
  const [cp, setCp] = useState(0);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  async function start() {
    let bundle = await bundleFor(Number(vid));
    if (!bundle) {
      try {
        bundle = await api<any>(`/versions/${vid}/bundle`);
        await saveBundle(bundle);
      } catch {
        setError("Esta lista não está no aparelho. Conecte e use Preparar pra mesa.");
        return;
      }
    }
    const id = crypto.randomUUID();
    const tag = "local";
    const event = {
      id: crypto.randomUUID(),
      game_id: id,
      seq: 1,
      device_id: deviceId(),
      type: "game_started",
      created_at: new Date().toISOString(),
      payload: {
        list_version_id: Number(vid),
        bundle_etag: tag,
        first_player: first,
        opponent_name: opponent,
        opponent_faction: faction,
        mission_name: mission,
        cp_me: cp,
        cp_opponent: 0,
        phases_v: 2,
        units: (bundle.units || []).map((unit: any) => ({ list_unit_id: unit.id, name: unit.datasheet_name })),
        attachments: bundle.attachments || [],
      },
    };
    await db.transaction("rw", db.games, db.game_events, db.sync_queue, async () => {
      await db.games.put({
        id,
        listVersionId: Number(vid),
        bundleEtag: tag,
        opponentName: opponent,
        opponentFaction: faction,
        missionName: mission,
        firstPlayer: first,
        cpMe: cp,
        cpOpponent: 0,
        seq: 1,
        status: "active",
        updatedAt: Date.now(),
      });
      await db.game_events.add(event);
      await db.sync_queue.add({ game_id: id, event });
    });
    flushSync();
    navigate(`/games/${id}`);
  }

  return (
    <VersionShell vid={vid} title="Nova partida">
      <form
        className="card stack"
        style={{ maxWidth: 520 }}
        onSubmit={(event) => {
          event.preventDefault();
          start();
        }}
      >
        <label className="stack" style={{ gap: 4 }}>
          <span className="muted">Oponente</span>
          <input value={opponent} onChange={(event) => setOpponent(event.target.value)} aria-label="Oponente" />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span className="muted">Facção do oponente</span>
          <input value={faction} onChange={(event) => setFaction(event.target.value)} />
        </label>
        <label className="stack" style={{ gap: 4 }}>
          <span className="muted">Missão</span>
          <input value={mission} onChange={(event) => setMission(event.target.value)} aria-label="Missão" />
        </label>
        <div className="seg">
          <button type="button" className={first === "me" ? "on" : ""} onClick={() => setFirst("me")}>
            Eu começo
          </button>
          <button type="button" className={first === "opponent" ? "on" : ""} onClick={() => setFirst("opponent")}>
            Oponente começa
          </button>
        </div>
        <label className="row">
          <span className="muted">CP inicial</span>
          <input className="mono narrow" type="number" min={0} max={99} value={cp} onChange={(event) => setCp(Number(event.target.value))} />
        </label>
        {error && <p className="warn">{error}</p>}
        <button className="primary" type="submit">
          Começar
        </button>
      </form>
    </VersionShell>
  );
}

export function SummaryScreen() {
  const { id = "" } = useParams();
  const events = useLiveQuery(() => db.game_events.where("game_id").equals(id).toArray(), [id], []);
  const game = useLiveQuery(() => db.games.get(id), [id]);
  const bundle = useLiveQuery(() => (game ? bundleFor(game.listVersionId) : undefined), [game?.listVersionId]);
  const projection = applyEvents(events);
  const names = new Map<number, string>((bundle?.units || []).map((unit: any) => [unit.id, unit.datasheet_name]));
  return (
    <main className="page" style={{ maxWidth: 760 }}>
      <div className="page-head">
        <h1>Resumo contra {game?.opponentName || "oponente"}</h1>
        <Link className="btn" to={`/games/${id}`}>
          Voltar à mesa
        </Link>
      </div>
      <div className="row" style={{ marginBottom: 16 }}>
        <span className="pts-badge mono">
          VP {projection.vp.me} – {projection.vp.opponent}
        </span>
        <span className="pts-badge mono">Rodada {projection.round}</span>
        <span className="pts-badge mono">CP {projection.cp.me}</span>
      </div>
      <EventTimeline events={events} names={names} />
    </main>
  );
}

export function WeaponsScreen() {
  const { vid = "" } = useParams();
  const offline = useLiveQuery(() => bundleFor(Number(vid)), [vid]);
  const query = useQuery({ queryKey: ["bundle", vid], queryFn: () => api<any>(`/versions/${vid}/bundle`), retry: false });
  const bundle = query.data || offline;
  const [target, setTarget] = useState(0);
  const [stationary, setStationary] = useState(false);
  const [charged, setCharged] = useState(false);
  const [halfRange, setHalfRange] = useState(false);
  if (!bundle) return <VersionShell vid={vid}>Carregando…</VersionShell>;
  const profiles = bundle.target_profiles || [];
  const chosen = profiles[target];
  const toggles = { stationary, charged, halfRange };
  return (
    <VersionShell
      vid={vid}
      actions={
        profiles.length > 0 && (
          <select value={target} onChange={(event) => setTarget(Number(event.target.value))} style={{ width: 240 }} aria-label="Alvo">
            {profiles.map((item: any, index: number) => (
              <option key={item.id} value={index}>
                Alvo: {item.name}
              </option>
            ))}
          </select>
        )
      }
    >
      <section className="card stack">
        <p className="muted">
          Dano esperado com Lethal, Sustained, Torrent e Twin-linked. Outras keywords ainda não entram.{" "}
          <span className="hypothesis">aproximado</span>
        </p>
        <div className="toggles">
          <button type="button" className={`toggle ${stationary ? "on" : ""}`} onClick={() => setStationary((v) => !v)}>
            Parada
          </button>
          <button type="button" className={`toggle ${charged ? "on" : ""}`} onClick={() => setCharged((v) => !v)}>
            Carregou
          </button>
          <button type="button" className={`toggle ${halfRange ? "on" : ""}`} onClick={() => setHalfRange((v) => !v)}>
            Meio alcance
          </button>
        </div>
        {!profiles.length && <p className="warn">Cadastre um perfil de alvo no catálogo para ver o dano esperado.</p>}
        {bundle.weapons?.some((item: any) => item.is_stub) && <p className="warn">Algumas armas não têm perfil numérico e aparecem como "—".</p>}
        <table className="units">
          <thead>
            <tr>
              <th>Unidade</th>
              <th>Arma</th>
              <th>Keywords</th>
              <th className="num">Dano médio (unidade inteira)</th>
            </tr>
          </thead>
          <tbody>
            {bundle.units.flatMap((unit: any) =>
              (unit.wargear || []).map((weapon: any, index: number) => (
                <tr key={`${unit.id}-${index}`}>
                  <td>{unit.datasheet_name}</td>
                  <td>{weapon.weapon_name}</td>
                  <td className="kw">{(weapon.keywords || []).join(" ")}</td>
                  <td className="num mono">
                    {(() => {
                      if (!chosen || weapon.is_stub) return "—";
                      const raw = expectedDamage(
                        { ...weapon, name: weapon.weapon_name, count: weapon.count ?? 1 },
                        chosen,
                        toggles,
                      );
                      return raw == null ? (
                        <span title="perfil incompleto">—</span>
                      ) : (
                        raw.toFixed(1)
                      );
                    })()}
                  </td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </section>
    </VersionShell>
  );
}

const SCALE = 10;
const BOARD_W = 60;
const BOARD_H = 44;

export function MapScreen() {
  const { vid = "" } = useParams();
  const { data } = useVersion(vid);
  const [spots, setSpots] = useState<{ id: number; name: string; x: number; y: number }[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [notice, setNotice] = useState("");
  if (!data) return <VersionShell vid={vid}>Carregando…</VersionShell>;
  return (
    <VersionShell vid={vid}>
      <div className="split">
        <section className="card stack" style={{ overflow: "auto" }}>
          <p className="muted">Escolha a unidade à direita e clique no tabuleiro (60″ × 44″). Arraste para ajustar.</p>
          <Stage
            width={BOARD_W * SCALE}
            height={BOARD_H * SCALE}
            onClick={(event) => {
              if (selected == null) return;
              const pos = event.target.getStage()?.getPointerPosition();
              if (!pos) return;
              const unit = data.units.find((item: any) => item.id === selected);
              setSpots((rows) => [...rows.filter((item) => item.id !== selected), { id: selected, name: unit.datasheet_name, x: pos.x, y: pos.y }]);
            }}
          >
            <Layer>
              <Rect width={BOARD_W * SCALE} height={BOARD_H * SCALE} fill="#1a2018" stroke="#3a4150" />
              <Rect width={BOARD_W * SCALE} height={12 * SCALE} fill="rgba(63,167,214,0.12)" />
              <Rect y={(BOARD_H - 12) * SCALE} width={BOARD_W * SCALE} height={12 * SCALE} fill="rgba(192,57,43,0.12)" />
              <Line points={[0, (BOARD_H / 2) * SCALE, BOARD_W * SCALE, (BOARD_H / 2) * SCALE]} stroke="#3a4150" dash={[6, 6]} />
              {spots.map((spot) => (
                <Circle
                  key={spot.id}
                  x={spot.x}
                  y={spot.y}
                  radius={14}
                  fill={selected === spot.id ? "#d4a017" : "#8A8A8A"}
                  draggable
                  onDragEnd={(event) => setSpots((rows) => rows.map((item) => (item.id === spot.id ? { ...item, x: event.target.x(), y: event.target.y() } : item)))}
                />
              ))}
              {spots.map((spot) => (
                <Text key={`t${spot.id}`} x={spot.x + 16} y={spot.y - 6} text={spot.name} fill="#E6E6E6" fontSize={12} />
              ))}
            </Layer>
          </Stage>
        </section>
        <aside className="card stack">
          <h2 style={{ margin: 0 }}>Unidades</h2>
          {data.units.map((unit: any) => (
            <button key={unit.id} className={selected === unit.id ? "primary" : ""} onClick={() => setSelected(unit.id)} style={{ justifyContent: "space-between", display: "flex", alignItems: "center" }}>
              <span>{unit.datasheet_name}</span>
              {spots.some((spot) => spot.id === unit.id) && <span>●</span>}
            </button>
          ))}
          <button
            className="primary"
            disabled={!spots.length}
            onClick={async () => {
              const board = await api<any>("/maps", { method: "POST", body: JSON.stringify({ list_version_id: Number(vid), name: "Mapa" }) });
              await api(`/maps/${board.id}/placements`, {
                method: "PUT",
                body: JSON.stringify({
                  placements: spots.map((spot) => ({ list_unit_id: spot.id, x_in: spot.x / SCALE, y_in: spot.y / SCALE, state: "on_table" })),
                }),
              });
              setNotice("Mapa salvo.");
              window.open(`/api/v1/maps/${board.id}/export.html`, "_blank");
            }}
          >
            Salvar e exportar HTML
          </button>
          {notice && <p role="status">{notice}</p>}
        </aside>
      </div>
    </VersionShell>
  );
}

export function DiffScreen() {
  const { vid = "" } = useParams();
  const { data } = useVersion(vid);
  const versions = useQuery({
    queryKey: ["versions-of", data?.version?.list_id],
    queryFn: () => api<any[]>(`/lists/${data.version.list_id}/versions`),
    enabled: Boolean(data?.version?.list_id),
  });
  const [other, setOther] = useState("");
  const [diff, setDiff] = useState<any>(null);
  const others = (versions.data || []).filter((item) => String(item.id) !== vid);
  return (
    <VersionShell vid={vid}>
      <section className="card stack" style={{ maxWidth: 720 }}>
        {!others.length && <p className="muted">Esta lista só tem uma versão. Importe de novo na mesma lista para comparar.</p>}
        {others.length > 0 && (
          <div className="row">
            <select value={other} onChange={(event) => setOther(event.target.value)} style={{ width: 220 }} aria-label="Outra versão">
              <option value="">Comparar com…</option>
              {others.map((item) => (
                <option key={item.id} value={item.id}>
                  v{item.version_no}
                </option>
              ))}
            </select>
            <button className="primary" disabled={!other} onClick={async () => setDiff(await api(`/versions/${vid}/diff/${other}`))}>
              Comparar
            </button>
          </div>
        )}
        {diff && (
          <>
            <p className="mono">
              Pontos {diff.points.left} → {diff.points.right}
            </p>
            {diff.added.map((item: any) => (
              <p key={`a${item.id}`} className="exact">
                + {item.datasheet_name}
              </p>
            ))}
            {diff.removed.map((item: any) => (
              <p key={`r${item.id}`} className="over">
                − {item.datasheet_name}
              </p>
            ))}
            {diff.changed.map((item: any) => (
              <p key={item.name} className="under">
                ~ {item.name}: {item.fields.map((field: any) => field.field).join(", ")}
              </p>
            ))}
            {!diff.added.length && !diff.removed.length && !diff.changed.length && <p className="muted">Sem diferenças nas unidades.</p>}
          </>
        )}
      </section>
    </VersionShell>
  );
}

const ABILITY_KINDS: [string, string, "datasheet" | "detachment" | "faction" | null][] = [
  ["unit", "Personagem / unidade", "datasheet"],
  ["leader", "Líder", "datasheet"],
  ["detachment", "Regra do detachment", "detachment"],
  ["faction", "Regra da facção", "faction"],
  ["general", "Geral (lembrete)", null],
];
const KIND_LABEL: Record<string, string> = { ...Object.fromEntries(ABILITY_KINDS.map(([id, label]) => [id, label])), core: "Core", stratagem: "Stratagem", enhancement: "Enhancement" };
const EFFECT_PHASES: [string, string][] = [
  ["round_start", "Início da rodada"],
  ["command", "Command"],
  ["battle_shock", "Battle-shock"],
  ["movement", "Movement"],
  ["shooting", "Shooting"],
  ["charge", "Charge"],
  ["fight", "Fight"],
  ["end_of_turn", "Fim do turno"],
  ["any", "Qualquer fase"],
];
const PERSONAL = new Set(["unit", "leader", "enhancement"]);
const LIST_LIMIT = 150;
const BSDATA_REPOS = ["wh40k-11e"];
const DIFF_LABELS: [string, string][] = [
  ["datasheets", "Fichas"],
  ["weapons", "Armas"],
  ["abilities", "Habilidades"],
  ["effects", "Efeitos com fase sugerida"],
  ["detachments", "Detachments"],
  ["enhancements", "Enhancements"],
];

type BsdataFile = { name: string; size: number; library: boolean; system: boolean };
type BsdataInfo = { repo: string; sha: string; date: string | null; message: string; files: BsdataFile[] };
type DiffGroup = { added: any[]; changed: any[]; kept: any[] };
type BsdataResult = {
  catalogue: string;
  faction: { id: number | null; name: string; created: boolean };
  applied: boolean;
  changes: Record<string, DiffGroup>;
  counts: Record<string, { added: number; changed: number; kept: number; same: number }>;
};

const diffLabel = (item: any) => (typeof item === "string" ? item : `${item.name}${item.fields ? ` (${item.fields.join(", ")})` : ""}${item.phase ? ` → ${item.phase}` : ""}`);

function BsdataPanel({ factions, onApplied }: { factions: any[]; onApplied: () => Promise<unknown> }) {
  const [repo, setRepo] = useState(BSDATA_REPOS[0]);
  const [info, setInfo] = useState<BsdataInfo | null>(null);
  const [catalogue, setCatalogue] = useState("");
  const [factionId, setFactionId] = useState("");
  const [result, setResult] = useState<BsdataResult | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const history = useQuery({ queryKey: ["bsdata-imports"], queryFn: () => api<any[]>("/bsdata/imports") });
  const playable = (info?.files || []).filter((file) => !file.library && !file.system);
  const last = history.data?.[0];

  async function run<T>(label: string, task: () => Promise<T>) {
    setBusy(label);
    setError(null);
    try {
      return await task();
    } catch (exc: any) {
      setError(exc?.message || "Falhou");
      return null;
    } finally {
      setBusy(null);
    }
  }

  const fetchCatalogues = () =>
    run("Buscando no GitHub…", async () => {
      const data = await api<BsdataInfo>(`/bsdata/repos/${repo}/catalogues`);
      setInfo(data);
      setResult(null);
      const known = data.files.find((file) => factions.some((faction) => `${faction.name}.json` === file.name));
      setCatalogue(known?.name || "");
    });

  const importNow = (apply: boolean) =>
    run(apply ? "Aplicando…" : "Comparando…", async () => {
      if (!info) return;
      const body = { repo: info.repo, sha: info.sha, catalogue, faction_id: factionId ? Number(factionId) : null, apply };
      const data = await api<BsdataResult>("/bsdata/import", { method: "POST", body: JSON.stringify(body) });
      setResult(data);
      if (apply) await Promise.all([onApplied(), history.refetch()]);
    });

  return (
    <section className="card stack bsdata" aria-label="Atualizar do BSData">
      <h2 style={{ margin: 0 }}>Atualizar do BSData</h2>
      <p className="muted">
        Baixa da BSData (GitHub) só a estrutura: fichas, armas, pontos, nomes das habilidades e a fase em que cada uma parece agir. O texto das regras não é guardado; o resumo você escreve com suas palavras.
        Stratagems não vêm da BSData.
      </p>
      {last && (
        <p className="muted mono">
          Última: {last.catalogue.replace(/\.json$/, "")} · commit {String(last.sha).slice(0, 7)} · {new Date(last.imported_at).toLocaleString()}
        </p>
      )}
      <div className="row">
        <label className="field">
          Edição
          <select value={repo} onChange={(event) => (setRepo(event.target.value), setInfo(null), setResult(null))}>
            {BSDATA_REPOS.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
        </label>
        <button onClick={fetchCatalogues} disabled={!!busy}>
          Buscar facções
        </button>
      </div>
      {info && (
        <>
          <p className="muted mono">
            Commit {info.sha.slice(0, 7)}
            {info.date ? ` · ${new Date(info.date).toLocaleDateString()}` : ""}
            {info.message ? ` · ${info.message}` : ""}
          </p>
          <div className="row">
            <label className="field">
              Catálogo
              <select value={catalogue} onChange={(event) => (setCatalogue(event.target.value), setResult(null))}>
                <option value="">Escolha…</option>
                {playable.map((file) => (
                  <option key={file.name} value={file.name}>
                    {file.name.replace(/\.json$/, "")}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Facção no app
              <select value={factionId} onChange={(event) => (setFactionId(event.target.value), setResult(null))}>
                <option value="">Detectar pelo nome</option>
                {factions.map((faction) => (
                  <option key={faction.id} value={faction.id}>
                    {faction.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button onClick={() => importNow(false)} disabled={!catalogue || !!busy}>
            Ver o que muda
          </button>
        </>
      )}
      {busy && <p className="muted">{busy}</p>}
      {error && <p className="error">{error}</p>}
      {result && (
        <div className="stack bsdata-diff">
          <p>
            {result.applied ? "Aplicado em" : "Vai atualizar"} <strong>{result.faction.name}</strong>
            {result.faction.id == null && !result.applied ? " (facção nova)" : ""}
            {result.faction.created ? " (facção criada)" : ""}.
          </p>
          <ul className="diff-list">
            {DIFF_LABELS.map(([key, label]) => {
              const count = result.counts[key];
              const group = result.changes[key];
              const items = [
                ...group.added.map((item) => ["novo", item] as const),
                ...group.changed.map((item) => ["muda", item] as const),
                ...group.kept.map((item) => ["mantido (você editou)", item] as const),
              ];
              return (
                <li key={key}>
                  <details>
                    <summary>
                      <strong>{label}</strong>{" "}
                      <span className="mono muted">
                        +{count.added} · ~{count.changed} · mantidos {count.kept} · iguais {count.same}
                      </span>
                    </summary>
                    {items.length ? (
                      <ul className="effect-mini">
                        {items.map(([tag, item], index) => (
                          <li key={index}>
                            <span className="tag">{tag}</span> {diffLabel(item)}
                          </li>
                        ))}
                      </ul>
                    ) : (
                      <p className="muted">Nada muda.</p>
                    )}
                  </details>
                </li>
              );
            })}
          </ul>
          {!result.applied ? (
            <button className="primary" onClick={() => importNow(true)} disabled={!!busy}>
              Aplicar
            </button>
          ) : (
            <p className="muted">Pronto. Os efeitos novos ficam como hipótese até você conferir e escrever o resumo.</p>
          )}
        </div>
      )}
    </section>
  );
}

export function CatalogScreen() {
  const abilities = useQuery({ queryKey: ["abilities"], queryFn: () => api<any[]>("/abilities") });
  const effects = useQuery({ queryKey: ["effects"], queryFn: () => api<any[]>("/effects") });
  const datasheets = useQuery({ queryKey: ["datasheets"], queryFn: () => api<any[]>("/datasheets") });
  const detachments = useQuery({ queryKey: ["detachments"], queryFn: () => api<any[]>("/detachments") });
  const factions = useQuery({ queryKey: ["factions"], queryFn: () => api<any[]>("/factions") });
  const [selected, setSelected] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const [kind, setKind] = useState("unit");
  const [owner, setOwner] = useState("");
  const [name, setName] = useState("");
  const [phase, setPhase] = useState("command");
  const [turnOwner, setTurnOwner] = useState("own");
  const [timing, setTiming] = useState("start");
  const [text, setText] = useState("");
  const [optionsText, setOptionsText] = useState("");
  const [count, setCount] = useState(1);
  const [scope, setScope] = useState("turn");
  const [hypothesis, setHypothesis] = useState(true);

  const ownerKind = ABILITY_KINDS.find(([id]) => id === kind)?.[2] ?? null;
  const ownerRows = ownerKind === "datasheet" ? datasheets.data : ownerKind === "detachment" ? detachments.data : ownerKind === "faction" ? factions.data : [];
  const options = optionsText.split("\n").map((item) => item.trim()).filter(Boolean);
  const byAbility = useMemo(() => {
    const map = new Map<number, any[]>();
    for (const row of effects.data || []) map.set(row.ability_id, [...(map.get(row.ability_id) || []), row]);
    return map;
  }, [effects.data]);
  const ownerName = (item: any) =>
    datasheets.data?.find((row) => row.id === item.datasheet_id)?.name ||
    detachments.data?.find((row) => row.id === item.detachment_id)?.name ||
    factions.data?.find((row) => row.id === item.faction_id)?.name ||
    "";
  const [search, setSearch] = useState("");
  const [onlyWithEffects, setOnlyWithEffects] = useState(false);
  const list = (abilities.data || []).filter((item) => item.kind !== "core");
  const needle = search.trim().toLowerCase();
  const visible = list.filter(
    (item) =>
      (!needle || `${item.name} ${ownerName(item)}`.toLowerCase().includes(needle)) &&
      (!onlyWithEffects || (byAbility.get(item.id) || []).length > 0),
  );
  const personal = visible.filter((item) => PERSONAL.has(item.kind));
  const general = visible.filter((item) => !PERSONAL.has(item.kind));
  const current = list.find((item) => item.id === selected);
  const refreshAll = () => Promise.all([abilities.refetch(), effects.refetch(), datasheets.refetch(), detachments.refetch(), factions.refetch()]);

  async function save() {
    setError(null);
    try {
      let abilityId = current?.id;
      if (!abilityId) {
        const body: Record<string, unknown> = { kind, name: name.trim(), is_hypothesis: hypothesis, summary_user: text.slice(0, 4000) };
        if (ownerKind) body[`${ownerKind}_id`] = Number(owner);
        const created = await api<any>("/abilities", { method: "POST", body: JSON.stringify(body) });
        abilityId = created.id;
      }
      await api(`/abilities/${abilityId}/effects`, {
        method: "POST",
        body: JSON.stringify({
          phase,
          turn_owner: turnOwner,
          timing,
          effect_kind: options.length ? "prompt" : "reminder",
          owner_label: current ? ownerName(current) || current.name : ownerRows?.find((row: any) => String(row.id) === owner)?.name || name.trim(),
          effect_text: text.trim(),
          choice_options: options,
          choice_count: options.length ? count : null,
          choice_scope: scope,
          is_hypothesis: hypothesis,
        }),
      });
      setText("");
      setOptionsText("");
      setSelected(abilityId ?? null);
      await Promise.all([abilities.refetch(), effects.refetch()]);
    } catch (exc: any) {
      setError(exc?.message || "Não foi possível salvar");
    }
  }

  const canSave = text.trim() && (current || (name.trim() && (!ownerKind || owner))) && (!options.length || (count >= 1 && count <= options.length));

  const group = (title: string, rows: any[]) => (
    <section className="card">
      <h2 style={{ marginTop: 0 }}>
        {title} <span className="muted mono">{rows.length}</span>
      </h2>
      {!rows.length && <p className="muted">{needle || onlyWithEffects ? "Nada com esse filtro." : "Nada cadastrado."}</p>}
      <ul className="ability-list">
        {rows.slice(0, LIST_LIMIT).map((item) => (
          <li key={item.id}>
            <button className={`ability-row ${selected === item.id ? "on" : ""}`} onClick={() => setSelected(selected === item.id ? null : item.id)}>
              <span>
                <strong>{item.name}</strong> <span className="muted">· {KIND_LABEL[item.kind] || item.kind}{ownerName(item) ? ` · ${ownerName(item)}` : ""}</span>
                {item.source === "bsdata" && <span className="tag">BSData</span>}
                {item.is_hypothesis && <span className="tag">hipótese</span>}
              </span>
              <span className="muted mono">{(byAbility.get(item.id) || []).length} efeitos</span>
            </button>
            {selected === item.id && (
              <ul className="effect-mini">
                {(byAbility.get(item.id) || []).map((effect) => (
                  <li key={effect.id}>
                    <span className="mono muted">
                      {EFFECT_PHASES.find(([id]) => id === effect.phase)?.[1] || effect.phase} · {effect.turn_owner}
                      {effect.source === "bsdata" && <span className="tag">fase sugerida</span>}
                    </span>
                    <span>{effect.effect_text}</span>
                    {(effect.choice_options || []).length > 0 && (
                      <span className="muted">
                        Escolhe {effect.choice_count} de: {effect.choice_options.join(", ")}
                      </span>
                    )}
                    <button
                      className="ghost link"
                      onClick={async () => {
                        if (!window.confirm("Apagar este efeito?")) return;
                        await api(`/effects/${effect.id}`, { method: "DELETE", body: "{}" });
                        effects.refetch();
                      }}
                    >
                      Apagar
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ul>
      {rows.length > LIST_LIMIT && <p className="muted">Mostrando {LIST_LIMIT} de {rows.length}. Use a busca para achar o resto.</p>}
    </section>
  );

  return (
    <main className="page">
      <div className="page-head">
        <h1>Catálogo de efeitos</h1>
        <p className="muted">Efeitos de personagem aparecem na carta da unidade. Detachment, facção e gerais aparecem no painel "Efeitos gerais" da mesa.</p>
      </div>
      <div className="split">
        <div className="stack">
          <BsdataPanel factions={factions.data || []} onApplied={refreshAll} />
          <div className="card row catalog-filter">
            <input aria-label="Buscar habilidade" placeholder="Buscar por habilidade ou dono" value={search} onChange={(event) => setSearch(event.target.value)} />
            <label className="row">
              <input type="checkbox" checked={onlyWithEffects} onChange={(event) => setOnlyWithEffects(event.target.checked)} />
              Só com efeitos
            </label>
          </div>
          {group("Personagens e unidades", personal)}
          {group("Gerais (detachment, facção, lembretes)", general)}
        </div>
        <aside className="card stack catalog-form">
          <h2 style={{ margin: 0 }}>{current ? `Novo efeito em ${current.name}` : "Nova habilidade"}</h2>
          {current && (
            <button className="ghost" onClick={() => setSelected(null)}>
              Criar outra habilidade
            </button>
          )}
          {!current && (
            <>
              <label className="field">
                Tipo
                <select value={kind} onChange={(event) => (setKind(event.target.value), setOwner(""))}>
                  {ABILITY_KINDS.map(([id, label]) => (
                    <option key={id} value={id}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              {ownerKind && (
                <label className="field">
                  {ownerKind === "datasheet" ? "Datasheet" : ownerKind === "detachment" ? "Detachment" : "Facção"}
                  <select value={owner} onChange={(event) => setOwner(event.target.value)}>
                    <option value="">Escolha…</option>
                    {(ownerRows || []).map((row: any) => (
                      <option key={row.id} value={row.id}>
                        {row.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label className="field">
                Nome da habilidade
                <input value={name} placeholder="Ex.: Lion — Command" onChange={(event) => setName(event.target.value)} />
              </label>
            </>
          )}
          <div className="row">
            <label className="field">
              Fase
              <select value={phase} onChange={(event) => setPhase(event.target.value)}>
                {EFFECT_PHASES.map(([id, label]) => (
                  <option key={id} value={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              Turno
              <select value={turnOwner} onChange={(event) => setTurnOwner(event.target.value)}>
                <option value="own">Meu</option>
                <option value="opponent">Do oponente</option>
                <option value="both">Ambos</option>
              </select>
            </label>
            <label className="field">
              Momento
              <select value={timing} onChange={(event) => setTiming(event.target.value)}>
                <option value="start">Início</option>
                <option value="during">Durante</option>
                <option value="end">Fim</option>
              </select>
            </label>
          </div>
          <label className="field">
            Texto do efeito
            <textarea rows={3} value={text} placeholder="Escreva com suas palavras" onChange={(event) => setText(event.target.value)} />
          </label>
          <label className="field">
            Opções para escolher (uma por linha, deixe vazio se não houver)
            <textarea rows={4} value={optionsText} onChange={(event) => setOptionsText(event.target.value)} />
          </label>
          {options.length > 0 && (
            <div className="row">
              <label className="field">
                Quantas escolher
                <input className="mono narrow" type="number" min={1} max={Math.min(6, options.length)} value={count} onChange={(event) => setCount(Number(event.target.value))} />
              </label>
              <label className="field">
                Vale por
                <select value={scope} onChange={(event) => setScope(event.target.value)}>
                  <option value="turn">Turno</option>
                  <option value="round">Rodada</option>
                  <option value="battle">Batalha inteira</option>
                </select>
              </label>
            </div>
          )}
          <label className="row">
            <input type="checkbox" checked={hypothesis} onChange={(event) => setHypothesis(event.target.checked)} />
            Marcar como hipótese (ainda não conferi no livro)
          </label>
          {error && <p className="error">{error}</p>}
          <button className="primary" disabled={!canSave} onClick={save}>
            Salvar efeito
          </button>
          <p className="muted">Partidas já abertas recebem o efeito novo quando a mesa recarregar com internet.</p>
        </aside>
      </div>
    </main>
  );
}

export function ConditionEditor() {
  const [phase, setPhase] = useState("shooting");
  const [state, setState] = useState("advanced");
  const condition = { all: [{ phase }, { "state.moved": state }] };
  return (
    <section className="card stack">
      <h2 style={{ margin: 0 }}>Condição</h2>
      <select value={phase} onChange={(event) => setPhase(event.target.value)} aria-label="Fase">
        <option value="shooting">Shooting</option>
        <option value="charge">Charge</option>
      </select>
      <select value={state} onChange={(event) => setState(event.target.value)} aria-label="Estado">
        <option value="advanced">Avançou</option>
        <option value="fell_back">Recuou</option>
      </select>
      <p className="mono muted" style={{ fontSize: 12, margin: 0 }}>
        {JSON.stringify(condition)}
      </p>
    </section>
  );
}

export function ConfigScreen() {
  const navigate = useNavigate();
  return (
    <main className="page" style={{ maxWidth: 560 }}>
      <h1>Config</h1>
      <section className="card stack">
        <p className="muted">Sair apaga as listas e partidas guardadas neste aparelho. O que já sincronizou continua no servidor.</p>
        <button
          onClick={async () => {
            const ok = await logout();
            if (ok) navigate("/login");
          }}
        >
          Sair e limpar este aparelho
        </button>
      </section>
    </main>
  );
}
