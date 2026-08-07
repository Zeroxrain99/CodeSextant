# ts_bridge: the CodeSextant C5b real-resolution bridge for TypeScript/JavaScript

Gives TS/JS **high-confidence** import resolution through ts-morph's `findReferences`, which rules
out same-name noise. It replaces the C5a fallback to name matching for non-Python code. On the Python
side, `ts_morph_references()` in `codesextant/references.py` calls `find_refs.mjs` over stdin/stdout
JSON.

## First-time install (when node_modules is missing)

```
cd ts_bridge && npm install
```

`node_modules/` is not version-controlled (see `.gitignore`; about 14.5 MB).

## Fallback (never breaks)

When CodeSextant cannot find `node`, or `ts_bridge/node_modules/ts-morph` is not installed, or the
subprocess fails, `engine.find_references` falls back to C5a name matching (low confidence) without
raising. The bridge is therefore an **optional enhancement** rather than a hard dependency.

## Protocol

| Direction | Format |
|---|---|
| stdin | `{projectRoot, defFile, symbol}` |
| stdout | `{symbol, definition:{path,line}, high_confidence:[{src_path,line,column,confidence}], engine:"ts-morph", elapsed_ms}` |
| failure | `{error, high_confidence:[]}` → the Python side falls back on this |
