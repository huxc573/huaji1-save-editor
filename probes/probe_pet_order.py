# -*- coding: utf-8 -*-
"""探查游戏脚本里召唤兽（宠物）的排列顺序 / 放生逻辑 / 名字修改。

用途：0.7 —— 让存档工具的召唤兽列表与游戏界面顺序一致、隐藏已放生的召唤兽。
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

HERE = os.path.dirname(os.path.abspath(__file__))
from paths import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SCRIPTS = os.path.join(GAME, 'Try', 'scripts')

KEYWORDS = sys.argv[1:] or ['放生', '@babys', 'Window_Baby', '宠物', '召唤兽']


def main():
    if not os.path.isdir(SCRIPTS):
        print('找不到脚本目录:', SCRIPTS)
        return
    hits = {k: [] for k in KEYWORDS}
    files = sorted(f for f in os.listdir(SCRIPTS) if f.endswith('.rb'))
    for fn in files:
        p = os.path.join(SCRIPTS, fn)
        try:
            with open(p, encoding='utf-8', errors='replace') as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            for k in KEYWORDS:
                if k in line:
                    hits[k].append((fn, i, line.strip()))
    for k in KEYWORDS:
        rows = hits[k]
        print('=' * 70)
        print('关键词 %r 命中 %d 处' % (k, len(rows)))
        print('=' * 70)
        # 按文件聚合，避免刷屏
        by_file = {}
        for fn, i, line in rows:
            by_file.setdefault(fn, []).append((i, line))
        for fn in sorted(by_file):
            print('--- %s (%d 行) ---' % (fn, len(by_file[fn])))
            for i, line in by_file[fn][:25]:
                if len(line) > 160:
                    line = line[:160] + ' …'
                print('%6d  %s' % (i, line))
            if len(by_file[fn]) > 25:
                print('        … 其余 %d 行省略' % (len(by_file[fn]) - 25))
        print()


if __name__ == '__main__':
    main()
