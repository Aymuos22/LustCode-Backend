"""Free Render services have no pre-deploy jobs: migrate before opening the API port."""

from app import release, serve


def main() -> None:
    release.main()
    serve.main()


if __name__ == "__main__":
    main()
