PYTHON ?= python

.PHONY: check lint test migrate run health compose-config compose-build

check:
	$(PYTHON) -m compileall app tests alembic
	ruff check .
	pytest -q

lint:
	$(PYTHON) -m compileall app tests alembic
	ruff check .

test:
	pytest -q

migrate:
	alembic upgrade head

run:
	$(PYTHON) -m app.main

health:
	$(PYTHON) -m app.healthcheck

compose-config:
	docker compose config

compose-build:
	docker compose build