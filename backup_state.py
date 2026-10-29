"""Archive stopped local application data; the caller must stop all API/index jobs."""
import argparse
import tarfile
from pathlib import Path

from config import BASE_DIRECTORY


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(BASE_DIRECTORY / "backups" / "trace-state.tar.gz"))
    args = parser.parse_args()
    output = Path(args.out).resolve()
    for name in ["data", "indexes"]:
        source = (BASE_DIRECTORY / name).resolve()
        if output.is_relative_to(source):
            parser.error("Backup output must be outside data/ and indexes/.")
    output.parent.mkdir(parents=True, exist_ok=True)
    print("All API and indexing processes must be stopped before this backup.")
    with tarfile.open(output, "w:gz") as archive:
        for name in ["data", "indexes"]:
            source = BASE_DIRECTORY / name
            if source.exists():
                archive.add(source, arcname=name, filter=lambda item: None if item.name.endswith("/.lock") else item)
    print("Saved private state backup:", output)


if __name__ == "__main__":
    main()
