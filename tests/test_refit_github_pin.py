"""Pinned default-branch GitHub import with no live network or inference."""
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from scripts.application_import import ImportProblem, github_snapshot, make_snapshot, resolve_default_revision
from scripts.application_http import ApplicationService


SHA = "91e48402cbfdd281f86d3ac313b06ff89fac7025"


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, _max_bytes):
        return self.payload


class FakeOpener:
    def __init__(self, response):
        self.response = response
        self.request = None

    def open(self, request, timeout):
        self.request = request
        assert timeout <= 15
        return FakeResponse(self.response)


class GithubPinTests(unittest.TestCase):
    def test_default_branch_is_resolved_and_sha_validated(self):
        opener = FakeOpener(json.dumps([{"sha": SHA}]).encode())
        with patch("scripts.application_import.build_opener", return_value=opener):
            self.assertEqual(resolve_default_revision("Davemafy/refit"), SHA)
        self.assertEqual(
            opener.request.full_url,
            "https://api.github.com/repos/Davemafy/refit/commits?per_page=1"
        )
        self.assertNotIn("Authorization", opener.request.headers)

    def test_private_import_uses_unredirected_scoped_token(self):
        opener = FakeOpener(json.dumps([{"sha": SHA}]).encode())
        with patch("scripts.application_import.build_opener", return_value=opener):
            self.assertEqual(resolve_default_revision("Davemafy/refit", "ghp_test_123"), SHA)
        self.assertEqual(opener.request.unredirected_hdrs["Authorization"], "Bearer ghp_test_123")

    def test_rejects_untrusted_paths_and_invalid_commit_responses(self):
        for repo in ("https://evil.test/test", "owner/../other", "owner/repo/path", "owner//repo"):
            with self.subTest(repo=repo):
                with self.assertRaises(ImportProblem):
                    resolve_default_revision(repo)
        for payload in (b"[]", b'{"sha":"fake"}', b'[{"sha":"not-a-sha"}]', b"invalid"):
            with self.subTest(payload=payload[:12]):
                with patch("scripts.application_import.build_opener", return_value=FakeOpener(payload)):
                    with self.assertRaises(ImportProblem):
                        resolve_default_revision("owner/repo")

    def test_application_pins_revision_before_importing_source(self):
        snapshot = make_snapshot({"agent.py": "cGFzcw=="}, "owner/repo", SHA, "", [])
        with TemporaryDirectory() as root:
            service = ApplicationService(
                Path(root), "local-testing-private-token-32chars", "image",
                public_origin="https://refit.test"
            )
            owner = "account-test"
            # Records a project only after its pinned tree passes inspection.
            with patch("scripts.application_http.resolve_default_revision", return_value=SHA) as pin, \
                 patch("scripts.application_http.github_snapshot", return_value=snapshot) as fetch, \
                 patch.object(service.accounts, "save_project") as saved:
                project = service.add_import(
                    {"method":"github", "repository":"owner/repo", "revision":"", "token":""},
                    owner
                )
            pin.assert_called_once_with("owner/repo", "")
            fetch.assert_called_once_with("owner/repo", SHA, "", "", None)
            self.assertEqual(project["revision"], SHA)
            self.assertEqual(project["repository"], "owner/repo")
            saved.assert_called_once()
            self.assertEqual(saved.call_args.args[2]["revision"], SHA)
            service.process_lock.close()

    def test_incomplete_public_tree_response_is_retried_but_never_trusted(self):
        source = b"print('verified')"
        sha = hashlib.sha1(f"blob {len(source)}\0".encode() + source).hexdigest()
        commit = json.dumps({"sha": SHA, "tree": {"sha": "c" * 40}}).encode()
        rows = json.dumps({"tree": [
            {"path": "agent.py", "mode": "100644", "type": "blob",
             "sha": sha, "size": len(source)}]}).encode()
        with patch("scripts.application_import.github_read", side_effect=[
                commit, b'{"message":"temporary"}', rows, source]) as read, \
             patch("scripts.application_import.time.sleep") as sleep:
            result = github_snapshot("owner/repo", SHA)
            self.assertEqual(result["revision"], SHA)
            self.assertEqual(read.call_count, 4)
            sleep.assert_called_once()
        with patch("scripts.application_import.github_read", side_effect=[
                commit, b'{}', b'{}', b'{}']), \
             patch("scripts.application_import.time.sleep"):
            with self.assertRaisesRegex(ImportProblem, "invalid tree"):
                github_snapshot("owner/repo", SHA)

    def test_tree_skips_large_files_and_verifies_selected_blob(self):
        source = b"print('hello')"
        blob = hashlib.sha1(f"blob {len(source)}\0".encode() + source).hexdigest()
        subtree = "f" * 40
        commit = json.dumps({"sha": SHA, "tree": {"sha": "c" * 40}}).encode()
        root = {"tree": [{"path": "app", "type": "tree", "sha": subtree}]}
        scoped = {"tree": [
            {"path": "agent.py", "mode": "100644", "type": "blob", "sha": blob, "size": len(source)},
            {"path": "demo.pdf", "mode": "100644", "type": "blob", "sha": "e"*40, "size": 5*1024*1024},
        ]}
        with patch("scripts.application_import.github_read", side_effect=[
            commit, json.dumps(root).encode(), json.dumps(scoped).encode(), source,
        ]) as read:
            snapshot = github_snapshot("owner/repo", SHA, directory="app")
        self.assertEqual(snapshot["revision"], SHA)
        self.assertEqual(snapshot["selection_counts"], {"included": 1, "excluded": 1})
        self.assertEqual(list(snapshot["files"]), ["agent.py"])
        self.assertEqual(read.call_count, 4)
        self.assertTrue(read.call_args_list[2].args[0].endswith(f"/trees/{subtree}?recursive=1"))
        self.assertTrue(read.call_args_list[3].args[0].endswith(f"/{SHA}/app/agent.py"))
        with patch("scripts.application_import.github_read", side_effect=[
            commit, json.dumps(scoped).encode(), b"x" * len(source),
        ]):
            with self.assertRaisesRegex(ImportProblem, "does not match the pinned tree"):
                github_snapshot("owner/repo", SHA)



if __name__ == "__main__":
    unittest.main()
