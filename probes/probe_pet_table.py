# -*- coding: utf-8 -*-
"""读出 $pet 表（脚本 0011）的合法宠物名，并检查当前存档里有没有"名字不在表里"的召唤兽。

背景（游戏脚本证据）：
  0011：if $pet.nil? ; $pet = { "宠物名" => [攻击资质,防御资质,体力资质,法力资质,
        速度资质,闪躲资质,成长,参战等级], ... }
  0163 第 147 行：$pet["#{baby.name}"][7]   -> 名字不在表里就是 nil[7] -> NoMethodError
  0044：            baby = $pet["#{@name}"]
  0164：            zz = $pet[baby.name]
所以召唤兽的 @name 必须是 $pet 里的键。
"""
# --- 开发期路径引导：让 import xj_* 找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import os
import re
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
SCRIPTS = os.path.join(GAME, 'Try', 'scripts')


def packed(fn):
    p = os.path.join(SCRIPTS, fn)
    with open(p, encoding='utf-8', errors='replace') as f:
        return [s for s in f.read().splitlines() if s.strip()]


def main():
    fn = next(f for f in os.listdir(SCRIPTS) if f.startswith('0011_'))
    lines = packed(fn)
    print('=== %s：$pet 表（前 60 行）===' % fn)
    for i, s in enumerate(lines[:60], 1):
        print('%5d  %s' % (i, s[:160]))
    print('')

    # 从文本里抠出键名：形如  "名字" => [ ... ]
    keys = []
    for s in lines:
        for m in re.finditer(r'"([^"]{1,20})"\s*=>', s):
            keys.append(m.group(1))
        for m in re.finditer(r'^\s*"([^"]{1,20})"\s*=>', s):
            keys.append(m.group(1))
    # 也支持 '名字' => 形式
    if not keys:
        for s in lines:
            for m in re.finditer(r"'([^']{1,20})'\s*=>", s):
                keys.append(m.group(1))
    keys = [k for k in dict.fromkeys(keys)]
    print('=== $pet 里共 %d 个键（宠物名）===' % len(keys))
    print('  ' + '、'.join(keys))
    print('')

    log = []
    doc = MOD.Doc(SAVE, C.make_bridge(DLL_DIR, log.append), log.append)
    keyset = set(keys)
    print('=== 当前存档里的召唤兽（含已放生的）===')
    bad = []
    for r in doc.actors_pet(include_unowned=True):
        nm = r['name']
        ok = nm in keyset if keyset else None
        if ok is False:
            bad.append(r)
        print('  槽%-5s 显示名=%-12s @name=%-12s 模板%-5s %-10s 在$pet表里=%s  主人=%s'
              % (r['id'], r['display'], nm, r['tpl'], r['tpl_name'],
                 '是' if ok else '否 ✘', r['owner_name'] or '（无主）'))
    print('')
    if bad:
        print('!!! 有 %d 只召唤兽的名字不在 $pet 表里 —— 这就是 “undefined method \'[]\' '
              'for nil” 的原因：' % len(bad))
        for r in bad:
            print('   槽位 %s：现在叫「%s」（模板 %s %s）'
                  % (r['id'], r['name'], r['tpl'], r['tpl_name']))
    else:
        print('召唤兽名字都在 $pet 表里（若游戏仍报错，查 @name 被改过的其它槽位）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
