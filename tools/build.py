# -*- coding: utf-8 -*-
"""
打包脚本（构建 + 发行）

步骤：
  1. 用系统自带 C# 编译器生成 32 位宿主 XJCodec32.exe（源码 src/XJCodec32.cs）
  2. 准备发行目录 dist/：
       画迹1存档工具v1.0.exe + XJCodec32.exe + TP.dll + Socket.dll + 使用说明.txt
     （TP.dll / Socket.dll 是**游戏自带**文件，从游戏目录复制，仓库里不放它们）
  3. PyInstaller 打包单文件 exe（带 tcl 库，原因见 docs/开发指南.md）

用法（在仓库根目录或任意目录均可）：
    python tools/build.py              # 全部
    python tools/build.py --nopack     # 只准备 dist/（不打包）
    python tools/build.py --hostonly   # 只编译 32 位宿主

游戏目录：优先环境变量 XJ_GAME，否则从当前目录/本文件向上找 Game.exe。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))          # tools/
ROOT = os.path.dirname(HERE)                               # 仓库根目录
SRC = os.path.join(ROOT, 'src')
sys.path.insert(0, SRC)

from xj_env import game_dir as _game_dir                   # noqa: E402

APP_VERSION = '1.1'
EXE_NAME = '画迹1存档工具v' + APP_VERSION
EXE_DIR = os.path.join(ROOT, 'dist')
PY = sys.executable

CSC_CANDIDATES = [
    r'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe',
    r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe',
]


def log(s):
    print(s)


def build_host():
    """用 csc.exe 编译 32 位宿主（TP.dll / Socket.dll 是 32 位库，64 位进程加载不了）。"""
    csc = next((p for p in CSC_CANDIDATES if os.path.exists(p)), None)
    if not csc:
        raise SystemExit('找不到 csc.exe（需要 .NET Framework 4.x）')
    exe = os.path.join(SRC, 'XJCodec32.exe')
    cmd = [csc, '/nologo', '/platform:x86', '/optimize+', '/target:exe',
           '/out:' + exe, os.path.join(SRC, 'XJCodec32.cs')]
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if p.returncode != 0 or not os.path.exists(exe):
        log(p.stdout)
        log(p.stderr)
        raise SystemExit('编译 XJCodec32.exe 失败')
    log('已编译 32 位宿主：%s（%d 字节）' % (exe, os.path.getsize(exe)))
    return exe


def prepare(host_exe):
    """准备发行目录：宿主 + 说明书 + 游戏自带的两个 dll。"""
    game = _game_dir()
    log('游戏目录：%s' % game)
    os.makedirs(EXE_DIR, exist_ok=True)
    for src, name in ((host_exe, 'XJCodec32.exe'),
                      (os.path.join(game, 'TP.dll'), 'TP.dll'),
                      (os.path.join(game, 'Socket.dll'), 'Socket.dll'),
                      (os.path.join(ROOT, '使用说明.txt'), '使用说明.txt')):
        if not os.path.exists(src):
            log('  ! 缺少 %s，跳过' % src)
            continue
        shutil.copyfile(src, os.path.join(EXE_DIR, name))
        log('已放入发行目录：%s' % name)


def tcl_data_args():
    """tcl/tk 的脚本库不会被 PyInstaller 自动收集，必须显式 --add-data 带上。"""
    root = os.path.join(sys.base_prefix, 'tcl')
    args = []
    if not os.path.isdir(root):
        return args
    for sub in ('tcl8.6', 'tk8.6', 'tcl8'):
        p = os.path.join(root, sub)
        if os.path.isdir(p):
            args += ['--add-data', '%s;%s' % (p, 'tcl/' + sub)]
    log('随包携带 Tcl/Tk 脚本库：tcl8.6 / tk8.6 / tcl8')
    return args


def build_exe():
    cmd = ([PY, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile',
            '--windowed', '--name', EXE_NAME,
            '--distpath', EXE_DIR,
            '--workpath', os.path.join(ROOT, 'build'),
            '--specpath', ROOT,
            '--paths', SRC]
           + tcl_data_args()
           + [os.path.join(SRC, 'xj_viewer.py')])
    log('打包中…')
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    if p.returncode != 0:
        log(p.stdout[-3000:])
        log(p.stderr[-3000:])
        raise SystemExit('PyInstaller 打包失败')
    log('打包完成：%s' % os.path.join(EXE_DIR, EXE_NAME + '.exe'))


def main():
    host = build_host()
    if '--hostonly' in sys.argv:
        log('仅编译宿主完成')
        return 0
    prepare(host)
    if '--nopack' in sys.argv:
        log('仅准备完成（未打包）')
        return 0
    build_exe()
    log('')
    log('发行目录 %s 内容：' % EXE_DIR)
    for n in sorted(os.listdir(EXE_DIR)):
        p = os.path.join(EXE_DIR, n)
        if os.path.isfile(p):
            log('   %-36s %.2f MB' % (n, os.path.getsize(p) / 1048576.0))
    return 0


if __name__ == '__main__':
    sys.exit(main())
