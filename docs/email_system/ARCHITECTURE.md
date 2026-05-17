# Email System Architecture

**Version:** 1.0 | **Date:** 2026-05-17 | **Status:** Design Phase → Phase 1 Implementation

---

## Overview

Modular Python architecture for unified email management. Separates concerns: backends (PST/IMAP), caching (SQLite), service layer (API), and Claude integration (analysis/drafting).

```
┌──────────────────────────────────────────────────────────┐
│  Lucent / Nick's Commands                                │
│  (Monitor, Search, Draft, Send)                          │
└────────────────────┬─────────────────────────────────────┘
                     │
┌────────────────────┴─────────────────────────────────────┐
│  EmailService (email_service.py)                         │
│  - search(query)                                          │
│  - get_email(id)                                          │
│  - get_conversation(msg_id)                              │
│  - sync_all()                                             │
│  - create_draft(...)                                      │
│  - send_email(...)                                        │
└────────────────────┬──────────────────┬──────────────────┘
                     │                  │
        ┌────────────┴────┐      ┌──────┴────────┐
        ▼                 ▼      ▼               ▼
    ┌────────┐      ┌──────────┐ ┌─────────┐ ┌───────┐
    │ PST    │      │ IMAP     │ │SQLite   │ │Claude │
    │Backend │      │Backend   │ │DB       │ │LLM    │
    │(RO)    │      │(R/W)     │ │         │ │       │
    └────────┘      └──────────┘ └─────────┘ └───────┘
```

### Layer Responsibilities

| Layer | Files | Responsibility |
|-------|-------|-----------------|
| **Service API** | `email_service.py` | High-level interface: search, sync, drafting, sending |
| **Backend** | `backend.py`, `pst_backend.py`, `imap_backend.py` | Read/write emails from PST or IMAP |
| **Database** | `db.py`, schema files | SQLite persistence, metadata cache, draft storage |
| **Integration** | `claude_integration.py` (Phase 2+) | Claude Haiku/Sonnet calls |
| **Agent** | `agents/email-agent.md` | Lucent agent personality + directives |

---

## Detailed Components

### 1. Backend Abstraction Layer

**Purpose:** Provide unified interface so service layer doesn't care about backend source.

**File:** `src/lucent_email/backend.py`

```python
class EmailBackend(ABC):
    """Abstract base class for email backends."""
    
    @abstractmethod
    def authenticate(self) -> bool:
        """Authenticate with backend (IMAP login, PST validation, etc.)."""
        pass
    
    @abstractmethod
    def list_folders(self) -> List[str]:
        """List available folders/labels."""
        pass
    
    @abstractmethod
    def list_emails(self, folder: str, limit: int = 100) -> List[EmailMetadata]:
        """List emails in folder. Return metadata (headers, IDs, timestamps)."""
        pass
    
    @abstractmethod
    def get_email(self, email_id: str) -> FullEmail:
        """Fetch full email with body + attachments."""
        pass
    
    @abstractmethod
    def search(self, query: str) -> List[str]:
        """Search emails. Return list of email IDs."""
        pass
    
    @abstractmethod
    def send_email(self, to: str, subject: str, body: str) -> bool:
        """Send email via backend. Return success."""
        pass
    
    @abstractmethod
    def move_email(self, email_id: str, folder: str) -> bool:
        """Move email to folder."""
        pass
    
    @abstractmethod
    def flag_email(self, email_id: str, flag: bool) -> bool:
        """Flag/unflag email."""
        pass
    
    @abstractmethod
    def mark_read(self, email_id: str, read: bool) -> bool:
        """Mark email as read/unread."""
        pass
    
    @abstractmethod
    def sync_metadata(self) -> List[EmailMetadata]:
        """Return newly added/modified emails since last sync."""
        pass
```

**Key Invariants:**
- `email_id` is prefixed with backend name: `pst_<id>` or `imap_<uid>`
- PST backend is read-only (no send, move, flag)
- IMAP backend is bidirectional
- Both backends return `EmailMetadata` and `FullEmail` dataclasses

### 2. PST Backend

**Purpose:** Read-only access to local Outlook PST file.

**File:** `src/lucent_email/pst_backend.py`

```python
class PSTBackend(EmailBackend):
    def __init__(self, pst_file_path: str):
        """Initialize PST backend with fixed path to PST file."""
        self.pst_file_path = pst_file_path
        self.pst_instance = None
    
    def authenticate(self) -> bool:
        """Validate PST file exists and is readable."""
        # Using pywin32 or python-pst to open/validate PST
        pass
    
    # ... implement required methods
```

**Implementation Notes:**
- PST is read-only (no send, move, delete to PST itself)
- Can read all folders + emails from Outlook archive
- Fixed file path (no dynamic discovery)
- Sync returns delta since last read (based on timestamps)
- Integration: Uses pywin32 (Windows) or python-pst (portable)

### 3. IMAP Backend

**Purpose:** Bidirectional email access via IMAP/SMTP.

**File:** `src/lucent_email/imap_backend.py`

```python
class IMAPBackend(EmailBackend):
    def __init__(self, email_addr: str, imap_host: str, smtp_host: str):
        """Initialize IMAP backend with credentials from config/keyring."""
        self.email_addr = email_addr
        self.imap_host = imap_host
        self.smtp_host = smtp_host
        self.imap_connection = None
        self.smtp_connection = None
    
    def authenticate(self) -> bool:
        """Log in to IMAP + SMTP using credentials from keyring."""
        # Retrieve password from keyring
        # IMAP login + SMTP login
        pass
    
    # ... implement required methods
```

**Implementation Notes:**
- Credentials: Retrieve from system keyring (not hardcoded)
- IMAP for read + folder operations
- SMTP for sending
- Sync: Use IMAP `RECENT` flag or timestamp
- Connection pooling: Keep connections open during sync

### 4. Database Layer

**Purpose:** SQLite persistence for metadata cache, drafts, sender history.

**File:** `src/lucent_email/db.py`

**Schema:**

```sql
-- Metadata cache
CREATE TABLE IF NOT EXISTS emails (
    id TEXT PRIMARY KEY,                  -- "pst_123" or "imap_456"
    backend TEXT NOT NULL,                -- "pst" or "imap"
    from_addr TEXT,
    to_addrs TEXT,                        -- JSON or semicolon-separated
    subject TEXT,
    timestamp DATETIME,
    received_date DATETIME,
    read BOOLEAN DEFAULT 0,
    flagged BOOLEAN DEFAULT 0,
    folder TEXT,                          -- "Inbox", "Sent", etc.
    labels TEXT,                          -- JSON array
    snippet TEXT,                         -- First 200 chars
    message_id TEXT UNIQUE,               -- For threading
    in_reply_to TEXT,
    sender_priority_score REAL DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_synced DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Sender interaction history
CREATE TABLE IF NOT EXISTS sender_priority (
    from_addr TEXT PRIMARY KEY,
    interaction_count INT DEFAULT 0,
    response_time_avg REAL DEFAULT 0,     -- Average seconds Nick takes to respond
    priority_score REAL DEFAULT 0,        -- 0-10 scale
    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Draft management
CREATE TABLE IF NOT EXISTS drafts (
    id TEXT PRIMARY KEY,                  -- UUID
    to_addrs TEXT NOT NULL,               -- JSON array
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    original_email_id TEXT,               -- Which email this responds to
    status TEXT DEFAULT 'pending_review', -- pending_review, approved, sent, discarded
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    approved_at DATETIME,
    sent_at DATETIME
);

-- Full-text search index
CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
    subject, snippet, from_addr, to_addrs,
    content='emails', content_rowid='id'
);
```

**Key Methods:**

```python
class EmailDatabase:
    def __init__(self, db_path: str):
        """Initialize SQLite connection + schema."""
        pass
    
    def insert_or_update_email(self, email: EmailMetadata) -> None:
        """Upsert email metadata into cache."""
        pass
    
    def search(self, query: str) -> List[EmailMetadata]:
        """Full-text search via FTS5."""
        pass
    
    def get_email_by_id(self, email_id: str) -> EmailMetadata:
        """Get cached metadata for email."""
        pass
    
    def sync_emails(self, emails: List[EmailMetadata]) -> None:
        """Batch insert/update emails from sync."""
        pass
    
    def update_sender_priority(self, from_addr: str, score: float) -> None:
        """Update priority score for sender."""
        pass
    
    def create_draft(self, draft: Draft) -> str:
        """Create new draft, return draft ID."""
        pass
    
    def update_draft_status(self, draft_id: str, status: str) -> None:
        """Update draft status (pending → approved → sent)."""
        pass
```

### 5. EmailService API

**Purpose:** High-level interface for all email operations.

**File:** `src/lucent_email/email_service.py`

```python
class EmailService:
    def __init__(self, config: EmailConfig):
        """Initialize service with backends + database."""
        self.pst_backend = PSTBackend(config.pst_file_path)
        self.imap_backend = IMAPBackend(config.imap_config)
        self.db = EmailDatabase(config.db_path)
        self.backends = [self.pst_backend, self.imap_backend]
    
    # Query operations
    def search(self, query: str, backend: str = None) -> List[EmailMetadata]:
        """Search across both backends (or specific backend)."""
        # Full-text search via SQLite FTS5
        pass
    
    def get_email(self, email_id: str) -> FullEmail:
        """Fetch full email from appropriate backend."""
        # Determine backend from email_id prefix
        # Fetch full email (body + attachments)
        pass
    
    def list_emails(self, folder: str = "Inbox", limit: int = 50) -> List[EmailMetadata]:
        """List recent emails in folder."""
        pass
    
    def get_conversation(self, message_id: str) -> List[Email]:
        """Get entire conversation thread."""
        # Use message_id + in_reply_to to thread
        pass
    
    # Sync operations
    def sync_all(self) -> SyncResult:
        """Sync all backends, update cache, return summary."""
        # PST: Full scan (it doesn't change much)
        # IMAP: Incremental sync (only new/modified)
        # Update SQLite
        # Return: { pst_new: N, imap_new: M, errors: [...] }
        pass
    
    def get_new_emails(self, since: datetime) -> List[EmailMetadata]:
        """Get emails added since timestamp."""
        pass
    
    # Priority analysis
    def compute_sender_priority(self, from_addr: str) -> float:
        """Compute priority score based on sender history."""
        # Interaction count, response time, keywords
        pass
    
    def detect_high_priority_emails(self, limit: int = 10) -> List[EmailMetadata]:
        """Return high-priority emails (Phase 2+)."""
        pass
    
    # Draft operations
    def create_draft(self, to: str, subject: str, body: str, 
                     responding_to_id: str = None) -> str:
        """Create draft, return draft ID."""
        pass
    
    def get_draft(self, draft_id: str) -> Draft:
        """Retrieve draft by ID."""
        pass
    
    def approve_draft(self, draft_id: str) -> bool:
        """Mark draft as approved for sending."""
        pass
    
    def send_email(self, to: str, subject: str, body: str) -> bool:
        """Send email via IMAP/SMTP."""
        pass
```

### 6. Data Models

**File:** `src/lucent_email/models.py`

```python
@dataclass
class EmailMetadata:
    """Lightweight email metadata (from cache)."""
    id: str                    # "pst_123" or "imap_456"
    backend: str               # "pst" or "imap"
    from_addr: str
    to_addrs: List[str]
    subject: str
    timestamp: datetime
    snippet: str
    read: bool
    flagged: bool
    folder: str
    message_id: str
    in_reply_to: str = None
    priority_score: float = 0.0

@dataclass
class FullEmail(EmailMetadata):
    """Complete email with body + attachments."""
    body: str
    html_body: str = None
    attachments: List[Attachment] = field(default_factory=list)

@dataclass
class Attachment:
    """Email attachment."""
    filename: str
    size: int
    content_type: str
    # content: bytes (optional, lazy-loaded)

@dataclass
class Draft:
    """Email draft."""
    id: str
    to_addrs: List[str]
    subject: str
    body: str
    responding_to_id: str = None
    status: str = "pending_review"  # pending_review, approved, sent, discarded
    created_at: datetime = field(default_factory=datetime.now)
    approved_at: datetime = None
    sent_at: datetime = None

@dataclass
class SyncResult:
    """Result of sync operation."""
    pst_new: int        # New emails from PST
    imap_new: int       # New emails from IMAP
    updated: int        # Updated emails
    errors: List[str]   # Any errors during sync
    duration_seconds: float
```

---

## Data Flow: Key Scenarios

### Scenario 1: Sync (Every 30 Minutes)

```
1. EmailService.sync_all()
   ├─ PST Backend: List all emails (time-based delta)
   ├─ IMAP Backend: List recent emails (IMAP RECENT flag)
   ├─ For each new email:
   │  ├─ Create EmailMetadata
   │  ├─ Compute sender priority (heuristic in Phase 1)
   │  └─ Insert into SQLite
   └─ Return SyncResult (counts, duration, errors)

2. Lucent (Phase 2+) receives SyncResult
   ├─ Calls EmailService.detect_high_priority_emails()
   ├─ Uses Claude Haiku to score priority
   └─ Alerts Nick: "3 high-priority emails arrived"
```

### Scenario 2: Search

```
1. Lucent: "Search for emails about Q2 planning from Sarah"
2. EmailService.search("from:sarah Q2 planning")
   ├─ SQLite FTS5 search: SELECT * FROM emails_fts WHERE ...
   ├─ Return top 20 results (EmailMetadata only)
   └─ Return in < 100ms

3. User selects one result
4. EmailService.get_email(email_id)
   ├─ Determine backend from ID prefix
   ├─ Fetch full email from appropriate backend
   ├─ Cache body in memory (optional: update SQLite)
   └─ Return FullEmail
```

### Scenario 3: Draft & Send (Phase 3+)

```
1. Lucent analyzes email, composes draft
2. EmailService.create_draft(
     to=sender,
     subject="Re: " + original_subject,
     body=composed_text,
     responding_to_id=original_email_id
   )
   ├─ Insert draft into drafts table
   ├─ Return draft_id
   └─ Status = "pending_review"

3. Lucent: "Here's my draft. Approve?"
4. Nick: "Looks good, send it"
5. EmailService.approve_draft(draft_id)
   ├─ Update status = "approved"
   └─ Trigger send (or wait for explicit send command)

6. EmailService.send_email(draft_id)
   ├─ IMAP Backend: Send via SMTP
   ├─ Track in Sent folder
   ├─ Update draft: status = "sent", sent_at = now
   └─ Return success
```

---

## Error Handling & Resilience

### Backend Errors
- If PST file is locked: Retry with backoff, skip PST on timeout
- If IMAP connection fails: Queue operations, retry at next sync
- If SMTP fails: Keep draft in pending_review state, don't discard

### Database Errors
- SQLite locked: Retry with WAL mode enabled
- Schema migration failure: Log error, fall back to old schema
- Corruption: Backup + rebuild from scratch

### Sync Conflicts
- Email modified on IMAP since last sync: Update local cache
- Draft created locally but email deleted remotely: Mark orphaned, notify user

---

## Configuration

**File:** `lucent_email.config.json` (or environment variables)

```json
{
  "email": {
    "pst_file_path": "/c/Users/nick/AppData/Local/Microsoft/Outlook/archive.pst",
    "imap": {
      "email": "nick@antonizick.com",
      "imap_host": "imap.example.com",
      "imap_port": 993,
      "smtp_host": "smtp.example.com",
      "smtp_port": 587,
      "use_tls": true
    },
    "database": {
      "path": "/home/nick/dev/lucent/.data/email.db"
    },
    "sync_interval_minutes": 30,
    "claude": {
      "model_haiku": "claude-3-5-haiku-20241022",
      "model_sonnet": "claude-3-5-sonnet-20241022"
    }
  }
}
```

---

## Performance & Scalability

### Design for 25K Emails

| Operation | Latency | Notes |
|-----------|---------|-------|
| Search | < 100ms | SQLite FTS5, cached |
| Get email | 200–500ms | Fetch body from backend on demand |
| List folder | 50–200ms | Cached metadata |
| Sync | 30–60s | Both backends, batch operations |
| Draft creation | 2–5s | Claude Sonnet call (Phase 3+) |

### Caching Strategy

- **Metadata always cached** — SQLite
- **Attachment metadata cached** — Filenames, sizes (not content)
- **Bodies fetched on demand** — Lazy load from backend
- **FTS index maintained** — Update on every sync

### Optimization Opportunities

- Connection pooling (IMAP)
- Incremental sync (only new messages)
- Batch Claude requests (priority scoring for 20 emails at once)
- Compress old emails in archive (Phase 5+)

---

## Testing Strategy

### Unit Tests
- Backend mock implementations
- Database schema validation
- Model serialization/deserialization

### Integration Tests
- Read from both PST + IMAP
- Search 100+ emails, verify results
- Sync new emails, verify cache update
- Draft creation + storage

### End-to-End Tests
- Full workflow: search → read → draft → (send when implemented)
- Error scenarios: missing PST, IMAP timeout, etc.

---

## Future Extensions

### Phase 2+
- Claude integration (Haiku for analysis, Sonnet for drafts)
- Proactive monitoring + priority detection
- Sending capability + approval workflow

### Phase 5
- Sender relationship learning
- Conversation importance scoring
- Long-form email composition

### Beyond
- Real-time sync (WebSocket?)
- Calendar integration (meeting context)
- Attachment analysis (image thumbnails, doc summaries)

---

**Last Updated:** 2026-05-17 | **Next Review:** After Phase 1 completion
