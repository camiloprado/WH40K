import { useEffect, useRef, useState } from "react";

type ConfirmDetail = {
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  resolve: (ok: boolean) => void;
};

let var_objPending: ConfirmDetail | null = null;
const con_lstListeners = new Set<() => void>();

function notify() {
  for (const fn of con_lstListeners) fn();
}

/** Folha de confirmação (F14) — substitui window.confirm. */
export function askConfirm(
  message: string,
  opts?: { confirmLabel?: string; cancelLabel?: string },
): Promise<boolean> {
  return new Promise((resolve) => {
    var_objPending = {
      message,
      confirmLabel: opts?.confirmLabel || "Confirmar",
      cancelLabel: opts?.cancelLabel || "Cancelar",
      resolve,
    };
    notify();
  });
}

export function ConfirmHost() {
  const [detail, setDetail] = useState<ConfirmDetail | null>(var_objPending);
  const firstBtn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const sync = () => setDetail(var_objPending);
    con_lstListeners.add(sync);
    return () => {
      con_lstListeners.delete(sync);
    };
  }, []);

  useEffect(() => {
    if (!detail) return;
    firstBtn.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        close(false);
      }
      if (event.key === "Tab" && detail) {
        const root = document.querySelector(".sheet-confirm[data-confirm]");
        if (!root) return;
        const focusable = [...root.querySelectorAll<HTMLElement>("button")];
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [detail]);

  function close(ok: boolean) {
    const current = var_objPending;
    var_objPending = null;
    setDetail(null);
    notify();
    current?.resolve(ok);
  }

  if (!detail) return null;
  return (
    <div className="sheet-confirm" role="dialog" aria-modal data-confirm aria-label="Confirmação">
      <p>{detail.message}</p>
      <div className="row">
        <button ref={firstBtn} className="ghost" type="button" onClick={() => close(false)}>
          {detail.cancelLabel}
        </button>
        <button className="primary" type="button" onClick={() => close(true)}>
          {detail.confirmLabel}
        </button>
      </div>
    </div>
  );
}
