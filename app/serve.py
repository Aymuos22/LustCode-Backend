"""Portable Docker/Render web entrypoint; no environment values are logged."""

import os

import uvicorn


def port(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise ValueError("PORT must be an integer between 1 and 65535") from None
    if not 1 <= number <= 65535:
        raise ValueError("PORT must be an integer between 1 and 65535")
    return number


def main() -> None:
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=port(os.environ.get("PORT", "8000")),
        proxy_headers=False,
        access_log=False,
        timeout_keep_alive=5,
        timeout_graceful_shutdown=25,
        limit_concurrency=100,
    )


if __name__ == "__main__":
    main()
