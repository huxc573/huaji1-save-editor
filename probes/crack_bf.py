# -*- coding: utf-8 -*-
"""
暴力验证 DS1 是不是"标准分组密码 + 某种前缀/IV"。

两套已知明文-密文对：
  A) 预言机：DS1(b'A'*8) 的内层块1 = 14 e6 58 7e 48 eb 8d 1f
     已知密文总长 16 = ceil((8+2)/8)*8，所以猜测明文 = [2 字节长度/标记] + A*6，或 A*8
  B) 真存档：明文 save_plain.bin 头 8 字节 = 04 08 5B 06 5B 07 22 1B
     对应密文（zlib 解开 sy.ogg）= 3D 84 1F FE A5 77 A2 8B
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

try:
    from Crypto.Cipher import DES, DES3, Blowfish, CAST, ARC2, AES
except Exception as e:
    print('pycryptodome 不可用：', e)
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
TRY = os.path.dirname(os.path.dirname(HERE))
from paths import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
PLAIN = os.path.join(TRY, 'save_plain.bin')

MAGIC = b'\x0D\x0F\x3E\x03'


def keys_for(algo):
    pw = b'xjy.11'
    out = []
    cands = [pw,
             pw + b'\x00\x00', pw + b'\x00\x00\x00', pw + b'\x00' * 10,
             pw * 2, pw * 3, pw + b'xjy.11xjy.',
             b'\x00\x00' + pw, b'xx' + pw, b'!!' + pw,
             pw.upper(), pw[::-1],
             hashlib.md5(pw).digest(), hashlib.md5(pw).hexdigest()[:8].encode(),
             hashlib.md5(pw).hexdigest().upper()[:8].encode(),
             hashlib.sha1(pw).digest()[:8],
             hashlib.md5(pw).digest()[:8], hashlib.md5(pw).digest()[8:],
             b'xjy.11\x00\x00xjy.11\x00\x00',
             b'xjy.11' + b'\x00' * 6 + b'xjy.11' + b'\x00' * 2,
             ]
    if algo is DES:
        return [k for k in cands if len(k) == 8]
    if algo is DES3:
        return [k for k in cands if len(k) in (16, 24)]
    if algo is Blowfish:
        return [k for k in cands if 4 <= len(k) <= 56]
    if algo is CAST:
        return [k for k in cands if len(k) in (5, 8, 16)]
    if algo is ARC2:
        return [k for k in cands if 1 <= len(k) <= 128]
    if algo is AES:
        return [k for k in cands if len(k) in (16, 24, 32)]
    return []


def modes_for(algo):
    ms = [('ECB', None)]
    for ivlen in (8, 16):
        ms.append(('CBC/0', b'\x00' * ivlen))
        ms.append(('CBC/magic', (MAGIC + b'\x00' * 16)[:ivlen]))
        ms.append(('CBC/pw', (b'xjy.11' * 4)[:ivlen]))
        ms.append(('CFB/0', b'\x00' * ivlen))
        ms.append(('OFB/0', b'\x00' * ivlen))
    return ms


def block_len(algo):
    try:
        return algo.block_size
    except Exception:
        return 8


def main():
    blob = open(SAVE, 'rb').read()
    d = zlib.decompressobj()
    C = d.decompress(blob[8:]) + d.flush()
    P = open(PLAIN, 'rb').read()
    print('密文 %d 字节，明文 %d 字节' % (len(C), len(P)))
    print('密文头 8:', C[:8].hex(' '))
    print('明文头 8:', P[:8].hex(' '))

    # 目标列表：(说明, 期望的 8 字节密文, [候选明文块...])
    targets = [
        ('存档头', C[:8], [P[:8]]),
        ('预言机 A*8', bytes.fromhex('14e6587e48eb8d1f'),
         [b'A' * 8, b'\x08\x00' + b'A' * 6, b'\x00\x08' + b'A' * 6,
          b'\x10\x00' + b'A' * 6]),
        ('预言机 00*8', bytes.fromhex('c7e3aeca3e911eef'),
         [b'\x00' * 8, b'\x08\x00' + b'\x00' * 6, b'\x00\x08' + b'\x00' * 6]),
    ]

    algos = []
    for a in (DES, DES3, Blowfish, CAST, ARC2, AES):
        try:
            algos.append((a.__name__.split('.')[-1], a))
        except Exception:
            pass

    found = 0
    for tname, want, plist in targets:
        for pblock in plist:
            for aname, algo in algos:
                bl = block_len(algo)
                if len(pblock) != bl:
                    continue
                variants = [('ECB', None, algo.MODE_ECB)]
                ivs = [b'\x00' * bl, MAGIC + b'\x00' * bl, (b'xjy.11' * 4)[:bl],
                       (b'xjy.11' + b'\x00' * bl)[:bl]]
                for iv in ivs:
                    for mname in ('CBC', 'CFB', 'OFB'):
                        mode = getattr(algo, 'MODE_' + mname, None)
                        if mode is not None:
                            variants.append((mname, iv, mode))
                for key in keys_for(algo):
                    for mname, iv, mode in variants:
                        try:
                            c = algo.new(key, mode, iv=iv) if iv is not None \
                                else algo.new(key, mode)
                            out = c.encrypt(pblock)
                        except Exception:
                            continue
                        if out[:bl] == want:
                            print('\n*** 命中 *** %s | %s | key=%r | 模式=%s iv=%r'
                                  % (tname, aname, key, mname, iv))
                            return 0
    print('\n共尝试完毕，未命中标准算法组合（%d 个算法族）' % len(algos))
    return 1


if __name__ == '__main__':
    sys.exit(main())
