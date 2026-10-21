FROM openapitools/openapi-generator-cli:v7.26.0 AS codegen

WORKDIR /workspace
COPY openapi ./openapi
RUN docker-entrypoint.sh generate -c openapi/generator.yaml

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/generated/src

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY --from=codegen /workspace/generated/src ./generated/src
COPY app ./app
COPY openapi/openapi.yaml ./openapi/openapi.yaml

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]

FROM runtime AS test

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt
COPY tests ./tests
COPY pytest.ini .
CMD ["python", "-m", "pytest", "-q"]

FROM runtime AS production
