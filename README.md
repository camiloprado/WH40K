# List Companion

Tracker de partida de Warhammer 40.000. Você importa uma lista do New Recruit, revisa pontos e líderes, e joga a rodada no celular sem papel: cada toque grava o que a unidade já fez, e o app avisa o que ela ainda pode fazer na fase atual.

Uso local / privado. O app não redistribui texto de regra da Games Workshop. Lembretes de facção, stratagems de exemplo e Shadow of Chaos são anotações do próprio usuário, marcadas como hipótese quando não foram revisadas.

## O que ele faz

1. **Importar** o export do New Recruit em JSON ou o texto Simple/WTC.
2. **Ver a lista** consolidada (abaixo, exato ou acima dos pontos declarados) e ajustar quem lidera quem.
3. **Guia de turno** por fase, mais a colinha que você cola na mão.
4. **Partida ao vivo**, offline. Uma unidade que avançou fica cinza no Shooting, com o motivo. Fechar e abrir de novo mantém o estado. Com rede, os eventos sincronizam.
5. **Depois da mesa:** checagem aproximada de armas, mapa e diff entre versões da mesma lista.

O motor só sinaliza. Ele não impede o toque. Um override fica registrado no evento.

## Como executar

Checklist rápido: (1) Postgres no overlay de dev, (2) API em `127.0.0.1:18001`, (3) Vite em `http://127.0.0.1:5173`. Abrir só a API no navegador devolve 404 — a interface é o Vite.

Credenciais e URL do banco vêm de `.env.example` (copie para `.env`). O Compose de desenvolvimento (`docker-compose.dev.yml`) publica portas locais alternativas para não conflitar com Postgres/API padrão na máquina:

| Serviço | Endereço (dev overlay) |
|---|---|
| Postgres 16 | `127.0.0.1:15432` |
| API | `127.0.0.1:18001` |
| Caddy (stack completo) | `127.0.0.1:18081` |
| Vite | `http://127.0.0.1:5173` |

No Compose base, o Caddy sobe em `127.0.0.1:443`. Ajuste as portas no overlay se precisar.

### 1. Banco

Na raiz do repositório:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d db
```

### 2. API

```powershell
cd api
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
# Defina DATABASE_URL como em .env.example (host/porta do overlay de dev)
$env:DATABASE_URL = "postgresql+psycopg://wh40k:wh40k@127.0.0.1:15432/wh40k"
.\.venv\Scripts\python -m alembic upgrade head
.\.venv\Scripts\python -m app.scripts.token
.\.venv\Scripts\python -m app.scripts.seed
.\.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 18001
```

`token` imprime a senha uma vez e grava só o hash em `api/data/app_token_hash` (fora do git). Guarde essa linha: é o que a tela de login pede. Rodar de novo invalida as sessões abertas.

`seed` grava lembretes das fases e um exemplo de facção. Não é texto de codex.

### 3. Interface

Em outro terminal:

```powershell
cd web
npm install
npm run dev
```

Abra `http://127.0.0.1:5173`, entre com o token e importe uma lista. O Vite encaminha `/api` para a porta da API no overlay de dev, então o cookie de sessão fica na mesma origem.

Para jogar sem rede: na lista, use **Preparar pra mesa**, comece a partida e pode derrubar a API. O estado fica no IndexedDB.

### Stack completo

`make` não vem no Windows. Com Make instalado, `make up` sobe Postgres, API e Caddy pelo `docker-compose.yml` (só o Caddy publica porta, em `127.0.0.1:443`). Os alvos `token`, `migrate`, `seed`, `backup`, `test` e `e2e` rodam dentro dos containers.

Com o overlay de desenvolvimento:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

## Testes

```powershell
cd api
.\.venv\Scripts\python -m pytest -q
```

O pytest recria e migra um banco separado, `wh40k_test`, no mesmo Postgres do overlay de dev. O banco de dados da aplicação não é tocado.

Depois de puxar uma migration nova, rode `alembic upgrade head` e reinicie o uvicorn: a API recusa requisições (503 `db_not_at_head`) se o código e o banco estiverem em revisões diferentes.

```powershell
cd web
npm test
npx playwright install chromium
npm run e2e
```

O Playwright espera o Vite em `http://127.0.0.1:5173`. O cenário cobre a unidade que avançou e aparece cinza no Shooting.

## Layout

- `api/` — FastAPI, SQLAlchemy e Alembic. O parser e o projetor de eventos não dependem da tela.
- `web/` — React, Vite e o motor de elegibilidade. A partida grava o evento antes de confirmar o toque.
- `fixtures/` — listas de exemplo e o replay dos eventos. Sem texto de regra.
- `deploy/` — Caddy na mesma origem da API.
- `SPEC.md` — o edital técnico (v0.3).

## Fora deste app

Sem scraping e sem acesso público. Um aparelho só; o sync é da mesma conta.

## Atualizar do BSData

No Catálogo, o painel "Atualizar do BSData" busca o commit mais recente de [BSData/wh40k-11e](https://github.com/BSData/wh40k-11e), deixa escolher a facção e mostra o que muda antes de aplicar. Ele traz fichas, armas, pontos, detachments, enhancements e os nomes das habilidades, com a fase sugerida e as opções de "escolha N". O texto das regras não é guardado: os efeitos chegam como hipótese, com um lembrete para o usuário escrever o resumo. Nada é apagado, e fichas ou resumos editados não são sobrescritos. Stratagems não estão no BSData e continuam manuais. Os arquivos baixados ficam em `api/data/bsdata/` (fora do git).
