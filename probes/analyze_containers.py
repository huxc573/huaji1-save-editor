# -*- coding: utf-8 -*-
"""侦察：物品到底存在哪几个容器里，实例是否在别处还有登记。

要查清：
  1. $data 里所有 ivar 的名字与结构（@pack / @wallet / @talisman 各是什么）
  2. 所有 RPG::Item 实例出现的位置（路径 + 模板 id + 实例 id + 数量）
  3. 是否存在"实例登记表"（比如 实例id -> 数量 的 Hash），
     这能解释"新增的物品游戏不认、改原有的却能用"
  4. 三个容器的元素格式是否一致
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
TARGETS = [('原档 sy.ogg.init', os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg.init')),
           ('现档 sy.ogg', os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg'))]

OUT = []


def say(s=''):
    print(s)
    OUT.append(s)


def labeled_kids(node):
    """(标签, 子节点) 列表。"""
    if isinstance(node, M.ArrayNode):
        return [('[%d]' % i, it) for i, it in enumerate(node.items)]
    if isinstance(node, (M.ObjNode, M.StructNode)):
        return [('@%s' % k.lstrip('@'), v) for k, v in node.ivars]
    if isinstance(node, M.IVarNode):
        out = [('@%s' % k.lstrip('@'), v) for k, v in node.ivars]
        if node.inner is not None:
            out.insert(0, ('<inner>', node.inner))
        return out
    if isinstance(node, M.HashNode):
        return [('{%s}' % MOD.value_text(k, 24), v) for k, v in node.pairs]
    if isinstance(node, M.UserMarshalNode):
        return [('<inner>', node.inner)] if node.inner is not None else []
    return []


def deref(node):
    n = node
    guard = 0
    while isinstance(n, M.LinkNode) and n.target is not None and guard < 100:
        n = n.target
        guard += 1
    return n


def walk(node, path, out, depth=0):
    if node is None or depth > 60:
        return
    out.append((path, node))
    for label, child in labeled_kids(node):
        walk(child, path + label, out, depth + 1)


def describe(node, maxlen=40):
    n = deref(node)
    if isinstance(n, M.ArrayNode):
        return 'Array[%d]' % len(n.items)
    if isinstance(n, M.HashNode):
        return 'Hash{%d}' % len(n.pairs)
    if isinstance(n, (M.ObjNode, M.StructNode)):
        return '%s(%d ivar)' % (n.cls, len(n.ivars))
    if isinstance(n, M.UserDefNode):
        return 'UserDef(%s,%dB)' % (n.cls, len(n.data))
    if isinstance(n, M.StrNode):
        s = n.str()
        return 'Str(%r)' % (s[:maxlen] if s else '')
    if isinstance(n, M.NilNode):
        return 'nil'
    return MOD.value_text(n, maxlen)


def item_info(node):
    """把 [物品实例, 数量] 解析成摘要。"""
    n = deref(node)
    if not isinstance(n, M.ArrayNode) or len(n.items) < 2:
        return None
    it = deref(n.items[0])
    if not isinstance(it, M.ObjNode):
        return None
    return {
        'cls': it.cls,
        'standard': M.value_of(it.get('@standard')),
        'iid': M.value_of(it.get('@id')),
        'quality': M.value_of(it.get('@quality')),
        'name': MOD.stext(it.get('@name'), '?'),
        'count': M.value_of(deref(n.items[1])),
        'len': len(n.items),
        'elems': [describe(x) for x in n.items],
    }


def report(path, title):
    say('=' * 78)
    say('%s' % title)
    say('=' * 78)
    if not os.path.exists(path):
        say('  文件不存在：%s' % path)
        return
    log = []
    doc = MOD.Doc(path, C.make_bridge(DLL_DIR, log.append), log.append)

    say('顶层对象：')
    for i, e in enumerate(doc.entries):
        n = e['node']
        say('  #%-2d %-14s %-12s %d 字节'
            % (i, MOD.TOP_NAMES[i] if i < len(MOD.TOP_NAMES) else '?',
               type(n).__name__, getattr(n, 'end', 0) - getattr(n, 'start', 0)))

    # ---- $data 的所有 ivar ----
    data = doc.node('data')
    say('')
    say('$data 的 ivar（System::Data）：')
    for k, v in data.ivars:
        say('  %-16s %s' % (k, describe(v, 60)))

    # ---- 所有 RPG::Item 实例出现的位置 ----
    say('')
    say('全部物品实例（RPG::Item）出现的位置：')
    nodes = []
    for i, name in enumerate(MOD.TOP_NAMES):
        n = doc.node(name)
        if n is not None:
            walk(n, name, nodes)
    items = [(p, n) for p, n in nodes
             if isinstance(deref(n), M.ObjNode) and deref(n).cls == 'RPG::Item']
    say('  共 %d 个' % len(items))
    for p, n in items:
        it = deref(n)
        say('  %-58s 模板%-5s 实例%-6s 品质%-5s %s'
            % (p[:58], M.value_of(it.get('@standard')), M.value_of(it.get('@id')),
               M.value_of(it.get('@quality')), MOD.stext(it.get('@name'), '?')[:16]))

    # ---- $data 里的三个容器 ----
    for key in ('@pack', '@wallet', '@talisman'):
        arr = data.get(key)
        say('')
        if arr is None:
            say('%s：不存在' % key)
            continue
        a = deref(arr)
        say('%s：%s' % (key, describe(a, 80)))
        if isinstance(a, M.ArrayNode):
            for i, cell in enumerate(a.items):
                info = item_info(cell)
                if info:
                    say('   [%2d] 模板%-5s 实例%-6s 数量%-5s 品质%-5s %-14s 元素=%s'
                        % (i, info['standard'], info['iid'], info['count'],
                           info['quality'], info['name'], info['elems']))
                else:
                    say('   [%2d] %s' % (i, describe(cell)))
    # ---- 找可能的"登记表"（Hash 或 数组里出现 实例id -> 数量）----
    say('')
    say('可能的登记表 / 其它含物品的容器（$data 和 $game_party 里）：')
    for top in ('data', 'game_party', 'game_actors', 'game_troop', 'game_map'):
        n = doc.node(top)
        if n is None:
            continue
        sub = []
        walk(n, top, sub)
        for p, node in sub:
            d = deref(node)
            if isinstance(d, M.HashNode) and p.count('.') <= 4:
                say('  %-58s %s' % (p[:58], describe(d)))
            if isinstance(d, M.ArrayNode) and len(d.items) and p.count('.') <= 3 \
                    and not isinstance(deref(d.items[0]), M.NilNode):
                first = deref(d.items[0])
                if isinstance(first, M.ArrayNode) and len(first.items) == 2:
                    say('  %-58s %s（看起来也是 [物品,数量] 表）' % (p[:58], describe(d)))
    return doc


def main():
    for title, path in TARGETS:
        report(path, title)
        say('')
        say('')
    with open(os.path.join(HERE, 'containers_report.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(OUT))
    print('（完整结果已写到 containers_report.txt）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
