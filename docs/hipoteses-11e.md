# Hipóteses da 11ª no List Companion

A flag `is_hypothesis` só marca o efeito na tela e no Markdown exportado; o motor de elegibilidade não lê essa flag e não deixa de aplicar a regra por causa dela.

Fontes conferidas em 20/10/2026: Core Rules (01/06/2026), Universal Rules Updates v1.1 (26/08/2026), Faction Pack Chaos Daemons v1.2 (30/09/2026), Event Companion v1.3 (14/10/2026). O efeito mecânico abaixo é paráfrase de uma linha. Nenhum parágrafo de regra foi copiado.

| Hipótese no app | O que o código faz hoje | O que a fonte oficial permite afirmar | URL |
|---|---|---|---|
| Unidade engajada no tiro (CLOSE-QUARTERS / PISTOL; MONSTER/VEHICLE). | Em Shooting: engajada e avançou → inativa (sem tiro). Engajada e não é MONSTER/VEHICLE → só CLOSE-QUARTERS/PISTOL sem BLAST, só contra quem está engajado; **sem −1**. MONSTER/VEHICLE engajado → todas as armas; aviso de −1 nas não-CQ e BLAST que não miram o engajado. Desengajada com CQ e outras armas → aviso de escolha (24.07). Override `shoot_engaged` libera. (`web/src/engine/eligibility.ts`) | Engajada e avançou não faz close-quarters shooting. Não-MV: só CLOSE-QUARTERS/PISTOL contra o engajado. MV: todas as armas; −1 exceto CQ no engajado; BLAST não mira o engajado. Seções 10.06, 17.03, 24.07, 24.27. | [Core Rules 01/06/2026](https://assets.warhammer-community.com/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf) |
| Battle-shock: OC traço; não recebe stratagem; não começa/conclui ação. | Aviso «OC vira traço…»; status `warn` fora da fase de battle-shock. Estado `battle_shocked` **persiste** entre turnos até passar no teste. Passou/Falhou só no turno próprio. Movement engajada + BS → Desperate Escape; engajada sem BS + recuo → lembrete de teste depois. `canStartAction` bloqueia engajada/BS/avançou (TITANIC engajada ok). Stratagem em alvo BS → aviso. | OC vira traço (não “0”). Teste na Command do jogador ativo (08.03). Desperate Escape (09.07). Ações (16.01). | Mesmo PDF, 01.07, 08.03, 09.07, 16.01. |
| A flag `is_hypothesis` bloqueia o uso da regra. | Não bloqueia. Selo visual + export Markdown. O motor não consulta o campo. | Nada a confirmar na Games Workshop: comportamento só do app. | Código do repositório. |
| Efeito importado do BSData traz a regra e a fase certa. | Fase/timing por palpite regex; texto gravado é placeholder com `is_hypothesis=True`. | O Core Rules não descreve esse import. | `api/app/services/bsdata/parse.py`, `sync.py`. |

O PDF [Universal Rules Updates v1.1](https://assets.warhammer-community.com/eng_wh40k_core&key_universal_rules_updates-lu3grocned-rphh78bl6k.pdf) não altera battle-shock nem tiro engajado.

## Shadow of Chaos (fonte: Daemons)

**Fonte oficial:** Faction Pack Chaos Daemons v1.2, p. 2 e FAQ p. 131.

- A zona de deploy do usuário está **sempre** no Shadow.
- No começo de **cada fase**, nos dois turnos, o app pergunta (ou calcula pelos objetivos) se a Terra de Ninguém e a zona do oponente estão no Shadow: controle ≥ metade dos objetivos da área; área sem objetivo nunca entra.
- Estado por `(round, turn_player, phase)`; `game.shadow_of_chaos` ∈ `own_dz | nml | opp_dz`.
- `true` = TdN ou zona do oponente (não basta `own_dz`); fato desconhecido falha fechado.
- Só exército Legiones Daemonica / Chaos Daemons; Daemonic Pact (HA/CK) sem card.
- Distâncias 6" (Terror) e 9" (Plague Legion): só lembrete de texto (o app não mede distância).
- Manifestation: paráfrase confirmada (não hipótese). Terror (`turn_owner: opponent`) e Plague Legion (`turn_owner: both`, só destacamento Plague Legion): `is_hypothesis=True` até errata. Card do Shadow sem selo HIPÓTESE.

## Política de paráfrase (S14)

Repo público sem LICENSE: em seeds, docs e commits, só uma linha parafraseada + seção/página. Nunca parágrafos ou tabelas do PDF.

## O que continua sem fonte / fora do motor

- **Textos de datasheet** no import: placeholder até o usuário escrever o resumo.
- **Keywords no dano:** Sustained/Lethal/Twin-linked/Torrent no cliente (`damage.ts`); Devastating Wounds e demais ainda fora.
- **C10–C17 / DB / B1–B3:** flags por turno, `activePlayer`, stratagem alvo, `phases_v=2`+`end_of_round`, sync `rejected[]`, seed Core/Invulnerability, perfis Tyranids com `source_ref`.
- **Unidades do oponente** para 17.03/Terror real: Q9 do SPEC.

## Gate manual (§11 Correcoes a–o)

Após merge desta rodada: smoke Daemons passos j–m; checklist a–o (inclui migrations Q7/DB1 e rejeitados DB3).
