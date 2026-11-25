"""Allowlist public files and distribution members; reject secret-bearing files."""

import email
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {"__init__.py", "__main__.py", "client.py", "onboarding.py", "server.py"}
TOP = {"README.md", "LICENSE", "pyproject.toml", "MANIFEST.in", "server.json", ".gitignore"}
PREFIXES = ("docs/", "examples/", "tests/", "scripts/", ".github/workflows/")
IGNORED = {".git", ".venv", "venv", "dist", "build", "__pycache__", ".pytest_cache"}


def permitted(name):
    if name in TOP:
        return True
    if name.startswith("src/realtortasksai_connector/"):
        return name.removeprefix("src/realtortasksai_connector/") in SOURCES
    return any(name.startswith(p) for p in PREFIXES) and name.endswith((".py", ".md", ".json", ".yml"))


def inspect_text(name, data):
    lower = name.lower()
    assert not any(x in lower for x in ("/catalog/", "/private/", "/wallet", "policy.json", ".sqlite", ".env")), name
    text = data.decode("utf-8")
    assert not re.search(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{20,}|pypi-[A-Za-z0-9_-]{30,}|0x[0-9a-fA-F]{64}\b", text), name
    # No workflow instruction schema, merchant data export or paid catalog file.
    assert not lower.endswith((".docx", ".xlsx", ".sqlite3", ".pem", ".key")), name


def main():
    public_files = []
    for file in ROOT.rglob("*"):
        relative = file.relative_to(ROOT)
        if not file.is_file() or any(p in IGNORED or p.endswith(".egg-info") for p in relative.parts):
            continue
        assert permitted(relative.as_posix()), f"Unreviewed public file: {relative}"
        inspect_text(relative.as_posix(), file.read_bytes())
        public_files.append(relative.as_posix())
    archives = []
    for wheel in (ROOT / "dist").glob("*.whl"):
        with zipfile.ZipFile(wheel) as archive:
            files = archive.namelist()
            for name in files:
                if name.endswith("/"):
                    continue
                if name.startswith("realtortasksai_connector/"):
                    assert name.split("/", 1)[1] in SOURCES, name
                else:
                    assert ".dist-info/" in name, name
                    assert name.split(".dist-info/", 1)[1] in {"METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD", "licenses/LICENSE"}, name
                inspect_text(name, archive.read(name))
            metadata = email.message_from_bytes(archive.read(next(n for n in files if n.endswith("/METADATA"))))
            assert metadata["Name"] == "tasksai-agent-skills"
            assert "mcp-name: io.github.TasksAI-Official/tasksai-agent-skills" in metadata.get_payload()
            archives.append({"file": wheel.name, "members": len(files)})
    for source in (ROOT / "dist").glob("*.tar.gz"):
        with tarfile.open(source) as archive:
            files = [m for m in archive.getmembers() if m.isfile()]
            for member in files:
                name = str(PurePosixPath(member.name).relative_to(member.name.split("/")[0]))
                generated = name == "PKG-INFO" or ".egg-info/" in name or name == "setup.cfg"
                assert generated or permitted(name), name
                inspect_text(name, archive.extractfile(member).read())
            archives.append({"file": source.name, "members": len(files)})
    assert len(archives) == 2, "Build one wheel and one source distribution before auditing"
    print(json.dumps({"public_files": len(public_files), "archives": archives,
                      "paid_catalog_files": 0, "embedded_credentials": 0}))


if __name__ == "__main__":
    main()
