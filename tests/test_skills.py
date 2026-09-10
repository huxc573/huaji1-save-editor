# -*- coding: utf-8 -*-
"""0.6 技能（含召唤兽技能）读写测试

游戏脚本 0044_Game_Actor：
    @skills = []
    def learn_skill(skill_id)  -> @skills.push(skill_id); @skills.sort!
    def forget_skill(skill_id) -> @skills.delete(skill_id)
    def skill_learn?(skill_id) -> @skills.include?(skill_id)
技能模板在 Data/Skills.rxdata（存档里没有这个顶层对象）。
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
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
TMP = os.path.join(HERE, 'test_skill_copy.ogg')

results = []


def check(name, ok, extra=''):
    results.append((name, ok, extra))
    print('%-52s %s %s' % (name, 'OK' if ok else '失败', extra))


def snap_pets(doc):
    """召唤兽/人物的等级+技能，用于确认只改了目标对象。"""
    out = {}
    for r in doc.actor_rows():
        out[r['id']] = (r['name'], r['level'], tuple(x for x, _ in r['skills']))
    return out


def main():
    shutil.copy2(SAVE, TMP)
    log = []
    bridge = C.make_bridge(DLL_DIR, log.append)
    doc = MOD.Doc(TMP, bridge, log.append)

    # ---------- 1. 技能模板表（从 Data/Skills.rxdata 读）----------
    tpls = doc.skill_templates()
    check('能找到技能模板表（Data/Skills.rxdata）', len(tpls) > 50,
          '%d 个技能，例：%s' % (len(tpls), tpls[:3]))
    check('_data_file 能找到 Data 目录（存档在 Audio/BGM 下）',
          doc._data_file('Skills.rxdata') is not None,
          str(doc._data_file('Skills.rxdata')))

    # ---------- 2. 读召唤兽技能 ----------
    pets = doc.actors_pet()
    persons = doc.actors_person()
    check('角色/召唤兽能分开', bool(pets) and bool(persons),
          '人物 %d 个（%s），召唤兽 %d 个（%s）'
          % (len(persons), [r['name'] for r in persons],
             len(pets), sorted(set(r['name'] for r in pets))))
    pet = max(pets, key=lambda r: len(r['skills']))
    check('召唤兽技能能读出来（带名字）', bool(pet['skills']),
          '%s：%s' % (pet['name'], pet['skills']))
    check('召唤兽专属字段能读（成长/忠诚/资质）',
          pet['growth'] is not None and pet['loyal'] is not None
          and pet['zz_attack'] is not None,
          '成长=%s 忠诚=%s 攻击资质=%s 体力资质=%s'
          % (pet['growth'], pet['loyal'], pet['zz_attack'], pet['zz_tili']))
    person = persons[0]
    check('人物技能也能读', isinstance(person['skills'], list),
          '%s：%s' % (person['name'], person['skills']))

    before = snap_pets(doc)
    pid = pet['id']
    old = [x for x, _ in pet['skills']]

    # ---------- 3. 增加技能 ----------
    new_id = next(i for i, _n in tpls if i not in old)
    doc.add_actor_skill(pid, new_id)
    after_add = [x for x, _ in doc.actor_skills(pid)]
    check('增加技能成功（保持升序）',
          new_id in after_add and after_add == sorted(after_add),
          '新增 %d(%s) -> %s' % (new_id, doc.skill_name(new_id), after_add))
    try:
        doc.add_actor_skill(pid, new_id)
        check('重复增加同一技能被拒绝', False, '竟然没报错')
    except Exception as e:
        check('重复增加同一技能被拒绝', '已经有' in str(e), str(e)[:34])

    # ---------- 4. 删除技能 ----------
    doc.remove_actor_skill(pid, old[0])
    after_del = [x for x, _ in doc.actor_skills(pid)]
    check('删除技能成功', old[0] not in after_del,
          '删了 %d(%s) -> %s' % (old[0], doc.skill_name(old[0]), after_del))

    # ---------- 5. 其它对象不受影响 ----------
    now = snap_pets(doc)
    changed = [k for k in before if k != pid and before[k] != now[k]]
    check('其它角色/召唤兽不受影响', not changed, '变动了 %s' % changed)
    check('目标召唤兽等级/名字没变',
          before[pid][0] == now[pid][0] and before[pid][1] == now[pid][1],
          '%s Lv%s' % (now[pid][0], now[pid][1]))

    # ---------- 6. 保存 -> 读回 ----------
    doc.save(backup=False)
    doc2 = MOD.Doc(TMP, bridge, log.append)
    got = [x for x, _ in doc2.actor_skills(pid)]
    check('保存后技能列表正确', got == after_del, '%s' % got)
    check('保存后顶层对象数仍为 19', len(doc2.entries) == 19, '%d' % len(doc2.entries))
    check('保存后其它对象仍然一致',
          all(before[k][1] == snap_pets(doc2)[k][1] for k in before),
          '对比 %d 个对象' % len(before))

    # ---------- 7. 人物也能加技能 ----------
    doc2.add_actor_skill(person['id'], new_id)
    doc2.save(backup=False)
    doc3 = MOD.Doc(TMP, bridge, log.append)
    check('人物也能加技能并保存',
          new_id in [x for x, _ in doc3.actor_skills(person['id'])],
          '%s：%s' % (person['name'], doc3.actor_skills(person['id'])))

    # ---------- 8. 批量设置（清空再恢复）----------
    doc3.set_actor_skills(pid, [])
    check('可以批量设置（清空）', doc3.actor_skills(pid) == [],
          '%s' % doc3.actor_skills(pid))
    doc3.set_actor_skills(pid, after_del)
    check('再恢复回来', [x for x, _ in doc3.actor_skills(pid)] == after_del,
          '%s' % [x for x, _ in doc3.actor_skills(pid)])

    try:
        os.remove(TMP)
        if os.path.exists(TMP + '.bak'):
            os.remove(TMP + '.bak')
    except OSError:
        pass

    print('')
    f = [r for r in results if not r[1]]
    print('===== 技能测试：%s（共 %d 项，失败 %d 项）====='
          % ('全部通过' if not f else '有失败', len(results), len(f)))
    return 0 if not f else 1


if __name__ == '__main__':
    sys.exit(main())
