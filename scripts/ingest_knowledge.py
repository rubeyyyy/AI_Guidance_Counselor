"""Run from the project root: python -m scripts.ingest_knowledge."""
import argparse
import json
from pathlib import Path

from app.core.config import PROJECT_ROOT, get_settings
from app.services.knowledge import ingest


def main():
    parser = argparse.ArgumentParser(description="Synchronize curated JSON documents into Chroma")
    parser.add_argument("--directory", type=Path, default=PROJECT_ROOT / "knowledge_base")
    args = parser.parse_args()
    try:
        result = ingest(args.directory, get_settings())
    except Exception as error:
        # Provider exceptions can contain request details; keep CLI errors sanitized.
        parser.exit(1, f"Ingestion failed ({type(error).__name__}). Check document metadata, credentials, and index configuration.\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
