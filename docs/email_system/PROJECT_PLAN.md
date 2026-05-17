# Lucent Email System — Project Plan

**Project Status:** Phase 1 (Foundation) — In Progress | **Started:** 2026-05-17 | **Owner:** Lucent + Nick

---

## Executive Summary

Full-featured email management system for Lucent. Monitors, analyzes, and manages Nick's inbox across dual backends (local PST + IMAP account). Proactive email intelligence with draft composition and sending capability.

**Scope:** 15K–25K emails with 30-minute monitoring interval. Annual archiving at year-end.

**Technology:** Python backend + SQLite + Claude (Haiku/Sonnet) + Lucent agent integration.

---

## Goals & Objectives

### Primary Goals
1. **Unified inbox view** — Single interface over PST (local archive) + IMAP (active mail)
2. **Proactive monitoring** — Periodic scans for high-priority emails, alerts to Nick
3. **Intelligent drafting** — Generate thoughtful responses based on email context
4. **Safe sending** — Drafts require approval before send (never automatic)
5. **No vendor lock-in** — Integrate with Lucent agent system, not tied to specific cloud provider

### Success Criteria
- Can read/search all emails from both PST + IMAP
- Search latency < 100ms (SQLite cached)
- New emails detected within 30 minutes
- Draft composition quality acceptable for business email
- All code documented with clear architecture + workflow docs
- Phase 1 completion: read + search fully functional
- Phase 2 completion: proactive monitoring + priority detection
- Phase 3 completion: draft workflow
- Phase 4 completion: sending capability
- Phase 5 completion: priority learning

---

## Architecture Overview

### System Components

```
┌────────────────────────────────────────────┐
│     Lucent (Nick's assistant)              │
└───────────────┬────────────────────────────┘
                │
┌───────────────┴────────────────────────────┐
│      Email Service API                      │
│  (search, read, analyze, draft, send)      │
└───────────────┬────────────────────────────┘
                │
        ┌───────┴──────────┐
        ▼                  ▼
   ┌─────────┐         ┌──────────┐
   │ PST     │         │ IMAP/    │
   │ Backend │         │ SMTP     │
   │ (RO)    │         │ (R/W)    │
   └─────────┘         └──────────┘
        │                  │
        └───────┬──────────┘
                ▼
        ┌──────────────────┐
        │   SQLite Cache   │
        │  (headers + MD)  │
        └──────────────────┘
```

### Key Design Decisions

1. **Metadata Cache First** — SQLite stores email headers/metadata. Bodies fetched on-demand. Fast search, offline capable.
2. **Backend Abstraction** — Both PST and IMAP implement unified `EmailBackend` interface. Service doesn't care which source.
3. **PST Read-Only** — PST is local archive; all writes go via IMAP/SMTP.
4. **Claude Integration** — Haiku for routine analysis (priority detection, summarization). Sonnet for drafting & complex Q&A.
5. **Lucent Agent System** — Integrates via agent personality file + service library. No standalone API server initially.

---

## Phases & Milestones

### Phase 1: Foundation (Current)
**Goal:** Unified read + search across both backends.

**Deliverables:**
- Backend abstraction layer (PST + IMAP)
- SQLite schema + sync logic
- EmailService API (search, get_email, list, sync)
- Integration tests
- Architecture + API documentation

**Duration:** ~3–5 days (focused implementation + testing)

**Definition of Done:** 
- ✓ Can read emails from both PST + IMAP
- ✓ SQLite cache populated + synced
- ✓ Full-text search latency < 100ms
- ✓ Tests pass (read from both backends)
- ✓ Docs complete (architecture, API, setup)

---

### Phase 2: Proactive Monitoring
**Goal:** Detect high-priority emails, alert Nick.

**Deliverables:**
- Monitoring loop (30-min sync)
- Priority scoring (Haiku Claude)
- Sender history tracking
- High-priority email detection
- Alerts to Lucent + Nick

**Duration:** ~2–3 days

**Definition of Done:**
- ✓ 30-min sync cycle operational
- ✓ Priority detection working (test with known high-priority senders)
- ✓ Lucent receives alerts + Nick is notified

---

### Phase 3: Draft Workflow
**Goal:** Compose thoughtful responses, require approval before send.

**Deliverables:**
- Draft creation + storage
- Response composition (Sonnet Claude)
- Approval workflow (voice + text)
- Draft state management
- Integration with Lucent

**Duration:** ~2–3 days

**Definition of Done:**
- ✓ Can create draft from email context
- ✓ Sonnet-generated drafts are coherent
- ✓ Approval workflow works (voice/text)
- ✓ Drafts persisted + retrievable

---

### Phase 4: Sending
**Goal:** Send emails safely after approval.

**Deliverables:**
- SMTP integration
- Send safety checks
- Sent folder tracking
- Draft → sent transition
- Testing (non-production first)

**Duration:** ~2 days

**Definition of Done:**
- ✓ Can send draft emails via IMAP/SMTP
- ✓ Sent emails tracked in cache
- ✓ Safety checks prevent accidental sends

---

### Phase 5: Priority Learning
**Goal:** Adaptive priority scoring based on Nick's actual behavior.

**Deliverables:**
- Sender interaction history
- Response time analysis
- Keyword + context boosting
- Conversation importance scoring
- Machine-learned priority model

**Duration:** ~3–4 days (data collection + refinement)

**Definition of Done:**
- ✓ Priority scores improve over time
- ✓ High-priority detection accuracy > 80%

---

## Technology Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| **Email Access** | imaplib, smtplib (stdlib) | IMAP/SMTP for active mail |
| **PST Reader** | pywin32 OR python-pst | Read Outlook PST file |
| **Database** | SQLite (stdlib) | Metadata cache, drafts |
| **Service** | Python 3.9+ | Core email logic |
| **LLM** | Anthropic SDK (Claude) | Haiku + Sonnet |
| **Agent Integration** | Lucent agent system | Via agents/email-agent.md |
| **Testing** | pytest | Unit + integration tests |

---

## Documentation Files

| File | Purpose |
|------|---------|
| `PROJECT_PLAN.md` | This file — project scope, phases, goals |
| `ARCHITECTURE.md` | System design, component details, data flow |
| `SETUP.md` | Development environment setup |
| `API.md` | EmailService API reference |
| `DATABASE_SCHEMA.md` | SQLite schema + migrations |
| `BACKEND_DESIGN.md` | Backend abstraction details |
| `INTEGRATION_GUIDE.md` | How to integrate with Lucent |
| `TESTING_STRATEGY.md` | Test approach + examples |
| `WORKFLOW.md` | Email workflow (monitoring, drafting, sending) |

---

## Timeline & Dependencies

```
Phase 1 (Foundation)
├─ Task 1: Project setup → Task 2–6 (parallel)
├─ Task 2: Backend abstraction
├─ Task 3: PST backend
├─ Task 4: IMAP backend
├─ Task 5: Database layer
├─ Task 6: EmailService
├─ Task 7: Agent personality
└─ Task 8: Testing

↓ (Phase 1 complete)

Phase 2 (Monitoring) → Phase 3 (Drafting) → Phase 4 (Sending) → Phase 5 (Learning)
```

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| PST library compatibility | Blocking Phase 1 | Test early; have fallback (pywin32 vs python-pst) |
| IMAP credential management | Security risk | Use keyring, encrypted config, no hardcoded secrets |
| SQLite schema changes | Data migration | Plan schema early; document migrations |
| Claude API costs | Budget | Use Haiku for routine, limit Sonnet to drafts/Q&A |
| Large email archives | Performance | Lazy-load bodies; cache search results |

---

## Success Metrics

### Phase 1 Completion
- All 8 tasks completed + tested
- Documentation 100% complete
- Code quality: type hints, clear naming, minimal comments
- Test coverage: > 80% of core logic

### Phase 2 Completion
- Monitoring alert latency < 5 min
- Priority detection accuracy measurable
- No false negatives on high-priority senders

### Overall System (Post-Phase 5)
- Email discovery time: < 5 min from arrival
- Draft composition time: 2–5s
- Draft approval rate: > 95% (quality acceptable)
- User satisfaction: "This handles my inbox well"

---

## Next Steps (Immediate)

1. ✓ Complete Phase 1 planning + documentation setup
2. Begin Task 1: Project structure + dependencies
3. Proceed through Tasks 2–8 in order
4. Conduct Phase 1 testing + validation
5. Transition to Phase 2 (monitoring) once Phase 1 is solid

---

**Last Updated:** 2026-05-17 | **Next Review:** After Phase 1 completion
