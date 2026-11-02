PYTHON ?= python3

.PHONY: generate up down seed

generate:
	mkdir -p generated
	$(PYTHON) -m grpc_tools.protoc -I proto --python_out=generated --pyi_out=generated --grpc_python_out=generated proto/flight.proto

up:
	docker compose up --build -d --wait

down:
	docker compose down

seed:
	docker compose exec -T flight python -m flight.seed
	docker compose restart flight
