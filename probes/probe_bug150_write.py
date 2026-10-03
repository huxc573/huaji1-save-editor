# -*- coding: utf-8 -*-
"""v1.5.1 物品栏两 bug 的回归探针（全程在临时副本上跑，不保存）。

bug 2 根因：下拉里选好模板后再点一览表的行，load_pack_edit 会用行类别
（空格默认"物品"）把用户选的类别冲掉 → 写入按错表 → 变 ?/别的物品。

bug 1：泡泡兜兜/灵石/糖果（RPG::Weapon 且 element_set 含 98，脚本 0162
右键使用→参战召唤兽装备→格子消失）按行为是物品：物品类可搜可写，
写入自动路由进 $data_weapons（baby.equip 只认它）。

只做内存操作，绝不调 save()。
"""
# --- 开发期路径引导 -----------------------------------------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import shutil
import tempfile
import tkinter as tk

import codec as C
import doctree as MOD
import marshal_ruby as M
import huaji1_save_editor as V

from paths import game_dir as _game_dir

GAME = _game_dir()
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else \
    os.path.dirname(os.path.abspath(__file__))

results = []


def check(name, ok, extra=''):
    results.append((name, ok, extra))
    print('[%s] %-48s %s' % ('OK' if ok else 'NG', name, extra))


def main():
    tmp = os.path.join(tempfile.gettempdir(), 'xj1_probe_bug151.ogg')
    shutil.copy2(SAVE, tmp)

    root = tk.Tk()
    root.withdraw()
    app = V.App(root, save_path=tmp)
    root.update()
    app.log = lambda *a, **k: None
    if app.doc is None:
        app.bridge = C.make_bridge(DLL_DIR, lambda s: None)
        app.load(tmp)
        root.update()
    if app.doc is None:
        print('!! 存档没加载成功')
        return 1

    doc = app.doc
    app.err = lambda e: print('[err] %s' % e)

    def info(slot):
        r = doc.pack_slot(slot, '@pack')
        if not r or r['item'] is None:
            return '(空)'
        st, _msg = doc.registration_state(r['iid'], r['standard'], r['kind'])
        return ('slot=%d kind=%s label=%s name=%s std=%s iid=%s reg=%s'
                % (slot, r['kind'], r['kind_label'], r['name'],
                   r['standard'], r['iid'], st))

    def first_empty():
        for slot in range(20):
            r = doc.pack_slot(slot, '@pack')
            if r and r['item'] is None:
                return slot
        return None

    def pick_from_search(kw, contains, startswith=None):
        app.var_tpl_search.set(kw)
        app.filter_templates()
        vals = list(app.cb_tpl['values'])
        s = next((v for v in vals if contains in v and
                  (startswith is None or v.startswith(startswith))), None)
        if s is None:
            return None, vals
        app.var_pack_std.set(s)
        app.on_tpl_pick()
        root.update()
        return s, vals

    # ---- A 选中装备行直接写入：原样重建 ----
    print('== A 选中装备行直接写入 ==')
    r0 = doc.pack_slot(4, '@pack')
    app.select_slot(4)
    root.update()
    app.pack_apply()
    root.update()
    r1 = doc.pack_slot(4, '@pack')
    check('A 选中装备行直接写入原样重建',
          (r1['kind'], r1['standard'], r1['iid']) ==
          (r0['kind'], r0['standard'], r0['iid']),
          '%s -> %s' % ((r0['kind'], r0['standard'], r0['iid']),
                        (r1['kind'], r1['standard'], r1['iid'])))

    # ---- B bug2 核心：选好「装备」模板后再点空格，类别不能被冲掉 ----
    print('== B 选装备模板 -> 点空格 -> 写入 ==')
    s, vals = pick_from_search('金丝', '金丝彩带')
    check('B0 下拉选中金丝彩带（装备）后锁定类别',
          s is not None and app.var_tpl_kind.get() == 'weapon'
          and getattr(app, '_picked_tpl', False),
          'pick=%r radio=%s' % (s, app.var_tpl_kind.get()))
    es = first_empty()
    app.select_slot(es)          # 点空格（旧版这里会把类别顶回"物品"）
    root.update()
    ok_radio = app.var_tpl_kind.get() == 'weapon'
    app.pack_apply()
    root.update()
    r = doc.pack_slot(es, '@pack')
    check('B1 点空格后类别仍是装备', ok_radio,
          'radio=%s' % app.var_tpl_kind.get())
    check('B2 写入走 $data_weapons 且名字正确',
          r['item'] is not None and r['kind'] == 'weapon'
          and r['standard'] == 56 and r['name'] == '金丝彩带'
          and doc.registration_state(r['iid'], r['standard'], r['kind'])[0] == 'ok',
          info(es))

    # ---- C bug1：泡泡兜兜按物品类写入，自动路由进装备表 ----
    print('== C 物品类写泡泡兜兜 ==')
    s, vals = pick_from_search('泡泡兜兜', '泡泡兜兜')
    print('   下拉命中:', vals)
    check('C0 泡泡兜兜列在物品类',
          any('泡泡兜兜（物品）' in v and v.startswith('468 |') for v in vals),
          'pick=%r' % s)
    check('C1 物品类选中后 radio=物品',
          s is not None and app.var_tpl_kind.get() == 'item',
          'radio=%s' % app.var_tpl_kind.get())
    es = first_empty()
    app.select_slot(es)
    root.update()
    app.pack_apply()
    root.update()
    r = doc.pack_slot(es, '@pack')
    node = r['item']
    check('C2 写入路由进 $data_weapons（RPG::Weapon + @identify）',
          node is not None and node.cls == 'RPG::Weapon'
          and r['kind'] == 'weapon' and r['standard'] == 468
          and doc.registration_state(r['iid'], r['standard'], 'weapon')[0] == 'ok'
          and (MOD.E.find_ivar(node, '@identify') is not None
               if hasattr(MOD, 'E') else
               M_find(node, '@identify') is not None),
          info(es))
    check('C3 新实例 id 并进泡泡职业 weapon_set（照 random_weapon）',
          doc.class_weapon_set_has(15, r['iid'])
          if hasattr(doc, 'class_weapon_set_has') else _ws_has(doc, 15, r['iid']),
          'iid=%s' % r['iid'])

    # ---- D 点宠物武器行：类别显示/切到"物品"，写入仍是装备表并复用原实例 ----
    print('== D 宠物武器行往返 ==')
    pslot = next(s for s in range(20)
                 if (doc.pack_slot(s, '@pack') or {}).get('standard') == 468)
    r0 = doc.pack_slot(pslot, '@pack')
    app._picked_tpl = False
    app.select_slot(pslot)
    root.update()
    check('D1 宠物武器行类别列显示"物品"', r0['kind_label'] == '物品',
          'label=%s' % r0['kind_label'])
    check('D2 点行后 radio=物品', app.var_tpl_kind.get() == 'item',
          'radio=%s' % app.var_tpl_kind.get())
    app.pack_apply()
    root.update()
    r = doc.pack_slot(pslot, '@pack')
    check('D3 写入后仍是装备表实例且复用原 id',
          r['kind'] == 'weapon' and r['standard'] == 468
          and r['iid'] == r0['iid']
          and doc.registration_state(r['iid'], r['standard'], 'weapon')[0] == 'ok',
          '%s -> %s' % ((r0['kind'], r0['iid']), (r['kind'], r['iid'])))

    # ---- E 模板列表：装备类不含宠物武器、物品类含 ----
    tps_w = dict(doc.templates('weapon'))
    tps_i = dict(doc.templates('item'))
    pet = sorted(i for i in doc._pet_weapon_ids() if 400 < i < 500)
    check('E1 装备类下拉不再列出宠物武器(400~500 段)',
          all(i not in tps_w for i in pet), 'pet=%s' % pet[:5])
    check('E2 物品类下拉列出泡泡兜兜 468',
          tps_i.get(468) == '泡泡兜兜', '%r' % tps_i.get(468))
    check('E3 物品类模板名仍以真物品优先（467=大海龟糖果在装备表）',
          doc.template_name('item', 87) != '?' and
          doc.template_name('item', 468) == '泡泡兜兜',
          '87=%s 468=%s' % (doc.template_name('item', 87),
                            doc.template_name('item', 468)))

    # ---- F 真档副本一键修复不应误报（回归 1.5.0 的 B 组） ----
    bad = doc.pack_scan_bad()
    check('F pack_scan_bad() = 0', not bad, repr(bad)[:120])

    ok = all(o for _n, o, _e in results)
    print('===== 探针：%s（%d/%d）====='
          % ('全部通过' if ok else '有失败',
             sum(1 for _n, o, _e in results if o), len(results)))
    root.destroy()
    os.remove(tmp)
    return 0 if ok else 1


def M_find(node, name):
    from marshal_ruby import value_of
    iv = node.get(name) if hasattr(node, 'get') else None
    return iv


def _ws_has(doc, class_id, iid):
    import marshal_ruby as M
    carr = doc._db('data_classes', 'Classes.rxdata')
    cn = carr[class_id]
    ws = cn.get('@weapon_set')
    return isinstance(ws, M.ArrayNode) and iid in [M.value_of(x) for x in ws.items]


if __name__ == '__main__':
    sys.exit(main())
