"""Build a standalone zipapp from public, explicitly allowlisted files."""

import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = (
    *(Path("decision_debugger") / name for name in (
        "__init__.py", "__main__.py", "models.py", "validation.py",
        "scoring.py", "comparison.py", "demo.py", "cli.py",
    )),
    Path("decision_debugger") / "demos" / "support_tickets.json",
    Path("LICENSE"),
    Path("README.md"),
)


def build_archive(destination: Path) -> Path:
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as directory:
        staged = Path(directory) / "decision-debugger.pyz"
        with zipfile.ZipFile(staged, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(
                "__main__.py",
                "from decision_debugger.cli import main\nraise SystemExit(main())\n",
            )
            for relative in SOURCES:
                archive.write(ROOT / relative, arcname=str(relative))
        staged.replace(destination)
    return destination


if __name__ == "__main__":
    print(build_archive(ROOT / "dist" / "decision-debugger.pyz"))
