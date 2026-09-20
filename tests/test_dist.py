"""1.0 独立性实测：把发行目录整体拷到临时目录，切换工作目录后运行 exe 自检。"""
# --- 开发期路径引导：让 import 项目模块找到 ../src ----------------------------
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

from paths import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
REL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'dist')
EXE = os.path.join(REL, '画迹1存档工具.exe')          # 本地产物名不带版本号（见 tools/build.py）
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')

# PyInstaller + uv 的 Python 在 VSCode 里会因 PYTHONHOME/PYTHONPATH 出错，必须清掉
BAD = ('PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP', 'PYTHONEXECUTABLE',
       'VIRTUAL_ENV', 'UV_PROJECT' + '_ENVIRONMENT')


def main():
    for f in (EXE, SAVE):
        if not os.path.exists(f):
            print('缺少文件:', f)
            return 1
    dst = os.path.join(tempfile.gettempdir(), 'xj_v124_dist_test')
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(REL, dst)
    print('临时目录:', dst)
    print('内容:', sorted(os.listdir(dst)))
    for name in ('selftest_result.txt', 'error.log'):
        p = os.path.join(dst, name)
        if os.path.exists(p):
            os.remove(p)
    env = dict(os.environ)
    for k in BAD:
        env.pop(k, None)
    env['XJ_SELFTEST'] = '1'
    exe = os.path.join(dst, os.path.basename(EXE))
    print('运行自检…')
    p = subprocess.run([exe, SAVE], cwd=dst, env=env, timeout=300,
                       creationflags=0x08000000)
    print('退出码:', p.returncode)
    res = os.path.join(dst, 'selftest_result.txt')
    err = os.path.join(dst, 'error.log')
    if os.path.exists(res):
        with open(res, encoding='utf-8') as fh:
            print('---- selftest_result.txt ----')
            print(fh.read())
    else:
        print('!! 没有生成 selftest_result.txt')
    if os.path.exists(err):
        with open(err, encoding='utf-8') as fh:
            print('---- error.log ----')
            print(fh.read())
    return 0


if __name__ == '__main__':
    sys.exit(main())


