"""2026-06-22 主流語言一批抽符號測試（csharp/java/c/cpp/kotlin/swift/php/ruby/bash/lua）。

節點型別/name field 全部 tools/_probe_langs.py 實測坐實（無腦推）。每語言驗證
(kind, name) 集合含預期符號 + scope 歸屬；含 Ruby keyword-token 撞名回歸測試。
"""
import os
import sys
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from codesextant import symbols  # noqa: E402
from codesextant.symbols import extract_symbols_from_source  # noqa: E402


def _syms(src: str, lang: str):
    return extract_symbols_from_source(textwrap.dedent(src).encode("utf-8"), lang)


def _kinds(src: str, lang: str):
    return {(s["kind"], s["name"]) for s in _syms(src, lang)}


def test_language_for_file_new_langs():
    cases = {
        "a.cs": "csharp", "a.java": "java", "a.c": "c", "a.h": "c",
        "a.cpp": "cpp", "a.hpp": "cpp", "a.cc": "cpp", "a.cxx": "cpp",
        "a.kt": "kotlin", "a.kts": "kotlin", "a.swift": "swift",
        "a.php": "php", "a.rb": "ruby", "a.sh": "bash", "a.bash": "bash", "a.lua": "lua",
    }
    for fn, lang in cases.items():
        assert symbols.language_for_file(fn) == lang, fn
    assert symbols.language_for_file("a.cobol") is None


def test_csharp():
    k = _kinds('''
        namespace Foo {
            public enum Color { Red, Green }
            public interface IThing { void DoIt(); }
            public struct Point { public int X; }
            public record Rec(int X);
            public class Widget : IThing {
                public string Name { get; set; }
                public Widget() {}
                public void DoIt() {}
                int Compute(int a) { return a; }
            }
        }
    ''', "csharp")
    assert ("enum", "Color") in k
    assert ("interface", "IThing") in k
    assert ("struct", "Point") in k
    assert ("class", "Rec") in k
    assert ("class", "Widget") in k
    assert ("property", "Name") in k
    assert ("constructor", "Widget") in k
    assert ("method", "DoIt") in k
    assert ("method", "Compute") in k


def test_csharp_method_scope():
    syms = _syms('class Widget { public void DoIt() {} }', "csharp")
    m = next(s for s in syms if s["name"] == "DoIt")
    assert m["scope"] == "Widget"


def test_java():
    k = _kinds('''
        public interface IThing { void doIt(); }
        enum Color { RED, GREEN }
        public class Widget implements IThing {
            public Widget() {}
            public void doIt() {}
            int compute(int a) { return a; }
        }
    ''', "java")
    assert ("interface", "IThing") in k
    assert ("enum", "Color") in k
    assert ("class", "Widget") in k
    assert ("constructor", "Widget") in k
    assert ("method", "doIt") in k
    assert ("method", "compute") in k


def test_java_inner_class_scope():
    syms = _syms('''
        class Widget {
            static class Inner { void m() {} }
        }
    ''', "java")
    m = next(s for s in syms if s["name"] == "m")
    assert m["scope"] == "Widget.Inner"


def test_c():
    k = _kinds('''
        typedef struct Point { int x; int y; } Point;
        enum Color { RED, GREEN };
        union U { int i; float f; };
        static int helper(int a) { return a; }
        int main(int argc, char** argv) { return helper(argc); }
    ''', "c")
    assert ("struct", "Point") in k
    assert ("enum", "Color") in k
    assert ("struct", "U") in k          # union 併入 struct kind
    assert ("function", "helper") in k   # c_declarator 鏈取名
    assert ("function", "main") in k


def test_cpp():
    k = _kinds('''
        namespace ns {
            enum class Color { Red, Green };
            struct Point { int x; };
            class Widget { public: void doIt(); };
            void Widget::doIt() {}
            int global_fn(int a) { return a; }
        }
    ''', "cpp")
    assert ("enum", "Color") in k
    assert ("struct", "Point") in k
    assert ("class", "Widget") in k
    assert ("function", "doIt") in k       # Widget::doIt → c_declarator 取末段 identifier
    assert ("function", "global_fn") in k


def test_kotlin():
    # Kotlin 定義節點「無 name field」、走 name_rules 的 child:<type> 取名
    k = _kinds('''
        interface IThing { fun doIt() }
        enum class Color { RED, GREEN }
        data class Point(val x: Int, val y: Int)
        class Widget : IThing {
            override fun doIt() {}
            fun compute(a: Int): Int = a
        }
        fun globalFn(a: Int) = a
    ''', "kotlin")
    assert ("class", "IThing") in k    # interface / enum class / data class 全 = class_declaration
    assert ("class", "Color") in k
    assert ("class", "Point") in k
    assert ("class", "Widget") in k
    assert ("function", "doIt") in k
    assert ("function", "compute") in k
    assert ("function", "globalFn") in k
    assert not any(s["name"] == "<anon>" for s in _syms('class X { fun y() {} }', "kotlin"))


def test_kotlin_method_scope():
    syms = _syms('class Widget { fun compute(a: Int): Int = a }', "kotlin")
    m = next(s for s in syms if s["name"] == "compute")
    assert m["scope"] == "Widget"


def test_swift():
    # Swift grammar 把 enum/struct/class/actor 全 parse 成 class_declaration → 一律 class（誠實限制）
    k = _kinds('''
        protocol IThing { func doIt() }
        enum Color { case red, green }
        struct Point { var x: Int }
        class Widget: IThing {
            init() {}
            func doIt() {}
            func compute(_ a: Int) -> Int { return a }
        }
        func globalFn(_ a: Int) -> Int { return a }
    ''', "swift")
    assert ("protocol", "IThing") in k
    assert ("class", "Color") in k     # enum 被歸 class（grammar 合一限制）
    assert ("class", "Point") in k     # struct 被歸 class
    assert ("class", "Widget") in k
    assert ("constructor", "init") in k
    assert ("function", "doIt") in k
    assert ("function", "globalFn") in k


def test_php():
    k = _kinds('''
        <?php
        namespace App;
        interface IThing { public function doIt(); }
        trait T { public function shared() {} }
        enum Color { case Red; case Green; }
        class Widget implements IThing {
            public function doIt() {}
            public function compute(int $a): int { return $a; }
        }
        function global_fn($a) { return $a; }
    ''', "php")
    assert ("interface", "IThing") in k
    assert ("trait", "T") in k
    assert ("enum", "Color") in k
    assert ("class", "Widget") in k
    assert ("method", "doIt") in k
    assert ("method", "compute") in k
    assert ("function", "global_fn") in k


def test_ruby_no_anon_keyword_token():
    # Ruby `module`/`class` keyword token type 與定義節點 type 撞名 → 只收 is_named（無 <anon>）
    syms = _syms('''
        module MyMod
          class Widget
            def initialize; end
            def compute(a); a; end
            def self.helper; 1; end
          end
          def self.mod_fn; 2; end
        end
    ''', "ruby")
    k = {(s["kind"], s["name"]) for s in syms}
    assert ("module", "MyMod") in k
    assert ("class", "Widget") in k
    assert ("method", "initialize") in k
    assert ("method", "compute") in k
    assert ("method", "helper") in k      # def self.helper → singleton_method
    assert ("method", "mod_fn") in k
    assert not any(s["name"] == "<anon>" for s in syms), "keyword token 不得被誤收成 <anon>"
    widget = next(s for s in syms if s["name"] == "Widget")
    assert widget["scope"] == "MyMod"


def test_bash():
    k = _kinds('''
        #!/bin/bash
        MY_VAR=1
        function explicit_fn() { echo hi; }
        posix_fn() { echo bye; }
    ''', "bash")
    assert ("function", "explicit_fn") in k
    assert ("function", "posix_fn") in k    # 兩種 bash 函數語法皆 function_definition


def test_lua():
    k = _kinds('''
        local M = {}
        function global_fn(a, b) return a + b end
        local function local_fn(x) return x end
        function M.method(self, y) return y end
        return M
    ''', "lua")
    assert ("function", "global_fn") in k
    assert ("function", "local_fn") in k
    assert ("function", "M.method") in k    # dotted name 保留
