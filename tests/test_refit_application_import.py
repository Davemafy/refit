"""Reject unsafe archives and keep separately supplied evaluation cases local."""
import base64
import io
from pathlib import Path
import stat
import tempfile
import unittest
import zipfile

from scripts.application_cli import local_zip
from scripts.application_import import ARCHIVE_LIMIT, ImportProblem, source_snapshot, unpack_zip


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
        for name in ["../agent.py", "/agent.py", ".env", "app/[bad[]]/route.ts", "app/[id]/../route.ts", link]:
            with self.subTest(name=name), self.assertRaises(ImportProblem):
                source_snapshot(archive([(name, b"example")]))

    def test_large_zip_reads_only_selected_source(self):
        data = archive([("agent.py", b"print('ready')"),
                        ("docs/demo.pdf", bytes(ARCHIVE_LIMIT + 1)),
                        ("node_modules/example/index.js", b"ignored")])
        with self.assertRaisesRegex(ImportProblem, "streaming ZIP upload"):
            source_snapshot(data)
        result = unpack_zip(io.BytesIO(data))
        self.assertEqual(list(result["files"]), ["agent.py"])
        self.assertEqual(result["selection_counts"], {"excluded": 2, "included": 1})

    def test_typescript_is_inspect_only(self):
        snapshot = source_snapshot(archive([("src/agent.ts", b"export const x = 1")]))
        self.assertEqual(snapshot["discovery"]["runtime"], "typescript")
        self.assertIsNone(snapshot["discovery"]["preset"])
        self.assertIn("TypeScript execution is unavailable", snapshot["discovery"]["setup"])

    def test_discovery_uses_application_boundaries_in_a_mixed_repository(self):
        python = b'import argparse\nOPENAI_BASE_URL = OPENAI_MODEL = ""\nif __name__ == "__main__": pass'
        entries = [
            ("agent.py", python),
            ("web/package.json", b'{"dependencies":{"react":"1.0.0"}}'),
            ("web/index.ts", b'export const ui = "web";'),
        ]
        result = source_snapshot(archive(entries))["discovery"]
        self.assertEqual(result["entry"], "python -m agent")
        entries.extend([("node/package.json", b'{"dependencies":{"ai":"7.0.0"},"main":"cli.ts"}'),
                        ("node/cli.ts", b'import {ToolLoopAgent} from "ai"; process.argv[2]')])
        result = source_snapshot(archive(entries))["discovery"]
        self.assertEqual(result["runtime"], "mixed")
        self.assertIsNone(result["entry"])
        self.assertEqual([(app["entry"], app["directory"]) for app in result["applications"]],
                         [("python -m agent", ""), ("node/cli.ts", "node")])

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

    def test_distinguishes_next_service_from_managed_cli(self):
        entries = [
            ("package.json", b'{"dependencies":{"next":"^16.0.0","ai":"7.0.0"},"engines":{"node":">=24"}}'),
            ("src/app/api/tasks/[id]/turn/route.ts", b'export async function POST(request: Request) {}'),
            ("src/app/api/account/route.ts", b'export const POST = () => Response.json({})'),
            ("src/app/api/health/route.ts", b'export function GET() {}'),
            ("src/tools/runtime.ts", b'process.env.ANTHROPIC_API_KEY; process.env.GEMINI_API_KEY; process.env.XAI_API_KEY;'),
            ("scripts/maintenance.ts", b'process.argv[2]'),
            ("evaluation/cases.json", b'[]'),
            ("scripts/blind-eval.test.mjs", b'export {}'),
            ("tests/browser/home.e2e.ts", b'export {}'),
        ]
        result = source_snapshot(archive(entries))["discovery"]
        self.assertEqual(result["framework"], "Next.js")
        self.assertEqual(result["node_requirement"], ">=24")
        self.assertEqual(result["dependencies"], ["ai", "next"])
        self.assertEqual(result["service_entries"][0]["route"], "/api/tasks/[id]/turn")
        self.assertEqual(len(result["service_entries"]), 2)
        self.assertEqual(result["provider_signals"], ["ANTHROPIC_API_KEY", "GEMINI_API_KEY", "XAI_API_KEY"])
        self.assertEqual(result["evaluation_inputs"], ["evaluation/cases.json"])
        self.assertEqual(result["evaluation_files"][0], "scripts/blind-eval.test.mjs")
        self.assertFalse(result["runnable"])
        self.assertFalse(result["applications"])
        self.assertIn("isolated test endpoint", result["setup"])

        entries += [("worker/package.json", b'{"main":"cli.ts","dependencies":{"ai":"7.0.0"}}'),
                    ("worker/cli.ts", b'process.argv[2]')]
        result = source_snapshot(archive(entries))["discovery"]
        self.assertEqual(result["entry"], "worker/cli.ts")
        self.assertIsNot(result.get("runnable"), False)
