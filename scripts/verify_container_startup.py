"""Exercise production container startup using synthetic, unreachable service URLs."""

import argparse
import subprocess
import sys

PROBE = """
import asyncio
import json
import os
import ssl

import httpx

from app.core.config import Settings
from app.db import create_engine
from app.main import create_app

async def main():
    settings = Settings()
    assert settings.environment == 'production'
    for migration in (False, True):
        engine = create_engine(settings, migration=migration)
        await engine.dispose()
    assert str(settings.database_ssl_root_cert) == '/srv/lustcode/certs/supabase-root-2021.crt'
    assert settings.database_ssl_root_cert.is_file()
    context = ssl.create_default_context(cafile=str(settings.database_ssl_root_cert))
    assert context.check_hostname and context.verify_mode == ssl.CERT_REQUIRED
    assert os.getuid() == 10001
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url='http://probe'
        ) as client:
            response = await client.get('/api/v1/health/live')
            assert response.status_code == 200, response.text
    print(json.dumps({'status': 'ok', 'production_lifespan': 'passed', 'liveness': 200,
                      'api_and_migration_engines': 'initialized', 'uid': os.getuid(),
                      'tls': 'CA and hostname verification enabled',
                      'copied_native_url_path': 'overridden by image CA default',
                      'external_connections': 'not required'}))

asyncio.run(main())
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="Already built Docker image to verify")
    image = parser.parse_args().image
    # These values are intentionally public fixtures, never the developer's .env.
    native_url = (
        "postgresql+asyncpg://postgres.fixture:synthetic@fixture.pooler.supabase.com:5432/postgres"
        "?sslmode=verify-full&sslrootcert=%2FUsers%2Ffixture%2Fbackend%2Fcerts%2Fsupabase-root-2021.crt"
    )
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-i",
            "--env",
            "ENVIRONMENT=production",
            "--env",
            "JWT_SECRET=synthetic-container-smoke-secret-at-least-32-characters",
            "--env",
            f"DATABASE_URL={native_url}",
            "--env",
            f"MIGRATION_DATABASE_URL={native_url}",
            "--env",
            "DATABASE_SSL=true",
            "--env",
            "REDIS_URL=redis://unavailable.fixture:6379/0",
            "--env",
            "CORS_ALLOW_ALL_ORIGINS=true",
            image,
            "python",
            "-",
        ],
        input=PROBE,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
