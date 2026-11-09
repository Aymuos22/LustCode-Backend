import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[1]
NATIVE_URL = "postgresql+asyncpg://postgres.fixture:dummy@fixture.pooler.supabase.com:5432/postgres?sslmode=verify-full&sslrootcert=/host/ca.crt"
CONTAINER_URL = "postgresql+asyncpg://postgres.fixture:dummy@fixture.pooler.supabase.com:5432/postgres?sslmode=verify-full&sslrootcert=/srv/lustcode/certs/supabase-root-2021.crt"


@pytest.fixture
def compose_project(tmp_path: Path) -> Path:
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose CLI is required for configuration integration tests")
    version = subprocess.run(["docker", "compose", "version"], capture_output=True, check=False)
    if version.returncode:
        pytest.skip("Docker Compose CLI is unavailable")
    for filename in ("compose.yaml", "compose.supabase.yaml"):
        shutil.copyfile(ROOT / filename, tmp_path / filename)
    (tmp_path / "certs").mkdir()
    return tmp_path


def configure(root: Path, *, hosted: bool = False, docker_url: bool = True) -> None:
    # All inputs are synthetic: tests must never read or log the real project .env.
    content = "JWT_SECRET=synthetic-test-secret-with-at-least-32-characters\n"
    content += f"DATABASE_URL={NATIVE_URL}\nDATABASE_SSL=true\n"
    if docker_url:
        content += f"DOCKER_DATABASE_URL={CONTAINER_URL}\n"
    if hosted:
        content += "COMPOSE_FILE=compose.yaml:compose.supabase.yaml\n"
    (root / ".env").write_text(content)


def resolve(root: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    for name in tuple(env):
        if name.startswith("COMPOSE_") or name.startswith(
            ("DOCKER_DATABASE_", "DOCKER_MIGRATION_DATABASE_")
        ):
            env.pop(name)
    return subprocess.run(
        [
            "docker",
            "compose",
            "--project-directory",
            str(root),
            "--env-file",
            str(root / ".env"),
            *arguments,
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_local_mode_preserves_original_database_and_network(compose_project: Path) -> None:
    configure(compose_project)
    result = resolve(compose_project, "-f", "compose.yaml", "config", "--format", "json")
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    for name in ("api", "worker", "migrate"):
        assert "@db:5432/lustcode" in services[name]["environment"]["DATABASE_URL"]
        assert services[name]["environment"]["DATABASE_SSL"] == "false"
        assert services[name]["environment"]["REDIS_URL"] == "redis://redis:6379/0"
    assert "db" in services["migrate"]["depends_on"]


def test_default_hosted_mode_uses_supabase_and_read_only_ca_mount(compose_project: Path) -> None:
    configure(compose_project, hosted=True)
    result = resolve(compose_project, "config", "--format", "json")
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    for name in ("api", "worker", "migrate"):
        assert services[name]["environment"]["DATABASE_URL"] == CONTAINER_URL
        assert services[name]["environment"]["MIGRATION_DATABASE_URL"] == CONTAINER_URL
        assert services[name]["environment"]["DATABASE_SSL"] == "true"
        assert services[name]["environment"]["READINESS_TIMEOUT_SECONDS"] == "8"
        assert services[name]["environment"]["REDIS_URL"] == "redis://redis:6379/0"
        assert any(
            volume["target"] == "/srv/lustcode/certs" and volume["read_only"]
            for volume in services[name]["volumes"]
        )
    assert "db" not in services["migrate"].get("depends_on", {})
    assert services["api"]["healthcheck"]["timeout"] == "14s"
    assert "timeout=12" in services["api"]["healthcheck"]["test"][-1]
    active = resolve(compose_project, "config", "--services")
    assert active.returncode == 0
    assert set(active.stdout.split()) == {"api", "worker", "migrate", "redis"}


def test_hosted_mode_never_silently_falls_back_when_url_missing(compose_project: Path) -> None:
    configure(compose_project, docker_url=False)
    result = resolve(
        compose_project, "-f", "compose.yaml", "-f", "compose.supabase.yaml", "config", "--quiet"
    )
    assert result.returncode != 0
    assert "DOCKER_DATABASE_URL" in result.stderr


def test_hosted_mode_supports_a_separate_migration_connection(compose_project: Path) -> None:
    configure(compose_project, hosted=True)
    migration_url = CONTAINER_URL.replace("fixture.pooler.supabase.com", "db.fixture.supabase.co")
    with (compose_project / ".env").open("a") as file:
        file.write(f"DOCKER_MIGRATION_DATABASE_URL={migration_url}\n")
    result = resolve(compose_project, "config", "--format", "json")
    assert result.returncode == 0, result.stderr
    environment = json.loads(result.stdout)["services"]["migrate"]["environment"]
    assert environment["DATABASE_URL"] == CONTAINER_URL
    assert environment["MIGRATION_DATABASE_URL"] == migration_url
