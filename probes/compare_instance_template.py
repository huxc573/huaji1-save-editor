# -*- coding: utf-8 -*-
"""对比 @pack 里的物品实例与它对应的 data_items 模板，逐字段列差异。

目的：搞清"游戏实例化物品"时给实例改了哪些字段值。
如果在模板里某字段是 0/nil 而实例里是别值，那么"从模板克隆"出来的新物品
就会缺少游戏运行时的加工 —— 表现就是"新增的物品不能用"。
"""
# --- 开发期路径引导：让 import 项目模块找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import codec as C
import marshal_ruby as M
import doctree as MOD

from paths import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE
FILES = [('原档 sy.ogg.init', os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg.init')),
         ('现档 sy.ogg', os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg'))]


def flat(node, depth=0):
    if node is None or depth > 30:
        return None
    if isinstance(node, M.LinkNode):
        return flat(node.target, depth + 1)
    if isinstance(node, M.NilNode):
        return node.value
    if isinstance(node, M.StrNode):
        return node.str()
    if isinstance(node, M.SymbolNode):
        return ':' + node.name
    if isinstance(node, (M.IntNode, M.BignumNode, M.FloatNode)):
        return node.value
    if isinstance(node, M.BoolNode):
        return node.value
    if isinstance(node, M.ArrayNode):
        return [flat(x, depth + 1) for x in node.items]
    if isinstance(node, M.HashNode):
        return {str(flat(k, depth + 1)): flat(v, depth + 1) for k, v in node.pairs}
    if isinstance(node, (M.ObjNode, M.StructNode)):
        return dict((k, flat(v, depth + 1)) for k, v in node.ivars)
    if isinstance(node, M.UserDefNode):
        return '<%s %dB>' % (node.cls, len(node.data))
    return '?' + type(node).__name__


def main():
    log = []
    bridge = C.make_bridge(DLL_DIR, log.append)
    for title, path in FILES:
        if not os.path.exists(path):
            print('缺少 %s' % path)
            continue
        doc = MOD.Doc(path, bridge, log.append)
        items = doc._db('data_items', 'Items.rxdata')
        print('=' * 78)
        print('%s（%s）' % (title, os.path.basename(path)))
        print('=' * 78)
        # 各容器的实例
        for key in ('@pack', '@wallet', '@talisman'):
            arr = doc.node('data').get(key)
            if not isinstance(arr, M.ArrayNode):
                continue
            used = [(i, c) for i, c in enumerate(arr.items)
                    if isinstance(c, M.ArrayNode) and len(c.items) >= 2
                    and isinstance(c.items[0], M.ObjNode)]
            if not used:
                continue
            print('')
            print('%s（%d 格在用）' % (key, len(used)))
            for slot, cell in used:
                inst = cell.items[0]
                std = M.value_of(inst.get('@standard'))
                cnt = M.value_of(cell.items[1])
                nm = MOD.stext(inst.get('@name'), '?')
                print('  格%-3d 模板%-5s 数量%-4s %s' % (slot, std, cnt, nm))
                if not isinstance(std, int) or not (0 <= std < len(items)) \
                        or not isinstance(items[std], M.ObjNode):
                    print('       （找不到模板，跳过对比）')
                    continue
                tpl = items[std]
                inst_d = dict((k, flat(v)) for k, v in inst.ivars)
                tpl_d = dict((k, flat(v)) for k, v in tpl.ivars)
                keys = [k for k, _ in tpl.ivars] + \
                       [k for k, _ in inst.ivars if k not in tpl_d]
                diffs = []
                for k in keys:
                    a, b = tpl_d.get(k, '<模板无此字段>'), inst_d.get(k, '<实例无此字段>')
                    if a != b:
                        diffs.append((k, a, b))
                if not diffs:
                    print('       与模板完全一致')
                for k, a, b in diffs:
                    print('       %-14s 模板=%-22s 实例=%s'
                          % (k.lstrip('@'), repr(a)[:22], repr(b)[:30]))
                # 模板里的 scope / occasion / element_set 值（判断能不能用的关键）
                print('       [模板关键字段] scope=%s occasion=%s element_set=%s '
                      'price=%s consumable=%s'
                      % (repr(flat(tpl.get('@scope')))[:20],
                         repr(flat(tpl.get('@occasion')))[:20],
                         repr(flat(tpl.get('@element_set')))[:26],
                         repr(flat(tpl.get('@price')))[:12],
                         repr(flat(tpl.get('@consumable')))[:12]))
        print('')


if __name__ == '__main__':
    main()
