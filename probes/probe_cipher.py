# -*- coding: utf-8 -*-
"""
用 TP.dll 当"加密预言机"：喂各种精心构造的短明文，看密文长什么样，
从而判定 DS1/DS2 用的是什么密码（分组大小、填充方式、是否用 IV/随机、是否 ECB…）。

不需要游戏存档，只借用 DLL。
"""
# --- 开发期路径引导：让 import 项目模块找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import hashlib
import io
import os
import struct
import sys
import zlib

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
TRY = os.path.dirname(os.path.dirname(HERE))
from paths import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()

sys.path.insert(0, os.path.join(TRY, 'Source', '0.2'))
import codec as C


def unwrap(blob):
    """拆开 DS1 输出的容器，返回内层字节。"""
    info = {'magic': blob[:4].hex(' ').upper(), 'len': len(blob)}
    if blob[:4] == C.MAGIC:
        declared = struct.unpack('<I', blob[4:8])[0]
        try:
            d = zlib.decompressobj()
            inner = d.decompress(blob[8:]) + d.flush()
            info['declared'] = declared
            info['inner'] = inner
            return info
        except zlib.error as e:
            info['zlib_error'] = str(e)
    return info


def main():
    br = C.Bridge(GAME, log=lambda s: None)
    tests = [
        ('空', b''),
        ('1 字节 A', b'A'),
        ('7 字节', b'A' * 7),
        ('8 字节', b'A' * 8),
        ('8 字节 00', b'\x00' * 8),
        ('9 字节', b'A' * 9),
        ('15 字节', b'A' * 15),
        ('16 字节', b'A' * 16),
        ('16 字节 两个相同块', b'A' * 8 + b'A' * 8),
        ('16 字节 两个不同块', b'A' * 8 + b'B' * 8),
        ('16 字节 00', b'\x00' * 16),
        ('24 字节 三块 A', b'A' * 24),
    ]
    results = {}
    for name, data in tests:
        out = br.encrypt(data)
        info = unwrap(out)
        inner = info.get('inner', b'')
        results[name] = inner
        print('%-20s 明文 %3d -> 文件 %5d  容器魔数 %s 声明长度 %s  内层 %3d 字节'
              % (name, len(data), info['len'], info['magic'],
                 info.get('declared'), len(inner)))
        print('                     内层 hex: %s' % inner.hex(' '))
    # 相同输入加密两次，看是否确定
    a1 = br.encrypt(b'A' * 8)
    a2 = br.encrypt(b'A' * 8)
    print('\n同一明文两次加密是否相同：%s' % (a1 == a2))
    # 长度规律
    print('\n长度规律（明文 -> 内层密文）：')
    for name, data in tests:
        print('   %3d -> %3d   (差 %d)' % (len(data), len(results[name]),
                                          len(results[name]) - len(data)))
    # ECB 特征：8 字节的 'A'*8 是否等于 'A'*16 的第一块 / 第二块
    b8 = results['8 字节']
    b16 = results['16 字节']
    if len(b8) >= 8 and len(b16) >= 16:
        for off in (0, 8, 16):
            if len(b16) >= off + 8:
                print('  "A"*8 密文 == "A"*16 的第 %d 字节起的块? %s'
                      % (off, b8[:8] == b16[off:off + 8]))
    br.close()


if __name__ == '__main__':
    main()
