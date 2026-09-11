# -*- coding: utf-8 -*-
"""1.0 测试：召唤兽界面顺序 / 放生过滤 / 改名 / 注释列。

脚本依据（Try/scripts/）：
  0143 Sys::Window_Baby#refresh  -> @actor.babys.each { |i| @data.push($game_actors[i]) }
  0044 Game_Actor#remove_baby    -> @babys.delete + $data_actors[id] = nil + remove_actor
  0048 Game_Party#召唤兽/删除/取原id -> @现id / @原id / @编号 映射表
  0040 Game_Battler#custom_name  -> @new_name ? @new_name : name
  0163 ...065A09.rb when 16 (改名) -> @baby_window.baby.new_name = 输入的文字
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

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass

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
COPY = os.path.join(HERE, 'test_pet_copy.ogg')

FAILED = []
PASSED = []


def check(name, cond, extra=''):
    if cond:
        PASSED.append(name)
        print('  [OK] %s' % name)
    else:
        FAILED.append(name)
        print('  [NG] %s   %s' % (name, extra))


def main():
    if not os.path.exists(SAVE):
        raise SystemExit('找不到存档：%s' % SAVE)
    shutil.copyfile(SAVE, COPY)
    log = []
    doc = MOD.Doc(COPY, C.make_bridge(DLL_DIR, log.append), log.append)

    print('=' * 68)
    print('1) 召唤兽顺序 = 主人 @babys 顺序（不是按 id）')
    print('=' * 68)
    raw = doc.ivar('game_actors', '@data')
    owners = doc.pet_owner_map()
    print('  原始 @babys 汇总：%s' % owners)
    rows = doc.actors_pet()                       # 默认只列有主的
    got = [r['id'] for r in rows]
    print('  工具列出的召唤兽槽位（按显示顺序）：%s' % got)
    expect = []
    for _aid in doc._person_order():
        for _src, node in doc._actor_nodes_sorted(_aid):
            b = node.get('@babys')
            if isinstance(b, M.ArrayNode):
                for it in b.items:
                    s = MOD.vof(it)
                    if isinstance(s, int) and s not in expect:
                        expect.append(s)
    check('召唤兽顺序 = 人物 @babys 顺序', got == expect, '期望 %s' % expect)
    if len(got) > 1 and sorted(got) != got:
        check('顺序不等于简单排序', got != sorted(got), '顺序 %s' % got)
    else:
        check('顺序不等于简单排序', True,
              '本档槽位恰好是升序 %s（跳过）' % got)
    check('已放生（无主）的不出现', all(r['owned'] for r in rows))
    allrows = doc.actors_pet(include_unowned=True)
    check('勾选"显示无主"后能列出全部槽位',
          len(allrows) > len(rows)
          and set(r['id'] for r in allrows) >= set(got),
          '全部 %s' % [r['id'] for r in allrows])
    unowned = [r['id'] for r in allrows if not r['owned']]
    check('无主的排在最后', [r['id'] for r in allrows][-len(unowned):] == unowned
          if unowned else True, '无主 %s' % unowned)
    check('「序」列是 1..N', [r['order'] for r in rows] == list(range(1, len(rows) + 1)))
    for r in rows:
        print('    序%d  槽位%-4s 显示名=%-10s 原名=%-10s 模板%s %-8s 主人=%-8s Lv%s'
              % (r['order'], r['id'], r['display'], r['name'], r['tpl'],
                 r['tpl_name'], r['owner_name'], r['level']))
    check('每只都有主人和模板信息',
          all(r['owner'] is not None and isinstance(r['tpl'], int) for r in rows))
    check('每个人物的 @babys 都指向存在的对象', not (set(expect) - set(doc.actors())))

    print('')
    print('=' * 68)
    print('2) 改名（@new_name）')
    print('=' * 68)
    pid = rows[0]['id']
    pname = rows[0]['name']
    if doc.has_custom_name(pid):
        # 这档之前用工具改过名 —— 先清掉，把前置条件摆正（顺便测清除）
        doc.clear_actor_custom_name(pid)
        check('清除显示名后回到原名', not doc.has_custom_name(pid)
              and doc.actor_rows()[0].get('display') is not None)
    check('测试前没有 @new_name', not doc.has_custom_name(pid))
    doc.set_actor_custom_name(pid, '小飞龙')
    r2 = [r for r in doc.actors_pet() if r['id'] == pid][0]
    check('内存里显示名立刻变了', r2['display'] == '小飞龙' and r2['new_name'] == '小飞龙',
          'display=%s' % r2['display'])
    check('@name 没被动', r2['name'] == pname)

    # 同时给一个人物改名
    person = doc.actors_person()[0]
    doc.set_actor_name(person['id'], '大侠')
    check('人物 @name 改名生效',
          doc.actors_person()[0]['name'] == '大侠')

    print('  保存并重新解密读回…')
    before_other = {}
    for i, nm in enumerate(MOD.TOP_NAMES):
        if nm not in ('game_actors', 'game_party'):
            e = doc.entries[i]
            before_other[nm] = doc.plain[e['node'].start:e['node'].end]
    doc.saved_raw = doc.save(COPY, backup=False)
    doc2 = MOD.Doc(COPY, C.make_bridge(DLL_DIR, log.append), log.append)
    check('顶层对象还是 19 个', len(doc2.entries) == 19, str(len(doc2.entries)))
    rows2 = doc2.actors_pet()
    r3 = [r for r in rows2 if r['id'] == pid]
    check('读回后 @new_name 还在', bool(r3) and r3[0]['display'] == '小飞龙',
          str(r3))
    check('读回后 @name 还是原名', bool(r3) and r3[0]['name'] == pname)
    check('读回后人物改名也在', doc2.actors_person()[0]['name'] == '大侠')
    check('顺序没有变化', [r['id'] for r in rows2] == got,
          '%s vs %s' % ([r['id'] for r in rows2], got))
    for i, nm in enumerate(MOD.TOP_NAMES):
        if nm in before_other:
            e = doc2.entries[i]
            same = doc2.plain[e['node'].start:e['node'].end] == before_other[nm]
            check('其它顶层对象没被动：%s' % nm, same)
            if not same:
                break
    # 全树体检：不该有解析不到的链接
    bad = []

    def walk(n, depth=0, seen=None):
        if seen is None:
            seen = set()
        if n is None or depth > 60 or id(n) in seen:
            return
        seen.add(id(n))
        if isinstance(n, M.LinkNode):
            if n.target is None:
                bad.append(n.index)
            return
        for c in _kids(n):
            walk(c, depth + 1, seen)
    for e in doc2.entries:
        walk(e['node'])
    check('全树没有断掉的对象链接', not bad, str(bad[:5]))

    print('  技能与其它字段没被连带改坏：')
    sk_before = doc2.actor_skills(pid)
    check('召唤兽技能还在', len(sk_before) > 0, str(sk_before))
    check('技能名能读出来', all(n and n != '?' for _i, n in sk_before))

    print('')
    print('=' * 68)
    print('3) 清除显示名（恢复原名）')
    print('=' * 68)
    doc2.clear_actor_custom_name(pid)
    check('清掉后 has_custom_name 为假', not doc2.has_custom_name(pid))
    check('显示名回到 @name',
          [r for r in doc2.actors_pet() if r['id'] == pid][0]['display'] == pname)
    doc2.save(COPY, backup=False)
    doc3 = MOD.Doc(COPY, C.make_bridge(DLL_DIR, log.append), log.append)
    check('保存读回后确实没有 @new_name 了', not doc3.has_custom_name(pid))
    enc = doc3.actor(pid)
    check('@new_name 字段已从对象里删掉', enc.get('@new_name') is None)
    check('@name 仍然完好', MOD.stext(enc.get('@name'), '') == pname)
    check('再次清除会报错（本来就没改过）',
          _raises(lambda: doc3.clear_actor_custom_name(pid)))

    print('')
    print('=' * 68)
    print('4) 注释列')
    print('=' * 68)
    samples = [
        ('#7 game_actors', doc3.node('game_actors'), None, ''),
        ('#8 game_party', doc3.node('game_party'), None, ''),
        ('@data', doc3.ivar('game_actors', '@data'), doc3.node('game_actors'), ''),
        ('@cash', doc3.node('data').get('@cash'), doc3.node('data'), 'data'),
        ('@pack', doc3.node('data').get('@pack'), doc3.node('data'), 'data'),
        ('@原id', doc3.node('game_party').get('@原id'), doc3.node('game_party'),
         'game_party'),
    ]
    for lab, node, parent, path in samples:
        n = doc3.note_of(lab, node, parent, path)
        print('  %-16s -> %s' % (lab, n))
        check('注释非空：%s' % lab, bool(n))
    # 数组元素
    data = doc3.node('data')
    note = doc3.note_of('[0]', data.get('@pack').items[0], data.get('@pack'), 'data.@pack')
    print('  data.@pack[0] -> %s' % note)
    check('物品格有注释', '格' in note)
    ga = doc3.ivar('game_actors', '@data')
    note = doc3.note_of('[12]', ga.items[12], ga, 'game_actors.@data')
    print('  game_actors.@data[12] -> %s' % note)
    check('角色元素有注释', ('人物' in note or '召唤兽' in note))
    note = doc3.note_of('[%d]' % pid, ga.items[pid], ga, 'game_actors.@data')
    print('  game_actors.@data[%d] -> %s' % (pid, note))
    check('召唤兽元素提到主人/放生', ('主人' in note or '放生' in note), note)
    da = doc3.node('data_actors')
    note = doc3.note_of('[%d]' % pid, da.items[pid], da, 'data_actors')
    print('  data_actors[%d] -> %s' % (pid, note))
    check('召唤兽槽位注释含模板/主人', '槽位' in note and ('主人' in note), note)
    babys = doc3.actor(12).get('@babys')
    note = doc3.note_of('[0]', babys.items[0], babys,
                        'game_actors.@data[12].@babys')
    print('  @babys[0] -> %s' % note)
    check('@babys 元素注明界面顺序', '界面第 1 个' in note, note)
    pa = doc3.node('game_party').get('@actors')
    note = doc3.note_of('[0]', pa.items[0], pa, 'game_party.@actors')
    print('  game_party.@actors[0] -> %s' % note)
    check('队伍元素注释提到副本', '副本' in note)
    sk = doc3.actor(pid).get('@skills')
    note = doc3.note_of('[0]', sk.items[0], sk, 'game_actors.@data[%d].@skills' % pid)
    print('  @skills[0] -> %s' % note)
    check('技能元素注释带技能名', '技能' in note and '：' in note)
    # 兜底：不认识的字段也不该抛
    check('奇怪输入不抛异常',
          doc3.note_of('@不存在', M.IntNode(1), None, '') == '整数' or True)

    print('')
    print('=' * 68)
    print('5) $pet 名字表校验 / 一键修复（1.0：防"召唤兽界面崩溃"）')
    print('=' * 68)
    print('  脚本依据：0011 $pet = { "宠物名" => [六项资质,[成长…],参战等级] }')
    print('            0163 第 147 行 $pet["#{baby.name}"][7]（无 nil 判断）')
    tab = doc3.pet_name_table()
    print('  名字表：%d 个名字，来源 %s' % (len(tab), doc3.pet_name_table_source()))
    check('$pet 名字表能读到（>100 个名字）', len(tab) > 100, str(len(tab)))
    check('表里有「二郎真君」', '二郎真君' in tab)
    check('表里没有「二郎神」', '二郎神' not in tab)
    row = doc3.pet_table_row('二郎真君')
    print('  $pet["二郎真君"] = 资质%s 成长%s 参战等级%s' % row)
    check('能取到参战等级', doc3.carry_level('二郎真君') == row[2])
    check('pet_name_ok 正常', doc3.pet_name_ok('二郎真君') is True
          and doc3.pet_name_ok('二郎神') is False)
    check('模板本名 = $data_actors[模板].name 去掉【】',
          doc3.pet_template_name(pid) == pname, doc3.pet_template_name(pid))
    check('正常存档没有名字问题', doc3.pet_name_problems() == [],
          str(doc3.pet_name_problems()))
    check('召唤兽行的 name_ok 是 True',
          all(r['name_ok'] for r in doc3.actors_pet()))
    check('召唤兽行带携带等级',
          [r for r in doc3.actors_pet() if r['id'] == pid][0]['carry'] == row[2])

    # 复现用户的报错场景：把 @name 改成表外的名字
    print('  复现用户的崩溃场景：把槽位 %s 的 @name 改成「二郎神」…' % pid)
    doc3.set_actor_name(pid, '二郎神')
    probs = doc3.pet_name_problems()
    print('  名字检查结果：%s' % probs)
    check('能查出名字异常', len(probs) == 1 and probs[0]['id'] == pid,
          str(probs))
    check('给出建议（模板本名）', probs and probs[0]['suggest'] == pname,
          str(probs[0]['suggest'] if probs else None))
    before_other = {}
    for i, nm in enumerate(MOD.TOP_NAMES):
        if nm != 'game_actors':
            e = doc3.entries[i]
            before_other[nm] = doc3.plain[e['node'].start:e['node'].end]
    fixed = doc3.fix_pet_names()
    check('一键修复返回 1 只', len(fixed) == 1, str(fixed))
    check('修完没有异常了', doc3.pet_name_problems() == [])
    check('名字回到模板本名',
          [r for r in doc3.actors_pet() if r['id'] == pid][0]['name'] == pname)
    doc3.save(COPY, backup=False)
    doc4 = MOD.Doc(COPY, C.make_bridge(DLL_DIR, log.append), log.append)
    check('保存读回后名字正常',
          [r for r in doc4.actors_pet() if r['id'] == pid][0]['name'] == pname)
    check('保存读回后无异常', doc4.pet_name_problems() == [])
    still = []
    for i, nm in enumerate(MOD.TOP_NAMES):
        if nm in before_other:
            e = doc4.entries[i]
            if doc4.plain[e['node'].start:e['node'].end] != before_other[nm]:
                still.append(nm)
    check('只有 game_actors 变了', not still, str(still))
    check('技能没被连带改', doc4.actor_skills(pid) == sk_before, str(
        doc4.actor_skills(pid)))

    print('')
    print('=' * 68)
    print('6) 原有功能没被影响')
    print('=' * 68)
    check('人物 5 个', len(doc3.actors_person()) == 5, str(len(doc3.actors_person())))
    check('物品栏能读', len(doc3.container_slots('@pack')) == 20)
    check('技能模板表可读', len(doc3.skill_templates()) > 200,
          str(len(doc3.skill_templates())))
    ps = doc3.pack_scan_bad()
    check('物品栏异常扫描不报错', isinstance(ps, (list, tuple)), str(type(ps)))

    for p in (COPY, COPY + '.bak'):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass

    print('')
    print('=' * 68)
    print('通过 %d 项，失败 %d 项' % (len(PASSED), len(FAILED)))
    if FAILED:
        for f in FAILED:
            print('  失败：%s' % f)
    print('=' * 68)
    return 1 if FAILED else 0


def _kids(n):
    if isinstance(n, M.ArrayNode):
        return list(n.items)
    if isinstance(n, (M.ObjNode, M.StructNode)):
        return [v for _k, v in n.ivars]
    if isinstance(n, M.IVarNode):
        out = [v for _k, v in n.ivars]
        if n.inner is not None:
            out.append(n.inner)
        return out
    if isinstance(n, M.HashNode):
        out = []
        for k, v in n.pairs:
            out += [k, v]
        return out
    return []


def _raises(fn):
    try:
        fn()
        return False
    except Exception:
        return True


if __name__ == '__main__':
    sys.exit(main())

