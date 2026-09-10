# -*- coding: utf-8 -*-
"""打印指定脚本段落（去掉隔行空行，行号 = 游戏里的行号）。用法：
    python probe_show_script.py 0045 1 45
"""
# --- 开发期路径引导：让 import xj_* 找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import os
import sys

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SCRIPTS = os.path.join(GAME, 'Try', 'scripts')


def main():
    pref = sys.argv[1] if len(sys.argv) > 1 else '0045'
    lo = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    hi = int(sys.argv[3]) if len(sys.argv) > 3 else 45
    fn = next((f for f in sorted(os.listdir(SCRIPTS)) if f.startswith(pref)), None)
    if not fn:
        print('找不到以 %r 开头的脚本' % pref)
        return 1
    with open(os.path.join(SCRIPTS, fn), encoding='utf-8', errors='replace') as f:
        raw = f.read().splitlines()
    packed = [s for s in raw if s.strip()]
    print('=== %s（原始 %d 行 -> 去空行 %d 行）===' % (fn, len(raw), len(packed)))
    for i in range(max(0, lo - 1), min(len(packed), hi)):
        print('%5d  %s' % (i + 1, packed[i][:170]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
