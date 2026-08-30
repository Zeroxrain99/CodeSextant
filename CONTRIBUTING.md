# Contributing to CodeSextant

Focused contributions are easier to review and validate.

## Getting set up

```bash
pip install -e ".[test]"
python -m pytest tests/ -q
```

High-confidence TypeScript/JavaScript resolution also requires Node and a
one-time `npm install` inside `ts_bridge/`. Without the bridge, TS/JS references
fall back to low-confidence name matching.

## What is most useful

- **Language coverage.** Import-resolved Go and Rust references are current
  priorities.
- **Reference accuracy.** Report false-positive references even if you do not
  have a fix. Include the repository layout, the `--src-root` you used, and the
  expected result.
- **Map ranking.** If PageRank produces an unhelpful map, include a repository
  or minimal case that reproduces it.

## Ground rules

- **Reference confidence is part of the public contract.** Only import-resolved
  references may be marked high confidence. Name matches must remain low
  confidence because agents may trust the label automatically.
- **SQLite is the only source of truth.** Snapshots and in-process caches are
  keyed on index revision and query parameters. If you add a cache, make sure
  it invalidates on both.
- **No network calls or API keys.** Do not add external network dependencies.
- **Never sleep to establish a precondition in a test.** `time.sleep` may only be
  used to let time genuinely pass, such as letting a deadline you set on purpose
  expire. It must not be used to wait for a background thread to reach some state,
  because "long enough on my machine" is not a synchronization primitive: the test
  passes locally and on most CI runners, then fails on whichever one is slower that
  day and reads like a real defect. Wait for the state with `wait_until` from
  `tests/conftest.py`, and if nothing observable exists, add the smallest possible
  observation point rather than a longer sleep.

  > If the assertion after a `time.sleep` could fail merely because the machine is
  > slow, the sleep is doing a job it cannot do.

- Add a test that fails before your change and passes after it.

## Reporting bugs

Open an issue with the command you ran, the output you got, the output you
expected, and your OS plus Python version. A minimal repo that reproduces the
problem is the fastest path to a fix.
