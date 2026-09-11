# -*- coding: utf-8 -*-
"""1.0 附加实测：把 exe 拷到"没有 Try/scripts 的目录"里跑，验证 $pet 名字表
用随程序携带的 pet_table.py 兜底（也就是确认 pet_table 真的被打进 exe 了）。"""
# --- 开发期路径引导：让 import xj_* 找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import os
import shutil
import subprocess
import sys
import tempfile

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass

from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
REL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'dist')
EXE = os.path.join(REL, '画迹1存档工具v1.3.1.exe')
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')

BAD = ('PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP', 'PYTHONEXECUTABLE',
       'VIRTUAL_ENV', 'UV_PROJECT' + '_ENVIRONMENT')


def main():
    for f in (EXE, SAVE):
        if not os.path.exists(f):
            print('缺少文件:', f)
            return 1
    dst = os.path.join(tempfile.gettempdir(), 'xj_v125_no_scripts')
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.join(dst, 'Audio', 'BGM'))
    shutil.copytree(REL, dst, dirs_exist_ok=True)
    shutil.copyfile(SAVE, os.path.join(dst, 'Audio', 'BGM', 'sy.ogg'))
    print('临时目录（故意没有 Try/scripts）:', dst)
    for name in ('selftest_result.txt', 'error.log'):
        p = os.path.join(dst, name)
        if os.path.exists(p):
            os.remove(p)
    env = dict(os.environ)
    for k in BAD:
        env.pop(k, None)
    # 关键：清掉 XJ_GAME，否则会走"现场解析游戏脚本"这条路，
    # 就测不到"内置 pet_table 兜底"了
    env.pop('XJ_GAME', None)
    env['XJ_SELFTEST'] = '1'
    exe = os.path.join(dst, os.path.basename(EXE))
    print('运行自检…')
    p = subprocess.run([exe, os.path.join(dst, 'Audio', 'BGM', 'sy.ogg')],
                       cwd=dst, env=env, timeout=300,
                       creationflags=0x08000000)
    print('退出码:', p.returncode)
    res = os.path.join(dst, 'selftest_result.txt')
    if os.path.exists(res):
        with open(res, encoding='utf-8') as fh:
            txt = fh.read()
        keep = ('$pet', '名字', '召唤兽', '结果')
        for line in txt.splitlines():
            if any(k in line for k in keep):
                print('  ', line)
        ok = '154' in txt
        print('')
        print('内置 pet_table 兜底可用：%s' % ('是 ✔' if ok else '否 ✘'))
        return 0 if ok else 1
    print('!! 没有生成 selftest_result.txt')
    return 1


if __name__ == '__main__':
    sys.exit(main())

