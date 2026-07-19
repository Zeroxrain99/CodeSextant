"""probe 多語言 tree-sitter 節點型別 — 為 LANGUAGE_SPECS 加語言坐實節點型別。

用法：C:/Python311/python.exe tools/_probe_langs.py [lang ...]
不帶參數 = 全部目標語言。對每語言 parse 一段涵蓋各種定義的樣本，印出
「定義類」節點型別 + 是否有 name field（child_by_field_name('name')）。
照 symbols.py 既有 Go/Rust 的做法，加語言只填表、不腦推。
"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")  # Windows console gbk 防崩

import tree_sitter
from tree_sitter_language_pack import get_language

SAMPLES = {
    "csharp": r'''
namespace Foo.Bar {
    public delegate void Handler(int x);
    public enum Color { Red, Green }
    public interface IThing { void DoIt(); }
    public struct Point { public int X; }
    public record Rec(int X, int Y);
    public class Widget : IThing {
        private int _field = 0;
        public string Name { get; set; }
        public Widget() { }
        public void DoIt() { }
        public int Compute(int a) { return a + _field; }
        static int Helper() { return 1; }
    }
}
''',
    "java": r'''
package com.example;
public interface IThing { void doIt(); }
enum Color { RED, GREEN }
public class Widget implements IThing {
    private int field = 0;
    public Widget() { }
    public void doIt() { }
    public int compute(int a) { return a + field; }
    static class Inner { void m() {} }
}
''',
    "c": r'''
#include <stdio.h>
#define MAX 10
typedef struct Point { int x; int y; } Point;
enum Color { RED, GREEN };
union U { int i; float f; };
int global_var = 0;
static int helper(int a) { return a; }
int main(int argc, char** argv) { return helper(argc); }
''',
    "cpp": r'''
namespace ns {
    template<typename T> T add(T a, T b) { return a + b; }
    enum class Color { Red, Green };
    struct Point { int x; int y; };
    class Widget {
    public:
        Widget();
        void doIt();
        int compute(int a);
    private:
        int field_;
    };
    void Widget::doIt() {}
    int global_fn(int a) { return a; }
}
''',
    "lua": r'''
local M = {}
function global_fn(a, b) return a + b end
local function local_fn(x) return x end
function M.method(self, y) return y end
M.field = 42
return M
''',
    "ruby": r'''
module MyMod
  class Widget
    def initialize
      @field = 0
    end
    def compute(a)
      a + @field
    end
    def self.helper
      1
    end
  end
  def self.mod_fn
    2
  end
end
''',
    "php": r'''
<?php
namespace App;
interface IThing { public function doIt(); }
trait T { public function shared() {} }
enum Color { case Red; case Green; }
class Widget implements IThing {
    private int $field = 0;
    public function __construct() {}
    public function doIt() {}
    public function compute(int $a): int { return $a + $this->field; }
}
function global_fn($a) { return $a; }
''',
    "bash": r'''
#!/bin/bash
MY_VAR=1
function explicit_fn() { echo hi; }
posix_fn() { echo bye; }
''',
    "kotlin": r'''
package com.example
interface IThing { fun doIt() }
enum class Color { RED, GREEN }
data class Point(val x: Int, val y: Int)
class Widget : IThing {
    private val field = 0
    override fun doIt() {}
    fun compute(a: Int): Int = a + field
    companion object { fun helper() = 1 }
}
fun globalFn(a: Int) = a
''',
    "swift": r'''
import Foundation
protocol IThing { func doIt() }
enum Color { case red, green }
struct Point { var x: Int; var y: Int }
class Widget: IThing {
    private var field = 0
    init() {}
    func doIt() {}
    func compute(_ a: Int) -> Int { return a + field }
    static func helper() -> Int { return 1 }
}
func globalFn(_ a: Int) -> Int { return a }
''',
    "go": r'''
package main
type Thing interface { DoIt() }
type Point struct { X int }
const C = 1
var V = 2
func helper(a int) int { return a }
func (p Point) Method() int { return p.X }
''',
}


def walk(node, src, depth, maxd, out):
    if node.is_named:
        nfield = node.child_by_field_name("name")
        nm = ""
        if nfield is not None:
            nm = src[nfield.start_byte:nfield.end_byte].decode("utf-8", "replace")
        # 只印有意義的容器/定義層（避免淹沒在 expression 細節）
        if depth <= maxd:
            mark = f"  name='{nm}'" if nfield is not None else "  (no name field)"
            out.append("  " * depth + f"{node.type}{mark}")
    if depth < maxd:
        for c in node.children:
            walk(c, src, depth + 1, maxd, out)


def main():
    langs = sys.argv[1:] or list(SAMPLES.keys())
    for lang in langs:
        code = SAMPLES.get(lang)
        if code is None:
            print(f"=== {lang} === (no sample)")
            continue
        print(f"\n{'='*60}\n=== {lang} ===\n{'='*60}")
        src = code.encode("utf-8")
        try:
            parser = tree_sitter.Parser(get_language(lang))
        except Exception as e:
            print(f"  load FAIL: {e}")
            continue
        tree = parser.parse(src)
        out = []
        maxd = int(os.environ.get("PROBE_MAXD", "3"))
        walk(tree.root_node, src, 0, maxd, out)
        print("\n".join(out))


if __name__ == "__main__":
    main()
