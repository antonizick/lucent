#!/usr/bin/env python3
"""
Standalone email monitoring daemon.

Runs background monitoring loop that syncs email every 30 minutes,
scores for priority, and alerts Nick via voice box.

Usage:
    python3 scripts/email_monitor.py [--config path] [--once]

Examples:
    # Start daemon
    python3 scripts/email_monitor.py

    # Run single sync+score pass then exit
    python3 scripts/email_monitor.py --once

    # Use custom config
    python3 scripts/email_monitor.py --config /etc/lucent/email.config.json
"""

import argparse
import logging
import signal
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.lucent_email.config import load_config
from src.lucent_email.email_service import EmailService
from src.lucent_email.logger import setup_logging
from src.lucent_email.monitor import EmailMonitor


def main():
    """Run email monitoring daemon."""
    parser = argparse.ArgumentParser(
        description="Email monitoring daemon with priority detection."
    )
    parser.add_argument(
        "--config",
        type=str,
        help="Path to email config file",
        default=None,
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run single sync+score pass then exit",
    )

    args = parser.parse_args()

    try:
        # Load configuration
        config = load_config(args.config)
        setup_logging(config.logging)
        logger = logging.getLogger(__name__)

        logger.info("=" * 60)
        logger.info("Email Monitor Started")
        logger.info(f"Config: {args.config or 'default'}")
        logger.info(f"Sync interval: {config.sync_interval_minutes} minutes")
        logger.info("=" * 60)

        # Initialize service
        service = EmailService(config)

        # Determine note path
        today = datetime.now().strftime("%Y-%m-%d")
        note_path = Path.home() / "dev/lucent/memory" / f"{today}.md"

        # Create monitor
        monitor = EmailMonitor(service, config, note_path=note_path)

        # Handle signals for graceful shutdown
        def signal_handler(signum, frame):
            logger.info("Received signal, shutting down...")
            monitor.stop()
            service.close()
            sys.exit(0)

        signal.signal(signal.SIGTERM, signal_handler)
        signal.signal(signal.SIGINT, signal_handler)

        # Run
        if args.once:
            logger.info("Running single sync pass...")
            monitor.run_once()
            logger.info("Single pass complete")
        else:
            logger.info("Starting monitoring loop...")
            monitor.start()
            # Keep daemon running
            try:
                signal.pause()
            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                monitor.stop()

        service.close()
        logger.info("Email Monitor Stopped")

    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
