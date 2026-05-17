# Development Setup — Email System

**Version:** 1.0 | **Date:** 2026-05-17

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements-email.txt

# 2. Create configuration
cp lucent_email.config.example.json lucent_email.config.json
# Edit with your details

# 3. Initialize database
python3 -m lucent_email.db init

# 4. Test backends
python3 -m lucent_email.test_backends

# 5. Run tests
pytest tests/email_system/
```

---

## Prerequisites

- Python 3.9+
- WSL or Linux environment (for Lucent integration)
- Local Outlook with PST file (for PST testing)
- IMAP/SMTP access to email account
- Anthropic API key (for Phase 2+)

---

## Installation

### 1. Dependencies

**File:** `requirements-email.txt`

```
# Core
anthropic>=0.25.0
python-keyring>=24.0.0

# Email backends
pywin32>=300; platform_system=='Windows'
python-pst>=2.0; platform_system!='Windows'

# Database
sqlite3  # stdlib, no install needed

# Testing
pytest>=7.0
pytest-asyncio>=0.20.0
pytest-cov>=4.0

# Development
black>=23.0
flake8>=6.0
mypy>=1.0
```

**Install:**

```bash
pip install -r requirements-email.txt

# On Windows, finish pywin32 setup:
python -m pip install pywin32
python -m pip install --upgrade pywin32
```

### 2. Configuration

**File:** `lucent_email.config.json`

```json
{
  "email": {
    "pst_file_path": "/path/to/outlook.pst",
    "imap": {
      "email_address": "your.email@example.com",
      "imap_host": "imap.gmail.com",
      "imap_port": 993,
      "smtp_host": "smtp.gmail.com",
      "smtp_port": 587,
      "use_tls": true
    },
    "database": {
      "path": "/home/nick/dev/lucent/.data/email.db"
    },
    "sync_interval_minutes": 30,
    "logging": {
      "level": "INFO",
      "path": "/tmp/lucent_email.log"
    },
    "claude": {
      "api_key_env": "ANTHROPIC_API_KEY",
      "model_haiku": "claude-3-5-haiku-20241022",
      "model_sonnet": "claude-3-5-sonnet-20241022"
    }
  }
}
```

**Environment Variables:**

```bash
# .env or export
export ANTHROPIC_API_KEY="sk-..."
export IMAP_PASSWORD="your-imap-password"  # Or use keyring
```

### 3. Database Initialization

```bash
# Create schema
python3 src/lucent_email/db.py --init

# Or via EmailDatabase class:
from src.lucent_email.db import EmailDatabase
db = EmailDatabase("/path/to/email.db")
db.initialize_schema()
```

### 4. Credentials & Security

**IMAP Password Management:**

Option A: System Keyring (Recommended)
```python
import keyring

# Store password
keyring.set_password("lucent-email", "imap", "your-password")

# Retrieve password
password = keyring.get_password("lucent-email", "imap")
```

Option B: Encrypted Config File (Future)
```python
# TBD: Encrypted config using cryptography library
```

**Important:** Never hardcode passwords or API keys.

---

## Project Structure

```
/home/nick/dev/lucent/
├── src/lucent_email/
│   ├── __init__.py
│   ├── backend.py              # Abstract EmailBackend
│   ├── pst_backend.py          # PST implementation
│   ├── imap_backend.py         # IMAP implementation
│   ├── db.py                   # SQLite database layer
│   ├── models.py               # Email dataclasses
│   ├── email_service.py        # EmailService API
│   ├── claude_integration.py  # Claude calls (Phase 2+)
│   ├── config.py               # Configuration loading
│   └── logger.py               # Logging setup
│
├── docs/email_system/
│   ├── PROJECT_PLAN.md
│   ├── ARCHITECTURE.md
│   ├── SETUP.md                 (this file)
│   ├── API.md
│   ├── DATABASE_SCHEMA.md
│   ├── BACKEND_DESIGN.md
│   ├── INTEGRATION_GUIDE.md
│   ├── TESTING_STRATEGY.md
│   └── WORKFLOW.md
│
├── tests/email_system/
│   ├── __init__.py
│   ├── test_backends.py
│   ├── test_db.py
│   ├── test_email_service.py
│   ├── fixtures.py              # Pytest fixtures
│   └── integration/
│       ├── test_pst_read.py
│       └── test_imap_sync.py
│
├── requirements-email.txt
├── lucent_email.config.json
└── agents/
    └── email-agent.md           (Lucent agent personality)
```

---

## Development Workflow

### 1. Making Changes

```bash
# Create feature branch (optional, or work on main)
git checkout -b feature/email-system

# Make changes to src/lucent_email/
# Write tests in tests/email_system/

# Run tests
pytest tests/email_system/ -v

# Format & lint
black src/lucent_email/ tests/email_system/
flake8 src/lucent_email/
mypy src/lucent_email/
```

### 2. Type Hints

All code must include type hints:

```python
from typing import List, Optional
from datetime import datetime

def search(self, query: str, limit: int = 100) -> List[EmailMetadata]:
    """Search emails. Return metadata list."""
    pass

def get_email(self, email_id: str) -> Optional[FullEmail]:
    """Fetch email, or None if not found."""
    pass
```

### 3. Code Style

- **Format:** Black (line length 100)
- **Lint:** Flake8 (ignore E501 if using Black)
- **Types:** MyPy (strict mode)
- **Naming:** snake_case for functions, PascalCase for classes
- **Docstrings:** One-liner for simple functions, multi-line for complex logic

### 4. Documentation

- Update ARCHITECTURE.md when changing component design
- Update API.md when adding/changing service methods
- Add docstrings to all public methods
- Leave comments only for non-obvious WHY (not WHAT)

---

## Testing

### Running Tests

```bash
# All tests
pytest tests/email_system/

# Specific test file
pytest tests/email_system/test_email_service.py

# Specific test
pytest tests/email_system/test_email_service.py::test_search

# With coverage
pytest tests/email_system/ --cov=src/lucent_email --cov-report=html

# Verbose output
pytest tests/email_system/ -v -s
```

### Test Structure

Each test should follow AAA pattern (Arrange, Act, Assert):

```python
def test_search_returns_results():
    """Test that search returns matching emails."""
    # Arrange
    service = EmailService(test_config)
    service.sync_all()  # Populate cache
    
    # Act
    results = service.search("important keyword")
    
    # Assert
    assert len(results) > 0
    assert "important keyword" in results[0].snippet
```

### Fixtures

Common test fixtures (in `fixtures.py`):

```python
@pytest.fixture
def email_service():
    """Fresh EmailService with test database."""
    config = load_test_config()
    service = EmailService(config)
    yield service
    # Cleanup
    service.db.close()

@pytest.fixture
def sample_email():
    """Sample EmailMetadata for testing."""
    return EmailMetadata(
        id="test_123",
        backend="test",
        from_addr="test@example.com",
        to_addrs=["recipient@example.com"],
        subject="Test Subject",
        timestamp=datetime.now(),
        snippet="Test email content",
        read=False,
        flagged=False,
        folder="Inbox",
        message_id="msg-123",
    )
```

---

## Debugging

### Logging

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Then run your code
service.sync_all()
# Output: DEBUG - Syncing PST backend...
#         DEBUG - Found 15 new emails
```

### Database Inspection

```bash
# Open SQLite database
sqlite3 /path/to/email.db

# Query
SELECT COUNT(*) FROM emails;
SELECT subject, from_addr FROM emails LIMIT 5;
```

### Troubleshooting

| Problem | Solution |
|---------|----------|
| **PST file not found** | Check path in config, use absolute path |
| **IMAP connection refused** | Verify IMAP host/port, check firewall |
| **SQLite database locked** | Close other connections, check for long-running queries |
| **Claude API 401** | Check ANTHROPIC_API_KEY environment variable |
| **Pywin32 import error** | On Windows: `python -m pip install --upgrade pywin32` |

---

## IDE Setup

### VS Code

**.vscode/settings.json:**

```json
{
  "python.linting.enabled": true,
  "python.linting.flake8Enabled": true,
  "python.formatting.provider": "black",
  "[python]": {
    "editor.formatOnSave": true,
    "editor.defaultFormatter": "ms-python.python"
  }
}
```

### PyCharm

- Set Python interpreter to venv
- Enable Black as formatter (Settings → Tools → Python Integrated Tools → Black)
- Enable MyPy (Settings → Tools → Python Integrated Tools → MyPy)

---

## Continuous Integration (Future)

Plan to add CI/CD pipeline:
- GitHub Actions for test + lint on PR
- Code coverage reporting
- Type checking (MyPy)
- Automated documentation builds

---

## Common Commands

```bash
# Install dependencies
pip install -r requirements-email.txt

# Run tests
pytest tests/email_system/ -v

# Format code
black src/lucent_email/ tests/email_system/

# Type check
mypy src/lucent_email/

# Lint
flake8 src/lucent_email/

# Initialize database
python3 -m lucent_email.db --init

# Run a quick test
python3 -c "from src.lucent_email.email_service import EmailService; print('Import OK')"
```

---

## Next Steps

1. Install dependencies: `pip install -r requirements-email.txt`
2. Create configuration file
3. Initialize database
4. Run tests to verify setup: `pytest tests/email_system/`
5. Proceed with Phase 1 implementation

---

**Last Updated:** 2026-05-17 | **Maintainer:** Lucent
