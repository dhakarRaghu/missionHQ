# Review checklist. Run it on every phase before publishing

A draft is not finished when it is written. It is finished when this checklist passes.

In the first course, this review found real errors in every phase. Examples:

- A simulation capped every tenant at 20 requests per second. The text said 40.
- A self-test passed with the rule it claimed to test removed.
- A code comment said "16 times" and the arithmetic gave 11.
- A docstring quoted a z-score that no run produced.
- Two facts from two papers were credited to "the same study".
- A quote from a checklist was not word for word.
- Three cross-references pointed at the wrong section number.
- An invented OpenTelemetry attribute name appeared where a real one existed.
- Cached prices were guessed instead of fetched.
- A table of contents included headings from inside a code block.

Every item below exists because of one of these.

## How to run the review

Work through the sections in order. Record every fix. The fixes go into `course.json` → `reviewLog` and into the report to the user.

Use scratch files: one per section, plus the lab, checkpoint, references, and cheatsheet. Edit the scratch files, then reassemble the document. Never hand-edit the assembled file and the scratch files separately.

## A. Numbers

- [ ] Every number in the text, diagrams, checkpoint answers, and cheatsheet comes from one of:
  - a command you ran in this session, with its output saved
  - a fetched source, with its conditions
  - arithmetic shown in the text
- [ ] Re-run every exercise command. Compare each "Expected" line with the real output.
- [ ] After any code change, re-run all commands. Then search the phase for every old number and replace it.
  ```bash
  grep -n "40.33\|0.47\|2.4x" <scratch files>     # the old values
  ```
- [ ] Numbers inside code comments and docstrings match a real run.
- [ ] Printed explanations in scripts match the computed values.
- [ ] Every "example" number in a diagram is labelled as an example.
- [ ] Every arithmetic step is correct. Recompute it.

## B. Code

- [ ] Every script has `--self-test`, and it passes.
- [ ] Every self-test checks known answers, not only "it runs".
- [ ] **Mutation check.** For each rule the text calls important, disable it and run the self-test. A check must fail. If none fails, add one.
  ```bash
  sed 's/<the rule line>/pass/' script.py > /tmp/mutant.py && python /tmp/mutant.py --self-test
  ```
- [ ] **Hidden limits.** Look for caps the model did not intend. Examples: one arrival per tick, integer division, a fixed queue size, a timeout shorter than a request.
- [ ] **Stated demand equals generated demand.** Count what the simulation generated, and compare it with what it prints.
- [ ] **Named algorithms match the paper.** Check the paper's algorithm listing line by line.
- [ ] **Numerical stability** at the largest sizes the text mentions.
- [ ] Every flag used in the text exists in `--help`.
- [ ] The regression suite passes: every self-test in the whole course.
  ```bash
  for t in $(grep -l "self-test" code/phase*/*.py code/*.py); do
    printf "%s: " "$t"; python "$t" --self-test 2>&1 | tail -1
  done
  ```

## C. Anchors and cross-references

- [ ] Every `file.py:NN` points at the line the text describes. Check after the last code edit, because edits shift lines.
  ```bash
  grep -n "^def \|<identifier>" code/phaseNN_x/file.py
  ```
- [ ] Every code snippet in the text matches the file. If comments were shortened, the text says so.
- [ ] Every "section N.M" and "Phase N" reference points at the right section. Check the heading list of the target document.
  ```bash
  grep -n "^## " <topic>-phase-*.md
  ```
- [ ] Every earlier-phase fact that this phase repeats matches the earlier document.

## D. Sources and quotes

- [ ] Every fact names its source in the text. No "a large provider" or "one study" when the name is known.
- [ ] Two facts from two sources are never merged into "the same study".
- [ ] Every quotation is word for word. Fetch the source and grep for the quoted text.
  ```bash
  curl -sL <url> | grep -i -n "<quoted phrase>"
  ```
- [ ] Every claim from an agent report keeps its label: verified, inferred, or not checked.
- [ ] Every "Things I could NOT verify" item that the text relies on is stated as a limit in the text.
- [ ] New or non-peer-reviewed sources are labelled as such.
- [ ] Standard names, such as API fields and telemetry attributes, come from the fetched spec.
- [ ] Prices, model names, and limits carry a date and were fetched in this session.

## E. URLs

- [ ] Every URL returns HTTP 200 today. Run `scripts/check_urls.py`.
- [ ] Redirected URLs are replaced with the destination.
- [ ] Every reference says what to focus on.

## F. Structure and counts

Run `scripts/audit_phase.py <file>` and fix every failure:

- [ ] size, diagrams, tagged code blocks, WRONG/RIGHT pairs
- [ ] sentence to remember, trap, and action in every concept section
- [ ] exercise numbering continuous across parts
- [ ] checkpoint count and one `<details>` block per part
- [ ] code fences balanced
- [ ] headings for the lab, check section, checkpoint, references, and cheatsheet

## G. Language

- [ ] No prose sentence over 32 words. Few over 20.
- [ ] No em-dashes, brackets, or semicolons in prose.
- [ ] No idioms or words from the avoid list in `writing-style.md`.
- [ ] Every term is defined at first use.
- [ ] Each section gives its point in the first sentence.
- [ ] First person appears only for a real mistake and its fix. Keep it plain.

## H. Teaching quality

Read the phase as the learner. Answer each question honestly.

- [ ] Does each section teach something the learner could not get from the documentation?
- [ ] Is anything taught that an earlier phase or course already covered? Link to it instead.
- [ ] Is anything missing that the phase title promises?
- [ ] Does each checkpoint need the section's content to answer it?
- [ ] Do the answer sketches contain the arithmetic?
- [ ] Is every trade-off stated with what is given up?
- [ ] Would a reviewer at a strong company accept every claim as stated?
- [ ] Does the text say where each simulation stops matching reality?

## I. Commitments and state

- [ ] Every commitment due this phase is fulfilled or deferred in the text.
- [ ] New forward promises are recorded.
- [ ] `course.json` has the phase, its parts, and a `reviewLog` entry.

## J. Publish check

- [ ] The dashboard shows N of N documents with matching SHA-256 hashes.
- [ ] The table of contents for each document has the expected headings, and none from inside code blocks.

## Shell traps seen during reviews

| Trap | Fix |
|---|---|
| zsh does not split `$var` into words | use `${=var}`, or a bash array |
| the working directory resets between tool calls | use absolute paths |
| a backtick inside a double-quoted grep pattern breaks the whole command | put Python edits in a script file |
| `timeout` does not exist on macOS | omit it, or use `gtimeout` |
| a uv virtual environment has no `pip` | use `uv pip` or `uv add` |
| `sed -i` differs between macOS and Linux | use `sed -i ''` on macOS, or edit with Python |
| a heredoc edit script is written but never run | print "ok" at the end, and check for it |

## Reliable edit pattern

Use exact-match replacements that fail loudly:

```python
def edit(path, replacements):
    text = open(path).read()
    for old, new in replacements:
        count = text.count(old)
        assert count == 1, (path, old[:60], count)
        text = text.replace(old, new)
    open(path, "w").write(text)
    print("ok")
```
