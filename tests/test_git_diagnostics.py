from __future__ import annotations

import unittest

from git_client import redact_command, redact_text


class GitDiagnosticsTest(unittest.TestCase):
    def test_redacts_credentials_in_command_display(self) -> None:
        command = redact_command(["git", "clone", "https://user:secret@gitverse.example/team/service.git"])

        self.assertEqual(command[2], "https://***@gitverse.example/team/service.git")
        self.assertNotIn("secret", " ".join(command))

    def test_plain_url_is_not_changed(self) -> None:
        self.assertEqual(redact_text("https://gitverse.example/team/service.git"), "https://gitverse.example/team/service.git")


if __name__ == "__main__":
    unittest.main()
