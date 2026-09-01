"""Thin runner. All startup lives in the API lifespan (single owner)."""
import uvicorn


def main() -> None:
    uvicorn.run("hq.api.app:app", host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    main()
