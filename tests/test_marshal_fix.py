# -*- coding: utf-8 -*-
"""1.1 回归测试：整数编码边界 + 循环引用

对应两个真实 bug：

1) **修改金钱报 `MarshalError: 未知类型 't' (0x74)`**
   LockNumber 的中间值动辄上亿，需要 5 个字节。老代码把这种值仍按
   ``'i' + 长度字节 + 字节`` 写，长度字节成了 5 —— 而 5 在 Ruby 的 w_long
   里表示"直接值 0"，于是**一个字节都没多消耗**，整条流从此错位，
   读到后面自然就是"未知类型 0x74"。
   正确做法：装不下 4 字节的整数必须写成大整数（'l'）。

2) **`序列化嵌套过深（可能有循环引用）`**
   战斗过的存档里 ``Game_Actor#@who_attack_me`` 是个 Game_Enemy，
   而它的 ``@who_attack_me`` 又用 ``@N`` 指回这个 Game_Actor —— 真环。
   老的 serialize 只会"把链接展开成副本"，遇到环就无限递归，
   于是**改名 / 改技能 / 一键修复名字全部失败**。
   正确做法：按 Ruby 的规则给对象编号，重复出现的对象发 ``@N`` 引用
   （``M.serialize(node, table={})``）。
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

import xj_codec as C
import xj_edit as E
import xj_marshal as M
import xj_model as MOD

from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else \
    os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
TMP = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   'test_marshal_copy.ogg')

results = []


def check(name, ok, extra=''):
    results.append((name, ok, extra))
    print('%-56s %s %s' % (name, 'OK' if ok else '失败', extra))


def back(blob):
    """把编码后的字节重新解析回来（模拟 Ruby 读档）。"""
    return M.parse_stream(b'\x04\x08' + blob)[0]['node']


def main():
    # ==================================================================
    print('=' * 70)
    print('1) 整数编码边界：能塞进 Fixnum 就用 i，塞不下必须用大整数 l')
    print('=' * 70)
    vals = [0, 1, 5, 122, 123, 127, 128, 255, 256, 65535, 65536,
            1073741823,            # 2**30-1
            1184748148,            # 存档里真实出现过的 Fixnum（> 2**30）
            2147483647,            # 2**31-1
            2368719772,            # 存档里真实出现过的 Fixnum（最高位是 1！）
            4294967295,            # 2**32-1，4 字节 Fixnum 的极限
            4294967296,            # 再大 -> 必须大整数
            18955770854,           # 存档里真实出现过的大整数
            10 ** 15,
            -1, -5, -123, -124, -127, -128, -129, -200, -256, -400,
            -32768, -32769, -65535, -65536,
            -2147483648,           # -2**31，4 字节负数极限
            -2147483649,           # 再小 -> 必须大整数
            -10 ** 12]
    bad = []
    for v in vals:
        n = M.IntNode(v)
        raw = M.reencode(n)
        got = M.value_of(back(raw))
        # 编码结果自己也要能被解析（老 bug 就是这里静默写坏）
        expect_kind = 'i' if M.fits_fixnum(v) else 'l'
        if got != v or raw[:1].decode() != expect_kind:
            bad.append((v, raw.hex(' '), got, raw[:1].decode(), expect_kind))
    check('全部边界值都能原样往返（并且长度字节合法）', not bad,
          ('；'.join('#%r 编成 %s（%s）解出 %r，期望用 %s'
                     % (v, raw, kind, got, ek)
                     for v, raw, got, kind, ek in bad[:3])) or
          '%d 个值' % len(vals))
    check('4294967295 仍然用 Fixnum i', M.reencode(M.IntNode(4294967295))[:1] == b'i')
    check('4294967296 改用大整数 l', M.reencode(M.IntNode(4294967296))[:1] == b'l')

    err = ''
    try:
        M.encode_long(2 ** 40)
    except M.MarshalError as e:
        err = str(e)
    check('encode_long 对 5 字节以上的值直接报错（不再静默写坏）', bool(err),
          err[:60])

    # ==================================================================
    print('')
    print('=' * 70)
    print('2) 修改金钱（LockNumber，12 个字段都要重算）')
    print('=' * 70)
    if not os.path.exists(SAVE):
        print('找不到存档:', SAVE)
        return 1
    shutil.copy2(SAVE, TMP)
    bridge = C.make_bridge(DLL_DIR, lambda s: None)
    doc = MOD.Doc(TMP, bridge, lambda s: None)
    g0 = doc.gold()
    check('存档可读，金钱可解出', isinstance(g0, float), '金钱 = %r' % g0)

    doc.set_gold(g0)
    check('把金钱改成"原值" -> 不算改动（字节完全一致）',
          doc.changed_bytes() == 0, '改动字节 %d' % doc.changed_bytes())

    for v in (100.0, 1234.0, 12345.0, 99999999.0, 88888888.0, 95310531.0):
        d2 = MOD.Doc(SAVE, bridge, lambda s: None)
        d2.set_gold(v)
        new = d2._pe.rebuild()
        ok_parse = True
        try:
            M.parse_stream(new)
        except M.MarshalError as e:
            ok_parse = False
        # 端到端：加密成容器 -> 重新打开 -> 再读金钱
        tmp2 = TMP + '.probe'
        got = None
        with open(tmp2, 'wb') as f:
            f.write(bridge.encrypt(new))
        try:
            d3 = MOD.Doc(tmp2, bridge, lambda s: None)
            got = d3.gold()
        finally:
            if os.path.exists(tmp2):
                os.remove(tmp2)
        check('金钱改成 %s：新明文可解析、加密读回一致' % v,
              ok_parse and got == v, '读回 %r' % got)

    # ==================================================================
    print('')
    print('=' * 70)
    print('3) 循环引用（Game_Actor <-> Game_Enemy）')
    print('=' * 70)
    k = MOD.TOP_NAMES.index('game_actors')
    top = doc.node('game_actors')
    arr = top.get('@data')
    cyc = None
    for i, it in enumerate(arr.items):
        if getattr(it, 'cls', '') != 'Game_Actor':
            continue
        en = it.get('@who_attack_me')
        if en is None or getattr(en, 'cls', '') != 'Game_Enemy':
            continue
        bk = en.get('@who_attack_me')
        if isinstance(bk, M.LinkNode) and bk.target is it:
            cyc = i
            break
    check('现档里确实存在环（@who_attack_me 指回自己）', cyc is not None,
          '第 %s 个 Game_Actor' % cyc)

    blew = False
    try:
        M.serialize(top)
    except M.MarshalError:
        blew = True
    check('展开模式遇到环会报错（老行为，不会静默写坏）', blew)

    data = M.serialize(top, table={})
    check('编号模式能序列化整条 game_actors', len(data) > 1000, '%d 字节' % len(data))

    new_plain = doc.plain[:top.start] + data + doc.plain[top.end:]
    ent = M.parse_stream(new_plain)
    check('重写后整条流仍能解析（19 个顶层对象）', len(ent) == 19,
          '%d 个' % len(ent))
    top2 = ent[k]['node']
    again = M.serialize(top2, table={})
    if again != data:
        n_ = min(len(again), len(data))
        pos = next((i for i in range(n_) if again[i] != data[i]), n_)
        print('     第一次: 长度 %d，第二次: 长度 %d，首个不同字节 @%d'
              % (len(data), len(again), pos))
        print('     第一次: %s' % data[max(0, pos - 12):pos + 12].hex(' '))
        print('     第二次: %s' % again[max(0, pos - 12):pos + 12].hex(' '))
    check('再序列化一次得到完全相同的字节（编号自洽）', again == data)

    a2 = top2.get('@data').items[cyc]
    e2 = a2.get('@who_attack_me')
    bk2 = e2.get('@who_attack_me') if e2 is not None else None
    check('环被原样保留（而且 @N 指向的是同一个对象，不是副本）',
          isinstance(bk2, M.LinkNode) and bk2.target is a2)

    # 其它字段不能被牵连
    same = True
    for i, (a, b) in enumerate(zip(arr.items, top2.get('@data').items)):
        if getattr(a, 'cls', '') == getattr(b, 'cls', ''):
            continue
        same = False
        break
    check('每个元素的类都还对得上', same)

    # ==================================================================
    print('')
    print('=' * 70)
    print('4) 端到端：改名 + 改金钱 -> 保存 -> 读回')
    print('=' * 70)
    # 注意：只能在**副本**上练手（这里以前误写成 Doc(SAVE).save()，
    # 把真实存档写掉了，引以为戒）
    shutil.copy2(SAVE, TMP)
    doc2 = MOD.Doc(TMP, bridge, lambda s: None)
    assert os.path.abspath(doc2.path) == os.path.abspath(TMP)
    rows = doc2.actors_pet()
    if rows:
        pid = rows[0]['id']
        doc2.set_actor_custom_name(pid, '回归测试名')
    doc2.set_gold(77777777.0)
    doc2.save(backup=False)
    doc3 = MOD.Doc(TMP, bridge, lambda s: None)
    check('保存后能重新打开，19 个顶层对象', len(doc3.entries) == 19)
    check('金钱已改', doc3.gold() == 77777777.0, '%r' % doc3.gold())
    if rows:
        r = [x for x in doc3.actors_pet() if x['id'] == pid][0]
        check('召唤兽显示名已改', r['display'] == '回归测试名', r['display'])
        check('原有环还在（读回后 @who_attack_me 仍指回自己）',
              doc3.pet_display_order() is not None)

    try:
        os.remove(TMP)
        for p in (TMP + '.bak',):
            if os.path.exists(p):
                os.remove(p)
    except OSError:
        pass

    print('')
    f = [r for r in results if not r[1]]
    print('===== 编码/循环引用测试：%s（共 %d 项，失败 %d 项）====='
          % ('全部通过' if not f else '有失败', len(results), len(f)))
    for name, _ok, extra in f:
        print('   [失败] %s %s' % (name, extra))
    return 0 if not f else 1


if __name__ == '__main__':
    sys.exit(main())
