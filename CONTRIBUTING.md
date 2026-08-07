# Contributing to CodeSextant

Thanks for looking. This is a small project with a narrow goal, so the most
useful contributions are usually specific rather than sweeping.

## Getting set up

```bash
pip install jedi tree-sitter tree-sitter-languages
python -m pytest tests/ -q
```

For high-confidence TypeScript/JavaScript resolution you also need Node and a
one-time `npm install` inside `ts_bridge/`. Everything still runs without it —
TS/JS resolution degrades to name matching and says so.

## What is most useful

- **Language coverage.** Go and Rust currently get tree-sitter symbols but
  name-matched references. Wiring a real resolver for either is the single
  biggest accuracy win available.
- **Wrong reference results.** If `references` returns something that is not
  actually a reference, that is a bug worth reporting even without a fix. Please
  include the repo layout, the `--src-root` you used, and what you expected.
- **Cases where the map is unhelpful.** The PageRank weighting is tuned against
  a limited set of repos. Concrete counter-examples are valuable.

## Ground rules

- **Confidence labels are load-bearing.** Anything that cannot be resolved
  through real import resolution must be reported as low confidence. Never
  present a name match as if it were resolved — agents auto-trust high
  confidence, so a wrong label is worse than no answer.
- **SQLite is the only source of truth.** Snapshots and in-process caches are
  keyed on index revision and query parameters. If you add a cache, make sure
  it invalidates on both.
- **No network calls, no API keys.** Running entirely locally is a feature, not
  an implementation detail.
- Add a test that fails before your change and passes after it.

## Reporting bugs

Open an issue with the command you ran, the output you got, the output you
expected, and your OS plus Python version. A minimal repo that reproduces the
problem is the fastest path to a fix.
