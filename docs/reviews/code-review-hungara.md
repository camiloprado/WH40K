# Code-review — húngara A + melhorias (fixed point `d335fd7`)

Diff: `git diff d335fd7...HEAD` (este documento acompanha o commit da fase).

Spec: [SPEC.md](../../SPEC.md). Standards: [CODING_STANDARDS.md](../../CODING_STANDARDS.md) + smell baseline Fowler.

## Standards

- **OK:** escopo A respeitado nos módulos tocados (`condition.py`, `eligibility.ts`, `damage.ts`, `sync.ts`, `api.ts`, `security.py`, `errors.py`, aliases em `project.py` / `project.ts`). Contrato HTTP/DB/props públicas não renomeado.
- **OK:** `PHASES` / `COOKIE` mantidos como aliases públicos onde já havia import externo.
- **Judgement — Shotgun Surgery:** a húngara ainda não cobre `screens.tsx` / `GameScreen.tsx` / `views.py` / routers por completo; CODING_STANDARDS marca o alvo, a migração continua por fatia.
- **Judgement — Duplicated Code:** aliases `PHASES = con_lstPhases` repetem o padrão em API e web — aceitável para compat.
- Nenhuma violação dura de CODING_STANDARDS nos arquivos convertidos.

## Spec

- **OK (SPEC shooting):** motor passa a usar CLOSE-QUARTERS / PISTOL, bloqueia BLAST no engajado, aviso de −1; SPEC § tabela de fases atualizada.
- **OK:** exclusão de lista com partida `finished` via `_detach_finished_games` (histórico com `list_label`).
- **OK:** uso local / sem texto GW; BSData continua sem guardar descrição.
- **Parcial:** húngara não era requisito do SPEC v0.3 — é padrão de projeto (CODING_STANDARDS). Scope creep consciente e documentado.
- **Parcial:** battle-shock ainda limpa no wrap do turno no projetor (SPEC/pesquisa 11e sugerem nuance); não reescrito nesta fatia além do texto de elegibilidade.

## Resumo

- Standards: 2 findings (judgement), 0 hard.
- Spec: 2 partials, 0 missing críticos do MVP.
- Pior Standards: cobertura incompleta da húngara nas telas grandes.
- Pior Spec: battle-shock / wrap ainda legado 10e-ish no projetor.
