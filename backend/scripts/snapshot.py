"""Save a source-only working demo without touching shared branches or files."""
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def main():
    root = Path(__file__).resolve().parents[2]
    excluded = {".venv", "__pycache__", ".pytest_cache", ".logs", "releases"}
    files = [
        path for folder in [root / "backend", root / "contracts"]
        for path in folder.rglob("*")
        if path.is_file() and not excluded.intersection(path.relative_to(root).parts)
    ]
    files.extend(root / name for name in ["README.md", "TEAM_HANDOFF.md", "CODEX_PLANNER.md", "docs/CODEX_STATUS.md"])
    contents = {str(path.relative_to(root)).replace("\\", "/"): path.read_bytes() for path in sorted(files)}
    manifest = {name: hashlib.sha256(content).hexdigest() for name, content in contents.items()}
    destination = root / "backend" / "releases"
    destination.mkdir(exist_ok=True)
    archive = destination / "known-working-backend-v1.zip"
    with ZipFile(archive, "w", compression=ZIP_DEFLATED) as zipped:
        for name, content in contents.items():
            zipped.writestr(name, content)
        zipped.writestr("SOURCE_SHA256.json", json.dumps(manifest, indent=2) + "\n")
    with ZipFile(archive) as zipped:
        assert zipped.testzip() is None
        for name, digest in manifest.items():
            assert hashlib.sha256(zipped.read(name)).hexdigest() == digest
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(digest + "\n", encoding="utf-8")
    print(f"Verified source backup: {archive} ({len(contents)} files, SHA256 {digest})")


if __name__ == "__main__":
    main()
