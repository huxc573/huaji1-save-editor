# -*- coding: utf-8 -*-
"""探测：物品实例 vs data_items 模板 的字段差异，找出"物品无法使用"的原因。

重点看：
  1) 模板里 @quality 是多少（怀疑是 0，游戏靠实例的 @quality=100）
  2) 实例比模板多出/缺少哪些字段（克隆模板会缺字段 -> 游戏判定不可用）
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
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE

log = []
doc = MOD.Doc(SAVE, C.make_bridge(DLL_DIR, log.append), log.append)
items = doc._db('data_items', 'Items.rxdata')

print('==== data_items 模板 ====')
for sid in (2, 3, 87, 186, 239):
    tpl = items[sid] if sid < len(items) else None
    if not isinstance(tpl, M.ObjNode):
        print('  模板 %s 不存在' % sid)
        continue
    keys = [k for k, _ in tpl.ivars]
    print('  模板 %-4s %s' % (sid, MOD.stext(tpl.get('@name'))))
    print('         字段 %d 个：%s' % (len(keys), ','.join(k.lstrip('@') for k in keys)))
    for k in ('@id', '@standard', '@quality', '@count', '@exp', '@level'):
        if k in keys:
            v = tpl.get(k)
            print('         %-10s = %s  [%s]' % (k, MOD.value_text(v, 40),
                                                 MOD.type_text(v)))

print('')
print('==== @pack 实例 ====')
for r in doc.pack():
    if r['item'] is None:
        continue
    it = r['item']
    keys = [k for k, _ in it.ivars]
    print('  格%-3d 模板%-5s %-12s 实例字段 %d 个' %
          (r['slot'], r['standard'], r['name'], len(keys)))
    for k in ('@id', '@standard', '@quality', '@count', '@exp', '@level'):
        if k in keys:
            v = it.get(k)
            print('         %-10s = %s  [%s]' % (k, MOD.value_text(v, 40),
                                                 MOD.type_text(v)))
    # 与模板对比字段差异
    if isinstance(r['standard'], int) and r['standard'] < len(items):
        tpl = items[r['standard']]
        if isinstance(tpl, M.ObjNode):
            tk = set(k for k, _ in tpl.ivars)
            ik = set(keys)
            extra = sorted(ik - tk)
            miss = sorted(tk - ik)
            print('         实例多出：%s' % (','.join(x.lstrip('@') for x in extra) or '无'))
            print('         实例缺少：%s' % (','.join(x.lstrip('@') for x in miss) or '无'))
    if r['slot'] >= 3:
        break
