# -*- coding: utf-8 -*-
"""
xj_edit —— 0.3 的写入引擎

思路（沿用 0.1 已验证的做法）：解析时每个节点都带明文里的字节区间，
修改时**只把改动过的字段重新编码**，再按原始偏移升序重放回明文；
没动过的字节原样保留 —— 因此不会破坏对象链接（'@N'）和 RPG::Table 之类的
不透明数据。

本文件提供两层能力：
  * PatchEngine —— 打补丁、重放、生成新明文
  * clone_node / make_pack_entry —— 深拷贝对象、构造 @pack 里的 [物品实例, 数量]
    给背包"新增物品"用（序列化时把 '@' 链接全部内联展开，保证自包含）
"""
import os
import shutil

import xj_marshal as M


class EditError(Exception):
    pass


# 物品实例的默认品质。
# 模板（data_items）里**没有** @quality 字段，它是实例专有字段；缺了它游戏读到
# nil 会按 0 处理，物品就提示"该物品无法使用"。所以写入实例时必须带上它。
DEFAULT_QUALITY = 100


def _dump(node):
    """整块重写时的序列化。

    * 节点是从存档里解析出来的（gidx >= 0）：用**编号模式** —— 重复对象发 '@N'
      引用，编号自洽，而且能处理循环引用（Game_Actor#@who_attack_me 会指回
      Game_Actor 自己）；
    * 节点是工具自己拼出来的（gidx = -1）：退回**展开模式**（输出自包含）。
    """
    if getattr(node, 'gidx', -1) >= 0:
        return M.serialize(node, table={})
    return M.serialize(node)


class PatchEngine(object):
    def __init__(self, plain):
        self.plain = bytes(plain)
        self._patch = []          # [(start, end, data)]
        # 本会话里被整体替换掉的节点（例如 @pack 的某一格）：
        #   {(start, end): 新节点}
        # 有了它，之后改新节点内部的字段（改数量/品质…）就能重算整个区间的字节
        self._roots = {}

    # ---------- 打补丁 ----------
    def drop_inside(self, start, end):
        """丢弃完全落在 [start,end) 内的旧补丁（用于整体替换一个槽位）。"""
        self._patch = [(s, e, d) for s, e, d in self._patch
                       if not (s >= start and e <= end)]

    def patch_range(self, start, end, data):
        if start >= end or end > len(self.plain):
            raise EditError('非法区间 %d..%d' % (start, end))
        keep = []
        for s, e, d in self._patch:
            if s == start and e == end:
                # 同一字段又改了一次：丢弃旧补丁，用新值替换
                # （否则"金钱先改 100 再改 200"会报错）
                continue
            if e <= start or s >= end:
                keep.append((s, e, d))
            elif s <= start and e >= end:
                raise EditError('该位置已被更大的改动覆盖，请先撤销那个改动')
            # 被新补丁覆盖的旧补丁直接丢弃
        keep.append((start, end, data))
        self._patch = keep

    def set_scalar(self, node, value=None):
        """修改一个标量节点（int/bignum/bool/str/float）。"""
        if isinstance(node, M.IntNode):
            node.value = int(value)
        elif isinstance(node, M.BignumNode):
            node.value = int(value)
        elif isinstance(node, M.BoolNode):
            node.value = bool(value)
        elif isinstance(node, M.StrNode):
            node.data = value.encode('utf-8') if isinstance(value, str) else bytes(value)
        elif isinstance(node, M.FloatNode):
            node.value = float(value)
        elif isinstance(node, M.NilNode):
            # nil 槽位可以直接写成 true/false 或整数（开关经常是 nil）
            node.value = bool(value) if isinstance(value, bool) else int(value)
        else:
            raise EditError('该字段类型不支持修改：%s' % type(node).__name__)
        root = self._roots.get((node.start, node.end))
        if root is not None:
            # 这个节点属于本会话新建/重建的整块（比如某一格物品）：
            # 直接重新序列化整块，写回那一块占用的区间
            self.patch_range(node.start, node.end, _dump(root))
        else:
            self.patch_range(node.start, node.end, M.reencode(node))
        return node

    def replace_node(self, node, new_bytes):
        """把一个节点整体换成任意 Marshal 字节（例如把槽位改成 nil）。"""
        self.patch_range(node.start, node.end, new_bytes)

    def replace_tree(self, node, new_data=None):
        """
        用"自包含序列化"的结果整体替换一棵子树 —— 所有的 '<literal>@N</literal>' 对象链接都被
        展开成独立副本。

        为什么要这样：Marshal 的对象编号是**按对象在流里出现的顺序**编的，
        而 '<literal>@N</literal>' 只能引用**前面出现过**的对象。@pack 里就有这种情况：
        第 2 格（佛手）的 @name / @icon_name / @menu_se 全是 '<literal>@N</literal>'，
        指向第 1 格内部的对象。如果只把第 1 格换成对象数量/顺序不同的新块，
        第 2 格的链接就会整体指错 —— 游戏读到的名字变成数组，直接报
        TypeError: cannot convert Array into String。

        做法：用 M.serialize 的**编号模式**（table={}）整体重序列化，
        重复出现的对象发 '@N' 引用、编号从该节点自己的 gidx 开始，
        所以既能保持编号自洽，又能处理循环引用（例如
        Game_Actor#@who_attack_me.@who_attack_me 指回自己 —— 战斗过的存档
        里很常见，展开模式会直接无限递归）。
        """
        if new_data is None:
            new_data = _dump(node)
        self.drop_inside(node.start, node.end)
        for k in [k for k in self._roots
                  if node.start <= k[0] and k[1] <= node.end]:
            del self._roots[k]
        self.patch_range(node.start, node.end, new_data)
        return new_data

    def replace_object(self, node, span=None, new_data=None):
        """
        整体替换一个节点，**并且把新子树登记成这一段的"根"**（见 _roots）。

        和 replace_tree 的区别：replace_tree 之后，如果又去改这个子树内部的某个
        字段，set_scalar 会打一个"落在更大补丁里面"的小补丁，patch_range 会直接
        报「该位置已被更大的改动覆盖，请先撤销那个改动」。
        登记成根之后，改内部字段会自动重新序列化整块，就不会冲突了。

        谁需要它：改名（给 Game_Actor 加/删 @new_name）这种"整体重写一个对象"
        的操作 —— 之后用户还会继续改这只召唤兽的等级/资质。
        """
        old = span or (node.start, node.end)
        if new_data is None:
            # 编号模式（gidx>=0）：区间之前的对象编号不变，区间内部重新编号，
            # 因此 Game_Actor 里的 '@who_attack_me' 这种**循环引用**也能写出去
            new_data = _dump(node)
        self.drop_inside(old[0], old[1])
        for k in [k for k in self._roots if old[0] <= k[0] and k[1] <= old[1]]:
            del self._roots[k]
        self.patch_range(old[0], old[1], new_data)
        _tag_new(node, old[0], old[1])
        self._roots[old] = node
        return new_data

    def set_array_element(self, array_node, idx, node_or_bytes):
        """
        替换数组元素（例如 @pack 的某一格）。

        0.3 的 bug：这里只打了字节补丁，没有把新节点放回内存树，
        于是界面重新读取时看到的还是旧值（写入空格后仍然显示"数量 0"），
        看起来像没写进去。现在补上内存同步，并给新子树打上整格区间标记。
        """
        el = array_node.items[idx]
        if isinstance(node_or_bytes, bytes):
            data = node_or_bytes
            node = M.parse_stream(b'\x04\x08' + data)[0]['node']
        else:
            node = node_or_bytes
            data = M.serialize(node)
        old = (el.start, el.end)
        self.drop_inside(old[0], old[1])
        for k in [k for k in self._roots if old[0] <= k[0] and k[1] <= old[1]]:
            del self._roots[k]
        self.patch_range(old[0], old[1], data)
        _tag_new(node, old[0], old[1])
        self._roots[old] = node
        array_node.items[idx] = node

    # ---------- 生成新明文 ----------
    def _effective(self):
        """真正有变化的补丁（改回原值的补丁不算改动，避免误报"已修改"）。"""
        return [(s, e, d) for s, e, d in self._patch if self.plain[s:e] != d]

    def rebuild(self):
        out = bytearray()
        cur = 0
        for s, e, d in sorted(self._effective(), key=lambda t: t[0]):
            if s < cur:
                raise EditError('补丁区间重叠：%d < %d' % (s, cur))
            out += self.plain[cur:s]
            out += d
            cur = e
        out += self.plain[cur:]
        return bytes(out)

    def has_changes(self):
        return bool(self._effective())

    def changed_bytes(self):
        return sum(e - s for s, e, _ in self._effective())


# --------------------------------------------------------------------------
# 深拷贝 / 构造 @pack 条目
# --------------------------------------------------------------------------
def _kids(node):
    """取一个节点的直接子节点（用于给新建的子树打区间标记）。"""
    if isinstance(node, M.ArrayNode):
        return list(node.items)
    if isinstance(node, (M.ObjNode, M.StructNode)):
        return [v for _, v in node.ivars]
    if isinstance(node, M.IVarNode):
        out = [v for _, v in node.ivars]
        if node.inner is not None:
            out.append(node.inner)
        return out
    if isinstance(node, M.HashNode):
        out = []
        for k, v in node.pairs:
            out += [k, v]
        return out
    return []


def _tag_new(node, start, end, _depth=0):
    """
    给新构造的节点树打上"我占用了明文 [start,end) 这一段"的标记。

    新建的节点本身没有偏移（start=end=0）。标记之后：
      * 界面能从内存树里读到新值（不再显示旧值/0）
      * 之后改它内部的字段（数量、品质…）时，PatchEngine 知道
        要重新序列化整块，而不是在子节点上打一个无法定位的补丁
    """
    if node is None or _depth > 200:
        return
    if hasattr(node, 'start'):
        node.start, node.end = start, end
    for child in _kids(node):
        _tag_new(child, start, end, _depth + 1)


def clone_node(node, _depth=0):
    """深拷贝一棵节点树，把 '@' 链接展开成独立副本（自包含）。"""
    if _depth > 200:
        raise EditError('对象嵌套过深，可能有循环引用')
    if node is None:
        return None
    if isinstance(node, M.LinkNode):
        if node.target is None:
            raise EditError('对象链接 %d 找不到目标' % node.index)
        return clone_node(node.target, _depth + 1)
    if isinstance(node, M.NilNode):
        return M.NilNode()
    if isinstance(node, M.BoolNode):
        return M.BoolNode(node.value)
    if isinstance(node, M.IntNode):
        return M.IntNode(node.value)
    if isinstance(node, M.BignumNode):
        return M.BignumNode(node.value)
    if isinstance(node, M.FloatNode):
        return M.FloatNode(node.value, node.raw)
    if isinstance(node, M.SymbolNode):
        return M.SymbolNode(node.name, raw=node.raw)
    if isinstance(node, M.StrNode):
        return M.StrNode(node.data)
    if isinstance(node, M.ArrayNode):
        return M.ArrayNode([clone_node(x, _depth + 1) for x in node.items])
    if isinstance(node, M.HashNode):
        return M.HashNode([(clone_node(k, _depth + 1), clone_node(v, _depth + 1))
                           for k, v in node.pairs])
    if isinstance(node, M.ObjNode):
        o = M.ObjNode(node.cls)
        o.ivars = [(k, clone_node(v, _depth + 1)) for k, v in node.ivars]
        return o
    if isinstance(node, M.StructNode):
        s = M.StructNode(node.cls)
        s.ivars = [(k, clone_node(v, _depth + 1)) for k, v in node.ivars]
        return s
    if isinstance(node, M.UserDefNode):
        return M.UserDefNode(node.cls, node.data)
    if isinstance(node, M.IVarNode):
        n = M.IVarNode()
        n.inner = clone_node(node.inner, _depth + 1)
        n.ivars = [(k, clone_node(v, _depth + 1)) for k, v in node.ivars]
        return n
    raise EditError('无法拷贝的类型 %s' % type(node).__name__)


def make_pack_entry(item_template, count, new_instance_id=None,
                    standard_id=None, quality=None):
    """
    构造 @pack 的一格：Array[ 物品实例, 数量 ]

    item_template 是 data_items 里的某个 RPG::Item（模板，25 个字段），
    这里深拷贝一份作为"物品实例"，再补上模板里**没有**的实例专有字段：
      @standard —— 指向模板 id（对应 data_items 的 id）
      @id       —— 实例唯一编号
      @quality  —— 品质，实例必需

    踩过的坑（0.3）：模板里既没有 @standard 也没有 @quality。以前写入时如果
    没指定品质就不补这个字段，游戏读到 nil 按 0 处理，于是提示
    "该物品无法使用"。所以现在**始终**写入 @quality（默认 100）。
    数量同理兜底：0 个物品在游戏里点不动，最小写 1。
    """
    inst = clone_node(item_template)
    if not isinstance(inst, M.ObjNode):
        raise EditError('模板不是对象')

    def ensure(name, value):
        for i, (k, v) in enumerate(inst.ivars):
            if k == name:
                inst.ivars[i] = (k, M.IntNode(int(value)))
                return
        inst.ivars.append((name, M.IntNode(int(value))))

    count = int(count)
    if count < 1:
        count = 1
    if quality is None or int(quality) < 1:
        quality = DEFAULT_QUALITY
    if new_instance_id is not None:
        ensure('@id', new_instance_id)
    if standard_id is not None:
        ensure('@standard', standard_id)
    ensure('@quality', quality)          # 必须写：缺了游戏判定品质 0 -> 无法使用
    return M.ArrayNode([inst, M.IntNode(count)])


def find_ivar(obj, name):
    for k, v in obj.ivars:
        if k == name:
            return v
    return None


def ensure_ivar(obj, name, value):
    """把 ivar 设成给定值；没这个字段就追加（值必须是 int）。"""
    for i, (k, v) in enumerate(obj.ivars):
        if k == name:
            if isinstance(v, M.IntNode):
                obj.ivars[i] = (k, M.IntNode(int(value)))
            elif isinstance(v, M.StrNode):
                obj.ivars[i] = (k, M.StrNode(value.encode('utf-8')
                                             if isinstance(value, str) else bytes(value)))
            else:
                obj.ivars[i] = (k, M.IntNode(int(value)))
            return True
    obj.ivars.append((name, M.IntNode(int(value))))
    return False


def scalar_bytes(value):
    """把一个 Python 标量编成 Marshal 字节（用于把 '@N' 链接换成具体值）。"""
    if isinstance(value, bool):
        return M.reencode(M.BoolNode(value))
    if isinstance(value, int):
        return M.reencode(M.IntNode(value))
    if isinstance(value, float):
        return M.reencode(M.FloatNode(value, repr(float(value)).encode('ascii')))
    if isinstance(value, str):
        return M.reencode(M.StrNode(value.encode('utf-8')))
    if value is None:
        return b'0'
    raise EditError('不支持的标量类型 %r' % type(value).__name__)


def set_ivar_value(obj, name, value):
    for i, (k, v) in enumerate(obj.ivars):
        if k == name:
            if isinstance(v, M.IntNode):
                obj.ivars[i] = (k, M.IntNode(int(value)))
            elif isinstance(v, M.StrNode):
                obj.ivars[i] = (k, M.StrNode(value.encode('utf-8')
                                             if isinstance(value, str) else value))
            else:
                raise EditError('字段 %s 类型不支持' % name)
            return True
    return False


def save_plain(plain, path, crypto, backup=True, log=None):
    """自检 -> 备份 -> 加密写回 -> 读回校验。"""
    log = log or (lambda s: None)
    # 1) 新明文必须还能被解析（避免写出坏档）
    M.parse_stream(plain)
    # 2) 备份
    if backup and os.path.exists(path):
        shutil.copyfile(path, path + '.bak')
        log('已备份 %s.bak' % os.path.basename(path))
    # 3) 写回
    blob = crypto.encrypt(plain)
    with open(path, 'wb') as f:
        f.write(blob)
    # 4) 读回校验
    with open(path, 'rb') as f:
        back = crypto.decrypt(f.read())
    if back != plain:
        raise EditError('写回校验失败：重新读出的内容与预期不一致（未改动原文件？'
                        '请检查磁盘空间）')
    return path
