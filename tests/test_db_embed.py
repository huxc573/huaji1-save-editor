# -*- coding: utf-8 -*-
"""1.4.0 回归测试：技能名/描述不再依赖游戏目录里的 Data/*.rxdata

背景（用户实测）：别人的机器上「改召唤兽技能」直接弹
    xj_marshal.MarshalError: 未知类型 'l' (0x6C) @1941269
根因不是存档，是**技能名去读游戏目录**了 —— Data/Skills.rxdata 在别人那儿
未必在、未必同版本、甚至可能被加密过；老代码连 try/except 都没有，
读出来不是数组就抛，整个召唤兽页跟着崩。

本版两处改动，这里逐条验：
  A) 内嵌表 tables/db_table.py（由 tools/gen_db_table.py 从游戏 Data 生成）
     成了**第一顺位**——技能名/描述根本不碰游戏文件；
  B) 真去读文件的地方（_db / _data_array）读不懂就降级成空表，
     **一个字节都不许因此弹错**。

全程只动 %TEMP% 里的存档副本，不碰真档、不在游戏目录留东西。
"""
# --- 开发期路径引导：让 import 项目模块找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import os
import shutil
import tempfile

import codec as C
import doctree as MOD

from paths import game_dir as _game_dir
GAME = _game_dir()
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else \
    os.path.dirname(os.path.abspath(__file__))
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
WORK = os.path.join(tempfile.gettempdir(), 'huaji1_dbembed')
TMP = os.path.join(WORK, 'sy.ogg')

results = []


def check(name, ok, extra=''):
    results.append((name, ok, extra))
    print('%-58s %s %s' % (name, 'OK' if ok else '失败', extra))


def main():
    # ==================================================================
    print('=' * 70)
    print('1) 内嵌表本身：tables/db_table.py 装了什么')
    print('=' * 70)
    mod = MOD._DB_TABLE_MOD
    check('随包带上了内嵌名字表 db_table', mod is not None)
    if mod is None:
        return 1
    keys = sorted(mod.NAMES)
    check('覆盖 技能/物品/武器/角色/职业', keys == ['data_actors', 'data_classes',
                                              'data_items', 'data_skills',
                                              'data_weapons'], str(keys))
    sk = mod.NAMES['data_skills']
    check('技能表条目数正常（>200）', len(sk) > 200, '%d 项' % len(sk))
    check('技能描述表也在（且与名字等长）',
          len(mod.DESCS.get('data_skills', ())) == len(sk))
    check('技能 1 = 嗜血追击', sk[1] == '嗜血追击', sk[1] if len(sk) > 1 else '')

    # ==================================================================
    print('')
    print('=' * 70)
    print('2) 断掉游戏目录：技能名仍然出得来（本次 bug 的核心）')
    print('=' * 70)
    if not os.path.exists(SAVE):
        print('找不到存档:', SAVE)
        return 1
    os.makedirs(WORK, exist_ok=True)
    shutil.copy2(SAVE, TMP)
    bridge = C.make_bridge(DLL_DIR, lambda s: None)
    doc = MOD.Doc(TMP, bridge, lambda s: None)

    check('正常情况就能取到技能名', doc.skill_name(1) == '嗜血追击',
          doc.skill_name(1))
    check('正常情况也能取到技能描述', '普通伤害' in doc.skill_desc(9),
          doc.skill_desc(9)[:40])

    # 造一个"别人的机器"：Data/Skills.rxdata 是坏文件（不是 Marshal 明文）
    bad_root = os.path.join(WORK, 'fake_game')
    os.makedirs(os.path.join(bad_root, 'Data'), exist_ok=True)
    bad_file = os.path.join(bad_root, 'Data', 'Skills.rxdata')
    with open(bad_file, 'wb') as f:
        f.write(b'\xff' * 64)                    # 0xFF 不是任何合法类型字节
    doc._search_bases = lambda: [bad_root]        # 让 _data_file 只找得到这个坏文件

    doc._cache.pop('data_skills', None)
    doc._cache.pop('db_bad', None)
    check('名字走内嵌表，根本不去读那个坏文件',
          doc.skill_name(1) == '嗜血追击' and doc.db_bad_files() == [],
          'db_bad=%r' % (doc.db_bad_files(),))
    check('技能描述同样不碰文件', '普通伤害' in doc.skill_desc(9))
    tpl = doc.skill_templates()
    check('技能下拉表照样有内容（不再是空的）', len(tpl) > 200, '%d 条' % len(tpl))
    check('下拉表里的名字正确', tpl[0][0] == 1 and tpl[0][1] == '嗜血追击',
          str(tpl[:1]))

    # ==================================================================
    print('')
    print('=' * 70)
    print('3) 非读不可的地方：坏文件只能降级，不许抛')
    print('=' * 70)
    # (a) 文件根本不在
    arr = None
    err = ''
    try:
        arr = doc._db('data_states', 'States.rxdata')
    except Exception as e:
        err = '%s: %s' % (type(e).__name__, e)
    check('文件不在：返回空表、不抛', not err and arr == [], err[:60])

    # (b) 文件在，但不是 Marshal 明文（别人装了加密版 / 别的版本）
    doc._cache.pop('data_skills', None)
    doc._cache.pop('db_bad', None)
    arr2 = None
    err2 = ''
    try:
        arr2 = doc._db('data_skills', 'Skills.rxdata')   # ← 以前这里直接抛
    except Exception as e:
        err2 = '%s: %s' % (type(e).__name__, e)
    check('文件读不懂：返回空表、不抛异常', not err2 and arr2 == [], err2[:70])
    bad = doc.db_bad_files()
    check('把这次失败记下来了（界面/排错能看）',
          any(n == 'Skills.rxdata' for n, _w in bad), str(bad)[:90])

    # 内嵌表里没有、游戏文件也读不到的 id —— 只能给占位，但不能崩
    check('取不到的 id 给占位不报错', doc.skill_name(9999).startswith('技能'),
          doc.skill_name(9999))

    # ==================================================================
    print('')
    print('=' * 70)
    print('4) 装备 HP/SP 加成（名字里带 "名字,HP,SP,等级"）走内嵌表')
    print('=' * 70)
    doc2 = MOD.Doc(TMP, bridge, lambda s: None)
    a = doc2.actor(1)
    if a is None:
        check('存档里有 1 号角色', False)
    else:
        hp = doc2.actor_maxhp(1)
        check('1 号角色 HP 上限仍能算出来（装备加成没断）',
              isinstance(hp, int) and 1 <= hp <= 999999, str(hp))

    # ==================================================================
    print('')
    f = [r for r in results if not r[1]]
    print('===== 技能名/内嵌表测试：%s（共 %d 项，失败 %d 项）====='
          % ('全部通过' if not f else '有失败', len(results), len(f)))
    for name, _ok, extra in f:
        print('   [失败] %s %s' % (name, extra))
    return 0 if not f else 1


if __name__ == '__main__':
    sys.exit(main())
