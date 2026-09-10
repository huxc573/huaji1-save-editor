# -*- coding: utf-8 -*-
"""
0.3 端到端测试：在**副本**上把能改的都改一遍，保存后重新解密逐项核对，
并做结构对比，确认只改了预期位置、存档没被改坏。
"""
# --- 开发期路径引导：让 import xj_* 找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import hashlib
import io
import os
import shutil
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

HERE = os.path.dirname(os.path.abspath(__file__))
TRY = os.path.dirname(os.path.dirname(HERE))
from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
EXE_DIR = os.path.join(TRY, 'Exe', '0.3')
sys.path.insert(0, HERE)

import xj_codec as C
import xj_edit as E
import xj_marshal as M
import xj_model as MOD

SRC = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
TMP = os.path.join(HERE, 'test_copy.ogg')
LOG = os.path.join(HERE, 'test_edit_out.txt')

_lines = []
ok = True


def say(s=''):
    print(s)
    _lines.append(s)


def check(label, cond, extra=''):
    global ok
    ok = ok and bool(cond)
    say('%s %-40s %s' % ('[OK]' if cond else '[失败]', label, extra))


def main():
    global ok
    shutil.copyfile(SRC, TMP)
    dll_dir = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else EXE_DIR
    bridge = C.make_bridge(dll_dir, log=lambda s: None)
    say('加解密通道：%s' % type(bridge).__name__)

    doc = MOD.Doc(TMP, bridge, log=lambda s: None)
    say('打开成功：明文 %d 字节，%d 个顶层对象' % (len(doc.plain), len(doc.entries)))
    say('原始：金钱=%s 角色=%d 物品栏在用=%d/%d'
        % (doc.gold(), len(doc.actor_rows()), doc.pack_used(), doc.PACK_SIZE))
    for r in doc.pack():
        say('   [%2d] %-16s 模板%-5s 实例%-6s 数量%-4s 品质%s'
            % (r['slot'], r['name'], r['standard'], r['iid'], r['count'], r['quality']))
    # 诊断：某些格的 @name 是链接，看能否解开
    for r in doc.pack()[:4]:
        if r['item'] is not None:
            nm = r['item'].get('@name')
            tgt = nm.target if isinstance(nm, M.LinkNode) else None
            say('   [%2d] @name 节点=%s  target=%s  解开后=%s'
                % (r['slot'], type(nm).__name__, type(tgt).__name__ if tgt else None,
                   MOD.stext(nm, '<空>')))
    say('本机机器码 = %s' % doc.machine_id_now())
    say('')

    aid = doc.actor_rows()[0]['id']
    say('测试角色 ID = %s（%s）' % (aid, doc.actor(aid).name if hasattr(doc.actor(aid), 'name') else ''))
    used_slots = [r['slot'] for r in doc.pack() if r['item'] is not None]
    say('已占用的物品格：%s' % used_slots)
    say('')

    # ---------------- 改 ----------------
    say('---- 开始修改 ----')
    doc.set_gold(88888888)
    doc.set_fame(999)
    doc.set_store_cash(6666)
    doc.set_steps(12345)
    doc.set_actor_level(aid, 99)
    for ivar in ('@tizhi', '@moli', '@liliang', '@naili', '@minjie'):
        doc.set_actor_field(aid, ivar, 300)
    doc.set_actor_field(aid, '@latent', 888)
    hp, sp = doc.heal_actor(aid)
    say('角色 %s：等级 99，五维 300，潜力 888，HP/SP -> %s/%s' % (aid, hp, sp))

    if used_slots:
        s0 = used_slots[0]
        doc.set_pack_count(s0, 77)
        say('第 %d 格数量 -> 77' % s0)
        if len(used_slots) > 1:
            s1 = used_slots[1]
            doc.pack_delete(s1)
            say('第 %d 格已清空' % s1)
    empty = [i for i in range(doc.PACK_SIZE)
             if doc.pack_slot(i)['item'] is None]
    if empty:
        s2 = empty[0]
        doc.pack_add(s2, 87, 9)          # 87 = 祈福酒肆
        say('第 %d 格新增模板 87（祈福酒肆）×9' % s2)
    doc.set_switch(0, True)
    doc.set_variable(3, 4321)
    doc.set_machine_id('AAAABBBBCCCCDDDD')
    say('开关0=True，变量3=4321，机器码 -> AAAABBBBCCCCDDDD')
    say('待写入改动 %d 字节' % doc.changed_bytes())

    # ---------------- 保存 ----------------
    say('')
    say('---- 保存并校验 ----')
    path = doc.save(TMP, backup=True)
    say('已保存：%s（备份 %s.bak）' % (path, os.path.basename(path)))
    check('备份文件已生成', os.path.exists(TMP + '.bak'))

    # ---------------- 重新打开核对 ----------------
    say('')
    say('---- 重新解密核对 ----')
    bridge2 = C.make_bridge(dll_dir, log=lambda s: None)
    doc2 = MOD.Doc(TMP, bridge2, log=lambda s: None)
    check('顶层对象数不变', len(doc2.entries) == len(doc.entries),
          '%d -> %d' % (len(doc.entries), len(doc2.entries)))
    check('金钱 = 88888888（LockNumber 6 组一致）',
          abs(doc2.gold() - 88888888) < 0.5, doc2.gold())
    check('声望 = 999', M.value_of(doc2.node('data').get('@fame')) == 999)
    check('仓库金额 = 6666',
          M.value_of(doc2.node('data').get('@store_cash')) == 6666)
    check('步数 = 12345',
          M.value_of(doc2.node('game_party').get('@steps')) == 12345)
    a2 = doc2.actor(aid)
    check('等级 = 99', M.value_of(a2.get('@level')) == 99)
    check('经验已同步', M.value_of(a2.get('@exp')) == MOD.exp_for_level(aid, 99),
          M.value_of(a2.get('@exp')))
    check('五维 = 300', all(M.value_of(a2.get(k)) == 300 for k in
                          ('@tizhi', '@moli', '@liliang', '@naili', '@minjie')))
    check('潜力 = 888', M.value_of(a2.get('@latent')) == 888)
    check('HP/SP 已填满',
          (M.value_of(a2.get('@hp')), M.value_of(a2.get('@sp'))) == (hp, sp),
          '%s/%s' % (M.value_of(a2.get('@hp')), M.value_of(a2.get('@sp'))))
    if used_slots:
        check('物品数量 = 77', doc2.pack_slot(used_slots[0])['count'] == 77,
              doc2.pack_slot(used_slots[0])['count'])
    if empty:
        r = doc2.pack_slot(empty[0])
        check('新增物品：模板 87 名称正确', r['standard'] == 87 and r['name'] == '祈福酒肆',
              '%s / 模板%s' % (r['name'], r['standard']))
        check('新增物品数量 = 9', r['count'] == 9)
        item = r['item']
        check('新增物品是完整 RPG::Item（27 字段 = 模板 25 + @standard + @quality）',
              isinstance(item, M.ObjNode) and item.cls == 'RPG::Item'
              and len(item.ivars) == 27
              and any(k == '@quality' for k, _ in item.ivars),
              '%s，%d 个字段' % (item.cls if isinstance(item, M.ObjNode) else '?',
                               len(item.ivars) if isinstance(item, M.ObjNode) else 0))
    check('开关0 = True', doc2.switches()[0][1] is True)
    check('变量3 = 4321', doc2.variables()[3][1] == 4321, doc2.variables()[3])
    check('机器码已改', doc2.machine_ids() == ['AAAABBBBCCCCDDDD'], doc2.machine_ids())

    # ---------------- 结构对比 ----------------
    say('')
    say('---- 与原始存档做逐字段对比 ----')
    ref = MOD.Doc(SRC, C.make_bridge(dll_dir, log=lambda s: None), log=lambda s: None)
    diff = []

    def walk(x, y, path):
        if isinstance(x, (M.ObjNode, M.StructNode)) and isinstance(y, type(x)):
            if len(x.ivars) != len(y.ivars):
                diff.append(path + '(字段数变化)')
                return
            for (k, va), (_, vb) in zip(x.ivars, y.ivars):
                walk(va, vb, path + '.' + k)
        elif isinstance(x, M.ArrayNode) and isinstance(y, M.ArrayNode):
            if len(x.items) != len(y.items):
                diff.append('%s(数组长度 %d->%d)' % (path, len(x.items), len(y.items)))
                return
            for i, (va, vb) in enumerate(zip(x.items, y.items)):
                walk(va, vb, '%s[%d]' % (path, i))
        elif isinstance(x, M.HashNode) and isinstance(y, M.HashNode):
            if len(x.pairs) != len(y.pairs):
                diff.append(path + '(哈希长度变化)')
                return
            for (k, va), (_, vb) in zip(x.pairs, y.pairs):
                walk(va, vb, path)
        elif isinstance(x, (M.UserDefNode, M.LinkNode)):
            if isinstance(y, M.LinkNode) != isinstance(x, M.LinkNode):
                diff.append(path + '(链接结构变化)')
        else:
            if M.value_of(x) != M.value_of(y):
                diff.append(path)

    for i, (ea, eb) in enumerate(zip(ref.entries, doc2.entries)):
        walk(ea['node'], eb['node'], MOD.TOP_NAMES[i] if i < len(MOD.TOP_NAMES) else str(i))
    # data_items 也会变：新增物品要像游戏那样把实例登记进 $data_items
    # （数组会增长 1 项），所以 data_items 的变化同样属于预期范围
    bad = [d for d in diff if not d.startswith(
        ('data.', 'game_party.', 'game_actors.', 'game_switches', 'game_variables',
         '存档id', 'data_items'))]
    check('改动都在预期范围内', not bad, bad[:6])
    say('共 %d 处字段变化：' % len(diff))
    for d in diff[:24]:
        say('   ' + d)
    if len(diff) > 24:
        say('   …还有 %d 处' % (len(diff) - 24))

    say('')
    say('===== 测试结果：%s =====' % ('全部通过' if ok else '存在失败项'))
    with open(LOG, 'w', encoding='utf-8') as f:
        f.write('\n'.join(_lines))
    try:
        os.remove(TMP)
        os.remove(TMP + '.bak')
    except OSError:
        pass
    return 0 if ok else 1


if __name__ == '__main__':
    try:
        rc = main()
    except Exception:
        import traceback
        tb = traceback.format_exc()
        print(tb)
        _lines.append(tb)
        with open(LOG, 'w', encoding='utf-8') as f:
            f.write('\n'.join(_lines))
        rc = 9
    sys.exit(rc)
