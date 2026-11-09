from dataclasses import dataclass

from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


@dataclass(frozen=True)
class DatabaseTarget:
    url: URL
    tls: bool
    ca_file: str | None
    statement_cache_size: int


def database_target(value: str, configured_tls: bool) -> DatabaseTarget:
    try:
        url = make_url(value)
    except (ArgumentError, ValueError) as exc:
        raise ValueError("Invalid database connection URL") from exc
    if url.drivername != "postgresql+asyncpg" or not url.host or not url.database:
        raise ValueError("Database URLs require postgresql+asyncpg://, a host, and a database")
    host = url.host.lower()
    supabase = host.endswith((".supabase.co", ".supabase.com", ".supabase.net"))
    if supabase and url.port == 6543:
        raise ValueError("Use a Supabase direct or session connection on port 5432, not port 6543")
    if set(url.query) - {"sslmode", "sslrootcert", "prepared_statement_cache_size"}:
        raise ValueError("Unsupported database URL option; use the documented TLS/pool settings")
    mode = url.query.get("sslmode")
    if mode not in (None, "disable", "require", "verify-ca", "verify-full"):
        raise ValueError("Unsupported database sslmode")
    if configured_tls and mode == "disable":
        raise ValueError("sslmode=disable conflicts with DATABASE_SSL=true")
    tls = configured_tls or mode in ("require", "verify-ca", "verify-full")
    if supabase and not tls:
        raise ValueError("Supabase database connections require TLS")
    ca_file = url.query.get("sslrootcert")
    if isinstance(ca_file, tuple) or (ca_file and not tls):
        raise ValueError("sslrootcert requires TLS and a single certificate path")
    try:
        cache_size = int(str(url.query.get("prepared_statement_cache_size", "100")))
    except ValueError as exc:
        raise ValueError("Invalid prepared statement cache size") from exc
    if not 0 <= cache_size <= 1000:
        raise ValueError("Prepared statement cache size must be between 0 and 1000")
    return DatabaseTarget(url.set(query={}), tls, ca_file, cache_size)
