# -*- coding: utf-8 -*-
"""0.3 重复修改 / 撤销测试：同一字段改两次、改回原值应算"未修改"。

不依赖游戏内运行，只用到 XJCodec32.exe + TP.dll（和正式程序一样的路径）。
临时副本写在源码目录，测试完自动删除，不动正式存档。
"""
# --- 开发期路径引导：让 import xj_* 找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import xj_codec as C
import xj_model as MOD

from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
TMP = os.path.join(HERE, 'test_repeat_copy.ogg')
# 源码目录里没有 TP.dll，直接用游戏根目录里的；宿主 XJCodec32.exe 在源码目录
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE

LOG = []
results = []


def check(name, ok, extra=''):
    results.append((name, ok, extra))
    print('%-42s %s %s' % (name, 'OK' if ok else '失败', extra))


def main():
    if not os.path.exists(SAVE):
        print('找不到存档:', SAVE)
        return 1
    shutil.copy2(SAVE, TMP)
    bridge = C.make_bridge(DLL_DIR, LOG.append)
    doc = MOD.Doc(TMP, bridge, LOG.append)

    if not [r for r in doc.pack() if r['item'] is not None]:
        # 背包可能是空的 —— 先塞一格并**存盘**。
        # （后面会反复 discard()，而 discard 的语义是"回到磁盘上的样子"，
        #   只存在内存里的播种会被丢掉）
        doc.pack_add([r['slot'] for r in doc.pack() if r['item'] is None][0], 3, 4)
        doc.pack_fix_all()
        doc.save(backup=False)
        doc = MOD.Doc(TMP, bridge, LOG.append)

    g0 = doc.gold()
    name0 = doc.actor_rows()[0]['name']
    aid = doc.actor_rows()[0]['id']
    lv0 = doc.actor_rows()[0]['level']
    slot0 = [r for r in doc.pack() if r['item'] is not None][0]
    sw_idx = next(i for i in range(len(doc.switches())) if doc.switches()[i][1] in (False, None))

    # --- 1. 同一字段连改三次 ---
    doc.set_gold(111)
    doc.set_gold(222)
    doc.set_gold(333)
    check('金钱连续改三次(111→222→333)', doc.gold() == 333, '现值 %s' % doc.gold())

    # --- 2. 改回原值应视为未修改 ---
    doc.discard()
    doc.set_gold(g0)
    check('金钱改成原值 → 视为未修改', not doc.is_dirty(),
          '补丁字节 %d' % doc.changed_bytes())

    # --- 3. 角色字段连改两次 ---
    doc.discard()
    doc.set_actor_field(aid, '@level', lv0)
    doc.set_actor_field(aid, '@level', lv0)
    check('角色等级改成原值两次', not doc.is_dirty())
    doc.set_actor_field(aid, '@level', 7)
    doc.set_actor_field(aid, '@level', 8)
    check('角色等级连改(7→8)', MOD.vof(doc.actor(aid).get('@level')) == 8,
          '现值 %s' % MOD.vof(doc.actor(aid).get('@level')))

    # --- 4. 名称/数量连改 ---
    doc.discard()
    names = [MOD.stext(n.get('@name')) for n in doc.actor_nodes(aid)]
    doc.set_actor_name(aid, names[0])
    same = len(set(names)) == 1
    check('角色名字改成原名', (not doc.is_dirty()) if same else True,
          '拷贝 %d 份：%s' % (len(names), '/'.join(names)))
    doc.discard()
    doc.set_actor_name(aid, '测试甲')
    doc.set_actor_name(aid, '测试乙')
    check('角色名字连改两次', MOD.stext(doc.actor(aid).get('@name')) == '测试乙',
          '现值 %s' % MOD.stext(doc.actor(aid).get('@name')))
    doc.set_pack_count(slot0['slot'], 11)
    doc.set_pack_count(slot0['slot'], 22)
    check('物品数量连改两次', doc.pack_slot(slot0['slot'])['count'] == 22,
          '现值 %s' % doc.pack_slot(slot0['slot'])['count'])

    # --- 5. 开关连改 ---
    doc.set_switch(sw_idx, False)
    doc.set_switch(sw_idx, True)
    check('开关连改两次', doc.switches()[sw_idx][1] is True)

    # --- 6. 数量改成原值 → 未修改 ---
    doc.discard()
    doc.set_pack_count(slot0['slot'], slot0['count'])
    check('物品数量改成原值', not doc.is_dirty())

    # --- 7. 保存并重新读回 ---
    doc.discard()
    doc.set_gold(24680)
    doc.set_actor_field(aid, '@level', 9)
    doc.set_pack_count(slot0['slot'], 33)
    doc.set_switch(sw_idx, True)
    n = doc.changed_bytes()
    path = doc.save(backup=False)
    check('保存成功', path == TMP and os.path.exists(TMP), '改动字节 %d' % n)

    doc2 = MOD.Doc(TMP, bridge, LOG.append)
    ok = (doc2.gold() == 24680
          and MOD.vof(doc2.actor(aid).get('@level')) == 9
          and doc2.pack_slot(slot0['slot'])['count'] == 33
          and doc2.switches()[sw_idx][1] is True)
    check('读回校验(金钱/等级/数量/开关)', ok,
          '金钱=%s 等级=%s 数量=%s 开关=%s'
          % (doc2.gold(), MOD.vof(doc2.actor(aid).get('@level')),
             doc2.pack_slot(slot0['slot'])['count'], doc2.switches()[sw_idx][1]))

    # --- 8. 保存后再改（补丁引擎已重置）---
    doc2.set_gold(35791)
    check('保存后继续修改', doc2.gold() == 35791 and doc2.is_dirty())
    doc2.discard()

    print('')
    bad = [r for r in results if not r[1]]
    print('===== 重复修改测试：%s（共 %d 项，失败 %d 项）====='
          % ('全部通过' if not bad else '有失败', len(results), len(bad)))
    try:
        os.remove(TMP)
        for ext in ('.bak',):
            if os.path.exists(TMP + ext):
                os.remove(TMP + ext)
    except OSError:
        pass
    return 0 if not bad else 1


if __name__ == '__main__':
    sys.exit(main())
