# -*- coding: utf-8 -*-
"""验证"物品实例必须登记进 $data_items"这个机制。

游戏代码（0156 脚本 random_item / System::Data#item_can_use?）：
    item = $data_items[item_id].clone
    item.standard = item_id
    if void.empty?            # 没有空槽
      item.id = $data_items.size
      $data_items.push(item)  # 追加到数组末尾
    else
      item.id = void[0]       # 占用空槽
      $data_items[void[0]] = item
    end
    ...
    def item_can_use?(item_id)
      return if $data_items[item_id].nil?    # ← 用实例的 @id 索引
      occasion = $data_items[item_id].occasion
      ...
本脚本检查：@pack 各格的实例 @id 在 $data_items 里是什么东西。
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


def walk(node, out=None, depth=0):
    out = [] if out is None else out
    out.append(node)
    if depth > 300:
        return out
    if isinstance(node, M.ArrayNode):
        kids = list(node.items)
    elif isinstance(node, (M.ObjNode, M.StructNode)):
        kids = [v for _, v in node.ivars]
    elif isinstance(node, M.IVarNode):
        kids = ([node.inner] if node.inner is not None else []) + \
               [v for _, v in node.ivars]
    elif isinstance(node, M.HashNode):
        kids = [x for kv in node.pairs for x in kv]
    else:
        kids = []
    for c in kids:
        walk(c, out, depth + 1)
    return out


def main():
    log = []
    bridge = C.make_bridge(DLL_DIR, log.append)
    for title, path in FILES:
        if not os.path.exists(path):
            continue
        doc = MOD.Doc(path, bridge, log.append)
        say = print
        say('=' * 78)
        say('%s' % title)
        say('=' * 78)
        ent = doc.entries[12]                       # $data_items
        node = ent['node']
        items = node.items
        links = ent.get('links') or []
        nil_slots = [i for i, x in enumerate(items) if isinstance(x, M.NilNode)]
        allnodes = walk(node)
        link_nodes = [n for n in allnodes if isinstance(n, M.LinkNode)]
        bad = [n for n in link_nodes if n.target is None]
        say('$data_items：%s，%d 项，字节 %d..%d'
            % (type(node).__name__, len(items), node.start, node.end))
        say('  data_items 内对象数（Ruby 编号）= %d' % len(links))
        say('  内部链接 %d 个（解析失败 %d）' % (len(link_nodes), len(bad)))
        say('  空槽（nil）：%d 个，前 20 个 = %s'
            % (len(nil_slots), nil_slots[:20]))

        say('')
        say('@pack / @wallet / @talisman 各格实例的 @id 在 $data_items 里对应什么：')
        for key in ('@pack', '@wallet', '@talisman'):
            arr = doc.node('data').get(key)
            if not isinstance(arr, M.ArrayNode):
                continue
            for slot, cell in enumerate(arr.items):
                if not (isinstance(cell, M.ArrayNode) and len(cell.items) >= 2):
                    continue
                inst = cell.items[0]
                if not isinstance(inst, M.ObjNode):
                    continue
                iid = M.value_of(inst.get('@id'))
                std = M.value_of(inst.get('@standard'))
                name = MOD.stext(inst.get('@name'), '?')
                if not isinstance(iid, int):
                    say('  %-10s 格%-3d 实例=%-8s 模板=%-5s %s（@id 不是整数！）'
                        % (key, slot, iid, std, name))
                    continue
                if iid >= len(items):
                    say('  %-10s 格%-3d 实例=%-6d 模板=%-5s %-12s '
                        '→ $data_items[%d] **越界**（数组只有 %d 项）'
                        % (key, slot, iid, std, name, iid, len(items)))
                    continue
                t = items[iid]
                if isinstance(t, M.NilNode) or t is None:
                    say('  %-10s 格%-3d 实例=%-6d 模板=%-5s %-12s → $data_items[%d] 是 nil'
                        % (key, slot, iid, std, name, iid))
                elif isinstance(t, M.ObjNode):
                    say('  %-10s 格%-3d 实例=%-6d 模板=%-5s %-12s '
                        '→ $data_items[%d]: %s 模板=%s occasion=%s'
                        % (key, slot, iid, std, name, iid, t.cls,
                           M.value_of(t.get('@standard')),
                           M.value_of(t.get('@occasion'))))
                else:
                    say('  %-10s 格%-3d 实例=%-6d → $data_items[%d] = %s'
                        % (key, slot, iid, iid, type(t).__name__))
        say('')


if __name__ == '__main__':
    main()
