PYTHON ?= python3

.PHONY: generate

generate:
	mkdir -p generated
	$(PYTHON) -m grpc_tools.protoc -I proto --python_out=generated --pyi_out=generated --grpc_python_out=generated proto/flight.proto
