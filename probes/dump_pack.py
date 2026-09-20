# -*- coding: utf-8 -*-
"""看一眼存档里 data.@pack（用户说这才是真正的物品栏）的结构。"""
# --- 开发期路径引导：让 import 项目模块找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
TRY = os.path.dirname(os.path.dirname(HERE))
from paths import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
sys.path.insert(0, os.path.join(TRY, 'Source', '0.1', 'code'))
sys.path.insert(0, os.path.join(TRY, 'Source', '0.2'))

import rmxp_marshal as M

OUT = os.path.join(HERE, 'pack_dump.txt')
PLAIN = os.path.join(TRY, 'save_plain.bin')


def vt(n, ml=90):
    if n is None:
        return 'nil'
    if isinstance(n, M.IntNode):
        return str(n.value)
    if isinstance(n, M.BignumNode):
        return str(n.value)[:30]
    if isinstance(n, M.BoolNode):
        return 'true' if n.value else 'false'
    if isinstance(n, M.NilNode):
        return 'nil'
    if isinstance(n, M.FloatNode):
        return repr(n.value)
    if isinstance(n, M.StrNode):
        s = n.str()
        return '"%s"' % (s if len(s) <= ml else s[:ml] + '…')
    if isinstance(n, M.SymbolNode):
        return ':' + n.name
    if isinstance(n, M.ArrayNode):
        return 'Array[%d]' % len(n.items)
    if isinstance(n, M.HashNode):
        return 'Hash{%d}' % len(n.pairs)
    if isinstance(n, M.ObjNode):
        return '<%s>' % n.cls
    if isinstance(n, M.UserDefNode):
        return 'userdef(%s,%d)' % (n.cls, len(n.data))
    if isinstance(n, M.LinkNode):
        return '&link%d' % n.index
    return type(n).__name__


def dump(node, lines, depth=0, maxdepth=8, seen=None):
    pad = '  ' * depth
    if depth > maxdepth:
        lines.append(pad + '…')
        return
    if isinstance(node, (M.ObjNode, M.StructNode)):
        lines.append('%s%s' % (pad, node.cls))
        for k, v in node.ivars:
            lines.append('%s  %s = %s' % (pad, k, vt(v)))
            dump(v, lines, depth + 2, maxdepth)
    elif isinstance(node, M.ArrayNode):
        for i, it in enumerate(node.items):
            lines.append('%s[%d] %s' % (pad, i, vt(it)))
            dump(it, lines, depth + 1, maxdepth)
    elif isinstance(node, M.HashNode):
        for k, v in node.pairs:
            lines.append('%s{%s} = %s' % (pad, vt(k, 40), vt(v)))
            dump(v, lines, depth + 1, maxdepth)


def main():
    entries = M.parse_stream(open(PLAIN, 'rb').read())
    data = entries[17]['node']
    lines = ['$data (System::Data) 的字段一览：']
    for k, v in data.ivars:
        lines.append('   %-20s %s' % (k, vt(v, 60)))
    lines.append('')
    for key in ('@pack', '@wallet', '@store', '@talisman', '@number', '@cipher'):
        node = data.get(key)
        if node is None:
            lines.append('== %s 不存在 ==' % key)
            continue
        lines.append('=' * 70)
        lines.append('== %s =  %s' % (key, vt(node, 60)))
        lines.append('=' * 70)
        dump(node, lines, 0, 6)
        lines.append('')
    # 也看看 data_items 里的一个样本（已知 id=87 祈福酒肆）
    items = entries[12]['node']
    for idx in (1, 87):
        if idx < len(items.items) and isinstance(items.items[idx], M.ObjNode):
            it = items.items[idx]
            lines.append('=' * 70)
            lines.append('== data_items[%d] ==' % idx)
            for k, v in it.ivars:
                lines.append('   %-20s %s' % (k, vt(v, 80)))
    with open(OUT, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('已写入', OUT, len(lines), '行')


if __name__ == '__main__':
    main()
