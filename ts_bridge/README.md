# TypeScript/JavaScript reference bridge

`ts_bridge` resolves TypeScript and JavaScript references through ts-morph's `findReferences`.
This avoids collisions between same-named symbols in unrelated modules. The Python function
`ts_morph_references()` calls `find_refs.mjs` over JSON on standard input and output.

## Install

```
cd ts_bridge && npm install
```

`node_modules/` is not version-controlled; see `.gitignore`.

## Fallback

When CodeSextant cannot find `node`, or `ts_bridge/node_modules/ts-morph` is not installed, or the
subprocess fails, `engine.find_references` returns low-confidence name matches without raising an
error. The bridge is optional.

## Protocol

| Direction | Format |
|---|---|
| stdin | `{projectRoot, defFile, symbol}` |
| stdout | `{symbol, definition:{path,line}, high_confidence:[{src_path,line,column,confidence}], engine:"ts-morph", elapsed_ms}` |
| failure | `{error, high_confidence:[]}` → the Python side falls back on this |
