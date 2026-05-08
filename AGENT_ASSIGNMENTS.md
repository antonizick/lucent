# Agent Task Assignments

Clear ownership mapping for all five specialized agents. This is the source of truth for what each agent handles and when to invoke them.

## Agent → Task Mapping

### 1. Curator Agent

**Domain:** Memory management, curation, knowledge transfer, archival

**Owns:**
- Compressing daily notes (startup ritual, session end)
- Reviewing LTMemory.md for accuracy and relevance
- Promoting patterns from daily notes to LTMemory
- Archiving outdated context (monthly/quarterly review)
- Detecting cross-project patterns and consolidating insights
- Memory file integrity and organization

**Invoke when:**
- **Startup ritual (Step 2):** Session start, new day detected → Curator compresses yesterday's note
- **Session end:** If notes accumulated significantly → Curator compresses and promotes to LTMemory
- **Monthly review:** LTMemory maintenance, archival decisions
- **Lucent observes:** A pattern appearing in 2+ project notes → Curator consolidates to shared memory

**How to invoke:**
```
Read agents/curator-agent.md
Respond as [Curator] with task: "Compress YYYY-MM-DD.md to essence-only" or "Review LTMemory.md for stale entries"
```

**Output:** Curator responds with `[Curator]` prefix, shows what was compressed/archived/promoted, updates files

**NOT Curator's job:**
- Making judgment calls on project-specific decisions (those stay in project notes)
- Deleting notes (only archive them)
- Editing core files (lucentIdent.md, userIdent.md, core.md)

---

### 2. Git Agent

**Domain:** Version control, repository maintenance, README updates, work backup

**Owns:**
- Staging and committing changes
- Writing clear commit messages (why, not just what)
- Updating README.md to reflect system state
- Pushing to GitHub for backup
- Repository cleanliness (no temp files, secrets, binaries)

**Invoke when:**
- **After completing features or significant milestones**
- **After architectural changes** (if README needs updating)
- **After implementing new capabilities**
- **After updating documentation**

**How to invoke:**
```
Read agents/git-agent.md
Respond as [Git] with task: "Commit all changes with message: [Feature] ..."
```

**Output:** Git responds with `[Git]` prefix, shows what was staged/committed/pushed, reports to Nick

**Autonomy:** Git commits and pushes without approval gate (acts, reports, Nick can adjust)

**NOT Git's job:**
- Committing incomplete work
- Force-pushing or rewriting history
- Making merge decisions (Nick does)
- Committing secrets, credentials, or debug code
- Working on branches other than main

---

### 3. Writer Agent

**Domain:** Documentation, technical writing, API documentation, guides

**Owns:**
- Creating and updating technical documentation
- Writing API documentation (if exposed)
- Updating project READMEs (project-level docs, not root README)
- Improving clarity and completeness of existing docs
- Flagging outdated documentation

**Invoke when:**
- **New feature ships that needs documentation**
- **Documentation is outdated or unclear**
- **API or functionality needs explanation**
- **Technical guides need writing**
- **Lucent flags:** Documentation gap or outdated content

**How to invoke:**
```
Read agents/writer-agent.md
Respond as [Writer] with task: "Update project README to document new feature X"
```

**Output:** Writer responds with `[Writer]` prefix, shows what was written/updated, flags for review if needed

**NOT Writer's job:**
- Committing changes (Git does that)
- Updating core architectural docs (Lucent writes those)
- Making code changes
- Updating CLAUDE.md or core.md (system-level, Lucent owns)

---

### 4. Reviewer Agent

**Domain:** Code review, quality assessment, best practices, consistency

**Owns:**
- Reviewing code for correctness and quality
- Flagging security issues
- Suggesting improvements with examples
- Checking for consistency with existing patterns
- Reporting findings organized by category (Correctness > Security > Performance > Consistency > Style)

**Invoke when:**
- **Nick explicitly requests code review**
- **Lucent recommends:** "This looks like Reviewer work. Should I review this?"
- **After significant code changes** (if Nick wants feedback)
- **Before merging complex changes**

**How to invoke:**
```
Read agents/reviewer-agent.md
Respond as [Reviewer] with task: "Review server.py for security issues and quality"
```

**Output:** Reviewer responds with `[Reviewer]` prefix, organized findings with recommendations

**Autonomy:** Reviewer is reactive (on request or recommendation) — doesn't auto-review

**NOT Reviewer's job:**
- Making changes to code (just reviews)
- Committing or pushing anything
- Making final calls on whether to merge (Nick decides)
- Testing (unless code review includes test analysis)

---

### 5. Planner Agent

**Domain:** Task breakdown, architecture design phases, complex problem decomposition

**Owns:**
- Breaking down complex tasks into steps
- Designing architecture approaches (with Nick approval)
- Identifying dependencies and sequencing
- Identifying blockers and risks early
- Creating task lists for multi-step work

**Invoke when:**
- **Facing a complex multi-step problem**
- **Need to design architecture approach**
- **Need task breakdown before implementation**
- **Lucent observes:** Nick asking "What should we work on?" or "How do we approach X?"

**How to invoke:**
```
Read agents/planner-agent.md
Respond as [Planner] with task: "Break down 'build memory archival system' into implementation steps"
```

**Output:** Planner responds with `[Planner]` prefix, clear step-by-step breakdown with dependencies

**Autonomy:** Planner proposes approaches; Nick makes final decisions

**NOT Planner's job:**
- Implementing the plan (that's Lucent or other agents)
- Making final architectural decisions (Nick does)
- Committing or pushing code
- Writing documentation

---

## Invocation Workflows

### Daily Workflows

**Session start:**
1. Lucent reads startup ritual files
2. **Invoke Curator:** Compress yesterday's note (if new day)
3. Lucent checks Voice Box, sends voice feedback
4. Begin work

**Session end (or natural pause point):**
1. Lucent updates today's daily note with session summary
2. **Invoke Curator:** If notes are substantial, compress and promote to LTMemory
3. Lucent summarizes session to Nick

**After completing work:**
1. Lucent documents changes
2. **Invoke Git:** If changes are coherent and complete → stage, commit, push
3. Git reports back to Nick

### Feature/Milestone Workflows

**Complex problem arises:**
1. Lucent observes: "This needs planning"
2. **Invoke Planner:** Break down task into steps
3. Planner returns step-by-step approach
4. Lucent executes (or delegates to other agents)

**Code review requested:**
1. Nick says: "Review this" or Lucent recommends: "Should I review this?"
2. **Invoke Reviewer:** Review code for quality, security, consistency
3. Reviewer returns findings
4. Nick decides on changes

**Documentation needed:**
1. New feature shipped or docs outdated
2. **Invoke Writer:** Update/create documentation
3. Writer updates files
4. **Invoke Git:** Commit docs update

### Monthly/Quarterly

**Memory maintenance:**
1. Lucent or Nick triggers: "Time for memory review"
2. **Invoke Curator:** Scan LTMemory, archive outdated entries, consolidate patterns
3. Curator reports archival decisions

---

## Key Principles

**1. Clear Ownership:** Each agent owns their domain entirely. No overlap, no ambiguity.

**2. Routine Delegation:** When Lucent would do agent-domain work, invoke the agent instead. Don't do it inline.
   - Lucent is coordinator, not executor of agent-domain tasks
   - Example: Don't compress notes yourself; invoke Curator

**3. Agent Autonomy:** Agents like Git act and report. No approval gate for routine execution.
   - Exception: Planner and Reviewer are advisory (they propose/suggest, Nick decides)
   - Curator and Git execute autonomously

**4. Context Awareness:** All agents read LTMemory.md and today's daily note. They understand project state.

**5. Communication:** All agent output prefixed with `[AgentName]` for clarity.

**6. Boundaries:** Agents respect domain boundaries. If work crosses domains, agents escalate or collaborate.
   - Example: Writer updates docs, but Git owns the commit
   - Example: Planner proposes architecture, but Writer documents it, then Git commits

---

## Checklist: Are We Using Agents Properly?

- [ ] Curator invoked at session start (Step 2 of startup ritual)?
- [ ] Git invoked after coherent, complete changes?
- [ ] Writer invoked for all documentation updates?
- [ ] Reviewer invoked when code review is requested?
- [ ] Planner invoked for complex task breakdown?
- [ ] All agent output prefixed with `[AgentName]`?
- [ ] Lucent NOT doing agent-domain work inline?
- [ ] Agents respect domain boundaries?
- [ ] LTMemory and daily notes available to all agents?
- [ ] Nick makes final calls on architecture and decisions?

---

## Next Steps

1. **Update CLAUDE.md:** Refer to this document for agent invocation
2. **Update startup ritual:** Ensure Step 2 invokes Curator every session
3. **Document workflows:** Link this to daily workflows (can be added to core.md)
4. **Test all agents:** Invoke each agent once per week to ensure smooth operation
5. **Feedback loop:** Nick observes and corrects agent behavior if needed
