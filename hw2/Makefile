.PHONY: generate validate build up down test demo db-migrate db-info db-validate db-shell db-inspect

generate:
	docker compose run --rm --no-deps codegen generate -c openapi/generator.yaml

validate:
	docker compose run --rm --no-deps codegen validate -i openapi/openapi.yaml

build:
	docker compose build marketplace-api

up:
	docker compose up --build -d marketplace-api

down:
	docker compose down

demo:
	docker compose exec -T marketplace-api python - < scripts/demo.py

test:
	docker compose build tests
	docker compose run --rm migrate-test
	docker compose run --rm --no-deps tests

db-migrate:
	docker compose run --rm migrate

db-info:
	docker compose run --rm migrate info

db-validate:
	docker compose run --rm migrate validate

db-shell:
	docker compose exec db sh -c 'exec psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB"'

db-inspect:
	docker compose exec -T db sh -c 'exec psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -v ON_ERROR_STOP=1' < db/inspect.sql
