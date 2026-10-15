"""Pure policy helpers shared by the check-in workflow and secret-free tests."""


VALID_NOTIFY_POLICIES = {"none", "failure_only", "change", "all"}


def get_notify_policy(value=None):
    """Return a supported notification policy; report every run by default."""
    policy = (value or "all").strip().lower()
    return policy if policy in VALID_NOTIFY_POLICIES else "failure_only"


def should_notify_success(policy, newly_signed):
    """Decide whether a successful run should emit a status email."""
    return policy == "all" or (policy == "change" and newly_signed)


def requires_manual_verification(captcha_type):
    """Known interactive challenges require a person; never solve them here."""
    return captcha_type in {"grid", "slider"}


def exit_code_for_result(run_success, manual_verification_required=False):
    """Use exit code 2 for a manual CAPTCHA and 1 for other failures."""
    if run_success:
        return 0
    if manual_verification_required:
        return 2
    return 1


def credentials_from_environment(username, password):
    """Return process credentials, None when unset, or reject partial config."""
    if username is None and password is None:
        return None
    if not username or not password:
        raise ValueError("SAKURA_USERNAME 和 SAKURA_PASSWORD 必须同时配置")
    return username, password
