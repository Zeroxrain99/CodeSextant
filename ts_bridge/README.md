# ts_bridge — CodeSextant C5b TypeScript/JavaScript 真解析橋

給 TS/JS **高信心** import 解析（ts-morph 的 `findReferences`，能排除同名干擾），
取代 C5a 對非 Python 的名稱比對退化。Python 端 `codesextant/references.py` 的
`ts_morph_references()` 透過 stdin/stdout JSON 呼叫 `find_refs.mjs`。

## 首次安裝（缺 node_modules 時）

```
cd ts_bridge && npm install
```

`node_modules/` 不進版控（見 `.gitignore`，約 14.5 MB）。

## Fallback（永不壞）

CodeSextant 偵測不到 `node`、或 `ts_bridge/node_modules/ts-morph` 未安裝、或子進程失敗時，
`engine.find_references` 自動退回 C5a 名稱比對（低信心），不會報錯。所以這個橋是
**選用增強**，不是硬性依賴。

## 協議

| 方向 | 格式 |
|---|---|
| 輸入 stdin | `{projectRoot, defFile, symbol}` |
| 輸出 stdout | `{symbol, definition:{path,line}, high_confidence:[{src_path,line,column,confidence}], engine:"ts-morph", elapsed_ms}` |
| 失敗 | `{error, high_confidence:[]}` → Python 端據此 fallback |
