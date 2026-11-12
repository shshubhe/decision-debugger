import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def test_published_expected_output_matches_the_approved_replay(self) -> None:
        result = subprocess.run(
            [sys.executable, "-S", "-m", "decision_debugger", "--approve-demo-edit"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = (ROOT / "examples" / "expected_output.txt").read_text(encoding="utf-8")
        self.assertEqual(result.stdout, expected)

    def test_module_entrypoint_needs_no_install_or_site_packages(self) -> None:
        result = subprocess.run(
            [sys.executable, "-S", "-m", "decision_debugger"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Illustrative demonstration", result.stdout)
        self.assertIn("Approval required", result.stdout)
        self.assertNotIn("Revised: 6/8", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_invalid_cli_flag_fails_explicitly(self) -> None:
        result = subprocess.run(
            [sys.executable, "-S", "-m", "decision_debugger", "--live"],
            cwd=ROOT, capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("unrecognized arguments", result.stderr)
        self.assertNotIn("Revised: 6/8", result.stdout)

    def test_changed_prompt_reports_an_error_without_replaying(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            shutil.copytree(
                ROOT / "decision_debugger", target / "decision_debugger",
                ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
            )
            fixture = target / "decision_debugger" / "demos" / "support_tickets.json"
            payload = json.loads(fixture.read_text(encoding="utf-8"))
            payload["baseline"]["prompt"] += "\nAn unrecorded edit."
            fixture.write_text(json.dumps(payload), encoding="utf-8")
            result = subprocess.run(
                [sys.executable, "-S", "-m", "decision_debugger", "--approve-demo-edit"],
                cwd=target, capture_output=True, text=True, timeout=15,
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("saved snapshot", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")


class ArchiveTests(unittest.TestCase):
    def test_archive_replays_outside_the_checkout_in_isolated_python(self) -> None:
        from tools.build_demo import build_archive

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            archive = build_archive(target / "decision-debugger.pyz")
            result = subprocess.run(
                [sys.executable, "-I", "-S", str(archive), "--approve-demo-edit"],
                cwd=target, capture_output=True, text=True, timeout=15,
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Baseline: 5/8", result.stdout)
        self.assertIn("Revised: 6/8", result.stdout)
        self.assertIn("Regressed: 1", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_archive_uses_only_public_allowlisted_files(self) -> None:
        from tools.build_demo import build_archive

        with tempfile.TemporaryDirectory() as directory:
            archive = build_archive(Path(directory) / "decision-debugger.pyz")
            with zipfile.ZipFile(archive) as bundled:
                names = bundled.namelist()
                self.assertEqual(len(names), len(set(names)))
                self.assertEqual(set(names), {
                    "__main__.py", "LICENSE", "README.md",
                    "decision_debugger/__init__.py",
                    "decision_debugger/__main__.py",
                    "decision_debugger/models.py",
                    "decision_debugger/validation.py",
                    "decision_debugger/scoring.py",
                    "decision_debugger/comparison.py",
                    "decision_debugger/demo.py",
                    "decision_debugger/cli.py",
                    "decision_debugger/demos/support_tickets.json",
                })
