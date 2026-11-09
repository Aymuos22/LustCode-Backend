FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    DATABASE_SSL_ROOT_CERT=/srv/lustcode/certs/supabase-root-2021.crt
WORKDIR /srv/lustcode
COPY requirements.lock ./
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.lock
COPY pyproject.toml ./
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-deps . \
    && useradd --create-home --uid 10001 lustcode \
    && mkdir -p /srv/lustcode/var/avatars \
    && chown -R lustcode:lustcode /srv/lustcode/var
COPY alembic.ini ./
COPY migrations ./migrations
COPY certs/supabase-root-2021.crt ./certs/supabase-root-2021.crt
USER lustcode
EXPOSE 8000
CMD ["python", "-m", "app.serve"]
