# Coding standards — List Companion

## Notação húngara (escopo A)

Variáveis e constantes **locais** usam prefixo + tipo + nome descritivo em PascalCase após o tipo:

| Papel | Prefixo | Exemplo |
|---|---|---|
| Variável local | `var_` | `var_strOpponent` |
| Constante local ou de módulo | `con_` | `con_intMaxCp` |

Tipos comuns: `str`, `int`, `bool`, `flt`, `lst`, `dct`, `obj`, `fn`, `uuid`, `set`, `tpl`.

```python
con_intMaxCp = 99
var_strOpponent = body.get("opponent_name") or ""
```

```ts
const con_strPhaseShooting = "shooting";
let var_strReason = "";
```

### Não renomear (contrato / superfície pública)

- Colunas SQL / migrations
- Keys JSON da API e payloads de evento
- Campos SQLAlchemy / Pydantic / Dexie
- Props e exports públicos de React
- Nomes de funções, classes, métodos e parâmetros de API pública (kwargs / props)

Parâmetros de funções internas podem usar húngara quando o nome não faz parte de um contrato externo.

## Mensagens de commit (PT-BR)

Formato Conventional Commits, assunto em português, sem `Co-Authored-By` nem crédito de AI:

```
<tipo>: <resumo no imperativo / descritivo curto>
```

Tipos: `feat`, `fix`, `docs`, `chore`, `refactor`, `test`, `ci`, `hotfix`, `style`, `perf`.

Exemplos:

- `feat: importar battle size do New Recruit`
- `fix: soltar unit_states ao apagar lista com partida finalizada`
- `docs: checklist API e Vite no README`
- `chore: ignorar regras de agentes no git`
- `hotfix: corrigir 503 db_not_at_head após migration`

## Outras regras do projeto

- Sem texto de regra da Games Workshop persistido; hipóteses marcadas.
- **Paráfrase de regras (S14):** o repositório é público e sem LICENSE. Em seeds, docs e commits use **só** uma linha parafraseada + seção/página da fonte. Nunca parágrafos, tabelas ou exemplos do PDF.
- Testes usam o banco `wh40k_test`, nunca `wh40k`.
- BSData: só hosts GitHub oficiais; cache em `api/data/` (fora do git).
- Pastas e arquivos de regras de modelos (Cursor, Claude, Codex, etc.) ficam fora do git (ver `.gitignore`).
- Login rate limit é global por IP do proxy (documentado); não confiar em `X-Forwarded-For` sem `--proxy-headers`.
