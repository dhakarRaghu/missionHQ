# Curriculum planning. Modules, order, size, and overlap

Use this file for `/study plan`, and before starting any new course.

A curriculum is a list of modules. Each module is one `/study` course. Plan the curriculum first, then plan each module's phases only when the learner starts it.

## Step 1: research what changed

Before writing or updating a curriculum, launch research agents on what changed in the field in the last 12 months. Use `research-method.md`. Report changes in a table:

| Change | Why it matters for this learner |
|---|---|

Label every claim. Vendor blogs overstate. Say "check this before you quote it" for numbers that only secondary sources carry.

## Step 2: group modules into layers

Order layers from the lowest level up. For applied AI, the first curriculum used:

| Layer | Example modules |
|---|---|
| The model | inference internals, context engineering |
| Knowledge | retrieval internals, advanced retrieval, document ingestion |
| Agents | tool layer and MCP, harness engineering, protocols and identity, orchestration, memory |
| Evals | eval engineering, agent and online evals |
| Infrastructure | serving, cost and routing, observability |
| Security | threat modelling, guardrails, compliance |
| Product and frontier | approval design, voice, post-training, electives |

For each module, write 3 to 8 topic bullets and, if relevant, why it was added or changed.

## Step 3: estimate time honestly

- One phase: 60 to 100 minutes of reading, plus 1 to 3 hours of lab work.
- One full module of 7 phases: about 10 to 20 hours.
- Give the total, and the weeks at the learner's stated hours per week.

If the total is more than about six months, propose a **core path**: the 6 to 8 modules that cover most of the job, in order. Put evals early, because later modules depend on them.

## Step 4: size each module by what is new

Seven phases is the default shape, not a rule.

1. List the section headings of every completed course.
   ```bash
   grep -h "^## [0-9]\|^### " <baseDir>/*/<topic>-phase-*.md
   ```
2. For the new module, mark each planned topic as:
   - **new**: not taught anywhere yet
   - **covered**: taught in an earlier course. Link to that section
   - **extends**: taught at a basic level. Teach only the next level
3. Choose the phase count from the new and extends topics:

   | New material | Phases |
   |---|---|
   | a large new area | 6 to 7 |
   | a medium area | 4 to 5 |
   | mostly covered by an earlier course | 3 to 4 |
   | a small topic | fold it into another module |

4. Write the reason for the count in the outline.
5. Record covered topics in `course.json` → `buildsOn`, with section numbers.

A course often grows beyond its plan. Module 1 of the first curriculum grew to cover parts of three later modules: serving, cost, and observability. After a course finishes, re-run step 4 for every later module and update `_curriculum.json`.

## Step 5: save `_curriculum.json`

```json
{
  "title": "Advanced applied AI",
  "updated": "2026-09-17",
  "hoursPerWeek": 5,
  "corePath": [1, 2, 11, 6, 7, 9, 16, 15],
  "modules": [
    {"id": 1, "layer": "The model", "title": "Inference internals",
     "topic": "inference-internals", "status": "completed", "phases": 7,
     "coveredLater": {"13": ["4.1-4.6", "6.1"], "14": ["3.4", "3.5"], "15": ["5.4-5.6", "6.3"]}},
    {"id": 2, "layer": "The model", "title": "Context engineering",
     "topic": "context-engineering", "status": "planned", "plannedPhases": "3-4",
     "reason": "Module 1 section 2.6 covers the budget and the compaction trigger",
     "topics": ["measure context rot", "validate compaction", "sub-agent isolation",
                "tool-result pruning", "long-task benchmarks"]}
  ]
}
```

## Step 6: present the plan

- A table of layers and modules, with status.
- The core path, in order, with the reason for the order.
- The time estimate.
- Overlaps found, and what will be trimmed.
- The next command to run.

Offer to publish the plan to the dashboard as its own page.

## Learning-only rule for curricula

If the learner is studying and not changing a product, remove every "project: rebuild <product> X" item. Replace it with a standalone lab that produces a number, a table, or a failing test. The product stays as background for difficulty and scenarios.
