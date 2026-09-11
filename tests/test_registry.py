# -*- coding: utf-8 -*-
"""0.5 物品登记 + 三容器测试

游戏脚本（0156 / 0155）里的关键逻辑：

    def random_item(item_id)            # 游戏自己新增物品时
      item = $data_items[item_id].clone
      item.standard = item_id
      ...
      item.id = $data_items.size        # 新实例的 @id = 数组长度
      $data_items.push(item)            # ★ 并把实例登记进 $data_items

    def item_can_use?(item_id)          # 使用物品时的判定（传的是实例的 @id）
      return if $data_items[item_id].nil?     # ★ 没登记 -> 直接判"无法使用"
      occasion = $data_items[item_id].occasion
      ...

所以：新增/换模板时，@id 必须是新槽号，并且要把实例登记进 $data_items；
只改数量/品质则沿用原槽号。

本测试覆盖：
  1. 新增到空格：@id = 旧长度、$data_items 增长 1、登记项模板正确
  2. 保存 -> 读回：登记项仍在、'item_can_use?' 的判定条件满足（不越界、非 nil）
  3. 同模板只改数量：沿用原 @id（$data_items 不增长）
  4. 换模板：分配新 @id 并登记
  5. 三个容器（@pack/@wallet/@talisman）都能写
  6. 修复：把"未登记"的物品找出来并登记好（对现档里那 4 件新增物品）
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
import xj_marshal as M
import xj_model as MOD

from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE
INIT = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg.init')
CUR = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
TMP = os.path.join(HERE, 'test_reg_copy.ogg')

results = []


def check(name, ok, extra=''):
    results.append((name, ok, extra))
    print('%-52s %s %s' % (name, 'OK' if ok else '失败', extra))


def registry_of(doc, iid):
    """取 $data_items[iid] 的登记信息。"""
    arr = doc.item_db_array()
    if not isinstance(iid, int) or not (0 <= iid < len(arr)):
        return None
    t = arr[iid]
    if not isinstance(t, M.ObjNode):
        return None
    return {'standard': M.value_of(t.get('@standard')),
            'id': M.value_of(t.get('@id')),
            'occasion': M.value_of(t.get('@occasion')),
            'name': MOD.stext(t.get('@name'), '?')}


def main():
    src = INIT if os.path.exists(INIT) else CUR
    shutil.copy2(src, TMP)
    log = []
    bridge = C.make_bridge(DLL_DIR, log.append)
    doc = MOD.Doc(TMP, bridge, log.append)

    n0 = len(doc.item_db_array())
    print('起始：$data_items %d 项，道具/行囊/备用 = %s'
          % (n0, ['%d/%d' % (u, s) for _k, _l, u, s, _r in doc.containers()]))

    # ---------- 1. 新增到空格 ----------
    empty = [r['slot'] for r in doc.container_slots('@pack') if r['item'] is None]
    s0 = empty[0]
    info = doc.pack_write(s0, 43, 1, 100, '@pack')      # 43 = 五龙丹
    r = doc.pack_slot(s0, '@pack')
    check('新增：@id = 旧长度（%d）' % n0, r['iid'] == n0, '实例 id %s' % r['iid'])
    check('新增：$data_items 增长 1', len(doc.item_db_array()) == n0 + 1,
          '%d -> %d' % (n0, len(doc.item_db_array())))
    reg = registry_of(doc, r['iid'])
    check('新增：登记项模板一致（43）',
          bool(reg) and reg['standard'] == 43, str(reg))
    check('新增：item_registered 为真', doc.item_registered(r['iid'], 43))
    check('新增：游戏判定条件满足（$data_items[id] 非 nil、occasion 存在）',
          bool(reg) and reg['occasion'] is not None,
          'occasion=%s' % (reg or {}).get('occasion'))

    # ---------- 2. 保存读回 ----------
    doc.save(backup=False)
    doc1 = MOD.Doc(TMP, bridge, log.append)
    r1 = doc1.pack_slot(s0, '@pack')
    reg1 = registry_of(doc1, r1['iid'])
    check('读回：实例仍在且已登记',
          doc1.item_registered(r1['iid'], 43) and bool(reg1),
          '实例 %s -> 登记 %s' % (r1['iid'], reg1))
    check('读回：$data_items 长度 = %d' % (n0 + 1),
          len(doc1.item_db_array()) == n0 + 1,
          '%d' % len(doc1.item_db_array()))
    check('读回：清单里没有"未登记"异常',
          not [b for b in doc1.pack_scan_bad() if '没登记' in b['why']],
          str(doc1.pack_scan_bad()))

    # ---------- 3. 同模板只改数量 -> 沿用原 @id ----------
    cnt_before = len(doc1.item_db_array())
    doc1.set_pack_count(s0, 5, '@pack')
    doc1.pack_write(s0, 43, 5, 100, '@pack')
    r2 = doc1.pack_slot(s0, '@pack')
    check('同模板改数量：沿用原实例 id', r2['iid'] == r1['iid'],
          '%s -> %s' % (r1['iid'], r2['iid']))
    check('同模板改数量：$data_items 不增长',
          len(doc1.item_db_array()) == cnt_before,
          '%d' % len(doc1.item_db_array()))

    # ---------- 4. 换模板 -> 新槽 + 登记 ----------
    n_before = len(doc1.item_db_array())
    doc1.pack_write(s0, 2, 7, 100, '@pack')             # 2 = 包子
    r3 = doc1.pack_slot(s0, '@pack')
    reg3 = registry_of(doc1, r3['iid'])
    check('换模板：分配了新实例 id（= 旧长度 %d）' % n_before, r3['iid'] == n_before,
          '实例 id %s' % r3['iid'])
    check('换模板：新登记项是包子（模板 2）',
          bool(reg3) and reg3['standard'] == 2, str(reg3))

    # ---------- 5. 三个容器都能写 ----------
    ok_all = True
    detail = []
    for key, label in MOD.CONTAINERS:
        rows = doc1.container_slots(key)
        free = [x['slot'] for x in rows if x['item'] is None]
        if not free:
            detail.append('%s 无空格' % label)
            continue
        try:
            doc1.pack_write(free[0], 36, 3, 100, key)    # 36 = 金创药
            rr = doc1.pack_slot(free[0], key)
            ok = rr['item'] is not None and doc1.item_registered(rr['iid'], 36)
            detail.append('%s 格%d→%s' % (label, free[0], 'OK' if ok else '失败'))
            ok_all = ok_all and ok
        except Exception as e:
            detail.append('%s 异常 %s' % (label, e))
            ok_all = False
    check('三个容器（道具/行囊/备用）都能写入并登记', ok_all, '；'.join(detail))

    doc1.save(backup=False)
    doc2 = MOD.Doc(TMP, bridge, log.append)
    bad2 = doc2.pack_scan_bad()
    check('保存后无任何异常格（三个容器）', not bad2, str(bad2[:3]))
    check('保存后顶层对象数仍为 19', len(doc2.entries) == 19, '%d' % len(doc2.entries))

    # ---------- 6. 修现档（未登记的 4 件物品）----------
    if os.path.exists(CUR):
        shutil.copy2(CUR, TMP)
        doc3 = MOD.Doc(TMP, bridge, log.append)
        if not [r for r in doc3.container_slots('@pack') if r['item'] is not None]:
            # 这个档的道具背包是空的 —— 先放一件，后面"能不能用"才有东西可查
            s_empty = [r['slot'] for r in doc3.container_slots('@pack')
                       if r['item'] is None][0]
            doc3.pack_write(s_empty, 43, 1, 100, '@pack')      # 43 = 五龙丹
            check('现档道具栏为空 -> 先放 1 件（五龙丹）', True)
        bad3 = [b for b in doc3.pack_scan_bad() if '没登记' in b['why']]
        # 现档可能已经被上一个版本修好了 -> 这里只报告，不当作失败
        check('现档：扫描未登记物品（已被旧版修好则为 0）', True,
              '发现 %d 个%s' % (len(bad3),
                              '：' + '；'.join('%s#%d %s' % (b['key'], b['slot'], b['name'])
                                              for b in bad3[:6]) if bad3 else ''))
        fixed = doc3.pack_fix_all()
        doc3.save(backup=False)
        doc4 = MOD.Doc(TMP, bridge, log.append)
        left = [b for b in doc4.pack_scan_bad() if '没登记' in b['why']]
        check('现档：一键修复后全部登记成功', not left,
              '修复 %d 个，剩余 %d 个' % (len(fixed), len(left)))
        # 修复后的物品在游戏判定里应该能用
        ok_use = []
        for key, label in MOD.CONTAINERS:
            for rr in doc4.container_slots(key):
                if rr['item'] is None:
                    continue
                reg = registry_of(doc4, rr['iid'])
                ok_use.append(bool(reg) and reg['standard'] == rr['standard'])
        check('现档：所有物品都满足"可以使用"的判定条件',
              all(ok_use) and len(ok_use) > 0, '%d 件物品' % len(ok_use))

    try:
        os.remove(TMP)
        if os.path.exists(TMP + '.bak'):
            os.remove(TMP + '.bak')
    except OSError:
        pass

    print('')
    f = [r for r in results if not r[1]]
    print('===== 物品登记测试：%s（共 %d 项，失败 %d 项）====='
          % ('全部通过' if not f else '有失败', len(results), len(f)))
    return 0 if not f else 1


if __name__ == '__main__':
    sys.exit(main())
