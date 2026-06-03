"""
Configuration management for Lucent Email System.

Loads config from JSON file + environment variables.
Supports both development and production environments.
"""

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class IMAPConfig:
    """IMAP/SMTP configuration."""
    email_address: str
    imap_host: str
    imap_port: int = 993
    smtp_host: str = None  # Defaults to imap_host if not specified
    smtp_port: int = 587
    use_tls: bool = True


@dataclass
class DatabaseConfig:
    """Database configuration."""
    path: str = None  # Defaults to ~/dev/lucent/memory/email/email.db


@dataclass
class ClaudeConfig:
    """Claude API configuration."""
    api_key_env: str = "ANTHROPIC_API_KEY"
    model_haiku: str = "claude-haiku-4-5-20251001"
    model_sonnet: str = "claude-sonnet-4-6"


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    path: Optional[str] = None  # If None, log to console only


@dataclass
class EmailConfig:
    """Main email system configuration."""
    pst_file_path: Optional[str]
    imap: IMAPConfig
    database: DatabaseConfig = None
    sync_interval_minutes: int = 30
    sync_folders: list = None  # Folders to sync (e.g., ["INBOX", "Inbox"]. None = all folders
    baseline_cutoff: str = None  # ISO timestamp for filtering old emails from display
    logging: LoggingConfig = None
    claude: ClaudeConfig = None

    def __post_init__(self):
        """Fill in defaults."""
        if self.database is None:
            self.database = DatabaseConfig(
                path=os.path.expanduser("~/dev/lucent/memory/email/email.db")
            )
        if self.logging is None:
            self.logging = LoggingConfig()
        if self.claude is None:
            self.claude = ClaudeConfig()


def load_config(config_path: str = None) -> EmailConfig:
    """
    Load configuration from JSON file.

    Args:
        config_path: Path to config.json. If None, searches common locations.

    Returns:
        EmailConfig instance with all settings.

    Raises:
        FileNotFoundError: If config file not found.
        ValueError: If config is invalid.
    """
    if config_path is None:
        # Search common locations
        candidates = [
            Path("lucent_email.config.json"),
            Path("~/dev/lucent/memory/email/email.config.json").expanduser(),
            Path("/etc/lucent/email.config.json"),
        ]
        for path in candidates:
            if path.exists():
                config_path = str(path)
                break

        if config_path is None:
            raise FileNotFoundError(
                "Config file not found. Tried: " + ", ".join(str(p) for p in candidates)
            )

    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        data = json.load(f)

    # Handle both nested and flat config formats
    # Flat format: {imap: {...}, database: {...}, ...}
    # Nested format: {email: {imap: {...}, database: {...}, ...}}
    if "email" in data:
        email_data = data["email"]
    else:
        email_data = data

    # Build IMAP config
    imap_data = email_data.get("imap", {})
    imap_config = IMAPConfig(
        email_address=imap_data["email_address"],
        imap_host=imap_data["imap_host"],
        imap_port=imap_data.get("imap_port", 993),
        smtp_host=imap_data.get("smtp_host", imap_data.get("imap_host")),
        smtp_port=imap_data.get("smtp_port", 587),
        use_tls=imap_data.get("use_tls", True),
    )

    # Build database config
    db_data = email_data.get("database", {})
    db_config = DatabaseConfig(
        path=db_data.get("path", os.path.expanduser("~/dev/lucent/memory/email/email.db"))
    )

    # Build logging config
    log_data = email_data.get("logging", {})
    log_config = LoggingConfig(
        level=log_data.get("level", "INFO"),
        path=log_data.get("path"),
    )

    # Build Claude config
    claude_data = email_data.get("claude", {})
    claude_config = ClaudeConfig(
        api_key_env=claude_data.get("api_key_env", "ANTHROPIC_API_KEY"),
        model_haiku=claude_data.get("model_haiku", "claude-3-5-haiku-20241022"),
        model_sonnet=claude_data.get("model_sonnet", "claude-3-5-sonnet-20241022"),
    )

    # Build main config
    config = EmailConfig(
        pst_file_path=email_data.get("pst_file_path"),
        imap=imap_config,
        database=db_config,
        sync_interval_minutes=email_data.get("sync_interval_minutes", 30),
        baseline_cutoff=email_data.get("baseline_cutoff"),
        logging=log_config,
        claude=claude_config,
    )

    return config


def get_api_key(config: EmailConfig) -> str:
    """
    Get Anthropic API key from environment.

    Args:
        config: EmailConfig instance.

    Returns:
        API key string.

    Raises:
        ValueError: If API key not found.
    """
    api_key = os.getenv(config.claude.api_key_env)
    if not api_key:
        raise ValueError(
            f"Anthropic API key not found in {config.claude.api_key_env} environment variable"
        )
    return api_key


def get_imap_password(config: EmailConfig) -> str:
    """
    Get IMAP password from environment variable, keyring, or config.

    Args:
        config: EmailConfig instance.

    Returns:
        Password string.

    Raises:
        ValueError: If password not found.
    """
    # Check environment variable first (LUCENT_EMAIL_PASSWORD)
    password = os.environ.get("LUCENT_EMAIL_PASSWORD")
    if password:
        return password

    # Fall back to keyring
    try:
        import keyring
        password = keyring.get_password("lucent-email", "imap")
        if password:
            return password
    except Exception as e:
        logger.debug(f"Keyring access failed: {e}")

    # If neither worked, raise error
    raise ValueError(
        "IMAP password not found. Set LUCENT_EMAIL_PASSWORD environment variable "
        "or configure keyring: keyring set_password('lucent-email', 'imap', 'your-password')"
    )
