# -*- coding: utf-8 -*-
"""0.4 物品修复测试

覆盖：
  1. 写入空格：数量 0 / 品质 0（或空）时，必须得到 数量 1、@quality=100、@standard=模板id
  2. 物品实例必须有 @quality 字段（0.3 的 bug 就是缺这个字段 ->"该物品无法使用"）
  3. 已有物品的格子重建：沿用原实例 id，数量/品质按输入
  4. 坏格子（缺 @quality）能靠"重新写入"修好
  5. 数量 < 1 会被拒绝（提示用删除按钮）
  6. 「全部解析数据」右键用的通用标量修改 set_node_value
  7. 保存 -> 重新解密读回，与元素对比只改了预期字段

测试用临时副本，不动正式存档。
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
import xj_edit as E
import xj_marshal as M
import xj_model as MOD

from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
TMP = os.path.join(HERE, 'test_pack_copy.ogg')
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE

TPL_ID = 87          # 祈福酒肆
results = []


def check(name, ok, extra=''):
    results.append((name, ok, extra))
    print('%-46s %s %s' % (name, 'OK' if ok else '失败', extra))


def fields_of(node):
    return [k for k, _ in node.ivars]


def main():
    shutil.copy2(SAVE, TMP)
    log = []
    bridge = C.make_bridge(DLL_DIR, log.append)
    doc = MOD.Doc(TMP, bridge, log.append)

    empty = [r['slot'] for r in doc.pack() if r['item'] is None]
    used = [r['slot'] for r in doc.pack() if r['item'] is not None]
    check('存档可读', len(empty) >= 2 and used, '空格 %s 在用 %s'
          % (empty[:4], used[:3]))

    # ---------- 1. make_pack_entry 不传品质也要有 @quality ----------
    tpl = doc._db('data_items', 'Items.rxdata')[TPL_ID]
    cell = E.make_pack_entry(tpl, 0, standard_id=TPL_ID)   # 数量 0、品质不传
    inst = cell.items[0]
    names = fields_of(inst)
    check('make_pack_entry 生成 27 字段（模板 25 + standard + quality）',
          len(names) == 27 and '@quality' in names and '@standard' in names,
          '%d 字段' % len(names))
    check('数量 0 被兜底成 1', M.value_of(cell.items[1]) == 1,
          '数量 %s' % M.value_of(cell.items[1]))

    # ---------- 2. 写入空格：数量 0 / 品质 0 ----------
    s0 = empty[0]
    info = doc.pack_write(s0, TPL_ID, 0, 0)   # 故意给 0 / 0
    r = doc.pack_slot(s0)
    check('写入空格（数量 0、品质 0）', r['item'] is not None and r['count'] == 1
          and r['quality'] == 100 and r['standard'] == TPL_ID,
          '数量 %s 品质 %s 模板 %s' % (r['count'], r['quality'], r['standard']))
    check('实例字段 27 个（含 @quality）',
          len(fields_of(r['item'])) == 27 and E.find_ivar(r['item'], '@quality') is not None,
          '%d 字段' % len(fields_of(r['item'])))
    check('实例 id 自动分配（>=1001 且唯一）', isinstance(r['iid'], int) and r['iid'] >= 1001,
          '实例 id %s' % r['iid'])

    # ---------- 3. 写物品用不填品质 ----------
    s1 = empty[1]
    doc.pack_write(s1, 3, 7)                  # 佛手 ×7，品质默认
    r1 = doc.pack_slot(s1)
    check('写入时省略品质 -> 默认 100', r1['quality'] == 100 and r1['count'] == 7,
          '数量 %s 品质 %s' % (r1['count'], r1['quality']))

    # ---------- 4. 重建已有格子：换模板 -> 分配新登记槽 ----------
    old_iid = doc.pack_slot(used[0])['iid']
    old_std = doc.pack_slot(used[0])['standard']
    n_before = len(doc.item_db_array())
    info2 = doc.pack_write(used[0], TPL_ID, 33, 100)
    r2 = doc.pack_slot(used[0])
    check('换模板：分配新登记槽并登记',
          r2['iid'] == n_before and r2['count'] == 33
          and doc.item_registered(r2['iid'], TPL_ID)
          and old_std != TPL_ID,
          '实例 id %s -> %s，数量 %s' % (old_iid, r2['iid'], r2['count']))
    new_iid = r2['iid']
    # 同模板再改一次（只改数量）-> 应沿用刚才的槽
    doc.pack_write(used[0], TPL_ID, 33, 100)
    check('同模板只改数量：沿用登记槽', doc.pack_slot(used[0])['iid'] == new_iid,
          '实例 id %s' % doc.pack_slot(used[0])['iid'])

    # ---------- 5. 制造坏格子（缺 @quality）再修好 ----------
    bad = E.clone_node(tpl)
    bad.ivars.append(('@standard', M.IntNode(TPL_ID)))    # 故意不加 @quality
    arr = doc.node('data').get('@pack')
    doc.begin_edit().set_array_element(arr, used[1], M.ArrayNode([bad, M.IntNode(5)]))
    rb = doc.pack_slot(used[1])
    check('坏格子：确实缺 @quality', rb['quality'] is None,
          '品质 %s，字段 %d 个' % (rb['quality'], len(fields_of(rb['item']))))
    doc.pack_write(used[1], rb['standard'], rb['count'], rb['quality'])   # 就是界面上点一下"写入"
    rb2 = doc.pack_slot(used[1])
    check('重新写入后修好（品质 100、27 字段）',
          rb2['quality'] == 100 and len(fields_of(rb2['item'])) == 27,
          '品质 %s，字段 %d 个' % (rb2['quality'], len(fields_of(rb2['item']))))

    # ---------- 5b. 一键修复异常格 ----------
    bad2 = E.clone_node(tpl)
    bad2.ivars.append(('@standard', M.IntNode(TPL_ID)))    # 同样缺 @quality
    doc.begin_edit().set_array_element(doc.node('data').get('@pack'), used[2],
                                       M.ArrayNode([bad2, M.IntNode(0)]))
    scan = doc.pack_scan_bad()
    hit = [x for x in scan if x['slot'] == used[2]]
    check('扫描发现异常格（缺品质 + 数量 0）', bool(hit),
          hit[0]['why'] if hit else '没发现')
    fixed = doc.pack_fix_all()
    rf = doc.pack_slot(used[2])
    check('一键修复后恢复正常', used[2] in [s for _k, s in fixed]
          and rf['quality'] == 100
          and rf['count'] == 1 and len(fields_of(rf['item'])) == 27,
          '修了 %s，品质 %s 数量 %s 字段 %d'
          % (fixed, rf['quality'], rf['count'], len(fields_of(rf['item']))))
    check('修复后不再报异常', not doc.pack_scan_bad(),
          '剩余 %d 个' % len(doc.pack_scan_bad()))

    # ---------- 6. 数量 < 1 应被拒绝 ----------
    try:
        doc.set_pack_count(s0, 0)
        check('数量 0 被拒绝', False, '竟然没报错')
    except Exception as e:
        check('数量 0 被拒绝（提示用删除）', '数量至少是 1' in str(e), str(e)[:40])

    # ---------- 7. 通用标量修改（解析树右键用的） ----------
    sw = doc.ivar('game_switches', '@data').items[0]
    doc.set_node_value(sw, True)
    check('set_node_value 改开关', doc.switches()[0][1] is True,
          '值 %s' % doc.switches()[0][1])
    try:
        doc.set_node_value(doc.node('data'), 1)
        check('非标量节点被拒绝', False, '竟然没报错')
    except Exception as e:
        check('非标量节点被拒绝', '只有标量' in str(e) or '不能直接改' in str(e), str(e)[:36])
    var = doc.ivar('game_variables', '@data').items[3]
    doc.set_node_value(var, 4321)
    check('set_node_value 改变量', doc.variables()[3][1] == 4321,
          '值 %s' % doc.variables()[3][1])

    # ---------- 8. 物品 id 不存在 / 格子越界 ----------
    try:
        doc.pack_write(s0, 999999, 1, 100)
        check('不存在的物品 id 被拒绝', False, '竟然没报错')
    except Exception as e:
        check('不存在的物品 id 被拒绝', '不存在' in str(e), str(e)[:36])
    try:
        doc.pack_write(99, TPL_ID, 1, 100)
        check('越界格子被拒绝', False, '竟然没报错')
    except Exception as e:
        check('越界格子被拒绝', '格子号' in str(e), str(e)[:36])

    # ---------- 9. 保存 + 读回 ----------
    doc.save(backup=False)
    doc2 = MOD.Doc(TMP, bridge, log.append)
    a = doc2.pack_slot(s0)
    b = doc2.pack_slot(s1)
    c = doc2.pack_slot(used[0])
    d = doc2.pack_slot(used[1])
    e = doc2.pack_slot(used[2])
    ok = (a['item'] is not None and a['count'] == 1 and a['quality'] == 100
          and b['count'] == 7 and b['quality'] == 100
          and c['count'] == 33 and c['iid'] == new_iid and c['standard'] == TPL_ID
          and d['quality'] == 100 and len(fields_of(d['item'])) == 27
          and e['quality'] == 100 and e['count'] == 1)
    check('保存后读回全部正确', ok,
          '新增格 数量%s 品质%s/%s 重建格 数量%s 修复格 品质%s 品质%s'
          % (a['count'], a['quality'], b['quality'], c['count'],
             d['quality'], e['quality']))
    check('物品栏在用格数 +2', doc2.pack_used() == len(used) + 2,
          '%d -> %d' % (len(used), doc2.pack_used()))
    check('顶层对象数不变', len(doc2.entries) == 19, '%d' % len(doc2.entries))

    # ---------- 10. 结构对比：变化都在预期前缀内 ----------
    ref = MOD.Doc(SAVE, bridge, log.append)
    diffs = diff_prefixes(ref.node('data'), doc2.node('data'))
    bad = [x for x in diffs if not (x.startswith('data.@pack')
                                    or x.startswith('data.@wallet')
                                    or x.startswith('data.@talisman')
                                    or x.startswith('data.@fame'))]
    check('data 里只有三个容器/声望变了', not bad, '变化 %d 处：%s'
          % (len(diffs), ', '.join(sorted(set(x.split('[')[0]
                                              for x in diffs))[:6])))

    try:
        os.remove(TMP)
        if os.path.exists(TMP + '.bak'):
            os.remove(TMP + '.bak')
    except OSError:
        pass

    print('')
    f = [r for r in results if not r[1]]
    print('===== 0.4 物品测试：%s（共 %d 项，失败 %d 项）====='
          % ('全部通过' if not f else '有失败', len(results), len(f)))
    return 0 if not f else 1


def diff_prefixes(n1, n2, path='data', out=None, depth=0):
    """递归比较两棵树，返回所有取值不同的路径（用于确认只改了预期字段）。"""
    out = [] if out is None else out
    if depth > 20 or type(n1) is not type(n2):
        out.append(path)
        return out
    if isinstance(n1, M.ArrayNode):
        if len(n1.items) != len(n2.items):
            out.append(path)
            return out
        for i, (a, b) in enumerate(zip(n1.items, n2.items)):
            diff_prefixes(a, b, '%s[%d]' % (path, i), out, depth + 1)
    elif isinstance(n1, (M.ObjNode, M.StructNode, M.IVarNode)):
        d1, d2 = dict(n1.ivars), dict(n2.ivars)
        if set(d1) != set(d2):
            out.append(path)
            return out
        for k in d1:
            diff_prefixes(d1[k], d2[k], '%s.%s' % (path, k), out, depth + 1)
    elif isinstance(n1, M.HashNode):
        if len(n1.pairs) != len(n2.pairs):
            out.append(path)
            return out
        for (k1, v1), (k2, v2) in zip(n1.pairs, n2.pairs):
            diff_prefixes(v1, v2, '%s.%s' % (path, MOD.value_text(k1, 20)), out, depth + 1)
    else:
        try:
            raw1 = M.reencode(n1)
            raw2 = M.reencode(n2)
        except Exception:
            raw1, raw2 = b'?1', b'?2'
        if raw1 != raw2:
            out.append(path)
    return out


if __name__ == '__main__':
    sys.exit(main())
