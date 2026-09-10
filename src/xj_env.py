# -*- coding: utf-8 -*-
"""
xj_env —— 开发期辅助：定位游戏目录 & 引导 sys.path

这个仓库（源码）和游戏本体是**分开**的：
    <画迹目录>/
    ├─ huaji1-save-editor/          ← 本仓库
    └─ 【画迹1：落日情缘】[…] /      ← 游戏本体（含 Game.exe / Data/ / Audio/BGM/sy.ogg）

所以工具/测试脚本不能再靠"往上数几层"来猜游戏目录，改成：

  1) 环境变量 ``XJ_GAME``（最优先，CI 或游戏装在别处时用）
  2) 从这些起点**逐级向上**找含 ``Game.exe`` 的目录：
     传入的 start/save → 当前工作目录 → 本文件所在目录
  3) 找不到就抛错并提示设置 ``XJ_GAME``

另外 ``bootstrap()`` 把 ``src/`` 加进 ``sys.path``，让 tools/tests/probes
里 ``import xj_model`` 之类能正常工作。

用法（tools/ tests/ probes/ 里的脚本）：

    import os, sys
    HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))
    from xj_env import game_dir as _game_dir
    GAME = _game_dir()

应用本体（``src/xj_viewer.py``）**不需要**这些东西：它在运行时完全靠
"存档路径 / 程序目录向上找"来定位 ``Data/`` 与 ``Try/scripts``。
"""
import os
import sys


def src_dir():
    """本文件所在目录（= 仓库的 src/）。"""
    return os.path.dirname(os.path.abspath(__file__))


def repo_root():
    """仓库根目录。"""
    return os.path.dirname(src_dir())


def bootstrap():
    """把 src/ 放到 sys.path 最前面（在 import xj_* 之前调用）。"""
    s = src_dir()
    if s in sys.path:
        sys.path.remove(s)
    sys.path.insert(0, s)
    return s


def looks_like_game(d):
    """一个目录像不像游戏根目录（有 Game.exe）。"""
    return bool(d) and os.path.isfile(os.path.join(d, 'Game.exe'))


def game_dir(start=None, save=None, levels=8):
    """
    找游戏根目录。

    start : 从哪个目录开始往上找（默认：cwd、本文件目录）
    save  : 存档路径；会从它所在目录开始找
    """
    env = os.environ.get('XJ_GAME')
    if env:
        env = os.path.abspath(env)
        if looks_like_game(env):
            return env
        raise RuntimeError('XJ_GAME=%s 下面没有 Game.exe' % env)
    starts = []
    if start:
        starts.append(start)
    if save:
        starts.append(os.path.dirname(os.path.abspath(save)))
    starts.append(os.getcwd())
    starts.append(src_dir())
    seen = set()
    for st in starts:
        cur = os.path.abspath(st)
        for _ in range(levels):
            if cur in seen:
                break
            seen.add(cur)
            if looks_like_game(cur):
                return cur
            nxt = os.path.dirname(cur)
            if nxt == cur:
                break
            cur = nxt
    raise RuntimeError(
        '找不到游戏目录（含 Game.exe）。\n'
        '  · 请在游戏目录下运行，或\n'
        '  · 设置环境变量 XJ_GAME=<游戏目录>\n'
        '    例如 PowerShell: $env:XJ_GAME="D:\\Games\\画迹1"')


def save_path(game=None):
    """本作存档的默认位置（Audio/BGM/sy.ogg，脚本 0030 里写死的）。"""
    g = game or game_dir()
    return os.path.join(g, 'Audio', 'BGM', 'sy.ogg')


def dll_dir(game=None):
    """游戏根目录（TP.dll / Socket.dll 就在那里）。"""
    return game or game_dir()


if __name__ == '__main__':
    print('src_dir   =', src_dir())
    print('repo_root =', repo_root())
    try:
        g = game_dir()
        print('game_dir  =', g)
        print('save      =', save_path(g))
        print('TP.dll    =', os.path.join(g, 'TP.dll'),
              os.path.exists(os.path.join(g, 'TP.dll')))
    except RuntimeError as e:
        print(e)
