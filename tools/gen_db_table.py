# -*- coding: utf-8 -*-
"""从游戏 Data/*.rxdata 抽出名字表，生成 src/tables/db_table.py（内嵌兜底）。

为什么要内嵌：这些名字本来靠**运行时读游戏目录**的 Data/Skills.rxdata 拿，
而别人的游戏目录里那些文件未必在、未必同版本、甚至可能是加密过的 ——
一旦读不到（或读出个别的东西）就报 MarshalError，技能名整片空掉。
名字表随包内嵌之后，「读不出来」这件事就只影响"超出内嵌范围的新条目"。

用法：
    python tools/gen_db_table.py            # 生成 src/tables/db_table.py
    python tools/gen_db_table.py --check    # 只比对，不写盘（CI/回归用）
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), 'src'))

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass

from paths import game_dir as _game_dir          # noqa: E402
import marshal_ruby as M                         # noqa: E402

#: 表键 -> (文件名, 是否连 @description 一起存)
TABLES = [
    ('data_skills', 'Skills.rxdata', True),
    ('data_items', 'Items.rxdata', True),
    ('data_weapons', 'Weapons.rxdata', False),
    ('data_armors', 'Armors.rxdata', False),
    ('data_actors', 'Actors.rxdata', False),
    ('data_classes', 'Classes.rxdata', False),
]

DST = os.path.join(HERE, '..', 'src', 'tables', 'db_table.py')


def _text(node):
    """取一个节点的字符串值（'' 表示没有）。"""
    if isinstance(node, M.StrNode):
        try:
            return node.str()
        except Exception:
            return ''
    return ''


def load_table(path):
    """读一张 .rxdata，返回 [(名字, 描述), ...]（下标 = id）。"""
    raw = open(path, 'rb').read()
    objs = M.parse_stream(raw)
    root = objs[-1]['node'] if objs else None
    if not isinstance(root, M.ArrayNode):
        raise SystemExit('%s 的根不是数组' % path)
    out = []
    for it in root.items:
        n = it
        # '@N' 链接：解引用
        while isinstance(n, M.LinkNode) and n.target is not None:
            n = n.target
        if isinstance(n, M.ObjNode):
            out.append((_text(n.get('@name')),
                        ' '.join(_text(n.get('@description')).split())))
        else:
            out.append(('', ''))
    return out


def build(game):
    data = {}
    for key, fname, with_desc in TABLES:
        path = os.path.join(game, 'Data', fname)
        if not os.path.exists(path):
            print('  [--] %-16s 游戏里没有这个文件，跳过' % fname)
            continue
        rows = load_table(path)
        names = tuple(r[0] for r in rows)
        descs = tuple(r[1] for r in rows) if with_desc else None
        data[key] = (names, descs)
        print('  [ok] %-16s %4d 项（有名 %d）'
              % (fname, len(rows), sum(1 for n in names if n)))
    return data


def render(data):
    out = ['# -*- coding: utf-8 -*-',
           '"""游戏 Data/*.rxdata 里的名字表（由 tools/gen_db_table.py 生成，请勿手改）。',
           '',
           '这些名字以前是**运行时去游戏目录读** Data/Skills.rxdata 之类拿的；',
           '别人的游戏目录里文件可能不在 / 不同版本 / 被加密过，读不到就整片空掉，',
           '甚至弹出 MarshalError。内嵌之后：**内嵌优先**，越界才回头去读游戏文件。',
           '',
           '表结构：下标 = 该表的 id（0 是占位空串），值 = @name 原文；',
           '带描述的表另有 *_DESCS（技能描述，多行已压成一行）。',
           '"""',
           '']
    for key, fname, with_desc in TABLES:
        if key not in data:
            continue
        names, descs = data[key]
        var = key.upper()
        out.append('%s = (' % var)
        for n in names:
            out.append('    %r,' % n)
        out.append(')')
        out.append('')
        if descs is not None:
            out.append('%s_DESCS = (' % var)
            for d in descs:
                out.append('    %r,' % d)
            out.append(')')
            out.append('')
    out.append('# 表键 -> 名字 / 描述（供 doctree 用）')
    out.append('NAMES = {')
    for key, _f, _d in TABLES:
        if key in data:
            out.append("    %r: %s," % (key, key.upper()))
    out.append('}')
    out.append('')
    out.append('DESCS = {')
    for key, _f, d in TABLES:
        if key in data and d:
            out.append("    %r: %s_DESCS," % (key, key.upper()))
    out.append('}')
    out.append('')
    return '\n'.join(out)


def main():
    game = _game_dir()
    print('游戏目录 = %s' % game)
    data = build(game)
    if not data:
        print('[NG] 一张表都没读到')
        return 1
    text = render(data)
    n = len(text)
    if '--check' in sys.argv:
        old = open(DST, encoding='utf-8').read().replace('\r\n', '\n')
        ok = (old == text)
        print('[%s] 现有 db_table.py 与游戏数据一致' % ('ok' if ok else 'NG'))
        return 0 if ok else 1
    with open(DST, 'w', encoding='utf-8', newline='\r\n') as f:
        f.write(text)
    print('已写入 %s（%d 字节）' % (os.path.abspath(DST), n))
    return 0


if __name__ == '__main__':
    sys.exit(main())
