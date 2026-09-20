# -*- coding: utf-8 -*-
"""对比原存档 sy.ogg.init 与当前存档 sy.ogg，查清"物品无法使用"的原因。

重点看 Marshal 的**对象链接**（'@N'）：@pack 各格之间是不是共享了对象，
以及用工具改过一格之后，后面格子的链接是不是指错了对象。
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
INIT = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg.init')     # 原存档
CUR = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')           # 现在的存档

OUT = []


def say(s=''):
    print(s)
    OUT.append(s)


def walk(node, out=None, depth=0):
    """递归收集整棵树里的所有节点（含 LinkNode 自己，不含 link 的 target）。"""
    out = [] if out is None else out
    out.append(node)
    if depth > 300:
        return out
    if isinstance(node, M.ArrayNode):
        kids = list(node.items)
    elif isinstance(node, (M.ObjNode, M.StructNode)):
        kids = [v for _, v in node.ivars]
    elif isinstance(node, M.IVarNode):
        kids = ([node.inner] if node.inner is not None else []) \
            + [v for _, v in node.ivars]
    elif isinstance(node, M.HashNode):
        kids = []
        for k, v in node.pairs:
            kids += [k, v]
    elif isinstance(node, M.UserMarshalNode):
        kids = [node.inner] if node.inner is not None else []
    else:
        kids = []
    for c in kids:
        walk(c, out, depth + 1)
    return out


def brief(node):
    t = type(node).__name__.replace('Node', '')
    if isinstance(node, M.StrNode):
        return 'Str(%r)' % node.str()[:20]
    if isinstance(node, M.SymbolNode):
        return 'Sym(:%s)' % node.name
    if isinstance(node, (M.IntNode, M.BignumNode)):
        return 'Int(%s)' % node.value
    if isinstance(node, M.BoolNode):
        return 'Bool(%s)' % node.value
    if isinstance(node, M.LinkNode):
        return 'Link->[%d]' % node.index
    if isinstance(node, M.ObjNode):
        return 'Obj(%s)' % node.cls
    if isinstance(node, M.UserDefNode):
        return 'UserDef(%s,%dB)' % (node.cls, len(node.data))
    if isinstance(node, M.ArrayNode):
        return 'Array[%d]' % len(node.items)
    if isinstance(node, M.NilNode):
        return 'nil'
    return t


def analyze(doc, title):
    say('=' * 78)
    say('%s   文件 %d 字节 → 明文 %d 字节' % (title, doc.file_size, len(doc.plain)))
    say('=' * 78)
    # ---- $data 流（System::Data，index 17）----
    ent = doc.entries[17]
    data = ent['node']
    links = ent.get('links') or []
    say('$data 节点：%s，明文 %d..%d（%d 字节）'
        % (type(data).__name__, data.start, data.end, data.end - data.start))
    say('$data 内对象总数（按 Ruby 规则编号）= %d' % len(links))
    idx_of = {id(n): i for i, n in enumerate(links)}

    allnodes = walk(data)
    by_type = {}
    for n in allnodes:
        by_type[type(n).__name__] = by_type.get(type(n).__name__, 0) + 1
    say('节点类型统计：%s' % ', '.join('%s=%d' % kv for kv in
                                   sorted(by_type.items(), key=lambda x: -x[1])))
    link_nodes = [n for n in allnodes if isinstance(n, M.LinkNode)]
    none_target = [n for n in link_nodes if n.target is None]
    say('链接总数 = %d，其中解析不到目标的 = %d' % (len(link_nodes), len(none_target)))

    # ---- @pack ----
    arr = data.get('@pack')
    say('')
    say('@pack：%s，明文 %d..%d（%d 字节）'
        % (type(arr).__name__, arr.start, arr.end, arr.end - arr.start))
    say('')
    say('  格   字节范围         大小   对象数  名称(实例)          模板  实例id  数量  品质  说明')
    cell_range = {}
    for i, cell in enumerate(arr.items):
        if isinstance(cell, M.ArrayNode) and len(cell.items) >= 2:
            item = cell.items[0]
            while isinstance(item, M.LinkNode) and item.target is not None:
                item = item.target
            cell_range[i] = (cell.start, cell.end)
            oids = [k for k, n in enumerate(links)
                    if cell.start <= n.start < cell.end]
            if isinstance(item, M.ObjNode):
                nm = MOD.stext(item.get('@name'), '?')
                std = M.value_of(item.get('@standard'))
                iid = M.value_of(item.get('@id'))
                q = M.value_of(item.get('@quality'))
                say('  %-4d %6d..%-6d %-6d %-7d %-20s %-5s %-7s %-5s %-5s'
                    % (i, cell.start, cell.end, cell.end - cell.start, len(oids),
                       nm, std, iid, M.value_of(cell.items[1]), q))
            else:
                say('  %-4d %6d..%-6d %-6d %-7d (不是对象: %s)'
                    % (i, cell.start, cell.end, cell.end - cell.start,
                       len(oids), brief(item)))
        else:
            say('  %-4d %-15s %s' % (i, '(空格)', brief(cell) if cell is not None else '?'))
            cell_range[i] = (getattr(cell, 'start', 0), getattr(cell, 'end', 0))

    # ---- @pack 里的链接指向 ----
    say('')
    say('@pack 内部的链接（看有没有跨格共享对象）：')
    for n in link_nodes:
        if not (arr.start <= n.start < arr.end):
            continue
        slot = next((i for i, (s, e) in cell_range.items() if s <= n.start < e), None)
        tgt = n.target
        tin = (tgt is not None and arr.start <= tgt.start < arr.end)
        say('  链接@%d（明文 %d，格%s）-> %s%s'
            % (n.index, n.start, slot, brief(tgt) if tgt is not None else '??',
               '  [在 @pack 内]' if tin else ''))

    # ---- @pack 之外但指向 @pack 内的链接 ----
    outside = [n for n in link_nodes
               if not (arr.start <= n.start < arr.end)
               and n.target is not None
               and arr.start <= n.target.start < arr.end]
    say('')
    say('@pack 之外、却指向 @pack 内对象的链接：%d 个' % len(outside))
    for n in outside[:10]:
        say('  %s（明文 %d）-> %s' % (brief(n), n.start, brief(n.target)))

    # ---- 各格内部对象明细（对象编号区间）----
    say('')
    say('各格占用的对象编号（Ruby 编号）：')
    for i in sorted(cell_range):
        s, e = cell_range[i]
        if s == e:
            continue
        oids = [k for k, n in enumerate(links) if s <= n.start < e]
        if oids:
            say('  格%-3d 编号 %d ~ %d（共 %d 个对象）：%s'
                % (i, oids[0], oids[-1], len(oids),
                   ', '.join('%d:%s' % (k, brief(links[k])) for k in oids[:8])))
    return arr, links, cell_range


def main():
    if not os.path.exists(INIT):
        print('找不到原存档：%s' % INIT)
        return 1
    log = []
    bridge = C.make_bridge(DLL_DIR, log.append)

    d1 = MOD.Doc(INIT, bridge, log.append)
    d2 = MOD.Doc(CUR, bridge, log.append)
    a1, l1, r1 = analyze(d1, '【原存档】sy.ogg.init')
    say('')
    a2, l2, r2 = analyze(d2, '【当前存档】sy.ogg')

    say('')
    say('=' * 78)
    say('对比：@pack 各格的对象编号数量')
    say('=' * 78)
    for i in sorted(set(list(r1) + list(r2))):
        s1, e1 = r1.get(i, (0, 0))
        s2, e2 = r2.get(i, (0, 0))
        n1 = len([k for k, n in enumerate(l1) if s1 <= n.start < e1]) if e1 > s1 else 0
        n2 = len([k for k, n in enumerate(l2) if s2 <= n.start < e2]) if e2 > s2 else 0
        flag = '' if n1 == n2 else '   <<<< 对象数变了'
        say('  格%-3d 原 %2d 个（%5d..%-5d）  现 %2d 个（%5d..%-5d）%s'
            % (i, n1, s1, e1, n2, s2, e2, flag))

    with open(os.path.join(HERE, 'pack_analyze.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(OUT))
    print('')
    print('（完整结果已写到 pack_analyze.txt）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
