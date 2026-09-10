# -*- coding: utf-8 -*-
"""
编译 32 位加解密宿主 XJCodec32.exe（用 Windows 自带的 .NET Framework C# 编译器），
然后跑一遍自检：DS1/DS2 是否可用、getid 能否拿到机器码。

用法：
    python build_host.py            # 编译 + 自检
    python build_host.py --compile  # 只编译
"""
# --- 开发期路径引导：让 import xj_* 找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import io
import os
import shutil
import subprocess
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
TRY = os.path.dirname(os.path.dirname(HERE))
from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SRC = os.path.join(HERE, 'XJCodec32.cs')

CSC_CANDIDATES = [
    r'C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe',      # 32 位
    r'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe',
    r'C:\Windows\Microsoft.NET\Framework\v3.5\csc.exe',
]

OUT_DIRS = [HERE, os.path.join(TRY, 'Exe', '0.3')]


def find_csc():
    for p in CSC_CANDIDATES:
        if os.path.exists(p):
            return p
    return None


def compile_host(csc):
    exe = os.path.join(HERE, 'XJCodec32.exe')
    cmd = [csc, '/nologo', '/platform:x86', '/optimize+', '/target:exe',
           '/out:' + exe, SRC]
    print('编译：%s' % ' '.join(cmd))
    p = subprocess.run(cmd, capture_output=True, text=True,
                       encoding='utf-8', errors='replace')
    print(p.stdout.strip() or '(无输出)')
    if p.stderr.strip():
        print('stderr: ' + p.stderr.strip())
    if p.returncode != 0 or not os.path.exists(exe):
        print('编译失败，退出码 %s' % p.returncode)
        return None
    print('编译成功：%s（%d 字节）' % (exe, os.path.getsize(exe)))
    for d in OUT_DIRS:
        if os.path.abspath(d) != os.path.abspath(HERE):
            os.makedirs(d, exist_ok=True)
            shutil.copyfile(exe, os.path.join(d, 'XJCodec32.exe'))
            print('已复制到 %s' % d)
    return exe


def run(exe, args, quiet=False):
    p = subprocess.run([exe] + args, capture_output=True, text=True,
                       encoding='utf-8', errors='replace', timeout=120)
    if not quiet:
        print('   返回码 %s' % p.returncode)
        if p.stdout.strip():
            print('   stdout: %s' % p.stdout.strip())
        if p.stderr.strip():
            print('   stderr: %s' % p.stderr.strip())
    return p


def selftest(exe):
    dll_dir = GAME
    print('\n==== 1) getid 直接取机器码 ====')
    run(exe, [dll_dir, 'getid'])

    print('\n==== 2) probe 诊断各种调用 ====')
    run(exe, [dll_dir, 'probe'])

    print('\n==== 3) 加解密往返测试 ====')
    import tempfile
    import zlib
    import struct
    src = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
    tmpdir = tempfile.mkdtemp(prefix='xj_host_')
    tmp = os.path.join(tmpdir, 'data.bin')
    shutil.copyfile(src, tmp)
    run(exe, [dll_dir, 'unlock', tmp], quiet=True)
    plain = open(tmp, 'rb').read()
    print('   解密后 %d 字节，头 8: %s' % (len(plain), plain[:8].hex(' ')))
    run(exe, [dll_dir, 'lock', tmp], quiet=True)
    back = open(tmp, 'rb').read()
    orig = open(src, 'rb').read()
    print('   重新加密后 %d 字节，与原文件一致：%s' % (len(back), back == orig))
    shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    csc = find_csc()
    if not csc:
        print('找不到 csc.exe（需要 .NET Framework 4.x，Win10/11 自带）')
        return 1
    print('使用编译器：%s' % csc)
    exe = compile_host(csc)
    if not exe:
        return 1
    if '--compile' in sys.argv:
        return 0
    selftest(exe)
    return 0


if __name__ == '__main__':
    sys.exit(main())
