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

## Outras regras do projeto

- Sem texto de regra da Games Workshop persistido; hipóteses marcadas.
- Testes usam o banco `wh40k_test`, nunca `wh40k`.
- BSData: só hosts GitHub oficiais; cache em `api/data/` (fora do git).
