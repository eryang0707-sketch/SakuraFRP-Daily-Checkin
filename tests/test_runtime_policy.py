"""Secret-free contract tests for notification and manual CAPTCHA handling."""

import re
import unittest
from pathlib import Path

from runtime_policy import (
    get_notify_policy,
    should_notify_success,
    requires_manual_verification,
    exit_code_for_result,
    credentials_from_environment,
)


ROOT = Path(__file__).resolve().parents[1]


class NotificationPolicyTests(unittest.TestCase):
    def test_default_policy_reports_every_daily_result(self):
        self.assertEqual(get_notify_policy(None), "all")
        self.assertTrue(should_notify_success("all", newly_signed=False))
        self.assertTrue(should_notify_success("all", newly_signed=True))

    def test_change_policy_skips_already_signed_but_reports_new_checkin(self):
        self.assertFalse(should_notify_success("change", newly_signed=False))
        self.assertTrue(should_notify_success("change", newly_signed=True))

    def test_failure_only_does_not_send_success_notice(self):
        self.assertFalse(should_notify_success("failure_only", newly_signed=True))


class CaptchaPolicyTests(unittest.TestCase):
    def test_known_captcha_types_require_manual_verification(self):
        self.assertTrue(requires_manual_verification("grid"))
        self.assertTrue(requires_manual_verification("slider"))
        self.assertFalse(requires_manual_verification("unknown"))

    def test_manual_verification_has_distinct_nonzero_exit_code(self):
        self.assertEqual(exit_code_for_result(False, manual_verification_required=True), 2)
        self.assertEqual(exit_code_for_result(False, manual_verification_required=False), 1)
        self.assertEqual(exit_code_for_result(True, manual_verification_required=False), 0)

    def test_credentials_are_taken_from_environment_without_partial_fallback(self):
        self.assertEqual(
            credentials_from_environment("fixture-user", "fixture-password"),
            ("fixture-user", "fixture-password"),
        )
        self.assertIsNone(credentials_from_environment(None, None))
        with self.assertRaises(ValueError):
            credentials_from_environment("fixture-user", None)


class WorkflowContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / ".github" / "workflows" / "checkin.yml").read_text(encoding="utf-8")

    def test_schedule_is_1207_beijing_time(self):
        match = re.search(r"^\s+- cron:\s*['\"]([^'\"]+)['\"]", self.workflow, re.MULTILINE)
        self.assertIsNotNone(match)
        fields = match.group(1).split()
        self.assertEqual(len(fields), 5)
        utc_minute = int(fields[0]) + int(fields[1]) * 60
        beijing_minute = (utc_minute + 8 * 60) % (24 * 60)
        self.assertEqual(beijing_minute, 12 * 60 + 7)
        self.assertIn("TZ: Asia/Shanghai", self.workflow)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("每天北京时间 12:07", readme)

    def test_workflow_uses_supported_node24_actions_and_stable_ubuntu(self):
        self.assertIn("runs-on: ubuntu-24.04", self.workflow)
        for action in ("actions/checkout@v7", "actions/setup-python@v7", "actions/upload-artifact@v7"):
            self.assertIn(action, self.workflow)

    def test_secret_expressions_are_not_interpolated_into_shell_scripts(self):
        lines = self.workflow.splitlines()
        run_blocks = []
        index = 0
        while index < len(lines):
            if re.match(r"^\s+run:\s*\|\s*$", lines[index]):
                indent = len(lines[index]) - len(lines[index].lstrip())
                index += 1
                block = []
                while index < len(lines):
                    line = lines[index]
                    if line.strip() and len(line) - len(line.lstrip()) <= indent:
                        break
                    block.append(line)
                    index += 1
                run_blocks.append("\n".join(block))
            else:
                index += 1
        self.assertTrue(run_blocks)
        self.assertNotRegex("\n".join(run_blocks), r"\$\{\{\s*secrets\.")
        self.assertIn("SAKURA_USERNAME", self.workflow)
        self.assertIn("ZHIPU_API_KEY", self.workflow)
        self.assertIn("SAKURA_USERNAME: ${{ secrets.SAKURA_USERNAME }}", self.workflow)

    def test_pull_requests_run_validation_without_running_checkin(self):
        self.assertIn("pull_request:", self.workflow)
        self.assertIn("python -m unittest discover -s tests -v", self.workflow)
        self.assertIn("if: github.event_name != 'pull_request'", self.workflow)

    def test_daily_email_policy_defaults_to_all(self):
        self.assertIn("EMAIL_NOTIFY_POLICY: ${{ vars.EMAIL_NOTIFY_POLICY || 'all' }}", self.workflow)


if __name__ == "__main__":
    unittest.main()
