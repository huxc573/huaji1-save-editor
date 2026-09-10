# -*- coding: utf-8 -*-
"""0.5 对象链接（'@N'）安全测试

背景：原存档 @pack 第 2 格（佛手）的 @name / @icon_name / @menu_se 等字段是
Marshal 的 '@N' 对象链接，指向第 1 格内部的对象。直接替换第 1 格的字节会让
第 2 格的链接整体指错 —— 游戏里就是"改了 1，2 的图标也变了"，读物品说明时
还会报 TypeError: cannot convert Array into String。

用原存档 sy.ogg.init（第 2 格确实是链接）做基准，验证：
  1. 整条重写 $data 之后，所有格子的字段值（展开链接后）与原档完全一致
  2. $data 里 @pack 之外的字段（金钱/声望/仓库…）也不变
  3. 改第 1 格之后，第 2 格一个字段都没变
  4. 新增 / 删除格子之后，其它格子一个字段都没变
  5. 重写后所有 '@N' 链接依旧能解析到目标
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
INIT = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg.init')     # 原存档（基准）
TMP = os.path.join(HERE, 'test_link_copy.ogg')

results = []


def check(name, ok, extra=''):
    results.append((name, ok, extra))
    print('%-50s %s %s' % (name, 'OK' if ok else '失败', extra))


def flat(node, depth=0):
    """把节点展开成可比较的纯 Python 结构（'@N' 链接按目标展开）。"""
    if node is None or depth > 30:
        return None
    if isinstance(node, M.LinkNode):
        return flat(node.target, depth + 1)
    if isinstance(node, M.NilNode):
        return node.value
    if isinstance(node, M.StrNode):
        return ('str', node.data)
    if isinstance(node, M.SymbolNode):
        return ('sym', node.name)
    if isinstance(node, (M.IntNode, M.BignumNode)):
        return ('int', node.value)
    if isinstance(node, M.FloatNode):
        return ('float', node.value)
    if isinstance(node, M.BoolNode):
        return ('bool', node.value)
    if isinstance(node, M.ArrayNode):
        return ('arr', tuple(flat(x, depth + 1) for x in node.items))
    if isinstance(node, M.HashNode):
        return ('hash', tuple((flat(k, depth + 1), flat(v, depth + 1))
                              for k, v in node.pairs))
    if isinstance(node, (M.ObjNode, M.StructNode)):
        return (node.cls, tuple((k, flat(v, depth + 1)) for k, v in node.ivars))
    if isinstance(node, M.UserDefNode):
        return ('userdef', node.cls, node.data)
    if isinstance(node, M.UserMarshalNode):
        return ('umarshal', node.cls, flat(node.inner, depth + 1))
    if isinstance(node, M.IVarNode):
        return ('ivar', flat(node.inner, depth + 1),
                tuple((k, flat(v, depth + 1)) for k, v in node.ivars))
    return ('?', type(node).__name__)


def pack_snapshot(doc):
    """每格一个快照：模板/实例id/数量/品质 + 物品的全部字段（链接已展开）。"""
    out = []
    for r in doc.pack():
        if r['item'] is None:
            out.append(None)
            continue
        out.append((r['standard'], r['iid'], r['count'], r['quality'],
                    flat(r['item'])))
    return out


def data_snapshot(doc):
    """$data 里除 @pack 之外的所有字段（含金钱 LockNumber）。"""
    d = doc.node('data')
    return {k: flat(v) for k, v in d.ivars if k != '@pack'}


def count_links(root):
    """统计整棵树里的 '@N' 数量与解析失败数。"""
    total = [0]
    bad = [0]
    seen = set()

    def walk(n, depth=0):
        if n is None or depth > 300 or id(n) in seen:
            return
        seen.add(id(n))
        if isinstance(n, M.LinkNode):
            total[0] += 1
            if n.target is None:
                bad[0] += 1
            return
        kids = (list(n.items) if isinstance(n, M.ArrayNode) else
                [v for _, v in n.ivars] if isinstance(n, (M.ObjNode, M.StructNode))
                else [v for _, v in n.ivars] if isinstance(n, M.IVarNode)
                else [x for kv in n.pairs for x in kv]
                if isinstance(n, M.HashNode) else [])
        for c in kids:
            walk(c, depth + 1)

    walk(root)
    return total[0], bad[0]


def main():
    if not os.path.exists(INIT):
        print('找不到原存档（基准）：%s' % INIT)
        print('提示：把未被工具改过的存档放在这里，命名为 sy.ogg.init')
        return 1
    shutil.copy2(INIT, TMP)
    log = []
    bridge = C.make_bridge(DLL_DIR, log.append)

    doc = MOD.Doc(TMP, bridge, log.append)
    snap0 = pack_snapshot(doc)
    data0 = data_snapshot(doc)
    links0, bad0 = count_links(doc.node('data'))
    check('原存档可读、链接全部可解析', bad0 == 0,
          '@pack 各格模板 %s，链接 %d 个（失败 %d）'
          % ([s[0] if s else None for s in snap0], links0, bad0))
    check('第 2 格在原档里确实是"链接格"（对象数少）',
          snap0[2] is not None and snap0[2][0] == 3, '模板 %s' % (snap0[2] or [None])[0])

    # ---------- 1. 整条重写 $data（内容不变）----------
    doc.begin_edit().replace_tree(doc.node('data'))
    doc._touch_pack()
    doc.save(backup=False)
    doc1 = MOD.Doc(TMP, bridge, log.append)
    snap1 = pack_snapshot(doc1)
    data1 = data_snapshot(doc1)
    links1, bad1 = count_links(doc1.node('data'))
    check('整条重写 $data：@pack 所有字段值不变', snap0 == snap1,
          '第2格 名字/图标值不变：%s' % (snap1[2] == snap0[2]))
    check('整条重写 $data：@pack 之外的字段不变', data0 == data1,
          '对比字段 %d 个' % len(data0))
    check('重写后链接依旧可解析', bad1 == 0, '链接 %d 个（失败 %d）' % (links1, bad1))
    check('重写后顶层对象数不变', len(doc1.entries) == 19,
          '%d 个' % len(doc1.entries))

    # ---------- 2. 改第 1 格：第 2 格必须一个字段都不变 ----------
    doc1.pack_write(1, 87, 95, 100)          # 87 = 祈福酒肆
    doc1.save(backup=False)
    doc2 = MOD.Doc(TMP, bridge, log.append)
    snap2 = pack_snapshot(doc2)
    check('改第 1 格：第 2 格完全没变（名字/图标/说明）', snap2[2] == snap0[2],
          '第2格=%s' % (snap2[2][2] if snap2[2] else None))
    check('改第 1 格：模板已是 87', snap2[1] is not None and snap2[1][0] == 87,
          '模板 %s 名字 %s' % (snap2[1][0] if snap2[1] else None,
                              MOD.stext(doc2.pack_slot(1)['item'].get('@name'))))
    check('改第 1 格：其它格（3-11）也没变',
          all(snap2[i] == snap0[i] for i in range(3, 12)))
    check('改第 1 格：@pack 之外的字段没变', data_snapshot(doc2) == data0)

    # ---------- 3. 新增空格 + 删除另一格 ----------
    doc2.pack_write(12, 87, 9, 100)          # 新增到空格
    doc2.pack_delete(0)                      # 清空第 0 格
    doc2.save(backup=False)
    doc3 = MOD.Doc(TMP, bridge, log.append)
    snap3 = pack_snapshot(doc3)
    check('新增+删除后：第 0 格已空', snap3[0] is None)
    check('新增+删除后：新增格正确',
          snap3[12] is not None and snap3[12][0] == 87 and snap3[12][2] == 9,
          '模板 %s 数量 %s' % (snap3[12][0], snap3[12][2]))
    check('新增+删除后：第 2 格仍没变', snap3[2] == snap0[2])
    check('新增+删除后：第 3-11 格仍没变',
          all(snap3[i] == snap0[i] for i in range(3, 12)))
    check('新增+删除后：@pack 之外的字段仍没变', data_snapshot(doc3) == data0)
    l3, b3 = count_links(doc3.node('data'))
    check('新增+删除后：链接仍全部可解析', b3 == 0, '链接 %d 个，失败 %d' % (l3, b3))

    # ---------- 4. 可被游戏读取（重新解密回读 + 再解析）----------
    check('最终顶层对象数 19、物品栏在用格数正确',
          len(doc3.entries) == 19 and doc3.pack_used() == 12,
          '%d 个对象，%d 格在用' % (len(doc3.entries), doc3.pack_used()))

    try:
        os.remove(TMP)
        if os.path.exists(TMP + '.bak'):
            os.remove(TMP + '.bak')
    except OSError:
        pass

    print('')
    f = [r for r in results if not r[1]]
    print('===== 链接安全测试：%s（共 %d 项，失败 %d 项）====='
          % ('全部通过' if not f else '有失败', len(results), len(f)))
    return 0 if not f else 1


if __name__ == '__main__':
    sys.exit(main())
