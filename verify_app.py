#!/usr/bin/env python3
"""拆分布局体检：把拆分过程中踩过的坑固化为自动化检查。

检查项：
1. 模板端点有效性：扫描 templates/ 下所有 url_for(...) 的端点名，
   与 Flask 已注册端点比对，找出拆分后遗留的失效引用（BuildError 源头）。
2. 模块未定义全局名：用 symtable 做真实作用域分析，找出引用了但
   模块级未定义的全局名（NameError 源头，如漏导入 _load_auth）。
3. 路由统计：输出总路由数与各蓝图路由数，便于比对是否意外丢失。

用法：
    python3 verify_app.py           # 只做静态检查
    python3 verify_app.py --http    # 额外跑一遍页面 HTTP 回归
"""
import builtins
import glob
import os
import re
import symtable
import sys

BASE = '/root/workbench'
MODULES = ['app.py', 'shared.py', 'printer.py', 'admin.py', 'knowledge.py']


def check_templates():
    """模板中 url_for 引用的端点必须全部已注册。"""
    import app as A
    valid = {r.endpoint for r in A.app.url_map.iter_rules()}
    missing = []
    for path in sorted(glob.glob(os.path.join(BASE, 'templates', '*.html'))):
        txt = open(path, encoding='utf-8').read()
        for m in re.finditer(
                r"url_for\(\s*['\"]([A-Za-z_][A-Za-z0-9_.]*)['\"]", txt):
            ep = m.group(1)
            if ep not in valid:
                line = txt[:m.start()].count('\n') + 1
                missing.append((os.path.basename(path), line, ep))
    return missing


def check_undefined(path):
    """模块内引用了但未定义的全局名（真实作用域分析）。"""
    src = open(path, encoding='utf-8').read()
    table = symtable.symtable(src, path, 'exec')
    defined = set()
    for sym in table.get_symbols():
        if sym.is_assigned() or sym.is_imported():
            defined.add(sym.get_name())

    used = set()

    def walk(t):
        for sym in t.get_symbols():
            if sym.is_referenced() and sym.is_global():
                used.add(sym.get_name())
        for child in t.get_children():
            walk(child)

    walk(table)
    allowed = (defined | set(dir(builtins))
               | {'__file__', '__name__', '__doc__'})
    return sorted(used - allowed)


def route_summary():
    import app as A
    rules = list(A.app.url_map.iter_rules())
    groups = {}
    for r in rules:
        prefix = r.endpoint.split('.')[0] if '.' in r.endpoint else 'app'
        groups[prefix] = groups.get(prefix, 0) + 1
    return len(rules), groups


def check_http():
    """页面回归，需要服务已启动。"""
    import requests
    base = 'http://127.0.0.1:8000'
    pw = open(os.path.join(BASE, 'INITIAL_PASSWORD.txt'),
              encoding='utf-8').read().strip()
    s = requests.Session()
    s.post(base + '/login', data={'password': pw}, timeout=15)
    pages = ['/', '/work', '/study', '/todo', '/diary', '/habit', '/bugs',
             '/roadmap', '/snippets', '/compile_errors', '/perf', '/commands',
             '/books', '/crashes', '/drivers', '/protocols', '/test_matrix',
             '/error_codes', '/log_analysis', '/printers', '/analytics',
             '/checklist', '/handbook', '/report/release', '/releases',
             '/interview', '/review/weekly', '/report/weekly', '/search',
             '/recycle', '/settings', '/history', '/status', '/import']
    bad = []
    for p in pages:
        try:
            code = s.get(base + p, allow_redirects=False,
                         timeout=30).status_code
        except requests.RequestException as exc:
            bad.append((p, 'ERR:%s' % exc.__class__.__name__))
            continue
        if code != 200:
            bad.append((p, code))
    return len(pages), bad


def main():
    do_http = '--http' in sys.argv
    failed = False

    print('=== 1. 模板端点有效性 ===')
    missing = check_templates()
    if missing:
        failed = True
        for f, line, ep in missing:
            print('  FAIL %s:%d -> %s' % (f, line, ep))
    else:
        print('  OK   所有模板 url_for 端点均已注册')

    print('=== 2. 模块未定义全局名 ===')
    for name in MODULES:
        path = os.path.join(BASE, name)
        if not os.path.exists(path):
            print('  SKIP %s 不存在' % name)
            continue
        undefined = check_undefined(path)
        if undefined:
            failed = True
            print('  FAIL %s: %s' % (name, ', '.join(undefined)))
        else:
            print('  OK   %s' % name)

    print('=== 3. 路由统计 ===')
    total, groups = route_summary()
    print('  总计 %d 条' % total)
    for k in sorted(groups):
        print('    %-12s %d' % (k, groups[k]))

    if do_http:
        print('=== 4. 页面回归 ===')
        count, bad = check_http()
        if bad:
            failed = True
            for p, code in bad:
                print('  FAIL %s -> %s' % (p, code))
        else:
            print('  OK   %d 个页面全部 200' % count)

    print()
    print('结果:', 'FAILED' if failed else 'ALL PASSED')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
