# Quality bar. The full specification for every phase

Read this before generating any phase. `writing-style.md` wins where the two conflict.

## Rule 0: better than every alternative

The material must be better than:

- an online video course, which is slow and stays at the surface
- a blog article, which skips the reasons and the failure modes
- a tutorial video, which rarely shows production patterns
- official documentation, which is reference material, not learning material
- a paid workshop, which has fixed time and cannot use the learner's own numbers

What makes this material better:

1. **Production first.** Every pattern appears as it runs at scale.
2. **Failure first.** The learner sees what breaks, and the exact output when it breaks.
3. **Measured.** The learner runs a script and gets the number the text quotes.
4. **Verified.** Every fact carries its source and its conditions.
5. **Curated references.** Specific sections, figures, and timestamps. Never "search for it".
6. **Complete.** The document is enough on its own. No other resource is needed to fill a gap.

## Rule 1: teaching voice in plain English

Write like a senior engineer explaining at a whiteboard. Use plain sentences.

WRONG, documentation voice:

```
## 2.1 — Log Storage: Segments & Indexes
A Kafka partition consists of segments. Each segment has a .log file...
```

RIGHT, teaching voice in plain English:

```
## 2.1 — The storage layer (what a partition is on disk)

Why this matters: most strange Kafka behaviour in production comes from five
places. They are storage, replication, leader election, delivery guarantees,
and the rebalance protocol. If you do not know these five, you can only guess
during an outage.

Here is how a partition is laid out on disk:
```

Techniques:

- Start every section with why it matters. "Why this matters: ..."
- Speak to the reader as "you".
- Put diagrams inside the explanation, at the point where they help.
- Use short transitions between sections: "The next section uses this number."
- Show the wrong belief first: "You might expect X. The measurement shows Y."
- Mark surprising facts plainly: "This surprises most people:" or "Important:".
- When your own first version was wrong, say so. Show the wrong result, the cause, and the fix. Real mistakes teach more than invented ones.

## Rule 2: self-contained

- All theory is in the document.
- A reader who opens the file in six months understands it without the chat.
- No "as we discussed". The document is the source of truth.
- Links to earlier sections name the section number, and the number must be checked.

## Rule 3: depth

The reader should feel they are reading an internal engineering document from a strong team.

- Exact sizes, timeouts, versions, and defaults, with the version they came from.
- What happens at the protocol or system-call level, when it explains behaviour.
- Failure modes with the exact error, status code, or log line.
- What the failure looks like in logs, metrics, and traces.
- Source code or design documents for "why it was built this way".
- Exact config keys with defaults, such as `max.poll.interval.ms=300000`. Never "the timeout setting".

## Rule 4: three passes inside each concept

1. **The mental model.** Three sentences and one diagram. A reader who stops here has the idea.
2. **The details.** Exact configs, edge cases, a code example, the arithmetic.
3. **The traps.** What breaks, measured, and an action for the reader.

## Rule 5: every concept ends with an action

End each concept section with these three lines:

```
**The sentence to remember:** <one line>

**The trap:** <the specific mistake, and what it costs>

**Try this now:** <an exact command, with what to look for>
```

`**Verify:**` or `**In your codebase:**` may replace `**Try this now:**` when no command fits.

## Rule 6: infrastructure

If the topic needs local infrastructure:

- Ship a `docker-compose.yml` or a setup script with exact image versions and ports.
- Give a check: "run X, you should see Y".
- If the learner's machine cannot run it, say where it runs and what it costs, in the outline and in the phase.

## Rule 7: runnable code

The code is part of the teaching. Every phase ships working files.

Each file must be:

- **Self-contained.** One command runs it.
- **Offline first.** A mode with no network and no key, plus a `--self-test`.
- **Tested against known answers.** A published table, a closed form, or a hand-worked case.
- **Tested against its own rules.** Removing a rule the text calls important must fail a check.
- **Production-grade.** Real error handling, real configs. No toy code, no `TODO`.
- **Commented with reasons.** Not `# create writer`. Write `# acks=all keeps the data if a broker dies`.
- **Configurable** through flags.
- **Documented at the top.** What it demonstrates, how to run it, what you should see, what it costs.
- **One concept per file**, plus shared helpers that have their own self-tests.

For AI topics, every exercise prints its tokens, cost, and latency. Quality exercises score against a labelled set.

## Element specifications

### 1. Concept sections

- Up to five paragraphs between diagrams or code blocks.
- Lead with why.
- Show the wrong way first, with the output it produces.
- End with the three action lines from Rule 5.

### 2. Diagrams. Mandatory wherever there is structure

Use box-drawing characters: `┌ ┐ └ ┘ │ ─ ├ ┤ ┬ ┴ ┼ ► ◄ ▲ ▼ █`.

Good:

```
┌──────────┐   request    ┌──────────┐   replicate   ┌──────────┐
│ Client   ├─────────────►│ Leader   ├──────────────►│ Follower │
│          │◄─────────────┤          │◄──────────────┤          │
└──────────┘   response   └──────────┘   ack         └──────────┘
```

Not acceptable: `Client -> Leader -> Follower`.

Use a diagram for:

- every architecture: boxes and labelled arrows
- every sequence: a timeline with times
- every comparison: side by side, with a column divider
- every state change: before and after
- every distribution or ratio: a bar chart with `█`, and the numbers printed next to the bars

Diagram rules:

- Columns line up. Build complex diagrams with a script and fixed widths, then check them.
- Numbers in a diagram are either real output or labelled "example".
- A table is not a diagram. It does not count toward the diagram target.

### 3. Code examples inside the `.md`

- 3 to 5 per part, with a language tag: `python`, `bash`, `yaml`, `markdown`.
- Copied from the shipped file, or copied from a fetched official source with the date.
- Name the file and line: "from `capacity_plan.py:60`". Check the line after the last code edit.
- If you shorten comments, say "comments shortened, logic unchanged".
- Wrong and right: `# WRONG:` first, then `# RIGHT:`, with the real error or real output of the wrong version.

### 4. Exercises: 7 to 12 per phase

```
- [ ] **E1 (offline).** <what to do>
  - Run: `<exact command>`
  - Expected: <the real output, with numbers from an actual run>
  - If it fails: <likely cause and fix>
  - Teaches: <one concept>
```

- Tag each exercise: `offline`, `live`, `rented GPU`, `written`, `break-it`.
- At least 2 break-it exercises per phase: kill a process, exhaust a resource, remove a safety rule, inject a prompt attack, overflow a budget.
- A break-it exercise shows the break happening, with the numbers.
- A live exercise either was run, or carries "UNVERIFIED against <provider>".
- Anything that can spend money carries "Costs at most: $X".
- State the run status at the top of the lab: "every command below was executed on <date>".
- Number exercises continuously across parts: part A has E1 to E8, part B starts at E9.

### 5. Checkpoint questions: 5 to 7 per part

- Test understanding, not memory.
- Frame each as a scenario with numbers. Never "explain X".
- Include at least one of each type:
  - "Walk through what happens when ..."
  - "A colleague says X. Argue for or against, with numbers."
  - "Given these constraints, design ..."
  - "This is broken: <symptoms>. What is the cause, and how do you check it?"
  - "Show the arithmetic: given <values>, compute <result>."
- End with a collapsible block:

```
<details>
<summary>Answer sketches</summary>

1. Two to four lines, with the arithmetic.
...

</details>
```

### 6. Codebase anchor, or "Check it yourself"

- 2 to 4 items with checked file paths, line numbers, and identifiers.
- Each item asks a pointed question that the reader answers by reading or running the code.
- In learning-only mode, point at the course's own code, and add questions that work on any repo:

```
1. Open `code/phase06_design/incident_drill.py:99`. This is `triage`.
   Read its docstring. What did the first version do, and how often did it miss?

2. In any LLM service you own, run:
   `grep -rn "response_model\|prompt_version" <your repo>/`
   For every field that returns nothing, name the incident you could not diagnose.
```

### 7. Comparison tables

Always compare alternatives with real numbers and conditions. Never "high, medium, low".

### 8. References

Group them by theme. Every entry has this shape:

```
- **Title, venue, year** — URL
  Focus on: section, figure, table, or timestamps. Why this source, and when to read it.
```

Rules:

- Every URL was fetched in this session and returned 200. State the check date at the top of the section.
- Primary sources first. At least one production postmortem or engineering report with conditions.
- The original paper or design document, when one exists.
- Videos carry 8 to 12 timestamps. Say if they came from captions.
- A source that is new or not peer reviewed says so.
- No generic "introduction to X" links.

### 9. Cheatsheet

- One per part, in a code block.
- Formulas, commands, thresholds, and rules in a "what, then value" layout.
- Fits on one screen.
- Every number in it appears in the body with its source.

## Phase and part templates

### Single phase

```
# Phase N — <Title>

<Why this phase matters. What you can do after it. What goes wrong if you skip it.>

<Commitments this phase pays, in one sentence each.>

┌─────────────────────────────────────────────────────────────┐
│  N.1  <Topic A>   — <one line>                              │
│  N.2  <Topic B>   — <one line>                              │
└─────────────────────────────────────────────────────────────┘

<Prerequisites. Where the exercises run. What they cost.>

Time: X to Y hours.

---

## N.1 — <Topic A> (<plain subtitle>)
<why → diagram → explanation → code → wrong/right → three action lines>

## N.2 — <Topic B>
<same shape, with a transition from N.1>

## 🧪 Hands-on lab
## 🏢 Codebase anchor   (or  ## 🔍 Check it yourself)
## ✅ Checkpoint N — answer in your own words
## References & Further Learning
## Cheatsheet
```

### Split phase

Each part follows the same template. Add:

- Part A's header names both parts and says which sections each holds.
- Part B's header says part A is a prerequisite, and why.
- Part A ends with one line that says what part B covers.
- Each part has its own lab, check section, checkpoint, references, and cheatsheet.

## DO

- Plain English, short sentences, "you".
- Start every section with why.
- Put diagrams inside the explanation.
- Several diagrams per concept: before and after, timeline, architecture.
- Check every number in every diagram.
- Show the wrong way first, with its real output.
- Tables for every comparison, with numbers and conditions.
- Timelines for every sequence, with times.
- Exact config names, defaults, and versions.
- Show the arithmetic for every formula.
- Name patterns: "this is the outbox pattern".
- Show what failure looks like: logs, metrics, error output.
- Name every source in the text.
- Report your own first-draft mistakes when they teach something.

## DO NOT

- No walls of text. At most five paragraphs before a diagram or a code block.
- No toy examples.
- No "simply", "just", or "easily".
- No metaphors, idioms, em-dashes in prose, or semicolons in prose.
- No vague exercises. Exact commands and real expected output only.
- No placeholder code.
- No hand-waved gotchas. Show exactly what goes wrong.
- No description of what a thing is without what it does.
- No theory without an action.
- No "high, medium, low".
- No 101 content for this learner.
- No number without a source or a run behind it.
- No "a large company" when the source has a name.

## FULL EXAMPLE. This is the bar

```markdown
## 2.3 — Leader election (what happens when a broker dies)

Why this matters: a dead broker is the most common Kafka incident. If you know
the sequence, a 5-second write pause is expected. If you do not, it looks like
data loss.

**The mental model.** Each partition has one leader broker. When the leader
dies, the controller picks a new leader from the in-sync replicas. An in-sync
replica is a follower that has every acknowledged write. Producers that retry
see a short pause and then continue.

┌─────────────────────────────────────────────────────────────────────┐
│ Timeline: leader failure and election                               │
├─────────────────────────────────────────────────────────────────────┤
│  t=0s    broker-1 leads partition 0 and serves writes               │
│  t=0s    docker kill kafka-1                                        │
│  t=3s    the controller misses broker-1's heartbeat                 │
│  t=3-5s  the controller elects broker-2 from the in-sync replicas   │
│  t=5s    new metadata reaches all brokers                           │
│  t=5s    the producer gets NOT_LEADER_OR_FOLLOWER, error code 6     │
│  t=5s    the producer refreshes metadata and finds broker-2         │
│  t=5.1s  the producer resends to broker-2, and the write succeeds   │
│                                                                     │
│  write pause: about 2 to 5 seconds                                  │
│  lost messages: 0, with acks=all and min.insync.replicas=2          │
└─────────────────────────────────────────────────────────────────────┘

**The details.** The controller tracks brokers through heartbeats. When one
dies, the controller does four things:

1. It removes the broker from the in-sync set of each partition.
2. It picks a new leader for each partition that the broker led.
3. It sends the new metadata to every broker.
4. Clients refresh their metadata on their next failed request.

Config: `controller.quorum.election.timeout.ms`, default 1000 ms, in KRaft mode.

The producer log shows:

    NOT_LEADER_OR_FOLLOWER: the client sent to a replica that is not the
    leader for this partition

**The traps.**

**The sentence to remember:** leader election is automatic and fast, and a
producer with acks=all and retries loses nothing.

**The trap:** `unclean.leader.election.enable=true` lets an out-of-sync
replica become leader after every in-sync replica dies. Acknowledged writes
are then lost. The default has been false since Kafka 2.0. Keep it false for
any data you cannot lose.

**Try this now:**

    docker exec kafka-1 kafka-topics.sh --bootstrap-server kafka-1:9092 \
      --describe --topic events | grep "Partition: 0"
    docker kill kafka-1
    docker exec kafka-2 kafka-topics.sh --bootstrap-server kafka-2:9092 \
      --describe --topic events | grep "Partition: 0"

The second command shows a new leader, and one fewer in-sync replica.
```

Exercise at the bar:

```markdown
- [ ] **E7 (break-it, local).** Kill the leader broker for partition 0.
  - Run: `docker kill kafka-1`. Use the leader that `--describe` printed.
  - Expected: `--describe` shows a new leader within 3 to 5 seconds. The in-sync set shrinks by one.
  - Run a producer during the kill. Expect 1 or 2 retry lines, then normal output.
  - Verify: the consumer count equals the producer count.
  - If it fails: check whether `min.insync.replicas` is larger than the remaining in-sync set. The producer then blocks.
  - Teaches: automatic failover with acks=all.
```

Checkpoint at the bar:

```markdown
4. **Exactly once, or not.** Your service grades support tickets with an LLM
   and stores the grade in Postgres. A teammate proposes Kafka transactions.
   (a) Which boundary does a Kafka transaction cover, and why is it the wrong tool here?
   (b) Draw the right pattern, including failure recovery.
   (c) The LLM call succeeds and the database write fails. How do you recover
       without paying for the LLM call twice?
```
