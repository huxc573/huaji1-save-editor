# -*- coding: utf-8 -*-
"""定位游戏报错：脚本 'Sys <召唤兽>' 的 147 行 NoMethodError: undefined method '[]' for nil。

做法：
  1) 在 _all_scripts.rb 里找 @@SCRIPT 编号 -> 段落起始行 + 段落名（pre='...' 里的可读部分）
  2) 打印该段落第 147 行附近的内容
  3) 顺便把 0163 那个 .rb 文件的行数关系算清楚（文件里为什么隔行是空的）
"""
# --- 开发期路径引导：让 import 项目模块找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import os
import re
import sys

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
from paths import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SCRIPTS = os.path.join(GAME, 'Try', 'scripts')
ALL = os.path.join(SCRIPTS, '_all_scripts.rb')


def main():
    with open(ALL, encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    print('_all_scripts.rb 共 %d 行' % len(lines))

    marks = []
    for i, s in enumerate(lines):
        m = re.match(r'#\s*@@SCRIPT\s+(\d+)\s+offset=(\S+)\s+pre=(.*)', s)
        if m:
            marks.append((int(m.group(1)), i, m.group(2), m.group(3)))
    print('找到 %d 个 @@SCRIPT 标记' % len(marks))
    print('')
    print('=== 编号 / 起始行 / offset / 段落名预览 ===')
    for n, i, off, pre in marks:
        if 155 <= n <= 175:
            print('  %-4d 行%-7d %-10s %s' % (n, i + 1, off, pre[:90]))
    print('')

    want = int(sys.argv[1]) if len(sys.argv) > 1 else 163
    idx = next((k for k, m in enumerate(marks) if m[0] == want), None)
    if idx is None:
        print('没有编号 %d' % want)
        return 1
    n, start, off, pre = marks[idx]
    end = marks[idx + 1][1] if idx + 1 < len(marks) else len(lines)
    body = lines[start + 1:end]
    print('=== @@SCRIPT %d：%s（段落共 %d 行）==='
          % (n, off, len(body) - 1))

    # 段落名：pre 里形如 '"...名字..."' 的那一段
    m = re.search(r'"([^"]+)"', pre)
    name = m.group(1) if m else '?'
    print('段落名（pre 引号里）= %r' % name)
    print('')
    target = int(sys.argv[2]) if len(sys.argv) > 2 else 147
    print('--- 第 %d 行附近（游戏里报的行号）---' % target)
    for k in range(max(0, target - 12), min(len(body), target + 8)):
        mark = '>>' if k + 1 == target else '  '
        print('%s %5d: %s' % (mark, k + 1, body[k]))
    print('')

    # 再看该段落里所有带 [ ] 下标、可能取到 nil 的行
    print('--- 段落里所有 "xxx[...]" 形式的行（找 nil 下标）---')
    for k, s in enumerate(body):
        if re.search(r'\[\s*[\w@$\.]+\s*\]', s) and 'Picture.new' not in s:
            print('  %5d: %s' % (k + 1, s.strip()[:150]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
