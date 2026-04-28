PYTHON ?= python

.PHONY: lint test migrate run

lint:
	$(PYTHON) -m compileall app tests
	ruff check .

test:
	pytest -q

migrate:
	alembic upgrade head

run:
	$(PYTHON) -m app.main
