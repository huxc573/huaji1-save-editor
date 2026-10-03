# -*- coding: utf-8 -*-
"""物品容器「按实例类别分表」测试（1.5.0）

起因（用户报「少了泡泡兜兜」）：它不在 Items.rxdata，而在 Weapons.rxdata[468]。
1.4.0 以前整条物品栏只认 $data_items，于是：

  1. 装备(Weapon)/防具(Armor)的模板名查错表；
  2. 「登记」列对装备格全判 ✘；
  3. ★「一键修复异常格」会把这些装备格按 $data_items 重建
     —— 真档 15 格装备（银腰带/珍珠链/马靴…）会被换成狼●孵化蛋一类的东西（毁档）。

覆盖：
  A. 类别模板表：item / weapon / armor 三张都取得到，weapon 里有 468 泡泡兜兜
  B. 真档副本 pack_scan_bad() = 0（装备格不再误判）
  C. 写装备：走 $data_weapons 登记、补 @identify、不写 @quality、名字正确
  D. 写防具：走 $data_armors
  E. 写物品：仍走 $data_items（回归）
  F. 装备新实例 id 并进职业 weapon_set（照游戏 random_weapon）
  G. 保存 -> 重新解密读回：只改了 data / data_items / data_weapons /
     data_armors / data_classes；顶层对象数不变
  H. 故意缺 @identify 的装备格能被扫出并按装备模板修好
  I. 错误路径：id 越界 / 类别不对时的提示

测试全程在临时副本上跑，不动正式存档。
"""
# --- 开发期路径引导：让 import 项目模块找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import hashlib
import os
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))

import codec as C
import patchwriter as E
import marshal_ruby as M
import doctree as MOD

from paths import game_dir as _game_dir
GAME = _game_dir()
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
TMP = os.path.join(HERE, 'test_pack_kinds_copy.ogg')
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE

BUBBLE = 468          # $data_weapons[468] = 泡泡兜兜
PEARL = 139           # $data_armors[139] = 珍珠链
ITEM = 87             # $data_items[87] = 祈福酒肆

results = []


def check(name, ok, extra=''):
    results.append((name, ok, extra))
    print('[%s] %-46s %s' % ('OK' if ok else 'NG', name, extra))


def md5(path):
    h = hashlib.md5()
    with open(path, 'rb') as f:
        for blk in iter(lambda: f.read(1 << 20), b''):
            h.update(blk)
    return h.hexdigest()


def fields_of(node):
    return [k for k, _ in node.ivars]


def node_sig(n, depth=0):
    """整棵子树的**语义**指纹。

    ⚠ 不能比原始字节：新增实例会让全局对象编号平移，所有 '@N' 链接的号码都变
    （而指向的东西没变）。所以这里先把链接解开，再递归成元组。
    """
    if depth > 40:
        return '...'
    n = MOD.deref(n)
    if isinstance(n, M.LinkNode):
        # 没解开的链接：'@N' 的号码会因插入新实例而整体平移，不比号码本身
        return ('L',)
    if isinstance(n, M.ArrayNode):
        return ('A', len(n.items), tuple(node_sig(x, depth + 1) for x in n.items))
    if isinstance(n, M.HashNode):
        return ('H', tuple((node_sig(k, depth + 1), node_sig(v, depth + 1))
                           for k, v in n.pairs))
    if hasattr(n, 'ivars'):
        return ('O', getattr(n, 'cls', type(n).__name__),
                tuple((k, node_sig(v, depth + 1)) for k, v in n.ivars))
    try:
        return M.reencode(n)
    except Exception:
        # ⚠ 别用 repr(n)：里面带对象地址（0x…），两边永远不相等（踩过这个坑）
        d = getattr(n, 'data', None)
        if isinstance(d, (bytes, bytearray)):
            return ('UD', len(d), bytes(d))
        return (type(n).__name__,)


def main():
    real_md5 = md5(SAVE)
    shutil.copy2(SAVE, TMP)
    log = []
    bridge = C.make_bridge(DLL_DIR, log.append)
    doc = MOD.Doc(TMP, bridge, log.append)

    # ---------- A. 三张类别模板表 ----------
    tp = {k: doc.templates(k) for k in ('item', 'weapon', 'armor')}
    for k, label in (('item', '物品'), ('weapon', '装备'), ('armor', '防具')):
        check('类别模板表 %s 取得到（%d 项）' % (label, len(tp[k])), len(tp[k]) > 0)
    wid = [i for i, n in tp['weapon'] if n == '泡泡兜兜']
    check('装备表里有「泡泡兜兜」', wid == [BUBBLE], 'id=%s' % wid)
    aid = [i for i, n in tp['armor'] if n == '珍珠链']
    check('防具表里有「珍珠链」', PEARL in aid, 'id=%s' % aid[:4])

    # ---------- B. 真档副本不该有任何"异常格" ----------
    bad0 = doc.pack_scan_bad()
    check('真档副本 pack_scan_bad() = 0（装备格不再误判）',
          len(bad0) == 0, '报了 %d 个' % len(bad0))

    # 找一个空格（三个容器都可以，先看 @pack）
    def first_empty(key):
        for r in doc.container_slots(key):
            if r['item'] is None:
                return r['slot']
        return None

    s_w = first_empty('@pack')
    check('道具栏有空位可写（第 %s 格）' % s_w, s_w is not None)

    # ---------- C. 写装备：泡泡兜兜 ----------
    info = doc.pack_write(s_w, BUBBLE, 1, None, '@pack', kind='weapon')
    r = doc.pack_slot(s_w, '@pack')
    check('写入装备：类是 Weapon', r['kind'] == 'weapon' and r['kind_label'] == '装备',
          'kind=%s' % r['kind'])
    check('写入装备：模板名 = 泡泡兜兜', r['template_name'] == '泡泡兜兜',
          r['template_name'])
    check('写入装备：显示名不带 ",HP,SP,等级"', r['name'] == '泡泡兜兜',
          '名字 %r' % r['name'])
    flds = fields_of(r['item'])
    check('装备实例补了 @identify、没有 @quality',
          '@identify' in flds and '@quality' not in flds, '%d 字段' % len(flds))
    check('装备实例登记进 $data_weapons',
          doc.item_registered(r['iid'], BUBBLE, 'weapon'), '实例 id %s' % r['iid'])
    check('装备实例没被错登记进 $data_items',
          not doc.item_registered(r['iid'], BUBBLE, 'item'), '实例 id %s' % r['iid'])
    check('返回信息带 kind/kind_label', info.get('kind') == 'weapon'
          and info.get('kind_label') == '装备')

    # ---------- D. 写防具 ----------
    s_a = first_empty('@wallet')
    doc.pack_write(s_a, PEARL, 1, None, '@wallet', kind='armor')
    ra = doc.pack_slot(s_a, '@wallet')
    check('写入防具：类 = 防具、登记进 $data_armors',
          ra['kind'] == 'armor' and doc.item_registered(ra['iid'], PEARL, 'armor'),
          '名字 %s / 实例 id %s' % (ra['template_name'], ra['iid']))
    check('防具实例也只补 @identify',
          '@identify' in fields_of(ra['item'])
          and '@quality' not in fields_of(ra['item']))

    # ---------- E. 写物品（回归） ----------
    s_i = first_empty('@talisman')
    doc.pack_write(s_i, ITEM, 3, 100, '@talisman', kind='item')
    ri = doc.pack_slot(s_i, '@talisman')
    check('写入物品：仍走 $data_items、带 @quality',
          ri['kind'] == 'item' and '@quality' in fields_of(ri['item'])
          and doc.item_registered(ri['iid'], ITEM, 'item'),
          '%s ×%s' % (ri['template_name'], ri['count']))

    # ---------- F. 新装备 id 并进职业 weapon_set ----------
    cls_arr = doc._db('data_classes', 'Classes.rxdata')
    owners = []
    for i, c in enumerate(cls_arr):
        if not isinstance(c, M.ObjNode):
            continue
        ws = c.get('@weapon_set')
        if isinstance(ws, M.ArrayNode):
            vals = [M.value_of(x) for x in ws.items]
            if BUBBLE in vals and r['iid'] in vals:
                owners.append(i)
    check('新装备 id 已并进"可装备该模板"的职业 weapon_set',
          bool(owners), '职业 %s' % owners[:6])

    # ---------- 同模板只改数量应沿用槽 ----------
    doc.pack_write(s_w, BUBBLE, 5, None, '@pack', kind='weapon')
    check('同模板只改数量：沿用登记槽',
          doc.pack_slot(s_w, '@pack')['iid'] == r['iid'],
          '实例 id %s' % doc.pack_slot(s_w, '@pack')['iid'])
    check('数量已改成 5', doc.pack_slot(s_w, '@pack')['count'] == 5)

    # ---------- I. 错误路径 ----------
    for label, kwargs in (('装备 id 越界', dict(kind='weapon')),
                          ('物品 id 越界', dict(kind='item'))):
        try:
            doc.pack_write(s_i, 999999, 1, 100, '@talisman', **kwargs)
            check('%s 会被拒绝' % label, False, '没报错')
        except E.EditError as e:
            check('%s 会被拒绝' % label, True, str(e)[:34])

    # ---------- 保存 -> 重新读回 ----------
    doc.save()
    d2 = MOD.Doc(TMP, bridge, log.append)
    ref = MOD.Doc(SAVE, bridge, log.append)          # 没动过的真档，只读
    r2 = d2.pack_slot(s_w, '@pack')
    check('重读：装备还在、名字/登记都对',
          r2['kind'] == 'weapon' and r2['name'] == '泡泡兜兜'
          and d2.item_registered(r2['iid'], BUBBLE, 'weapon'),
          '%s / 实例 id %s' % (r2['template_name'], r2['iid']))
    check('重读：防具与物品也在',
          d2.pack_slot(s_a, '@wallet')['kind'] == 'armor'
          and d2.pack_slot(s_i, '@talisman')['kind'] == 'item')
    check('重读：顶层对象数仍是 19', len(d2.entries) == 19, '%d' % len(d2.entries))
    check('重读：真档仍是 0 个异常格', len(d2.pack_scan_bad()) == 0,
          '%d 个' % len(d2.pack_scan_bad()))

    # 只有预期的那几个顶层对象变了
    # （跟"没动过的真档"重新解析出来的一份比 —— 浏览器里那份已经被就地改过，
    #   而且保存时会把被重写的对象里的 '@N' 链接展开，跟内存态不可直接比）
    changed = []
    for name in MOD.TOP_NAMES:
        n1, n2 = ref.node(name), d2.node(name)
        if n1 is None or n2 is None:
            continue
        if node_sig(n1) != node_sig(n2):
            changed.append(name)
    allow = {'data', 'data_items', 'data_weapons', 'data_armors', 'data_classes'}
    check('改动只落在容器/三张登记表/职业表',
          set(changed) <= allow, '变了：%s' % (changed or '无'))

    # ---------- H. 缺 @identify 的装备格：能扫出、能按装备模板修好 ----------
    d3 = MOD.Doc(TMP, bridge, log.append)
    arr = d3.container_node('@pack')
    cell = arr.items[s_w]
    inst = cell.items[0]
    inst.ivars = [(k, v) for k, v in inst.ivars if k != '@identify']
    hit = [b for b in d3.pack_scan_bad() if b['slot'] == s_w and b['kind'] == 'weapon']
    check('缺 @identify 的装备格能被扫出', bool(hit),
          hit[0]['why'][:40] if hit else '没扫到')
    fixed = d3.pack_fix_all()
    r3 = d3.pack_slot(s_w, '@pack')
    check('修复后：仍是装备、名字还是泡泡兜兜',
          r3['kind'] == 'weapon' and r3['name'] == '泡泡兜兜'
          and '@identify' in fields_of(r3['item']) and (s_w in [x[1] for x in fixed]),
          '修了 %s' % (fixed,))
    check('修复后不再有异常格', len(d3.pack_scan_bad()) == 0,
          '%d 个' % len(d3.pack_scan_bad()))

    # 真档没被动过
    check('正式存档 md5 未变', md5(SAVE) == real_md5)

    try:
        os.remove(TMP)
        if os.path.exists(TMP + '.bak'):
            os.remove(TMP + '.bak')
    except OSError:
        pass

    print('')
    f = [x for x in results if not x[1]]
    print('===== 物品类别分表测试：%s（共 %d 项，失败 %d 项）====='
          % ('全部通过' if not f else '有失败', len(results), len(f)))
    return 0 if not f else 1


if __name__ == '__main__':
    sys.exit(main())
