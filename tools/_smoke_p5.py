"""P5 冒煙：印 5 語言關鍵案例的實際 cognitive 值，人工核對後再寫進黃金案例測試。"""
import os
import sys

sys.stdout.reconfigure(encoding="utf-8")
CS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CS not in sys.path:
    sys.path.insert(0, CS)
import tree_sitter

from codesextant import complexity, symbols

_FUNC_TYPES = {"function_definition", "function_declaration", "method_definition",
               "method_declaration", "function_item", "method", "singleton_method"}


def _name(fn, sb):
    nn = fn.child_by_field_name("name")
    if nn is not None:
        return sb[nn.start_byte:nn.end_byte].decode()
    decl = fn.child_by_field_name("declarator")
    while decl is not None:
        if decl.type == "identifier":
            return sb[decl.start_byte:decl.end_byte].decode()
        decl = decl.child_by_field_name("declarator")
    for c in fn.children:
        if c.type == "simple_identifier":
            return sb[c.start_byte:c.end_byte].decode()
    return None


def cc(src, lang):
    sb = src.encode("utf-8")
    parser = tree_sitter.Parser(symbols._ts_language(lang))
    tree = parser.parse(sb)
    found = []

    def rec(n):
        if n.type in _FUNC_TYPES:
            found.append(n)
            return
        for c in n.children:
            rec(c)
    rec(tree.root_node)
    if not found:
        return "NO-FUNC"
    fn = found[0]
    body = complexity.function_body(fn, lang)
    return complexity.cognitive_complexity(body, lang, _name(fn, sb), sb)


CASES = {
    "c": [
        ("sumOfPrimes goto=7", "int s(int max){int t=0;for(int i=2;i<=max;i++){for(int j=2;j<i;j++){if(i%j==0){goto next;}}t+=i;next:;}return t;}", 7),
        ("trivial=0", "int f(int x){int y=x+1;return y;}", 0),
        ("if/elseif/else=3", "int f(int x){if(x>0)return 1;else if(x<0)return -1;else return 0;}", 3),
        ("nested if=3", "int f(int a,int b){if(a){if(b){return 1;}}return 0;}", 3),
        ("switch=1", "int f(int x){switch(x){case 1:return 1;default:return 0;}}", 1),
        ("while+do=2", "int f(int x){while(x>0){x--;}do{x++;}while(x<0);return x;}", 2),
        ("boolean a&&b||c=3", "int f(int a,int b,int c){if(a&&b||c){return 1;}return 0;}", 3),
        ("ternary=1", "int f(int x){return x>0?1:0;}", 1),
        ("recursion fib=3", "int fib(int n){if(n<2){return n;}return fib(n-1)+fib(n-2);}", 3),
    ],
    "cpp": [
        ("sumOfPrimes goto=7", "int s(int max){int t=0;for(int i=2;i<=max;i++){for(int j=2;j<i;j++){if(i%j==0){goto next;}}t+=i;next:;}return t;}", 7),
        ("try/catch=1", "int f(){try{g();}catch(std::exception&e){h();}return 0;}", 1),
        ("range-for=1", "int f(std::vector<int>v){int t=0;for(auto&x:v){t+=x;}return t;}", 1),
        ("lambda nest", "int f(int x){auto g=[](int q){if(q>0){return q;}return 0;};return g(x);}", 2),
    ],
    "ruby": [
        ("for/for/if=6", "def s(max)\n  t=0\n  for i in 2..max\n    for j in 2...i\n      if i%j==0\n        t+=1\n      end\n    end\n  end\n  t\nend\n", 6),
        ("trivial=0", "def f(x)\n  y=x+1\n  y\nend\n", 0),
        ("if/elsif/else=3", "def f(x)\n  if x>0\n    1\n  elsif x<0\n    2\n  else\n    3\n  end\nend\n", 3),
        ("case/when=1", "def f(x)\n  case x\n  when 1 then 1\n  when 2 then 2\n  else 0\n  end\nend\n", 1),
        ("while+until=2", "def f(x)\n  while x>0\n    x-=1\n  end\n  until x<0\n    x-=1\n  end\nend\n", 2),
        ("unless=1", "def f(x)\n  unless x>0\n    a\n  end\nend\n", 1),
        ("if_modifier=1", "def f(x)\n  a=1 if x>0\nend\n", 1),
        ("rescue=1", "def f(x)\n  begin\n    risky\n  rescue StandardError=>e\n    handle\n  ensure\n    cleanup\n  end\nend\n", 1),
        ("boolean a&&b||c=2run+if=3", "def f(a,b,c)\n  if a && b || c\n    1\n  end\nend\n", 3),
        ("recursion=1", "def f(n)\n  f(n-1)\nend\n", 1),
        ("no-false-recursion obj.f=0", "def f(o)\n  o.f\nend\n", 0),
        ("each block nest", "def f(xs)\n  xs.each do |i|\n    if i>0\n      i\n    end\n  end\nend\n", 2),
    ],
    "kotlin": [
        ("sumOfPrimes labeled=7", "fun s(max:Int):Int{var t=0\nouter@ for(i in 2..max){for(j in 2 until i){if(i%j==0){continue@outer}}\nt+=i}\nreturn t}", 7),
        ("trivial=0", "fun f(x:Int):Int{val y=x+1\nreturn y}", 0),
        ("when=1", "fun f(x:Int){when(x){1->println(1)\nelse->println(0)}}", 1),
        ("if/elseif/else field=3", "fun f(x:Int):Int{if(x>0)return 1 else if(x<0)return -1 else return 0}", 3),
        ("while+dowhile=2", "fun f(x:Int){var y=x\nwhile(y>0){y--}\ndo{y++}while(y<0)}", 2),
        ("try/catch=1", "fun f(){try{risky()}catch(e:Exception){handle()}finally{cleanup()}}", 1),
        ("boolean a&&b||c=2", "fun f(a:Boolean,b:Boolean,c:Boolean){val y=a&&b||c}", 2),
        ("recursion=1", "fun f(n:Int):Int{return f(n-1)}", 1),
        ("nested if field=3", "fun f(a:Boolean,b:Boolean){if(a){if(b){println(1)}}}", 3),
    ],
    "swift": [
        ("sumOfPrimes labeled=7", "func s(_ max:Int)->Int{var t=0\nouter: for i in 2...max{for j in 2..<i{if i%j==0{continue outer}}\nt+=i}\nreturn t}", 7),
        ("trivial=0", "func f(x:Int)->Int{let y=x+1\nreturn y}", 0),
        ("switch=1", "func f(x:Int){switch x{case 1:print(1)\ndefault:print(0)}}", 1),
        ("guard=1", "func f(x:Int)->Int{guard x>0 else{return 0}\nreturn x}", 1),
        ("if/elseif/else swift=3", "func f(x:Int)->Int{if x>0{return 1}else if x<0{return -1}else{return 0}}", 3),
        ("while+repeat=2", "func f(x:Int){var y=x\nwhile y>0{y-=1}\nrepeat{y+=1}while y<0}", 2),
        ("do/catch=1", "func f(){do{try risky()}catch{handle()}}", 1),
        ("ternary=1", "func f(x:Int)->Int{return x>0 ?1:0}", 1),
        ("recursion=1", "func f(n:Int)->Int{return f(n-1)}", 1),
        ("nested if swift=3", "func f(a:Bool,b:Bool){if a{if b{print(1)}}}", 3),
    ],
}


def main():
    for lang, cases in CASES.items():
        print(f"\n{'='*54}\n{lang}\n{'='*54}")
        for label, src, expect in cases:
            got = cc(src, lang)
            mark = "OK " if got == expect else "!! "
            print(f"  {mark}{label:<32} expect={expect} got={got}")


if __name__ == "__main__":
    main()
