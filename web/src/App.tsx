import { useEffect } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useLiveQuery } from "dexie-react-hooks";
import { useSession } from "./api";
import { db } from "./db";
import { flushSync } from "./sync";
import { GameScreen } from "./GameScreen";
import {
  CatalogScreen,
  CheatsheetScreen,
  ConfigScreen,
  DiffScreen,
  GuideScreen,
  HomeScreen,
  ImportScreen,
  LeadersScreen,
  LoginScreen,
  MapScreen,
  NewGameScreen,
  SummaryScreen,
  VersionScreen,
  WeaponsScreen,
} from "./screens";

export function App() {
  const needsAuth = useSession((state) => state.needsAuth);
  const updateReady = useSession((state) => state.updateReady);
  const location = useLocation();
  const activeGame = useLiveQuery(() => db.games.where("status").equals("active").reverse().sortBy("updatedAt").then((rows) => rows[0]), []);
  useEffect(() => {
    const run = () => flushSync();
    window.addEventListener("online", run);
    return () => window.removeEventListener("online", run);
  }, []);
  const inGame = location.pathname.startsWith("/games/") && !location.pathname.endsWith("/summary");
  return (
    <>
      {location.pathname !== "/login" && (
        <nav className="topnav" aria-label="Principal">
          <NavLink to="/" className="brand">
            List Companion
          </NavLink>
          <NavLink to="/" end className={({ isActive }) => `tab ${isActive ? "active" : ""}`}>
            Listas
          </NavLink>
          <NavLink to="/import" className={({ isActive }) => `tab ${isActive ? "active" : ""}`}>
            Importar
          </NavLink>
          {activeGame && (
            <NavLink to={`/games/${activeGame.id}`} className={() => `tab ${inGame ? "active" : ""}`}>
              Partida
            </NavLink>
          )}
          <NavLink to="/catalog" className={({ isActive }) => `tab ${isActive ? "active" : ""}`}>
            Catálogo
          </NavLink>
          <NavLink to="/config" className={({ isActive }) => `tab ${isActive ? "active" : ""}`}>
            Config
          </NavLink>
        </nav>
      )}
      {updateReady && (
        <div className="card update-toast row">
          Nova versão disponível
          <button
            className="primary"
            onClick={() => {
              if (inGame && !window.confirm("Recarregar agora? A partida fica salva neste aparelho.")) return;
              (window as unknown as { __applyUpdate?: () => void }).__applyUpdate?.();
            }}
          >
            Recarregar
          </button>
        </div>
      )}
      <Routes>
        <Route path="/login" element={<LoginScreen />} />
        <Route path="/" element={needsAuth ? <Navigate to="/login" /> : <HomeScreen />} />
        <Route path="/import" element={<ImportScreen />} />
        <Route path="/versions/:vid" element={<VersionScreen />} />
        <Route path="/versions/:vid/leaders" element={<LeadersScreen />} />
        <Route path="/versions/:vid/guide" element={<GuideScreen />} />
        <Route path="/versions/:vid/cheatsheet" element={<CheatsheetScreen />} />
        <Route path="/versions/:vid/weapons" element={<WeaponsScreen />} />
        <Route path="/versions/:vid/map" element={<MapScreen />} />
        <Route path="/versions/:vid/diff" element={<DiffScreen />} />
        <Route path="/versions/:vid/game/new" element={<NewGameScreen />} />
        <Route path="/games/:id" element={<GameScreen />} />
        <Route path="/games/:id/summary" element={<SummaryScreen />} />
        <Route path="/catalog" element={<CatalogScreen />} />
        <Route path="/config" element={<ConfigScreen />} />
      </Routes>
    </>
  );
}
