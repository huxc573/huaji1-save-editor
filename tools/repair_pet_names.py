# -*- coding: utf-8 -*-
"""立刻修复：把召唤兽的 @name 恢复成 $pet 名字表里的本名。

问题（用户实测）：
  游戏报 `脚本 'Sys <召唤兽>' 的 147 行发生了 NoMethodError.
  undefined method '[]' for nil:NilClass`
  0163 第 147 行： $pet["#{baby.name}"][7]
  0011 里 $pet 是以宠物**名字**为键的表；名字不在表里 -> nil[7] -> 崩溃。
  Game_Actor#name 就是 @name（0044 setup：@name = actor.name.split(/【/)[0]），
  所以把 @name 改成了表外的名字（例如 二郎真君 -> 二郎神）就会让召唤兽界面打不开。

本脚本：
  1) 打印所有召唤兽的 @name 是否在表里
  2) 把不在表里的，用"槽位模板名"（$data_actors[模板].name 去掉【…】后缀）恢复
     —— 这正是游戏 0044 Game_Actor#setup 里的算法
  3) 备份 -> 写回 -> 重新解密读回校验；只动 @name，其它顶层对象字节必须完全不变
"""
# --- 开发期路径引导：让 import 项目模块找到 ../src ----------------------------
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

import codec as C
import marshal_ruby as M
import doctree as MOD

from paths import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
APPLY = '--apply' in sys.argv


def tpl_name(doc, slot):
    """槽位对应模板的本名（复刻 0044 Game_Actor#setup：split(/【/)[0]）。"""
    tpl = doc.pet_slot_map().get(slot)
    if not isinstance(tpl, int):
        return None
    a = doc.node('data_actors')
    it = a.items[tpl] if isinstance(a, M.ArrayNode) and tpl < len(a.items) else None
    if isinstance(it, M.LinkNode):
        it = it.target
    nm = MOD.stext(it.get('@name'), '') if isinstance(it, M.ObjNode) else ''
    nm = nm.split('【')[0].strip()
    return nm or None


def main():
    log = []
    doc = MOD.Doc(SAVE, C.make_bridge(DLL_DIR, log.append), log.append)
    table = doc.pet_name_table()
    names = set(table.keys())
    print('$pet 名字表：%d 个名字（来源：%s）'
          % (len(names), doc.pet_name_table_source() or '未找到，跳过校验'))
    print('')
    print('=== 所有召唤兽（含已放生的）===')
    bad = []
    for r in doc.actors_pet(include_unowned=True):
        ok = r['name'] in names
        suggest = tpl_name(doc, r['id'])
        if not ok:
            bad.append((r, suggest))
        print('  槽%-5s @name=%-12s 在表里=%-4s 模板%-6s 模板本名=%-12s 主人=%s'
              % (r['id'], r['name'], '是' if ok else '否 ✘', r['tpl'],
                 suggest or '?', r['owner_name'] or '（无主）'))
    print('')
    if not bad:
        print('没有名字异常的召唤兽，无需修复。')
        return 0

    print('=== 需要修复 %d 只 ===' % len(bad))
    for r, sug in bad:
        print('  槽位 %-5s「%s」-> 「%s」（%s）'
              % (r['id'], r['name'], sug or '?',
                 '模板本名在 $pet 表里 ✔' if (sug in names) else '⚠ 模板本名也不在表里'))
    if not APPLY:
        print('')
        print('（这是预演。确认无误后加 --apply 真正写回。）')
        return 0

    # 记录除 @name 外的一切，稍后比对
    before = {}
    for i, nm in enumerate(MOD.TOP_NAMES):
        e = doc.entries[i]
        before[nm] = doc.plain[e['node'].start:e['node'].end]
    before_skills = {r['id']: r['skills'] for r in doc.actors_pet(include_unowned=True)}

    print('')
    print('=== 开始修复 ===')
    for r, sug in bad:
        if not sug:
            print('  跳过 槽位 %s：拿不到模板本名' % r['id'])
            continue
        doc.set_actor_name(r['id'], sug)
        print('  槽位 %-5s @name: 「%s」-> 「%s」' % (r['id'], r['name'], sug))

    print('')
    print('保存（自动备份 .bak）…')
    doc.save(SAVE, backup=True)

    doc2 = MOD.Doc(SAVE, C.make_bridge(DLL_DIR, log.append), log.append)
    print('')
    print('=== 读回校验 ===')
    ok = True
    for r in doc2.actors_pet(include_unowned=True):
        good = r['name'] in names
        if not good:
            ok = False
        print('  槽%-5s @name=%-12s 在表里=%s' % (r['id'], r['name'], '是' if good else '否 ✘'))
    print('')
    print('顶层对象数：%d（应为 19）' % len(doc2.entries))
    changed = []
    for i, nm in enumerate(MOD.TOP_NAMES):
        e = doc2.entries[i]
        if doc2.plain[e['node'].start:e['node'].end] != before[nm]:
            changed.append(nm)
    print('字节有变化的顶层对象：%s' % (changed or '（无）'))
    after_skills = {r['id']: r['skills'] for r in doc2.actors_pet(include_unowned=True)}
    same_sk = before_skills.keys() == after_skills.keys() and \
        all(before_skills[k] == after_skills[k] for k in before_skills)
    print('技能一点没动：%s' % ('是 ✔' if same_sk else '否 ✘'))
    print('备份文件：%s（%d 字节）' % (SAVE + '.bak', os.path.getsize(SAVE + '.bak')
                                 if os.path.exists(SAVE + '.bak') else 0))
    print('')
    print('结果：%s' % ('修复成功 ✔' if ok else '仍有问题 ✘'))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
