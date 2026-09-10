# -*- coding: utf-8 -*-
"""看清 $game_party 的 @原id / @现id / @编号 映射，以及两个副本的 @babys 是否一致。"""
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

BUF = []


def out(*a):
    BUF.append(' '.join(str(x) for x in a))


def arr(node):
    return [M.value_of(x) for x in node.items] if isinstance(node, M.ArrayNode) else None


def main():
    log = []
    doc = MOD.Doc(SAVE, C.make_bridge(DLL_DIR, log.append), log.append)
    gp = doc.node('game_party')
    out('@编号 = %s' % M.value_of(gp.get('@编号')))
    out('@原id = %s' % arr(gp.get('@原id')))
    out('@现id = %s' % arr(gp.get('@现id')))
    out('')
    out('槽 -> 模板 映射（@现id[k] -> @原id[k]）:')
    x, y = arr(gp.get('@现id')) or [], arr(gp.get('@原id')) or []
    for i, s in enumerate(x):
        out('  k=%-3d 现id(槽)=%-5s 原id(模板)=%s' % (i, s, y[i] if i < len(y) else '?'))

    out('')
    out('=== 两个副本的 @babys 对比 ===')
    ga = doc.ivar('game_actors', '@data')
    copyA = {}
    for it in ga.items:
        if isinstance(it, M.ObjNode):
            aid = M.value_of(it.get('@actor_id'))
            b = it.get('@babys')
            copyA[aid] = arr(b) if b is not None else None
    pa = gp.get('@actors')
    copyB = {}
    if isinstance(pa, M.ArrayNode):
        for it in pa.items:
            if isinstance(it, M.ObjNode):
                aid = M.value_of(it.get('@actor_id'))
                b = it.get('@babys')
                copyB[aid] = arr(b) if b is not None else None
    for aid in sorted(set(list(copyA) + list(copyB)), key=lambda v: (v is None, v)):
        out('  人物 %-5s 角色表@babys=%-26s 队伍@babys=%s'
            % (aid, copyA.get(aid, '（不在角色表）'), copyB.get(aid, '（不在队伍）')))

    out('')
    out('=== 每个召唤兽槽位：名字 / @new_name / 等级 / 技能数 / 是否被引用 ===')
    owned = set()
    for v in list(copyA.values()) + list(copyB.values()):
        if v:
            owned |= set(v)
    for it in ga.items:
        if not isinstance(it, M.ObjNode):
            continue
        aid = M.value_of(it.get('@actor_id'))
        if aid is None or aid <= 20:
            continue
        out('  槽%-5s @name=%-12s @new_name=%-8s 等级=%-4s 技能=%-2s 忠诚=%-5s 引用=%s'
            % (aid, repr(MOD.stext(it.get('@name'), '')),
               repr(MOD.stext(it.get('@new_name'), '<无>')),
               M.value_of(it.get('@level')),
               len(arr(it.get('@skills')) or []),
               MOD.vof(it.get('@loyal')), '是' if aid in owned else '否'))

    out_dir = os.path.join(GAME, 'Try', 'tmp')
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, 'pet_map.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(BUF) + '\n')
    print('已写入 Try/tmp/pet_map.txt（%d 行）' % len(BUF))
    return 0


if __name__ == '__main__':
    sys.exit(main())
