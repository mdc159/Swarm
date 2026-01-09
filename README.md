# Swarm Learning Framework

A learning-oriented evaluation framework for LSP-Swarm that captures decision traces, identifies patterns, and produces actionable improvement recommendations.

## Philosophy

> **Archon is a passive repository, NOT a controller.**
> Agents execute freely based on their training. Archon records what happens and enables learning from patterns.

## What This Framework Does

Instead of testing "does it work?" (pass/fail), this framework answers:

| Question | How We Answer It |
|----------|------------------|
| **Why** did agents make specific decisions? | Decision trace hooks capture reasoning |
| What **information was missing** that would have helped? | Context snapshots at decision time |
| What **skills/tools** are agents reaching for that don't exist? | Gap analyzer detects missing capabilities |
| What **patterns predict failure** before they happen? | Anticipation signals from historical data |
| How well do **plans match execution**? | Plan fidelity comparison |

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Learning Feedback Loop                     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ┌─────────────────┐                                       │
│   │   LSP-Swarm     │◀──── Primary Actors (unconstrained)   │
│   │   Agents        │      Sisyphus, Prometheus, Oracle...  │
│   └────────┬────────┘                                       │
│            │                                                 │
│            │ Execute tasks, make decisions                   │
│            ▼                                                 │
│   ┌─────────────────┐    ┌─────────────────┐                │
│   │ Decision Trace  │───▶│ Pattern         │                │
│   │ Hooks           │    │ Analysis        │                │
│   └─────────────────┘    └────────┬────────┘                │
│                                   │                          │
│                                   ▼                          │
│   ┌─────────────────┐    ┌─────────────────┐                │
│   │   Archon MCP    │◀───│ Improvement     │                │
│   │   (repository)  │    │ Recommendations │                │
│   └─────────────────┘    └─────────────────┘                │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Run a learning scenario
./scripts/run-scenario.sh hostinger-rebuild

# Analyze captured data
./scripts/analyze.sh

# Generate improvement reports
./scripts/report.sh
```

## Directory Structure

```
Swarm/
├── README.md                    # This file
├── CLAUDE.md                    # Agent instructions
├── .mcp.json                    # Archon MCP configuration
│
├── framework/
│   ├── hooks/                   # Decision trace capture
│   │   ├── decision_trace.py   # Agent reasoning capture
│   │   ├── context_snapshot.py # Knowledge state at decision time
│   │   └── outcome_logger.py   # Rich outcome context
│   │
│   ├── analysis/                # Pattern detection
│   │   ├── pattern_detector.py # Failure pattern identification
│   │   ├── gap_analyzer.py     # Tool/skill gaps
│   │   ├── plan_fidelity.py    # Plan vs execution
│   │   └── anticipation.py     # Early warning signals
│   │
│   └── reports/                 # Actionable outputs
│       ├── agent_improvements.py
│       ├── skill_gaps.py
│       └── failure_patterns.py
│
├── scenarios/                   # Test scenarios
│   └── hostinger-rebuild/       # Primary scenario
│       ├── README.md
│       ├── inputs/              # Reference materials
│       └── expected/            # Success criteria
│
├── scripts/                     # Execution scripts
│   ├── run-scenario.sh
│   ├── analyze.sh
│   └── report.sh
│
└── docs/
    └── LEARNING_FRAMEWORK.md    # Complete specification
```

## Key Metrics

| Metric | What It Reveals |
|--------|-----------------|
| **Decision Reversal Rate** | How often agents undo their own work |
| **Exploration Efficiency** | Useful info found / total exploration time |
| **Delegation Accuracy** | Right agent chosen on first try |
| **Plan Fidelity Score** | How well execution matches plan (0-100%) |
| **Recovery Success Rate** | Failures that were recovered vs cascaded |
| **Tool Gap Incidents** | Times agents needed unavailable capability |

## Reference Materials

This framework uses these repositories for testing:

| Repository | Purpose |
|------------|---------|
| **Hostinger** | Messy real-world codebase for realistic scenarios |
| **oh-my-opencode** | Agent definitions and capabilities |
| **LSP-Swarm** | Swarm patterns and OpenCode integration |
| **Archon** | MCP server for plan/task storage |

## Archon Integration

Archon stores plans and tracks progress but **never dictates agent behavior**:

```bash
# Plans stored as documents
archon:manage_document → Learning Framework Design spec

# Tasks tracked on kanban
archon:manage_task → Progress through todo → doing → done

# Lessons learned in knowledge base
archon:rag_search_knowledge_base → Historical patterns
```

## Contributing

1. Add new analysis modules in `framework/analysis/`
2. Create new scenarios in `scenarios/`
3. Extend hooks for additional data capture
4. Store lessons learned via Archon documents

## License

MIT
