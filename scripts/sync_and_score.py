#!/usr/bin/env python3
"""Sync emails and score them for priority."""

import sys
import os
from pathlib import Path

# Add parent to path
parent = Path(__file__).parent.parent
sys.path.insert(0, str(parent))

from src.lucent_email.config import load_config
from src.lucent_email.email_service import EmailService

def main():
    try:
        # Load config and service
        config = load_config()
        service = EmailService(config)
        
        # Sync all backends
        result = service.sync_all()
        print(f"Sync: {result.imap_new} IMAP emails")
        
        # Score recent unread emails (last 8 days, unread only)
        recent = service.get_recent_emails(days=8, limit=100)
        unread = [e for e in recent if not e.read]
        
        if unread:
            print(f"Scoring {len(unread)} unread emails...")
            scores = service.score_new_emails(unread)
            print(f"Scored: {len(scores)} emails")
        
        print("Sync and score complete")
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
