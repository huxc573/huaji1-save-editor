# -*- coding: utf-8 -*-
"""从游戏脚本 0011 里抽出 $pet 表，生成 pet_table.py（守护数据，供 xj_model 兜底用）。

$pet 的结构（脚本 0011）：
    $pet = { "宠物名" => [攻击资质,防御资质,体力资质,法力资质,速度资质,闪躲资质,
                          [成长…], 参战等级], ... }
它被这些地方无保护地索引（名字不在表里就 nil[...] -> 游戏崩溃）：
    0044 Game_Actor#setup     : baby = $pet["#{@name}"]           （有 nil 判断）
    0121 战斗                  : $pet[@baby_window.baby.name][7]  （无判断）
    0163 Sys <召唤兽> 第 147 行 : $pet["#{baby.name}"][7]          （无判断）★用户报错这行
    0163 第 436/439 行          : $pet[@baby_window.baby.name][7]  （无判断）
    0164 召唤兽图鉴             : zz = $pet[baby.name]             （无判断）
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
from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SCRIPTS = os.path.join(GAME, 'Try', 'scripts')


def split_top(s):
    """按顶层逗号切分（忽略 [ ] 里的逗号）。"""
    out, depth, cur = [], 0, ''
    for ch in s:
        if ch == '[':
            depth += 1
            cur += ch
        elif ch == ']':
            depth -= 1
            cur += ch
        elif ch == ',' and depth == 0:
            out.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def parse(fn):
    with open(fn, encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    table = {}
    order = []
    for s in lines:
        m = re.match(r'^\s*"([^"]{1,24})"\s*=>\s*\[(.*)\]\s*,?\s*$', s)
        if not m:
            continue
        name = m.group(1)
        parts = split_top(m.group(2))
        if len(parts) < 8:
            continue
        try:
            zz = [int(x) for x in parts[:6]]
        except ValueError:
            continue
        grow = re.findall(r'[-\d.]+', parts[6])
        try:
            carry = int(parts[7])
        except ValueError:
            carry = 0
        table[name] = (zz, [float(g) for g in grow], carry)
        if name not in order:
            order.append(name)
    return order, table


def main():
    fn = next((f for f in sorted(os.listdir(SCRIPTS)) if f.startswith('0011_')), None)
    if not fn:
        print('找不到 0011 脚本')
        return 1
    order, table = parse(os.path.join(SCRIPTS, fn))
    print('解析 %s：%d 条' % (fn, len(table)))

    out = ['# -*- coding: utf-8 -*-',
           '"""$pet 名字表（由 gen_pet_table.py 从游戏脚本 %s 生成，请勿手改）。' % fn,
           '',
           '结构：名字 -> ([攻击资质,防御资质,体力资质,法力资质,速度资质,躲闪资质],',
           '               [成长…], 参战等级)',
           '',
           '为什么要这张表：游戏这些地方**无 nil 判断**地索引它，',
           '召唤兽的 @name 一旦不是表里的键，就会 NoMethodError: undefined method',
           '\'[]\' for nil:NilClass（用户实测报错在 Sys <召唤兽> 第 147 行）。',
           '所以本工具改名时会拿它校验。',
           '"""',
           '',
           'SOURCE_SCRIPT = %r' % fn,
           '',
           'NAMES = (',
           ]
    for n in order:
        out.append('    %r,' % n)
    out.append(')')
    out.append('')
    out.append('TABLE = {')
    for n in order:
        zz, grow, carry = table[n]
        out.append('    %r: (%r, %r, %d),' % (n, zz, grow, carry))
    out.append('}')
    out.append('')
    dst = os.path.join(HERE, 'pet_table.py')
    with open(dst, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out) + '\n')
    print('已写入 %s（%d 字节，%d 个名字）' % (dst, os.path.getsize(dst), len(order)))
    for probe in ('二郎真君', '二郎神', '白麒麟', '哮天犬', '周杰伦'):
        print('  %-8s -> %s' % (probe, table.get(probe, '（不在表里）')))
    return 0


if __name__ == '__main__':
    sys.exit(main())
