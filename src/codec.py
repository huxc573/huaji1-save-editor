# -*- coding: utf-8 -*-
"""
codec —— 存档容器解析 + TP.dll 加解密（0.2，独立版）

与 0.1 的区别：**不再依赖游戏目录**。
程序把 TP.dll / Socket.dll 放在自己目录（或子目录 dll/）里，
运行时按下面的顺序查找，找到就用，找不到才提示用户手动指定。

容器格式（实测）：
    0D 0F 3E 03              魔数，即 uint32LE 0x033E0F0D
    <uint32 LE>              密文长度
    78 9C ...                zlib(密文)

加解密：TP.dll 导出 DS1(加密) / DS2(解密)，第二个参数是口令 "xjy.11"，
        这两个函数自己负责整个容器，并且是**原地改写文件**。
        TP.dll 是 32 位，64 位 Python 加载不了，所以通过 32 位 PowerShell 中转。
"""
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib

MAGIC = b'\x0D\x0F\x3E\x03'
MAGIC_U32 = 0x033E0F0D
PASSWORD = 'xjy.11'

DLL_NAMES = ('TP.dll', 'Socket.dll')
DLL_SUBDIRS = ('', 'dll', 'DLL', 'bin', '依赖DLL')
HOST_NAME = 'XJCodec32.exe'          # 0.3：自带 32 位宿主，取代 PowerShell
PS32 = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'SysWOW64',
                    'WindowsPowerShell', '0.1', 'powershell.exe')
CREATE_NO_WINDOW = 0x08000000        # 子进程不弹黑框


class CodecError(Exception):
    pass


def app_dir():
    """程序所在目录（PyInstaller 打包后取 exe 所在目录）。"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def dll_search_dirs(extra=None):
    dirs = []
    if extra:
        dirs.append(extra)
    env = os.environ.get('XJ_DLL_DIR')
    if env:
        dirs.append(env)
    base = app_dir()
    for sub in DLL_SUBDIRS:
        dirs.append(os.path.join(base, sub) if sub else base)
    dirs.append(os.getcwd())
    out = []
    for d in dirs:
        d = os.path.abspath(d)
        if d not in out and os.path.isdir(d):
            out.append(d)
    return out


def find_dll(name, extra=None):
    for d in dll_search_dirs(extra):
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def find_host(extra=None):
    """找自带的 32 位宿主 XJCodec32.exe（源码态在 src/native/）。"""
    if not getattr(sys, 'frozen', False):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'native', HOST_NAME)
        if os.path.exists(p):
            return p
    return find_dll(HOST_NAME, extra)


def dll_status(extra=None):
    """返回 {'TP.dll': 路径或 None, ...}，供界面显示。"""
    st = {n: find_dll(n, extra) for n in DLL_NAMES}
    st[HOST_NAME] = find_host(extra)
    return st


# --------------------------------------------------------------------------
# 32 位 PowerShell 桥
# --------------------------------------------------------------------------
_PS_TEMPLATE = r'''param([string]$DllPath, [string]$FilePath, [string]$Mode, [string]$Pass)
$dir = Split-Path -Parent $DllPath
[System.IO.Directory]::SetCurrentDirectory($dir)
$src = @"
using System;
using System.Runtime.InteropServices;
public class XJBridge {
  [DllImport("kernel32", EntryPoint="LoadLibraryExA", CallingConvention=CallingConvention.StdCall, CharSet=CharSet.Ansi, SetLastError=true)]
  public static extern IntPtr LoadLibraryEx(string path, IntPtr hFile, uint flags);
  [DllImport("TP.dll", EntryPoint="DS1", CallingConvention=CallingConvention.StdCall, CharSet=CharSet.Ansi)]
  public static extern int DS1(string file, string pass);
  [DllImport("TP.dll", EntryPoint="DS2", CallingConvention=CallingConvention.StdCall, CharSet=CharSet.Ansi)]
  public static extern int DS2(string file, string pass);
  [DllImport("Socket.dll", EntryPoint="GetID", CallingConvention=CallingConvention.StdCall, CharSet=CharSet.Ansi)]
  public static extern IntPtr GetID();
}
"@
Add-Type -TypeDefinition $src
if ([XJBridge]::LoadLibraryEx($DllPath, [IntPtr]::Zero, 0x8) -eq [IntPtr]::Zero) {
  Write-Error ("LoadLibraryEx failed: " + [System.Runtime.InteropServices.Marshal]::GetLastWin32Error())
  exit 2
}
# 取机器码要用 Socket.dll，必须显式加载（0.2 漏了这步导致 GetID 返回空）
$sockPath = Join-Path $dir 'Socket.dll'
if (Test-Path -LiteralPath $sockPath) {
  [void][XJBridge]::LoadLibraryEx($sockPath, [IntPtr]::Zero, 0x8)
}
if ($Mode -eq "lock") { [XJBridge]::DS1($FilePath, $Pass); exit 0 }
if ($Mode -eq "unlock") { [XJBridge]::DS2($FilePath, $Pass); exit 0 }
[System.Runtime.InteropServices.Marshal]::PtrToStringAnsi([XJBridge]::GetID())
'''


class Bridge(object):
    """调用 TP.dll 做加解密 / 取机器码。"""

    def __init__(self, dll_dir=None, log=None):
        self.dll_dir = dll_dir
        self.log = log or (lambda s: None)
        self.tp = find_dll('TP.dll', dll_dir)
        if not self.tp:
            raise CodecError(
                '找不到 TP.dll。请把游戏目录里的 TP.dll（和 Socket.dll）\n'
                '复制到本程序所在目录（或程序目录下的 dll 文件夹）后重试。\n'
                '当前查找过的目录：\n  ' + '\n  '.join(dll_search_dirs(dll_dir)))
        if not os.path.exists(PS32):
            raise CodecError('找不到 32 位 PowerShell：%s' % PS32)
        fd, self.ps1 = tempfile.mkstemp(suffix='.ps1', prefix='xj_bridge_')
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(_PS_TEMPLATE)

    def close(self):
        try:
            os.remove(self.ps1)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    # ---- 底层 ----
    def _run(self, file_path, mode):
        cmd = [PS32, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
               '-File', self.ps1, '-DllPath', self.tp, '-FilePath', file_path,
               '-Mode', mode, '-Pass', PASSWORD]
        self.log('调用 TP.dll %s ...' % mode)
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           creationflags=CREATE_NO_WINDOW)
        if p.returncode != 0:
            raise CodecError('TP.dll %s 失败（退出码 %d）：\n%s\n%s'
                             % (mode, p.returncode, p.stdout.strip(), p.stderr.strip()))
        return p.stdout.strip()

    def _tmpfile(self):
        d = tempfile.mkdtemp(prefix='xj_save_')
        return d, os.path.join(d, 'data.bin')

    def decrypt(self, blob):
        """存档文件字节 -> 明文 Marshal 数据流。"""
        d, tmp = self._tmpfile()
        try:
            with open(tmp, 'wb') as f:
                f.write(blob)
            self._run(tmp, 'unlock')
            with open(tmp, 'rb') as f:
                return f.read()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def encrypt(self, plain):
        """明文 Marshal 数据流 -> 完整存档字节（0.2 暂不写回，留给后续版本）。"""
        d, tmp = self._tmpfile()
        try:
            with open(tmp, 'wb') as f:
                f.write(plain)
            self._run(tmp, 'lock')
            with open(tmp, 'rb') as f:
                return f.read()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def machine_id(self):
        return self._run(os.path.dirname(self.tp), 'getid')


# --------------------------------------------------------------------------
# 32 位原生宿主（0.3 默认通道）
# --------------------------------------------------------------------------
class HostBridge(object):
    """
    调用随程序携带的 32 位宿主 XJCodec32.exe 完成加解密 / 取机器码。

    相比 PowerShell 方案的好处：
      * 完全静默（CREATE_NO_WINDOW），不会闪黑框
      * 启动几十毫秒（PowerShell 每次要 1~3 秒）
      * 不依赖系统里的 PowerShell
    """

    def __init__(self, dll_dir=None, log=None):
        self.log = log or (lambda s: None)
        self.exe = find_host(dll_dir)
        if not self.exe:
            raise CodecError('找不到 %s（它应该和本程序放在同一目录）' % HOST_NAME)
        self.tp = find_dll('TP.dll', dll_dir)
        if not self.tp:
            raise CodecError(
                '找不到 TP.dll。请把游戏目录里的 TP.dll（和 Socket.dll）\n'
                '复制到本程序所在目录后重试。\n当前查找过的目录：\n  '
                + '\n  '.join(dll_search_dirs(dll_dir)))
        # 宿主的第一个参数是"DLL 所在目录"（宿主和 DLL 允许分开放）
        self.dll_dir = os.path.dirname(os.path.abspath(self.tp))

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()

    def _run(self, mode, path=''):
        cmd = [self.exe, self.dll_dir, mode]
        if path:
            cmd.append(path)
        self.log('%s（%s）…' % (mode, HOST_NAME))
        p = subprocess.run(cmd, capture_output=True, text=True,
                           encoding='utf-8', errors='replace',
                           creationflags=CREATE_NO_WINDOW)
        if p.returncode != 0:
            raise CodecError('%s %s 失败（退出码 %d）：\n%s\n%s'
                             % (HOST_NAME, mode, p.returncode,
                                p.stdout.strip(), p.stderr.strip()))
        return p.stdout.strip()

    def _tmpfile(self):
        d = tempfile.mkdtemp(prefix='xj_save_')
        return d, os.path.join(d, 'data.bin')

    def decrypt(self, blob):
        d, tmp = self._tmpfile()
        try:
            with open(tmp, 'wb') as f:
                f.write(blob)
            self._run('unlock', tmp)
            with open(tmp, 'rb') as f:
                return f.read()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def encrypt(self, plain):
        d, tmp = self._tmpfile()
        try:
            with open(tmp, 'wb') as f:
                f.write(plain)
            self._run('lock', tmp)
            with open(tmp, 'rb') as f:
                return f.read()
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def machine_id(self):
        return self._run('getid')


def make_bridge(dll_dir=None, log=None):
    """优先用自带宿主；没有宿主时退回 PowerShell（同样静默）。"""
    log = log or (lambda s: None)
    try:
        return HostBridge(dll_dir, log)
    except CodecError as host_err:
        log('没有找到 %s，改用 PowerShell 通道' % HOST_NAME)
        try:
            return Bridge(dll_dir, log)
        except CodecError:
            raise host_err


# --------------------------------------------------------------------------
# 容器
# --------------------------------------------------------------------------
def peek_container(blob):
    """只看外层，不解密：返回 (是否本作存档, 魔数文本, 密文长度, zlib解出字节数)。"""
    ok = blob[:4] == MAGIC
    declared = struct.unpack('<I', blob[4:8])[0] if len(blob) >= 8 else 0
    real = None
    if ok:
        try:
            d = zlib.decompressobj()
            out = d.decompress(blob[8:]) + d.flush()
            real = len(out)
        except zlib.error:
            real = None
    return ok, MAGIC.hex(' ').upper(), declared, real


def is_encrypted_save(blob):
    return blob[:4] == MAGIC


# --------------------------------------------------------------------------
# LockNumber（数字防作弊，脚本 0007）
# --------------------------------------------------------------------------
class LockNumberError(Exception):
    pass


def lock_decode(values, key3, key1, key2):
    """按游戏 show 公式还原 6 组并校验一致性。"""
    out = []
    for i in range(len(values)):
        t = (((((((((((values[i] + key3[i]) ^ 999) - 11) ^ key2[i]) ^ key1[i]) + 858) // 3)
              ^ key2[i]) + (129323 * i)) // 2) >> key1[i]) - 1123
        out.append(t / 10000.0)
    if len(set(out)) != 1:
        raise LockNumberError('LockNumber 校验不一致：%r' % out)
    return out[0]


def lock_encode_pairs(n, key1, key2, i):
    """按脚本 0007 的构造公式算第 i 组的 (value, key3) —— 修改金钱时用。"""
    v = int(n * 10000) + 1123
    v = v << key1[i]
    v = v * 2 - (129323 * i)
    v = v ^ key2[i]
    v = v * 3 - 858
    v = v ^ key1[i]
    v = v ^ key2[i]
    v = v + 11
    v = v ^ 999
    return v - v // 2, v // 2
