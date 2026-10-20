import type { ReactNode } from "react";

export const PHASES = [
  ["round_start", "INI"],
  ["command", "CMD"],
  ["battle_shock", "BS"],
  ["movement", "MOV"],
  ["shooting", "SHT"],
  ["charge", "CHG"],
  ["fight", "FGT"],
  ["end_of_turn", "END"],
] as const;

export function HypothesisBadge({ on }: { on?: boolean }) {
  if (!on) return null;
  return <span className="hypothesis">HIPÓTESE</span>;
}

export function WakeLockChip({ supported }: { supported: boolean }) {
  if (supported) return null;
  return (
    <p className="card muted">
      Tela pode apagar. Seu navegador não mantém a tela acesa. Ajuste o bloqueio automático do celular.
    </p>
  );
}

export function PhaseBar({ phase, onPick }: { phase: string; onPick: (phase: string) => void }) {
  return (
    <nav className="phasebar">
      {PHASES.map(([id, label]) => (
        <button key={id} className={phase === id ? "on" : ""} style={{ color: `var(--${id})` }} onClick={() => onPick(id)}>
          {label}
        </button>
      ))}
    </nav>
  );
}

export function NextPhaseButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="primary next" onClick={onClick}>
      Próxima fase
    </button>
  );
}

export function EligibilityReason({ reasons }: { reasons: string[] }) {
  if (!reasons.length) return null;
  return <span className="muted">{reasons.join(" · ")}</span>;
}

export function SyncIndicator({ online, pending }: { online: boolean; pending: number }) {
  const label = !online ? "Offline" : pending ? `Sync ${pending}` : "Sync ok";
  return <span className="mono muted">{label}</span>;
}

export function ListVersionBadge({ createdAt }: { createdAt?: string }) {
  if (!createdAt) return null;
  return <span className="mono muted">{new Date(createdAt).toLocaleString("pt-BR")}</span>;
}

export function ParseWarnings({ warnings }: { warnings: { reason: string; text?: string; line_no?: number }[] }) {
  if (!warnings?.length) return null;
  return (
    <ul className="card">
      {warnings.map((item, index) => (
        <li key={index}>
          {item.line_no ? `L${item.line_no} ` : ""}
          {item.reason}
          {item.text ? ` — ${item.text}` : ""}
        </li>
      ))}
    </ul>
  );
}

export function ArmyHeader({ name, points, state }: { name: string; points: string; state?: string }) {
  return (
    <header className="card">
      <h1>{name}</h1>
      <p className={`mono ${state || ""}`}>{points}</p>
    </header>
  );
}

export function EffectRow({ text, name, owner, hypothesis }: { text: string; name: string; owner: string; hypothesis?: boolean }) {
  return (
    <p>
      {text} — {name} ({owner}) <HypothesisBadge on={hypothesis} />
    </p>
  );
}

export function UnitCard({ children }: { children: ReactNode }) {
  return <div className="card">{children}</div>;
}

export function GameHeader({ round, player, phase, cp, vp, extra }: { round: number; player: string; phase: string; cp: number; vp: string; extra?: ReactNode }) {
  const who = player === "me" ? "Meu turno" : "Oponente";
  const label = PHASES.find(([id]) => id === phase)?.[1] || phase;
  return (
    <header className="top">
      <strong className="mono">
        R{round} · {who} · {label} · CP {cp} · VP {vp}
      </strong>
      {extra}
    </header>
  );
}

export function UndoToast({ message, onUndo }: { message: string | null; onUndo: () => void }) {
  if (!message) return null;
  return (
    <div className="toast">
      {message} <button onClick={onUndo}>Desfazer</button>
    </div>
  );
}
