"""probe 控制流節點型別 — 為 D3 認知複雜度（cognitive complexity）子系統坐實 taxonomy。

用法：C:/Python311/python.exe tools/_probe_cflow.py [lang ...]
不帶參數 = python/typescript/tsx 三語言。對每語言 parse 一段「涵蓋各種控制流」的樣本，
印出整棵 named 節點樹（帶深度），讓人眼坐實：
  - 增量點（if/for/while/do/catch/switch-case/ternary/...）的確切 tree-sitter type
  - else/elif 是獨立 clause 還是巢進 if_statement
  - boolean operator（and/or、&&/||）的節點 type
  - comprehension / lambda / arrow 的 type
照 _probe_langs.py 既有做法：填表不腦推、實測坐實。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows console gbk 防崩

import tree_sitter
from tree_sitter_language_pack import get_language

SAMPLES = {
    "python": r'''
def f(x, items):
    if x > 0:
        return 1
    elif x < 0:
        return -1
    else:
        for i in items:
            while i:
                try:
                    pass
                except ValueError:
                    pass
                else:
                    pass
                finally:
                    pass
    with open("f") as fh:
        pass
    match x:
        case 1:
            pass
        case _:
            pass
    y = a if x else b
    z = x and a or b
    lst = [i for i in items if i]
    d = {k: v for k, v in items}
    g = (i for i in items)
    h = lambda q: q
    assert x, "msg"
    return f(x - 1, items)
''',
    "typescript": r'''
function f(x: number, items: number[]): number {
  if (x > 0) { return 1; }
  else if (x < 0) { return -1; }
  else {
    for (const i of items) {
      for (let j = 0; j < x; j++) {
        while (j) {
          do { j--; } while (j);
          try { foo(); } catch (e) { bar(); } finally { baz(); }
          switch (x) { case 1: break; case 2: break; default: break; }
        }
      }
    }
  }
  const y = x > 0 ? a : b;
  const z = x && a || b;
  const g = (q: number) => q;
  items.forEach(function (it) { return it; });
  return f(x - 1, items);
}
''',
    "tsx": r'''
function C(props: {x: number}) {
  if (props.x > 0) { return <div>{props.x > 1 ? "a" : "b"}</div>; }
  for (const i of [1, 2]) { console.log(i); }
  return <span>{props.x && "y"}</span>;
}
''',
    "edge_ts": r'''
function f(x: number): number {
  OUT: for (let i = 0; i < x; i++) {
    for (let j = 0; j < i; j++) {
      if (i % j === 0) { continue OUT; }
      break;
    }
  }
  try { a(); } catch (e) { b(); } finally { c(); }
  do { x--; } while (x > 0);
  const g = () => { if (x > 0) { return 1; } return 0; };
  return x;
}
''',
    "edge_py": r'''
def f(x):
    try:
        pass
    except ValueError:
        pass
    except KeyError:
        pass
    else:
        pass
    finally:
        pass
    def inner():
        if x:
            pass
    for i in range(x):
        continue
    return inner
''',
    "go": r'''
package main
func f(x int, items []int) int {
	if x > 0 {
		return 1
	} else if x < 0 {
		return -1
	}
	for i, v := range items {
		for j := 0; j < x; j++ {
			switch v {
			case 1:
				break
			default:
				break
			}
			select {
			case <-ch:
			}
		}
	}
	y := x > 0 && x < 10 || x == 0
	return f(x-1, items)
}
''',
    "rust": r'''
fn f(x: i32, items: Vec<i32>) -> i32 {
    if x > 0 {
        return 1;
    } else if x < 0 {
        return -1;
    }
    for v in &items {
        while *v > 0 {
            match x {
                1 => {},
                _ => {},
            }
            if let Some(y) = Some(x) {}
            loop { break; }
        }
    }
    let y = x > 0 && x < 10 || x == 0;
    f(x - 1, items)
}
''',
    "java": r'''
class C {
    int f(int x, int[] items) {
        if (x > 0) { return 1; }
        else if (x < 0) { return -1; }
        for (int v : items) {
            while (v > 0) {
                do { v--; } while (v > 0);
                try { g(); } catch (Exception e) { } finally { }
                switch (x) { case 1: break; default: break; }
            }
        }
        boolean y = x > 0 && x < 10 || x == 0;
        int z = x > 0 ? 1 : 0;
        return f(x - 1, items);
    }
}
''',
    "csharp": r'''
class C {
    int F(int x, int[] items) {
        if (x > 0) { return 1; }
        else if (x < 0) { return -1; }
        foreach (var v in items) {
            while (v > 0) {
                do { } while (v > 0);
                try { G(); } catch (System.Exception e) { } finally { }
                switch (x) { case 1: break; default: break; }
            }
        }
        bool y = x > 0 && x < 10 || x == 0;
        int z = x > 0 ? 1 : 0;
        return F(x - 1, items);
    }
}
''',
}


def walk(node, src, depth, maxd, out):
    if node.is_named:
        if depth <= maxd:
            txt = src[node.start_byte:node.end_byte].decode("utf-8", "replace")
            snippet = txt.split("\n")[0][:40]
            out.append("  " * depth + f"{node.type}  | {snippet!r}")
    if depth < maxd:
        for c in node.children:
            walk(c, src, depth + 1, maxd, out)


def main():
    langs = sys.argv[1:] or ["python", "typescript", "tsx", "go"]
    for lang in langs:
        code = SAMPLES.get(lang)
        if code is None:
            print(f"=== {lang} === (no sample)")
            continue
        print(f"\n{'=' * 60}\n=== {lang} ===\n{'=' * 60}")
        src = code.encode("utf-8")
        tlang = {"edge_ts": "typescript", "edge_py": "python"}.get(lang, lang)
        try:
            parser = tree_sitter.Parser(get_language(tlang))
        except Exception as e:  # noqa: BLE001
            print(f"  load FAIL: {e}")
            continue
        tree = parser.parse(src)
        out = []
        maxd = int(os.environ.get("PROBE_MAXD", "10"))
        walk(tree.root_node, src, 0, maxd, out)
        print("\n".join(out))


if __name__ == "__main__":
    main()
