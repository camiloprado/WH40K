FROM python:3.15-slim AS build
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir --prefix=/install .

FROM python:3.15-slim AS test
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
COPY tests ./tests
RUN pip install --no-cache-dir -e ".[dev]"
ENV APP_ENV=test
CMD ["pytest", "-q"]

FROM python:3.15-slim
RUN useradd --create-home --uid 1000 app \
  && mkdir -p /app/data /app/backups \
  && chown -R app:app /app
WORKDIR /app
COPY --from=build /install /usr/local
COPY --chown=app:app app ./app
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app alembic.ini ./
USER app
ENV APP_ENV=prod
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
