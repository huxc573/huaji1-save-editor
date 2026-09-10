# -*- coding: utf-8 -*-
"""列出"角色数据"在存档里的确切位置（供回答/排查用）。

游戏存档里跟角色有关的顶层对象有三个：
  #7  $game_actors  -> @data   数组，元素是 Game_Actor（副本A，角色表）
  #8  $game_party   -> @actors 数组，元素是 Game_Actor（副本B，队伍）
  #16 $data_actors  -> 数据库快照（角色模板：名字/职业/初始装备/等级曲线），不是进度
本脚本打印每一份 Game_Actor 的字段路径、明文偏移，以及关键字段的值。
"""
# --- 开发期路径引导：让 import xj_* 找到 ../src ----------------------------
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

import xj_codec as C
import xj_marshal as M
import xj_model as MOD

from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')


def kids(node):
    if isinstance(node, M.ArrayNode):
        return [('[%d]' % i, x) for i, x in enumerate(node.items)]
    if isinstance(node, (M.ObjNode, M.StructNode)):
        return [('@%s' % k.lstrip('@'), v) for k, v in node.ivars]
    if isinstance(node, M.IVarNode):
        out = [('@%s' % k.lstrip('@'), v) for k, v in node.ivars]
        if node.inner is not None:
            out.insert(0, ('<inner>', node.inner))
        return out
    if isinstance(node, M.HashNode):
        return [('{%s}' % MOD.value_text(k, 18), v) for k, v in node.pairs]
    return []


def walk(node, path, out, depth=0):
    if node is None or depth > 40:
        return
    out.append((path, node))
    for label, child in kids(node):
        walk(child, path + label, out, depth + 1)


def main():
    log = []
    doc = MOD.Doc(SAVE, C.make_bridge(DLL_DIR, log.append), log.append)
    print('存档：%s（明文 %d 字节，%d 个顶层对象）'
          % (doc.path, len(doc.plain), len(doc.entries)))
    print('')

    # 1) 哪里装着 Game_Actor
    print('=== 存档里所有 Game_Actor 对象（这就是"角色"数据）===')
    n = 0
    for i, name in enumerate(MOD.TOP_NAMES):
        top = doc.node(name)
        if top is None:
            continue
        nodes = []
        walk(top, name, nodes)
        acts = [(p, x) for p, x in nodes
                if isinstance(x, M.ObjNode) and x.cls == 'Game_Actor']
        if not acts:
            continue
        print('顶层 #%d %s：%d 个 Game_Actor' % (i, name, len(acts)))
        for p, x in acts:
            n += 1
            print('   %-28s 明文 %6d..%-6d 实例 id=%-4s 名字=%-8s 等级=%s HP=%s/%s'
                  % (p, x.start, x.end,
                     M.value_of(x.get('@actor_id')), MOD.stext(x.get('@name'), '?'),
                     M.value_of(x.get('@level')), M.value_of(x.get('@hp')),
                     doc.actor_maxhp(M.value_of(x.get('@actor_id')))))
    print('  合计 %d 份' % n)

    # 2) 聚合结果（界面"角色"页用的就是这个）
    print('')
    print('=== 按 @actor_id 聚合（工具里"角色"页的数据来源）===')
    for r in doc.actor_rows():
        print('  角色 %-3s %-10s 职业=%-8s 等级=%-4s 经验=%-10s HP=%s/%s SP=%s/%s'
              % (r['id'], r['name'], r['class'], r['level'], r['exp'],
                 r['hp'], r['maxhp'], r['sp'], r['maxsp']))
        print('      五维：体质=%s 魔力=%s 力量=%s 耐力=%s 敏捷=%s  潜力=%s 活力=%s 体力=%s 五行=%s'
              % (r['tizhi'], r['moli'], r['liliang'], r['naili'], r['minjie'],
                 r['latent'], r['vitality'], r['spirit'], r['element']))
        print('      存在位置：%s' % r['where'])

    # 3) 一个 Game_Actor 的全部字段
    rows = doc.actor_rows()
    if rows:
        print('')
        print('=== Game_Actor 的全部字段（以第一个角色为例）===')
        obj = doc.actor(rows[0]['id'])
        for k, v in obj.ivars:
            s = MOD.value_text(v, 60)
            print('  %-16s = %s' % (k, s))

    # 4) $data_actors 是什么
    da = doc.node('data_actors')
    if isinstance(da, M.ArrayNode):
        print('')
        print('=== #16 $data_actors（数据库快照，不是进度数据）===')
        print('  共 %d 项；每一项是 RPG::Actor 模板（名字/职业/初始等级/装备/成长曲线）' % len(da.items))
        for i in (1, 2, 3):
            if i < len(da.items) and isinstance(da.items[i], M.ObjNode):
                a = da.items[i]
                print('  [%d] %-8s 职业id=%s 初始等级=%s 初始HP=%s 初始SP=%s 五行=%s'
                      % (i, MOD.stext(a.get('@name'), '?'),
                         M.value_of(a.get('@class_id')), M.value_of(a.get('@level')),
                         M.value_of(a.get('@parameters')), '',
                         MOD.stext(a.get('@五行'), '')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
