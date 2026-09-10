# -*- coding: utf-8 -*-
"""追查 NoMethodError: undefined method '[]' for nil:NilClass（脚本 163 第 147 行）。

提取出来的 .rb 文件里"隔行是空行"，所以游戏里的行号 = 文件行号 / 2。
推测出问题的是：$pet["#{baby.name}"][7]  —— $pet 里没有这个宠物名字 -> nil[7]。
"""
# --- 开发期路径引导：让 import xj_* 找到 ../src ----------------------------
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
from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SCRIPTS = os.path.join(GAME, 'Try', 'scripts')

KEYS = sys.argv[1:] or ['$pet', 'def name', '@babys', '名字']


def main():
    files = sorted(f for f in os.listdir(SCRIPTS) if f.endswith('.rb')
                   and f != '_all_scripts.rb')
    print('扫描 %d 个脚本文件' % len(files))
    # 先验证"隔行空行"规律
    probe = os.path.join(SCRIPTS, '0163_P__.Sys _.........__.q_065A09.rb')
    if os.path.exists(probe):
        with open(probe, 'rb') as f:
            raw = f.read()
        print('0163 原始字节：\\n=%d  \\r=%d  长度=%d'
              % (raw.count(b'\n'), raw.count(b'\r'), len(raw)))
        txt = raw.decode('utf-8', 'replace').splitlines()
        blank = sum(1 for s in txt if not s.strip())
        print('0163 行数 %d，其中空行 %d（%.1f%%）'
              % (len(txt), blank, blank * 100.0 / max(1, len(txt))))
    print('')

    hits = {k: [] for k in KEYS}
    for fn in files:
        p = os.path.join(SCRIPTS, fn)
        try:
            with open(p, encoding='utf-8', errors='replace') as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        # 把"隔行空行"压掉，得到游戏里的真实行号
        packed = [s for s in lines if s.strip()]
        for k in KEYS:
            for i, s in enumerate(packed, 1):
                if k in s:
                    hits[k].append((fn, i, s.strip()))

    for k in KEYS:
        rows = hits[k]
        print('=' * 70)
        print('关键词 %r：%d 处（行号已去掉空行，= 游戏里的行号）' % (k, len(rows)))
        print('=' * 70)
        by = {}
        for fn, i, s in rows:
            by.setdefault(fn, []).append((i, s))
        for fn in sorted(by):
            print('--- %s ---' % fn)
            for i, s in by[fn][:30]:
                print('%6d  %s' % (i, s[:170]))
            if len(by[fn]) > 30:
                print('        … 其余 %d 行' % (len(by[fn]) - 30))
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
