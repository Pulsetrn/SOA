FROM python:3.12-slim AS codegen

WORKDIR /build
COPY requirements-codegen.txt .
RUN pip install --no-cache-dir -r requirements-codegen.txt
COPY proto ./proto
RUN mkdir generated && python -m grpc_tools.protoc -I proto --python_out=generated --pyi_out=generated --grpc_python_out=generated proto/flight.proto

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/generated

WORKDIR /app
COPY requirements.txt requirements-codegen.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=codegen /build/generated ./generated
COPY common ./common
COPY flight ./flight
COPY booking ./booking

CMD ["uvicorn", "booking.main:app", "--host", "0.0.0.0", "--port", "8000"]
