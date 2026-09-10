# -*- coding: utf-8 -*-
"""侦察：召唤兽对象的字段与技能（@skills），以及技能模板表。

脚本证据（Try/scripts/0044_Game_Actor…）：
    @skills = []
    def learn_skill(skill_id)   -> @skills.push(skill_id); @skills.sort!
    def forget_skill(skill_id)  -> @skills.delete(skill_id)
    def skill_learn?(skill_id)  -> @skills.include?(skill_id)
技能模板在 Data/Skills.rxdata（RPG::Skill，含 @name / @occasion / @scope…）。
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
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')


def main():
    log = []
    doc = MOD.Doc(SAVE, C.make_bridge(DLL_DIR, log.append), log.append)
    skills = doc._db('data_skills', 'Skills.rxdata')
    print('技能模板表（Data/Skills.rxdata）：%d 项' % len(skills))
    named = [(i, MOD.stext(s.get('@name'), ''))
             for i, s in enumerate(skills)
             if isinstance(s, M.ObjNode) and MOD.stext(s.get('@name'), '')]
    print('  有名字的技能 %d 个，前 10 个：%s' % (len(named), named[:10]))
    print('')

    print('=== 人物（@actor_id <= 20）的技能 ===')
    for r in doc.actor_rows():
        if r['id'] > 20:
            continue
        obj = doc.actor(r['id'])
        sk = obj.get('@skills')
        vals = [M.value_of(x) for x in sk.items] if isinstance(sk, M.ArrayNode) else None
        print('  角色 %-3s %-8s @skills=%s%s'
              % (r['id'], r['name'], vals,
                 '  → %s' % [MOD.stext(skills[v].get('@name'), '?')
                             for v in (vals or []) if 0 <= v < len(skills)]
                 if vals else ''))

    print('')
    print('=== 召唤兽（@actor_id > 20）的技能 ===')
    for r in doc.actor_rows():
        if r['id'] <= 20:
            continue
        obj = doc.actor(r['id'])
        sk = obj.get('@skills')
        vals = [M.value_of(x) for x in sk.items] if isinstance(sk, M.ArrayNode) else None
        names = [MOD.stext(skills[v].get('@name'), '?') for v in (vals or [])
                 if 0 <= v < len(skills)]
        print('  召唤兽 %-4s %-10s 等级=%-3s @skills(%s 个)=%s'
              % (r['id'], r['name'], r['level'],
                 len(vals) if vals is not None else '?', vals))
        if names:
            print('        技能：%s' % '，'.join(names))

    # 召唤兽对象的全部字段（看还有什么值得改）
    pets = [r for r in doc.actor_rows() if r['id'] > 20]
    if pets:
        print('')
        print('=== 召唤兽 Game_Actor 的全部字段（以 %s 为例）===' % pets[0]['name'])
        obj = doc.actor(pets[0]['id'])
        for k, v in obj.ivars:
            print('  %-18s = %s' % (k, MOD.value_text(v, 70)))
        print('')
        print('=== 人物 Game_Actor 的全部字段（以第一个角色为例）===')
        pp = [r for r in doc.actor_rows() if r['id'] <= 20]
        if pp:
            obj = doc.actor(pp[0]['id'])
            for k, v in obj.ivars:
                print('  %-18s = %s' % (k, MOD.value_text(v, 70)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
