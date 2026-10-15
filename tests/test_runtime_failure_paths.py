"""Secret-free tests for notification and manual-verification failure paths."""

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def _load_main_without_optional_runtime_dependencies():
    """Import main.py without installing browsers, image libraries, or API clients."""
    stubs = {
        "dotenv": types.ModuleType("dotenv"),
        "PIL": types.ModuleType("PIL"),
        "playwright": types.ModuleType("playwright"),
        "playwright.sync_api": types.ModuleType("playwright.sync_api"),
        "ai_service": types.ModuleType("ai_service"),
        "pytweening": types.ModuleType("pytweening"),
    }
    stubs["dotenv"].load_dotenv = lambda *args, **kwargs: None
    stubs["PIL"].Image = object()
    stubs["playwright.sync_api"].sync_playwright = lambda: None
    stubs["ai_service"].AIService = object
    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    try:
        import main
    finally:
        for name, module in previous.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module
    return main


main = _load_main_without_optional_runtime_dependencies()


class FakeLogger:
    def __init__(self):
        self.errors = []
        self.infos = []

    def log_start(self):
        pass

    def log_error(self, message):
        self.errors.append(message)

    def log_info(self, message):
        self.infos.append(message)

    def log_captcha_result(self, message):
        pass

    def log_debug(self, message):
        pass


class MainFailureNotificationTests(unittest.TestCase):
    def test_early_ai_initialization_failure_sends_failure_email(self):
        logger = FakeLogger()
        with (
            patch.dict(os.environ, {"SUPPRESS_FAIL_EMAIL": "false"}, clear=True),
            patch.object(main, "clean_old_logs"),
            patch.object(main, "CheckinLogger", return_value=logger),
            patch.object(main, "AIService", side_effect=RuntimeError("fixture failure")),
            patch.object(main, "send_failure_email") as send_email,
            patch.object(main, "update_failure_alert_state"),
            patch.object(sys, "argv", ["main.py"]),
        ):
            result = main.main()

        self.assertEqual(result, 1)
        send_email.assert_called_once()
        self.assertNotIn("fixture-user", str(send_email.call_args))

    def test_early_failure_respects_retry_email_suppression(self):
        logger = FakeLogger()
        with (
            patch.dict(os.environ, {"SUPPRESS_FAIL_EMAIL": "true"}, clear=True),
            patch.object(main, "clean_old_logs"),
            patch.object(main, "CheckinLogger", return_value=logger),
            patch.object(main, "AIService", side_effect=RuntimeError("fixture failure")),
            patch.object(main, "send_failure_email") as send_email,
            patch.object(main, "update_failure_alert_state"),
            patch.object(sys, "argv", ["main.py"]),
        ):
            result = main.main()

        self.assertEqual(result, 1)
        send_email.assert_not_called()

    def test_manual_captcha_notification_overrides_retry_suppression(self):
        logger = FakeLogger()
        with (
            patch.dict(os.environ, {"SUPPRESS_FAIL_EMAIL": "true"}, clear=True),
            patch.object(main, "send_failure_email") as send_email,
        ):
            main.notify_failure_email("manual verification required", logger, manual_verification_required=True)

        send_email.assert_called_once()

    def test_main_routes_detected_captcha_to_manual_verification(self):
        tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
        main_function = next(
            node for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main"
        )
        called = {
            node.func.id
            for node in ast.walk(main_function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        self.assertIn("require_manual_captcha", called)
        self.assertIn("resolve_failure_reason", called)
        self.assertIn("exit_code_for_result", called)
        self.assertFalse({"solve_geetest_multistep", "solve_geetest_slider"} & called)

    def test_captcha_helper_returns_a_manual_action_reason(self):
        logger = FakeLogger()
        reason = main.require_manual_captcha("grid", logger)
        self.assertIn("人工", reason)
        self.assertTrue(logger.errors)

    def test_manual_captcha_reason_wins_when_sign_button_remains_visible(self):
        reason = main.resolve_failure_reason(
            final_success=False,
            manual_verification_required=True,
            pending_failure_reason="manual CAPTCHA action required",
            final_sign_button_visible=True,
        )
        self.assertEqual(reason, "manual CAPTCHA action required")


@unittest.skipUnless(os.name == "posix", "requires a POSIX shell for run_checkin.sh")
class LocalRetryWrapperTests(unittest.TestCase):
    def test_manual_verification_exit_code_is_not_retried(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            bin_dir = temp / "bin"
            bin_dir.mkdir()
            (temp / ".env").write_text(
                "CHECKIN_MAX_RETRIES=5\nCHECKIN_RETRY_INTERVAL_SECONDS=1\n",
                encoding="utf-8",
            )
            (temp / "random_time_2026-01-01.txt").write_text("12:07:00", encoding="utf-8")
            script = temp / "run_checkin.sh"
            shutil.copy2(ROOT / "run_checkin.sh", script)
            (bin_dir / "date").write_text(
                "#!/bin/bash\ncase \"$1\" in\n"
                "  +%Y-%m-%d) echo 2026-01-01 ;;\n"
                "  +%H) echo 12 ;;\n"
                "  +%M) echo 07 ;;\n"
                "  +%S) echo 00 ;;\n"
                "  +%H:%M:%S) echo 12:07:00 ;;\n"
                "  *) /bin/date \"$@\" ;;\nesac\n",
                encoding="utf-8",
            )
            call_log = temp / "attempts.txt"
            uv = bin_dir / "uv"
            uv.write_text(
                "#!/bin/bash\necho attempt >> \"$CALL_LOG\"\nexit 2\n",
                encoding="utf-8",
            )
            sleep = bin_dir / "sleep"
            sleep.write_text("#!/bin/bash\nexit 0\n", encoding="utf-8")
            for executable in (bin_dir / "date", uv, sleep):
                executable.chmod(0o755)

            env = os.environ.copy()
            env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
            env["CALL_LOG"] = str(call_log)
            result = subprocess.run(
                ["bash", str(script)],
                cwd=temp,
                env=env,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

            attempts = call_log.read_text(encoding="utf-8").splitlines()
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertEqual(attempts, ["attempt"])


if __name__ == "__main__":
    unittest.main()
