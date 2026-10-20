COMPOSE ?= docker compose
API ?= $(COMPOSE) exec -T api
DB ?= $(COMPOSE) exec -T db

.PHONY: up down token migrate seed backup restore-test test e2e

up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

token:
	$(API) python -m app.scripts.token --invalidate

migrate:
	@mkdir -p backups
	$(DB) pg_dump -U wh40k wh40k > backups/pre-migrate-$$(date +%Y%m%d%H%M%S).dump
	$(API) alembic upgrade head

seed:
	$(API) python -m app.scripts.seed

backup:
	@mkdir -p backups
	$(DB) pg_dump -U wh40k wh40k > backups/wh40k-$$(date +%Y%m%d%H%M%S).dump

restore-test:
	$(API) python -m pytest -q tests/test_restore.py

test:
	$(API) python -m pytest -q
	cd web && npm test

e2e:
	cd web && npm run e2e
