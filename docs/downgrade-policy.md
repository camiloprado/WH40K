# Política de downgrade (DB5)

Downgrades Alembic **não apagam** log de eventos nem histórico de partida.

Se um downgrade precisaria deletar linhas (`effect_chosen`, `round_start`, games sem lista, etc.), ele falha com `RAISE EXCEPTION` e mensagem clara pedindo restaurar o snapshot (S3 / `make restore-test`).

O CI pode rodar `alembic downgrade base` em banco **vazio**; com dados reais, use backup antes de qualquer downgrade.
