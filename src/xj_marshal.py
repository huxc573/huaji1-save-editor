# -*- coding: utf-8 -*-
"""
RPG Maker XP (Ruby 1.8 / Marshal 4.8) 读写库。

特点：
  * 解析时记录每个节点的字节区间 [start, end)，因此可以"就地改写"某一个值，
    而不必重新序列化整个数据流（对 2MB 级别的存档非常安全且飞快）。
  * 支持对象链接表（'@' 反向引用）与 'I' 包裹类型。
  * 提供 w_long / fixnum / string 的编码器，用于生成替换字节。

Ruby 1.8 Marshal 长整数编码（本游戏 .rxdata 与存档一致）：
    c == 0x00            -> 0
    0x01..0x04           -> 后续 c 字节，小端【无符号】
    0x05..0x7F           -> c - 5   （0..122）
    0x80..0xFB           -> 理论不出现
    0xFC..0xFF           -> 后续 (256-c) 字节，小端【二补数】
"""
import struct

__all__ = [
    'parse_stream', 'parse_object', 'dump_summary',
    'Node', 'NilNode', 'BoolNode', 'IntNode', 'FloatNode', 'BignumNode',
    'SymbolNode', 'StrNode', 'ArrayNode', 'HashNode', 'ObjNode',
    'StructNode', 'UserDefNode', 'UserMarshalNode', 'IVarNode', 'LinkNode',
    'ExtNode',
    'encode_long', 'encode_fixnum', 'encode_string', 'encode_bignum', 'reencode',
    'serialize', 'serialize_with_header', 'w_symbol_bytes',
]


# --------------------------------------------------------------------------
# 节点
# --------------------------------------------------------------------------
class Node(object):
    type = '?'
    __slots__ = ('start', 'end')

    def __init__(self, start=0, end=0):
        self.start = start
        self.end = end

    # 原始字节（需要 buf 才能取，交给 Cursor.raw_of）
    def text(self):
        return repr(self)


class NilNode(Node):
    type = '0'
    __slots__ = ('value',)

    def __init__(self, start=0, end=0):
        Node.__init__(self, start, end)
        self.value = None

    def text(self):
        # value 被改写过时（开关从 nil 改成 true 之类）显示真实值，
        # 否则界面会一直显示 nil，让人以为没改成功
        if isinstance(self.value, bool):
            return 'true' if self.value else 'false'
        if isinstance(self.value, int):
            return str(self.value)
        return 'nil'


class BoolNode(Node):
    __slots__ = ('value',)

    def __init__(self, value, start=0, end=0):
        Node.__init__(self, start, end)
        self.value = value

    def text(self):
        return 'true' if self.value else 'false'


class IntNode(Node):
    type = 'i'
    __slots__ = ('value',)

    def __init__(self, value, start=0, end=0):
        Node.__init__(self, start, end)
        self.value = value

    def text(self):
        return str(self.value)


class FloatNode(Node):
    type = 'f'
    __slots__ = ('value', 'raw')

    def __init__(self, value, raw, start=0, end=0):
        Node.__init__(self, start, end)
        self.value = value
        self.raw = raw

    def text(self):
        return repr(self.value)


class BignumNode(Node):
    type = 'l'
    __slots__ = ('value',)

    def __init__(self, value, start=0, end=0):
        Node.__init__(self, start, end)
        self.value = value

    def text(self):
        return str(self.value)


class SymbolNode(Node):
    type = ':'
    __slots__ = ('name', 'raw')

    def __init__(self, name, start=0, end=0, raw=None):
        Node.__init__(self, start, end)
        self.name = name
        if raw is not None:
            self.raw = raw
        else:
            self.raw = name.encode('utf-8') if isinstance(name, str) else bytes(name)

    def text(self):
        return ':' + self.name


class StrNode(Node):
    type = '"'
    __slots__ = ('data',)

    def __init__(self, data, start=0, end=0):
        Node.__init__(self, start, end)
        self.data = data            # bytes

    def text(self):
        return self.str()

    def str(self, enc='utf-8', errors='replace'):
        return self.data.decode(enc, errors)


class ArrayNode(Node):
    type = '['
    __slots__ = ('items',)

    def __init__(self, items, start=0, end=0):
        Node.__init__(self, start, end)
        self.items = items


class HashNode(Node):
    type = '{'
    __slots__ = ('pairs',)

    def __init__(self, pairs, start=0, end=0):
        Node.__init__(self, start, end)
        self.pairs = pairs          # [(knode, vnode), ...]

    def as_dict(self):
        """仅当键都是 int/str/symbol 时可用。"""
        d = {}
        for k, v in self.pairs:
            d[value_of(k)] = v
        return d


class ObjNode(Node):
    type = 'o'
    __slots__ = ('cls', 'ivars')

    def __init__(self, cls, start=0, end=0):
        Node.__init__(self, start, end)
        self.cls = cls
        self.ivars = []             # [(name, node), ...] 保持原始顺序

    def get(self, name, default=None):
        for k, v in self.ivars:
            if k == name:
                return v
        return default

    def settable(self, name):
        for k, v in self.ivars:
            if k == name:
                return v
        return None


class StructNode(Node):
    type = 'S'
    __slots__ = ('cls', 'ivars')

    def __init__(self, cls, start=0, end=0):
        Node.__init__(self, start, end)
        self.cls = cls
        self.ivars = []

    def get(self, name, default=None):
        for k, v in self.ivars:
            if k == name:
                return v
        return default


class UserDefNode(Node):
    type = 'u'
    __slots__ = ('cls', 'data')

    def __init__(self, cls, data, start=0, end=0):
        Node.__init__(self, start, end)
        self.cls = cls
        self.data = data            # bytes（原样保留，例如 RPG::Table）

    def text(self):
        return '<userdef %s %d bytes>' % (self.cls, len(self.data))


class UserMarshalNode(Node):
    type = 'U'
    __slots__ = ('cls', 'inner')

    def __init__(self, cls, start=0, end=0):
        Node.__init__(self, start, end)
        self.cls = cls
        self.inner = None           # 内嵌 Marshal 流（一般存档里没有）


class IVarNode(Node):
    type = 'I'
    __slots__ = ('inner', 'ivars')

    def __init__(self, start=0, end=0):
        Node.__init__(self, start, end)
        self.inner = None
        self.ivars = []


class LinkNode(Node):
    type = '@'
    __slots__ = ('index', 'target')

    def __init__(self, index, start=0, end=0):
        Node.__init__(self, start, end)
        self.index = index
        self.target = None

    def text(self):
        return '&%d' % self.index


class ExtNode(Node):
    """'e' 扩展类型（Ruby 1.9+），存档中极少出现，原样保留字节。"""
    type = 'e'
    __slots__ = ()


def value_of(node):
    """取标量值，用于展示/比较。"""
    if node is None:
        return None
    if isinstance(node, IntNode):
        return node.value
    if isinstance(node, BignumNode):
        return node.value
    if isinstance(node, BoolNode):
        return node.value
    if isinstance(node, StrNode):
        return node.data
    if isinstance(node, SymbolNode):
        return node.name
    if isinstance(node, FloatNode):
        return node.value
    if isinstance(node, NilNode):
        # nil 槽位可以被改写成 true/false 或整数（开关常见），
        # 所以这里返回 value 而不是硬编码 None
        return node.value
    return node


def ruby_str(obj):
    """Ruby inspect 风格的短文本。"""
    if obj is None:
        return 'nil'
    if obj is True:
        return 'true'
    if obj is False:
        return 'false'
    if isinstance(obj, bytes):
        try:
            return '"%s"' % obj.decode('utf-8')
        except UnicodeDecodeError:
            return '"%s"' % obj.decode('gbk', 'replace')
    if isinstance(obj, list):
        return '[' + ', '.join(ruby_str(x) for x in obj[:8]) + (', ...' if len(obj) > 8 else '') + ']'
    if isinstance(obj, dict):
        return '{' + ', '.join('%s=>%s' % (ruby_str(k), ruby_str(v)) for k, v in list(obj.items())[:8]) + '}'
    return str(obj)


# --------------------------------------------------------------------------
# 解析
# --------------------------------------------------------------------------
class MarshalError(Exception):
    pass


class Parser(object):
    def __init__(self, buf, base=0):
        self.b = buf
        self.i = 0
        self.base = base
        self.links = []             # 对象链接表（'@'）
        self.symbols = []           # 符号链接表（';'）

    # ---- 基础读取 ----
    def u8(self):
        v = self.b[self.i]
        self.i += 1
        return v

    def take(self, n):
        s = self.b[self.i:self.i + n]
        if len(s) != n:
            raise MarshalError('数据不足：需要 %d 字节，剩余 %d' % (n, len(s)))
        self.i += n
        return s

    def read_unsigned(self, n):
        x = 0
        for k in range(n):
            x |= self.u8() << (8 * k)
        return x

    def read_signed(self, n):
        x = self.read_unsigned(n)
        if x & (1 << (8 * n - 1)):
            x -= 1 << (8 * n)
        return x

    def w_long(self):
        c = self.u8()
        if c == 0:
            return 0
        if 1 <= c <= 4:
            return self.read_unsigned(c)
        if 5 <= c <= 0x7F:
            return c - 5
        if c >= 0xFC:
            return self.read_signed(256 - c)
        return c - 256

    # ---- 组合读取 ----
    def register(self, node):
        self.links.append(node)
        return node

    def read_symbol(self):
        t = self.u8()
        if t == ord(':'):
            n = self.w_long()
            raw = self.take(n)
            try:
                name = raw.decode('utf-8')
            except UnicodeDecodeError:
                name = raw.decode('latin-1')
            self.symbols.append(name)
            return SymbolNode(name)
        if t == ord(';'):
            # RGSS(Ruby) 符号链接表：';' + 索引
            n = self.w_long()
            if n >= len(self.symbols):
                raise MarshalError('符号链接越界 %d (共 %d 个)' % (n, len(self.symbols)))
            return SymbolNode(self.symbols[n])
        raise MarshalError('坏符号 0x%02X @%d' % (t, self.i - 1))

    def class_ref(self):
        """'o' / 'u' / 'S' / 'U' 之后的类名引用（可能带 'c' 前缀）。"""
        t = self.u8()
        if t == ord('c'):
            return self.read_symbol().name
        if t in (ord(':'), ord(';')):
            self.i -= 1
            return self.read_symbol().name
        raise MarshalError('坏类名 0x%02X @%d' % (t, self.i - 1))

    def read_ivars(self):
        n = self.w_long()
        out = []
        for _ in range(n):
            key = self.read_symbol()
            val = self.read_object()
            out.append((key.name, val))
        return out

    def read_string_bytes(self):
        n = self.w_long()
        return self.take(n)

    # ---- 主分派 ----
    def read_object(self):
        start = self.i
        t = self.u8()
        c = chr(t)

        if c == '0':
            return NilNode(start, self.i)
        if c == 'T':
            return BoolNode(True, start, self.i)
        if c == 'F':
            return BoolNode(False, start, self.i)
        if c == 'i':
            return IntNode(self.w_long(), start, self.i)
        if c == ':':
            self.i -= 1
            return self.read_symbol()
        if c == ';':
            self.i -= 1
            return self.read_symbol()
        if c == '"':
            node = StrNode(self.read_string_bytes(), start, self.i)
            node.end = self.i
            return self.register(node)
        if c == 'f':
            n = self.w_long()
            raw = self.take(n)
            try:
                val = float(raw.decode('ascii') or '0')
            except ValueError:
                val = 0.0
            # Ruby 的规则：除 nil/true/false/Fixnum/Symbol 外一切对象都占一个
            # 对象编号（Float 也算）—— 不注册的话后面所有 '@N' 链接会整体错位
            return self.register(FloatNode(val, raw, start, self.i))
        if c == 'l':                                  # Bignum：'l' + 符号 + w_long(16位字数) + 小端字
            sign = self.u8()
            n = self.w_long()
            words = []
            for _ in range(n):
                words.append(self.read_unsigned(2))
            val = 0
            for w in reversed(words):
                val = (val << 16) | w
            if sign == ord('-'):
                val = -val
            return self.register(BignumNode(val, start, self.i))
        if c == '[':
            n = self.w_long()
            node = ArrayNode([], start, 0)
            self.register(node)
            for _ in range(n):
                node.items.append(self.read_object())
            node.end = self.i
            return node
        if c == '{':
            n = self.w_long()
            node = HashNode([], start, 0)
            self.register(node)
            for _ in range(n):
                k = self.read_object()
                v = self.read_object()
                node.pairs.append((k, v))
            node.end = self.i
            return node
        if c == 'o':
            cls = self.class_ref()
            node = ObjNode(cls, start, 0)
            self.register(node)
            node.ivars = self.read_ivars()
            node.end = self.i
            return node
        if c == 'S':
            cls = self.class_ref()
            node = StructNode(cls, start, 0)
            self.register(node)
            node.ivars = self.read_ivars()
            node.end = self.i
            return node
        if c == 'u':
            cls = self.class_ref()
            n = self.w_long()
            node = UserDefNode(cls, self.take(n), start, self.i)
            node.end = self.i
            # RPG::Table 这类自定义序列化对象就是 'u'，它**也占一个对象编号**：
            # 以前漏了注册，导致它后面所有 '@N' 链接全部错位
            return self.register(node)
        if c == 'U':
            cls = self.class_ref()
            node = UserMarshalNode(cls, start, 0)
            self.register(node)
            node.inner = self.read_object()
            node.end = self.i
            return node
        if c == 'I':
            node = IVarNode(start, 0)
            self.register(node)
            node.inner = self.read_object()
            node.ivars = self.read_ivars()
            node.end = self.i
            return node
        if c == '@':
            idx = self.w_long()
            node = LinkNode(idx, start, self.i)
            if idx < len(self.links):
                node.target = self.links[idx]
            return node
        if c == 'e':                                  # 'e' + 模块名 + 对象（对象被 extend）
            self.read_symbol()
            # 被 extend 的是内层对象，编号也记在内层对象（它自己会注册）
            return self.read_object()
        raise MarshalError('未知类型 %r (0x%02X) @%d' % (c, t, start))


def parse_object(buf, pos, base=0, links=None):
    """从 buf[pos:] 解析一个对象，返回 (node, 新位置, links)。"""
    p = Parser(buf, base)
    p.i = pos
    p.links = links if links is not None else []
    node = p.read_object()
    return node, p.i, p.links


def parse_stream(buf):
    """
    解析"多个 Marshal 对象拼接"的数据流（RMXP 存档就是这样写的）。
    返回 [{'head': 版本头位置, 'node': 节点}, ...]

    注意：Ruby 每次 Marshal.load 都会**重置对象链接表**，所以每个顶层对象
    都从 0 开始编号 —— 这里必须每个对象新建一个 links 列表，不能跨对象累积。
    """
    out = []
    pos = 0
    n = len(buf)
    while pos < n:
        if buf[pos:pos + 2] == b'\x04\x08':
            head = pos
            pos += 2
        else:
            head = None
        node, pos, links = parse_object(buf, pos, 0, [])
        out.append({'head': head, 'node': node, 'links': links})
    return out


def encode_long(x):
    """Ruby 1.8 w_long 编码。"""
    if x == 0:
        return b'\x00'
    if 0 < x < 123:
        return bytes([x + 5])
    if -124 < x < 0:
        return bytes([(x - 5) & 0xFF])
    if x > 0:
        raw = bytearray()
        v = x
        while v:
            raw.append(v & 0xFF)
            v >>= 8
        return bytes([len(raw)]) + bytes(raw)
    v = x
    raw = bytearray()
    while True:
        raw.append(v & 0xFF)
        v >>= 8
        if v == -1:
            break
    return bytes([256 - len(raw)]) + bytes(raw)


def encode_fixnum(x):
    return b'i' + encode_long(int(x))


def encode_bignum(x):
    """'l' + 符号字节 + w_long(16 位字数) + 小端字。"""
    x = int(x)
    sign = b'-' if x < 0 else b'+'
    n = abs(x)
    words = []
    while n:
        words.append(n & 0xFFFF)
        n >>= 16
    return b'l' + sign + encode_long(len(words)) + b''.join(
        struct.pack('<H', w) for w in words)


def encode_string(s):
    if isinstance(s, str):
        s = s.encode('utf-8')
    return b'"' + encode_long(len(s)) + s


def encode_bool(v):
    return b'T' if v else b'F'


def reencode(node):
    """
    把一个**叶子标量节点**重新编码成 Marshal 字节（用于替换原始字节）。
    仅支持 int / bignum / bool / string / float / nil。
    """
    if isinstance(node, IntNode):
        return encode_fixnum(node.value)
    if isinstance(node, BignumNode):
        return encode_bignum(node.value)
    if isinstance(node, BoolNode):
        return encode_bool(node.value)
    if isinstance(node, StrNode):
        return encode_string(node.data)
    if isinstance(node, FloatNode):
        s = repr(float(node.value)).encode('ascii')
        return b'f' + encode_long(len(s)) + s
    if isinstance(node, NilNode):
        if isinstance(node.value, bool):
            return encode_bool(node.value)
        if isinstance(node.value, int):
            return encode_fixnum(node.value)
        return b'0'
    raise TypeError('不支持的节点类型 %r' % type(node).__name__)


# --------------------------------------------------------------------------
# 完整序列化（0.3 新增）：把任意解析树重新写成自包含的 Marshal 字节
#
# 为什么需要：给 @pack 添加物品时，要复制一个 RPG::Item 对象到另一个 Marshal
# 流里。原对象里可能含 '&link N'（对象链接），直接复制字节会让索引指向错误的
# 位置；所以这里**不使用链接**，把共用对象全部内联展开成独立的副本。
# 对游戏逻辑没有影响（物品本来就该是独立对象）。
# --------------------------------------------------------------------------
MAX_SERIALIZE_DEPTH = 300


def w_symbol_bytes(name):
    """符号（ivar 名 / 类名）编码：':' + 长度 + 原始字节。"""
    b = name if isinstance(name, bytes) else name.encode('utf-8')
    return b':' + encode_long(len(b)) + b


def serialize(node, depth=0):
    """把一个节点序列化成完整、自包含的 Marshal 字节（不含 04 08 版本头）。"""
    if depth > MAX_SERIALIZE_DEPTH:
        raise MarshalError('序列化嵌套过深（可能有循环引用）')
    if node is None:
        return b'0'
    if isinstance(node, NilNode):
        if isinstance(node.value, bool):
            return encode_bool(node.value)
        if isinstance(node.value, int):
            return encode_fixnum(node.value)
        return b'0'
    if isinstance(node, BoolNode):
        return encode_bool(node.value)
    if isinstance(node, IntNode):
        return encode_fixnum(node.value)
    if isinstance(node, BignumNode):
        return encode_bignum(node.value)
    if isinstance(node, FloatNode):
        return b'f' + encode_long(len(node.raw)) + node.raw
    if isinstance(node, SymbolNode):
        return w_symbol_bytes(node.raw)
    if isinstance(node, StrNode):
        return b'"' + encode_long(len(node.data)) + node.data
    if isinstance(node, ArrayNode):
        out = [b'[', encode_long(len(node.items))]
        for it in node.items:
            out.append(serialize(it, depth + 1))
        return b''.join(out)
    if isinstance(node, HashNode):
        out = [b'{', encode_long(len(node.pairs))]
        for k, v in node.pairs:
            out.append(serialize(k, depth + 1))
            out.append(serialize(v, depth + 1))
        return b''.join(out)
    if isinstance(node, (ObjNode, StructNode)):
        tag = b'o' if isinstance(node, ObjNode) else b'S'
        out = [tag, w_symbol_bytes(node.cls), encode_long(len(node.ivars))]
        for k, v in node.ivars:
            out.append(w_symbol_bytes(k))
            out.append(serialize(v, depth + 1))
        return b''.join(out)
    if isinstance(node, UserDefNode):
        return (b'u' + w_symbol_bytes(node.cls) + encode_long(len(node.data))
                + node.data)
    if isinstance(node, UserMarshalNode):
        return b'U' + w_symbol_bytes(node.cls) + serialize(node.inner, depth + 1)
    if isinstance(node, IVarNode):
        out = [b'I', serialize(node.inner, depth + 1),
               encode_long(len(node.ivars))]
        for k, v in node.ivars:
            out.append(w_symbol_bytes(k))
            out.append(serialize(v, depth + 1))
        return b''.join(out)
    if isinstance(node, LinkNode):
        if node.target is None:
            raise MarshalError('对象链接 %d 没有目标，无法展开' % node.index)
        return serialize(node.target, depth + 1)
    raise TypeError('不支持的节点类型 %r' % type(node).__name__)


def serialize_with_header(node):
    """带 04 08 版本头的完整 Marshal 对象。"""
    return b'\x04\x08' + serialize(node)
