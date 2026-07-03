import os


def project_slug() -> str:
    return os.environ.get("PLATFORM_PROJECT_SLUG", "claude-config")


def config_version_path() -> str:
    """Path to the deployed agent-config VERSION file. Empty string disables the badge."""
    return os.environ.get("CONFIG_VERSION_PATH", "/claude-config/VERSION")
