"""Reject unsafe archives and keep separately supplied evaluation cases local."""
import base64
import io
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from scripts.application_cli import local_zip
from scripts.application_import import ARCHIVE_LIMIT, ImportProblem, source_snapshot


def archive(entries):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as zipped:
        for name, content in entries:
            zipped.writestr(name, content)
    return output.getvalue()


class ApplicationImportTests(unittest.TestCase):
    def test_rejects_escape_secret_and_symlink(self):
        link = zipfile.ZipInfo("link")
        link.create_system = 3
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        for name in ["../agent.py", "/agent.py", ".env", link]:
            with self.subTest(name=name), self.assertRaises(ImportProblem):
                source_snapshot(archive([(name, b"example")]))

    def test_oversized_archives_have_source_specific_guidance(self):
        oversized = bytes(ARCHIVE_LIMIT + 1)
        with self.assertRaisesRegex(ImportProblem, r"GitHub archive.*4 MiB.*Switch to Upload ZIP"):
            source_snapshot(oversized, "owner/repository", "a" * 40)
        with self.assertRaisesRegex(ImportProblem, r"uploaded ZIP.*4 MiB"):
            source_snapshot(oversized)

    def test_typescript_is_inspect_only(self):
        snapshot = source_snapshot(archive([("src/agent.ts", b"export const x = 1")]))
        self.assertEqual(snapshot["discovery"]["runtime"], "typescript")
        self.assertIsNone(snapshot["discovery"]["preset"])
        self.assertIn("TypeScript execution is unavailable", snapshot["discovery"]["setup"])

    def test_local_cli_excludes_the_separately_supplied_setup_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            setup = root / "evaluation.json"
            setup.write_text('{"holdout": "private"}')
            (root / "agent.py").write_text("pass")
            (root / ".env").write_text("PRIVATE=1")
            snapshot = source_snapshot(base64.b64decode(local_zip(root, setup.resolve())))
            self.assertEqual(list(snapshot["files"]), ["agent.py"])

    def test_detects_a_generic_candidate_without_selecting_a_preset(self):
        snapshot = source_snapshot(archive([
            ("src/qa.py", b'if __name__ == "__main__": pass\nOPENAI_BASE_URL = OPENAI_MODEL = ""'),
            ("test_qa.py", b"pass"),
        ]))
        discovery = snapshot["discovery"]
        self.assertEqual(discovery["entry"], "python -m src.qa")
        self.assertIsNone(discovery["preset"])
        self.assertEqual(discovery["evaluation_files"], ["test_qa.py"])
