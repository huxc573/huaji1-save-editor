# -*- coding: utf-8 -*-
"""探查召唤兽的“界面顺序 / 放生状态 / 名字字段”。

脚本证据（Try/scripts/）：
  0044_Game_Actor#add_baby   -> i = $game_party.召唤兽(baby_id); @babys.push(i)
  0048_Game_Party#召唤兽(id) -> 在 21..998 里找第一个 $data_actors[i].name == "" 的空位
  0048_Game_Party#删除(id)   -> @原id[@现id.index(id)] = 999; $data_actors[id] = $data_actors[999]
  0044_Game_Actor#remove_baby-> $game_party.删除 ; @babys.delete ; $data_actors[id] = nil
  0143_Sys::Window_Baby#refresh -> @actor.babys.each { |i| @data.push($game_actors[i]) }   <<< 界面顺序
  0040_Game_Battler#custom_name -> @new_name == nil ? name : @new_name
  0163_...065A09.rb when 16 (改名) -> @baby_window.baby.new_name = textbox.text
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

BUF = []


def out(*a):
    BUF.append(' '.join(str(x) for x in a))


def main():
    log = []
    doc = MOD.Doc(SAVE, C.make_bridge(DLL_DIR, log.append), log.append)

    gp = doc.node('game_party')
    out('=== $game_party 的实例变量 ===')
    for k, v in gp.ivars:
        out('  %-14s = %s' % (k, MOD.value_text(v, 120)))

    pa = gp.get('@actors')
    order = [M.value_of(x.get('@actor_id')) if isinstance(x, M.ObjNode) else x
             for x in pa.items] if isinstance(pa, M.ArrayNode) else []
    out('')
    out('$game_party.@actors 顺序 = %s' % order)

    out('')
    out('=== 每个 Game_Actor 的 @actor_id / @name / @new_name / @baby / @babys ===')
    ga = doc.ivar('game_actors', '@data')
    for i, it in enumerate(ga.items):
        if not isinstance(it, M.ObjNode):
            continue
        aid = M.value_of(it.get('@actor_id'))
        bab = it.get('@babys')
        babv = [M.value_of(x) for x in bab.items] if isinstance(bab, M.ArrayNode) else None
        out('  槽%-4d @actor_id=%-4s @name=%-14s @new_name=%-10s @baby=%-5s @babys=%s'
            % (i, aid, repr(MOD.stext(it.get('@name'), '')),
               repr(MOD.stext(it.get('@new_name'), '')),
               M.value_of(it.get('@baby')), babv))

    out('')
    out('=== $data_actors 的 21..998（召唤兽槽位；&链接 = 与别的槽共用同一对象）===')
    da = doc.node('data_actors')
    items = da.items if isinstance(da, M.ArrayNode) else []
    out('$data_actors 长度 = %d' % len(items))
    for i in range(21, min(len(items), 1000)):
        it = items[i]
        if it is None:
            continue
        if isinstance(it, M.LinkNode):
            tgt = getattr(it, 'target', None)
            out('  [%d] = &链接 -> id=%s name=%r' %
                (i, M.value_of(tgt.get('@id')) if isinstance(tgt, M.ObjNode) else '?',
                 MOD.stext(tgt.get('@name'), '') if isinstance(tgt, M.ObjNode) else '?'))
            continue
        if not isinstance(it, M.ObjNode):
            out('  [%d] = %s' % (i, MOD.value_text(it, 60)))
            continue
        nm = MOD.stext(it.get('@name'), '')
        if nm == '':
            continue
        out('  [%d] id=%-4s name=%r' % (i, M.value_of(it.get('@id')), nm))

    out('')
    out('=== @babys 汇总（界面顺序来源）===')
    owners = {}
    for i, it in enumerate(ga.items):
        if not isinstance(it, M.ObjNode):
            continue
        aid = M.value_of(it.get('@actor_id'))
        if aid is None or aid > 20:
            continue
        bab = it.get('@babys')
        if isinstance(bab, M.ArrayNode):
            owners[aid] = [M.value_of(x) for x in bab.items]
    for k in sorted(owners):
        out('    人物 %-4s -> %s' % (k, owners[k]))
    owned = set()
    for v in owners.values():
        owned |= set(v)
    pets = []
    for it in ga.items:
        if isinstance(it, M.ObjNode):
            aid = M.value_of(it.get('@actor_id'))
            if aid is not None and aid > 20:
                pets.append(aid)
    out('')
    out('  Game_Actor(@actor_id>20) 共 %d 个：%s' % (len(pets), sorted(pets)))
    out('  被人物 @babys 引用的  共 %d 个：%s' % (len(owned), sorted(owned)))
    out('  没人引用（疑似已放生）：%s' % sorted(set(pets) - owned))
    out('  引用了但没有对象（数据损坏）：%s' % sorted(owned - set(pets)))

    out('')
    out('=== 被引用的召唤兽对象详情 ===')
    for slot in sorted(owned):
        obj = doc.actor(slot)
        if obj is None:
            out('  %s -> 找不到 Game_Actor' % slot)
            continue
        out('  --- 槽位 %s ---' % slot)
        for k, v in obj.ivars:
            out('      %-16s = %s' % (k, MOD.value_text(v, 70)))

    out_dir = os.path.join(GAME, 'Try', 'tmp')
    try:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, 'pet_state.txt'), 'w', encoding='utf-8') as f:
            f.write('\n'.join(BUF) + '\n')
        print('已写入 Try/tmp/pet_state.txt（%d 行）' % len(BUF))
    except OSError as e:
        print('写文件失败：%s' % e)
    return 0


if __name__ == '__main__':
    sys.exit(main())
