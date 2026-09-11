# -*- coding: utf-8 -*-
"""
xj_model —— 把解密后的 Marshal 数据整理成"界面能显示的一切"（0.2，只读）

对应游戏脚本：
  0030 Module Save_Load  存档路径与读写顺序
  0007 LockNumber        数字防作弊编码（金钱）
  0044 Game_Actor        等级/经验/五维/潜力、exp_list、maxhp/maxsp
  0045 装备名后缀        名字,HP,SP,等级
"""
import hashlib
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import xj_codec as C
import xj_edit as E
import xj_marshal as M

try:
    import pet_table as _PET_TABLE_MOD      # 由 gen_pet_table.py 从游戏脚本生成
except Exception:                           # pragma: no cover
    _PET_TABLE_MOD = None

# 项目元信息（界面、文档、打包都用它，只维护这一处）
APP_NAME = '画迹1：落日情缘 存档工具'
APP_VERSION = '1.3.1'
AUTHOR = 'huxc573'
HOMEPAGE = 'https://github.com/huxc573/huaji1-save-editor'
LICENSE_NAME = 'MIT License'
ISSUES = HOMEPAGE + '/issues'

# 明文里 19 个顶层对象的顺序（来自 0030 脚本的 read_save_data）
TOP_NAMES = ['characters', 'frame_count', 'game_system', 'game_switches',
             'game_variables', 'game_self_switches', 'game_screen', 'game_actors',
             'game_party', 'game_troop', 'game_map', 'game_player',
             'data_items', 'data_classes', 'data_weapons', 'data_armors',
             'data_actors', 'data', '存档id']

# 游戏里的三个 20 格物品容器（脚本 0155 System::Data）
#   道具 = @pack，行囊 = @wallet，备用 = @talisman
CONTAINERS = (('@pack', '道具'), ('@wallet', '行囊'), ('@talisman', '备用'))

TOP_DESC = {
    'characters': '队伍角色的行走图 [名字, 色相]',
    'frame_count': '游戏帧数（60 帧 = 1 秒）',
    'game_system': '音量 / 存档次数 / 改名开关等',
    'game_switches': '@data 布尔数组（开关）',
    'game_variables': '@data 数值数组（变量）',
    'game_self_switches': '独立开关 Hash',
    'game_screen': '画面震动 / 闪烁 / 天气',
    'game_actors': '@data 全部角色＋召唤兽（下标 = @actor_id；>20 是召唤兽）',
    'game_party': '@actors 出战队伍（副本B）＋ @原id/@现id 召唤兽槽位表 ＋ 步数 / 金钱',
    'game_troop': '当前战斗队伍',
    'game_map': '地图状态（含 RPG::Table 通行表）',
    'game_player': '玩家坐标与朝向',
    'data_items': '数据库快照：物品（新增的物品要登记进来游戏才认）',
    'data_classes': '数据库快照：职业',
    'data_weapons': '数据库快照：武器',
    'data_armors': '数据库快照：防具',
    'data_actors': '数据库快照：角色；21..998 是召唤兽模板（运行时也当召唤兽槽位用）',
    'data': 'System::Data：@pack/@wallet/@talisman（三个 20 格物品容器）/ @cash / @fame',
    '存档id': '机器码数组（读档时会与当前机器比对）',
}

# ---------------------------------------------------------------------------
# 字段注释表（0.7）：给"全部解析数据"页的每一行一句人话说明
#
# 顺序：先按"父对象的类"查专表，再查通用表；都没有就按类型给一句兜底。
# 值里的 %s 之类由 _note_of 填。
# ---------------------------------------------------------------------------
NOTE_FIELD = {
    # ---- 通用 / Game_Actor ----
    '@name': '名字',
    '@id': '编号',
    '@level': '等级',
    '@exp': '经验值（游戏用 @exp_list 表换算，工具里改等级会自动同步）',
    '@hp': '当前气血 HP',
    '@sp': '当前法力 SP',
    '@maxhp_plus': '气血上限加成（装备/宝石给的）',
    '@maxsp_plus': '法力上限加成',
    '@str_plus': '附加攻击',
    '@dex_plus': '附加灵巧',
    '@agi_plus': '附加速度',
    '@int_plus': '附加灵力',
    '@latent': '潜力（升级可分配的点数）',
    '@vitality': '活力（游戏里的行动点）',
    '@spirit': '体力',
    '@tizhi': '体质（五维之一）',
    '@moli': '魔力（五维之一）',
    '@liliang': '力量（五维之一）',
    '@naili': '耐力（五维之一）',
    '@minjie': '敏捷（五维之一）',
    '@add_tizhi': '附加体质',
    '@add_moli': '附加魔力',
    '@add_liliang': '附加力量',
    '@add_naili': '附加耐力',
    '@add_minjie': '附加敏捷',
    '@五行': '五行属性（金木水火土）',
    '@skills': '已学技能 id 数组 —— 游戏的 learn_skill 就是 push + sort!',
    '@states': '当前状态 id 数组',
    '@states_turn': '状态剩余回合 Hash',
    '@babys': '拥有的召唤兽槽位 —— 召唤兽界面就按这个数组的顺序显示',
    '@baby': '当前参战的召唤兽槽位（0 = 没参战）',
    '@new_name': '改过的名字（游戏显示名 custom_name = @new_name 或 @name）',
    '@actor_id': '角色编号：≤20 是人物，>20 是召唤兽',
    '@class_id': '职业 id（查 data_classes）',
    '@weapon_id': '武器 id（查 data_weapons）',
    '@armor1_id': '装备 1 id',
    '@armor2_id': '装备 2 id',
    '@armor3_id': '装备 3 id',
    '@armor4_id': '装备 4 id',
    '@armor5_id': '装备 5 id',
    '@exp_list': '各级所需经验表（下标 = 等级）',
    '@character_name': '行走图文件名',
    '@battler_name': '战斗图文件名',
    '@character_hue': '行走图色相',
    '@battler_hue': '战斗图色相',
    '@current_action': '当前战斗行动（战斗用）',
    '@past_action': '历史行动（战斗用）',
    '@who_attack_me': '上一次攻击我的人（战斗用）',
    '@immortal': '不死身标志',
    '@hidden': '隐藏标志',
    '@damage': '待弹出的伤害数字',
    '@critical': '本次是否暴击',
    '@animation_id': '正在播放的动画 id',
    '@修炼等级': '召唤兽修炼等级（5 项）',
    '@成长': '召唤兽成长率（影响升级时涨多少属性）',
    '@loyal': '召唤兽忠诚度',
    '@攻击资质': '召唤兽攻击资质',
    '@防御资质': '召唤兽防御资质',
    '@体力资质': '召唤兽体力资质',
    '@法力资质': '召唤兽法力资质',
    '@速度资质': '召唤兽速度资质',
    '@躲闪资质': '召唤兽躲闪资质',
    '@多体攻击': '技能标志：群体攻击',
    '@多人攻击': '技能标志：多人攻击',
    '@吸血': '技能标志：吸血',
    '@连击': '技能标志：连击',
    '@反击': '技能标志：反击',
    '@闪避': '技能标志：闪避',
    '@法术连击': '技能标志：法术连击',
    '@保护者': '保护我的人（战斗用）',
    '@startactive': '待机动作名',
    '@startactive1': '待机动作名 2',
    # ---- 物品 / 装备 ----
    '@standard': '模板 id（指向 $data_items 的下标，名字/图标/效果都看它）',
    '@quality': '品质（实例专有字段，缺了游戏按 0 处理 → 物品点不动）',
    '@occasion': '使用场合：0=随时 1=战斗 2=菜单 3=不能用',
    '@price': '价格',
    '@consumable': '是否消耗品（true 时使用后数量 -1）',
    '@icon_name': '图标文件名（少写扩展名）',
    '@description': '说明文字',
    '@element_set': '属性集合（含 26 表示不可叠加，一次只能占一格）',
    '@scope': '使用范围（1=单个敌人 … 7=己方全体）',
    '@animation1_id': '动画 id 1',
    '@animation2_id': '动画 id 2',
    '@common_event_id': '使用后触发的公共事件 id',
    '@menu_se': '菜单音效',
    '@minus_state_set': '使用后解除的状态',
    '@plus_state_set': '使用后附加的状态',
    '@atk': '攻击力',
    '@def': '防御力',
    '@spi': '灵力',
    '@agi': '敏捷',
    '@mdef': '法术防御',
    '@dex': '灵巧',
    '@two_handed': '双手武器',
    '@arms_type': '武器类型',
    '@armor_type': '防具类型',
    '@auto_state_id': '附带状态 id',
    '@item_id': '关联物品 id',
    '@parameter_points': '成长点数',
    # ---- 数量 / 数量对 ----
    '@n': '个数',
    # ---- $game_party ----
    '@actors': '出战队伍（副本B，和"角色表"里的同一个角色两份数据）',
    '@gold': '金钱（LockNumber 编码，工具会重算 6 组）',
    '@steps': '步数',
    '@items': '旧版背包 Hash（本作用的不是它，见 System::Data 的 @pack/@wallet/@talisman）',
    '@weapons': '武器袋 Hash',
    '@armors': '防具袋 Hash',
    '@mounts': '坐骑 Hash',
    '@equip_mount_id': '各角色已装备的坐骑',
    '@select_index': '上次选择的光标位置',
    '@原id': '召唤兽槽位 → 原始模板 id（@现id[k] 的模板就是 @原id[k]）',
    '@现id': '召唤兽槽位表（真正的槽号 21..998）',
    '@编号': '已分配的召唤兽槽位数量',
    # ---- System::Data ----
    '@cash': '金钱（LockNumber 6 组校验，改这里要用工具的「金钱」）',
    '@fame': '声望',
    '@store_cash': '仓库金额',
    '@pack': '道具栏：20 格，每格 = [物品实例, 数量] 或 nil',
    '@wallet': '行囊：20 格，结构同道具栏',
    '@talisman': '备用：20 格，结构同道具栏',
    # ---- Game_System ----
    '@save_count': '保存次数',
    '@bgm_volume': 'BGM 音量',
    '@bgs_volume': 'BGS 音量',
    '@se_volume': '音效音量',
    '@me_volume': 'ME 音量',
    '@改名开关': '召唤兽改名系统开关（true = 允许在游戏里花活力改名）',
    '@magic_number': '存档魔数',
    '@battle_bgm': '战斗 BGM',
    '@battle_end_me': '战斗结束 ME',
    '@gameover_me': 'Game Over ME',
    '@battleback_name': '战斗背景图',
    '@window_tone': '窗口色调',
    '@message_position': '对话框位置',
    '@menu_commands': '菜单命令',
    '@map_interpreter': '地图事件解释器',
    # ---- Game_Screen / Game_Map / Game_Player ----
    '@tone': '色调',
    '@flash': '闪烁',
    '@shake': '震动',
    '@weather_type': '天气类型',
    '@weather_max': '天气强度',
    '@weather_duration': '天气剩余帧数',
    '@map_id': '当前地图 id',
    '@tileset_id': '图块组 id',
    '@display_x': '地图显示 X',
    '@display_y': '地图显示 Y',
    '@scroll_directions': '滚动方向表',
    '@x': 'X 坐标',
    '@y': 'Y 坐标',
    '@direction': '朝向（2 下 4 左 6 右 8 上）',
    '@real_x': '实际 X（×128）',
    '@real_y': '实际 Y（×128）',
    '@pattern': '行走图帧',
    '@move_speed': '移动速度',
    '@move_frequency': '移动频率',
    '@move_route': '移动路线',
    '@through': '穿透（可穿墙）',
    '@always_on_top': '总在最上层',
    '@opacity': '不透明度',
    '@blend_type': '混合模式',
    '@walk_anime': '行走动画',
    '@step_anime': '踏步动画',
    '@jump_count': '跳跃计数',
    # ---- LockNumber ----
    '@value': '编码后的数值（6 组之一）',
    '@key1': '随机密钥 1',
    '@key2': '随机密钥 2',
    '@key3': '随机密钥 3',
    # ---- 战斗 / 杂项 ----
    '@troop_id': '敌人队伍 id',
    '@members': '成员',
    '@enemies': '敌人',
    '@missing': '（不使用的字段）',
}


def deref(node):
    """解开对象链接（'&N'）拿到真正的节点（背包里的字符串/图标经常是链接）。"""
    if isinstance(node, M.LinkNode) and node.target is not None:
        return node.target
    return node


def vof(node, default=None):
    """取标量值，自动解开链接。"""
    if node is None:
        return default
    v = M.value_of(deref(node))
    return default if v is None else v


def stext(node, default=''):
    n = deref(node)
    return n.str() if isinstance(n, M.StrNode) else default


def value_text(node, maxlen=120):
    """把一个节点显示成一行简短文本。"""
    if node is None:
        return 'nil'
    if isinstance(node, M.NilNode):
        # nil 槽位被改写成 true/false/整数后要显示新值（开关常见）
        return node.text()
    if isinstance(node, M.BoolNode):
        return 'true' if node.value else 'false'
    if isinstance(node, M.IntNode):
        return str(node.value)
    if isinstance(node, M.BignumNode):
        s = str(node.value)
        return s if len(s) <= 40 else s[:20] + '…(' + str(len(s)) + '位)'
    if isinstance(node, M.FloatNode):
        return repr(node.value)
    if isinstance(node, M.SymbolNode):
        return ':' + node.name
    if isinstance(node, M.StrNode):
        s = node.str()
        return '"%s"' % (s if len(s) <= maxlen else s[:maxlen] + '…')
    if isinstance(node, M.ArrayNode):
        return 'Array[%d]' % len(node.items)
    if isinstance(node, M.HashNode):
        return 'Hash{%d}' % len(node.pairs)
    if isinstance(node, M.ObjNode):
        return node.cls
    if isinstance(node, M.StructNode):
        return 'Struct:%s' % node.cls
    if isinstance(node, M.UserDefNode):
        return 'userdef(%s, %d 字节)' % (node.cls, len(node.data))
    if isinstance(node, M.LinkNode):
        return '&链接%d' % node.index
    return type(node).__name__


def type_text(node):
    if node is None:
        return '?'
    if isinstance(node, M.IntNode):
        return '整数'
    if isinstance(node, M.BignumNode):
        return '大整数'
    if isinstance(node, M.BoolNode):
        return '布尔'
    if isinstance(node, M.NilNode):
        if isinstance(node.value, bool):
            return '布尔'
        if isinstance(node.value, int):
            return '整数'
        return 'nil'
    if isinstance(node, M.FloatNode):
        return '浮点'
    if isinstance(node, M.SymbolNode):
        return '符号'
    if isinstance(node, M.StrNode):
        return '字符串'
    if isinstance(node, M.ArrayNode):
        return '数组'
    if isinstance(node, M.HashNode):
        return '哈希'
    if isinstance(node, M.ObjNode):
        return '对象:' + node.cls
    if isinstance(node, M.StructNode):
        return '结构:' + node.cls
    if isinstance(node, M.UserDefNode):
        return '自定义:' + node.cls
    if isinstance(node, M.LinkNode):
        return '对象链接'
    return type(node).__name__


def children_of(node):
    """返回 [(子标签, 子节点), ...]；没有子节点返回 []。"""
    if isinstance(node, (M.ObjNode, M.StructNode)):
        return [(k, v) for k, v in node.ivars]
    if isinstance(node, M.ArrayNode):
        return [('[%d]' % i, v) for i, v in enumerate(node.items)]
    if isinstance(node, M.HashNode):
        return [('{%s}' % value_text(k, 40), v) for k, v in node.pairs]
    return []


def exp_for_level(actor_id, level):
    """复刻 Game_Actor#make_exp_list（0044）。"""
    total = 0
    for i in range(1, int(level) + 1):
        total += (i * i * 50 + i ** 2) if actor_id > 20 else (i * i * 100 + i ** 3)
    return total


# ---------------------------------------------------------------------------
# $pet 名字表（脚本 0011）—— 现场解析
# ---------------------------------------------------------------------------
def split_top_level(s):
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


def parse_pet_table(path):
    """把脚本里的 $pet = { "名字" => [...], ... } 解析成 dict。"""
    with open(path, encoding='utf-8', errors='replace') as f:
        lines = f.read().splitlines()
    table = {}
    for s in lines:
        m = re.match(r'^\s*"([^"]{1,24})"\s*=>\s*\[(.*)\]\s*,?\s*$', s)
        if not m:
            continue
        parts = split_top_level(m.group(2))
        if len(parts) < 8:
            continue
        try:
            zz = [int(x) for x in parts[:6]]
            carry = int(parts[7])
        except ValueError:
            continue
        grow = [float(g) for g in re.findall(r'[-\d.]+', parts[6])]
        table[m.group(1)] = (zz, grow, carry)
    return table


# 版本更新日志（界面上"更新日志"页直接显示这段）
CHANGELOG = ("""【画迹1：落日情缘】存档工具 —— 更新日志
================================================================
作者 %s　·　开源地址 %s　·　%s
反馈：%s
版本规则：0.1 ~ 0.7 是开发期迭代，v1.0 首次公开发布，v1.1~v1.2 修 bug，v1.3 起加功能
================================================================

""" % (AUTHOR, HOMEPAGE, LICENSE_NAME, ISSUES)) + """1.3.1 2026-09-12 （修：点【克隆技能…】报 bad window path name）
----------------------------------------------------------------
* 对话框的按钮不能在自己的回调里同步 destroy()：ttk 的按钮绑定脚本
  调完 -command 后还会去操作这个按钮（复位 pressed 等），窗口没了就报
    TclError: bad window path name ".!toplevel.!frame.!button"
  现在一律用 win.after_idle(win.destroy) 延后销毁。
* 界面测试改成模拟真实点击（Press+Release），并断言没有 Tk 回调异常
  —— 只调 button.invoke() 是绕过绑定脚本的，抓不到这类问题。

""" + """1.3  2026-09-11  （新功能：召唤兽技能克隆）
----------------------------------------------------------------
[新] 【克隆技能…】：把另一个角色/召唤兽的**整张技能表**复制到当前这只。
  * 用途：新抓的宝宝想直接拥有主宠那套技能，不用一个个手点。
  * 下拉里能看到每个角色的技能数和前几个技能名，按技能多少排序；
  * 目标原有的技能表会被整表替换，**源不受影响**；
  * 目标哪怕是个 "@N" 链接对象（嵌在别处）也能克隆。
[修] set_actor_skills 现在一律给 @skills 换**新数组**（不原地改 items）——
  万这个数组是共享对象，原地改会连源一起改掉。

""" + """1.2  2026-09-11  （修召唤兽列不全 + 技能表加“技能描述”列）
----------------------------------------------------------------
[1] 召唤兽少了一只（游戏里能看到，工具列表里没有）
  * 根因：$game_actors.@data[槽位] 可能是 **'@N' 对象链接**，不是真的对象。
    实测：@data[165] = '@62'，而那个真正的 Game_Actor(@actor_id=165)
    嵌在 @data[12].@who_attack_me.@who_attack_me 里。
    游戏能正常显示，而工具只认 ObjNode，于是那只召唤兽被当成不存在。
  * 现在 actors() 会自动解引用 '@N'，列表与游戏界面一致。
[2] 召唤兽技能表新增“技能描述”列（技能名右边，可横向滚动）
  * 取自 Data/Skills.rxdata 的 @description；“搜索技能”也会匹配描述。

""" + """1.1  2026-09-11  （修 bug：改金钱报错、改名/改技能失效、负数被改坏）
----------------------------------------------------------------
[1] 改金钱报 MarshalError: 未知类型 't' (0x74)
  * 金钱是 LockNumber 编码（6 组校验值），中间值动辄上亿、要 5 个字节；
    老代码仍按 'i' + 长度字节 写，长度字节成了 05 —— 而 5 在 Ruby 的
    w_long 里表示"直接值 0"，一个字节都不多消耗，整条流从此错位。
  * 现在：装得进 4 字节就用 'i'，装不下就写大整数 'l'；encode_long() 对
    5 字节以上的值直接报错，不再静默写坏。
[2] 负数被读错，改名/改技能时把存档改坏
  * 解析"直接小负数"时少了 +5（Ruby 写 x-5，读要 +5）：-1 被读成 -6；
    而改名/改技能会整条重写 $game_actors，于是把读错的 -6 按正确公式写回
    —— 每重写一次偏移 -5（实测 @target_index：-1 → -6 → -11 → -16）。
  * 现在修正读取；另外【放弃修改】以前只丢补丁引擎，内存树还留着被打过
    整块区间标记的节点，之后改物品数量会把整格写成一个数字（数量变 0），
    现在会用原始明文重新解析。
[3] 改名 / 改技能 / 一键修复名字 报「序列化嵌套过深」
  * 战斗过的存档里 Game_Actor#@who_attack_me 是 Game_Enemy，它的
    @who_attack_me 又用 '@N' 指回同一个 Game_Actor —— 真循环；
    老的 serialize() 只会把链接展开成副本，遇到环就无限递归。
  * 现在按 Ruby 规则编号、重复对象发 '@N' 引用，环自然收住，
    而且重写子树时"占用的对象个数不变"，不会把后面的链接弄错位。

""" + """1.0  2026-09-11  （改名安全：校验 $pet 名字表 + 一键修复；防止召唤兽界面崩溃）
----------------------------------------------------------------
[严重修复] 把召唤兽的 @name 改成表外的名字会让游戏直接报错
  * 现象：打开召唤兽界面弹
       脚本 'Sys <召唤兽>' 的 147 行发生了 NoMethodError.
       undefined method '[]' for nil:NilClass
  * 根因（脚本证据）：
      0011：$pet = { "宠物名" => [六项资质, [成长…], 参战等级], ... }  ← 以**名字**为键
      0163 第 147 行：$pet["#{baby.name}"][7]        ← 没有 nil 判断
      0163 第 436/439 行、0121 第 572 行、0164 第 231/242 行 同样没有判断
      0044 Game_Actor#setup：@name = actor.name.split(/【/)[0]，且 name 就是 @name
    ⇒ 召唤兽的 @name 必须正好是 $pet 里的某个键；否则 $pet[名字] 是 nil，
      nil[7] 就抛 NoMethodError。
  * 本版改动：
      · 「角色 / 召唤兽」页新增「名字表」列：✔ = 在 $pet 表里，⚠ = 不在（会让游戏崩）
      · 新增「携带等级」列（就是 $pet[名字][7]，游戏用它判断能不能参战）
      · 名字栏实时显示校验结果；【改基础名(@name)】写召唤兽时若名字不在表里，
        会先弹确认，并给出模板本名建议
      · 新增【恢复模板本名】：把 @name 改回 $data_actors[模板].name
        （复刻游戏 0044 的 name.split(/【/)[0]）
      · 新增【一键修复名字】：把所有名字异常的召唤兽批量改回模板本名
      · 「概览」页也直接报「⚠ 有 N 只名字不在 $pet 表里」
      · 召唤兽的**显示名**（@new_name）不受影响 —— 游戏里花活力改名写的是
        @new_name，不参与 $pet 查表，随便改都不会崩
  * 名字表来源：优先现场解析游戏脚本 Try/scripts/0011_*.rb，
    找不到就用随程序携带的 pet_table.py（由 gen_pet_table.py 从同一脚本生成，154 个名字）
* 保留 0.7 的：召唤兽按界面顺序（主人 @babys）、已放生默认不显示、
  改名（@new_name / @name）、解析页注释列。

0.7  2026-09-11  （召唤兽按界面顺序 + 隐藏已放生；能改名；解析页加注释列）
----------------------------------------------------------------
[修复] 召唤兽列表的顺序与游戏不一致
  * 以前是按 @actor_id 排序；游戏"召唤兽"界面其实是按主人角色 @babys 数组的
    顺序显示的（脚本 0143 Window_Baby#refresh：@actor.babys.each）
  * 现在顺序 = 主人（队伍顺序）× 主人 @babys 的顺序，表格新增「序」列
[修复] 已经放生的召唤兽还显示在列表里
  * 放生（脚本 0044 remove_baby）只会把槽位从人物 @babys 里删掉、
    把 $data_actors[槽位] 清空，$game_actors 里的 Game_Actor 对象还留着 ——
    所以以前按 @actor_id > 20 枚举就把放生过的也列出来了
  * 现在只列"还被某个角色持有"的召唤兽；想查看残留数据可以勾上
    「显示无主（已放生）的召唤兽」，这些行会标出「无主」
[新功能] 改名字（人物 + 召唤兽）
  * 游戏显示名 = @new_name 存在 ? @new_name : @name（0040 Game_Battler#custom_name）
  * 【设为显示名】写 @new_name（等于游戏里花 30 活力改名）；【改基础名】写 @name；
    【清除显示名】删掉 @new_name 恢复本名
  * @new_name 平时不在存档里，改名会往对象里追加字段 —— 工具会自动整条重写
    $game_actors / $game_party，对象链接全部展开，编号自洽
[新功能] 「全部解析数据」页增加「注释」列
  * 每个字段/元素都给一句说明：@babys 会说"召唤兽界面就按这个数组顺序显示"、
    @skills 的元素会显示技能名、data_items 的元素会显示物品名、
    data_actors 的召唤兽槽位会显示"模板 145 白麒麟 —— 主人 义龙翔"、
    物品实例会显示"模板 87 祈福酒肆 品质 100"……
  * 摘要列同时补上了召唤兽的顺序/主人/槽位/模板信息
[改进] 召唤兽表新增列：序（界面顺序）/ 主人 / 槽位 / 模板 / 显示名 / 原名
* 保留 0.6 的：人物与召唤兽分组、召唤兽技能增删、解析页全局搜索 + 双击跳转；
  0.5 的：物品登记进 $data_items、对象链接整条重写、三个物品容器。

0.6  2026-09-11  （人物/召唤兽分开，召唤兽可改技能；解析页全局搜索）
----------------------------------------------------------------
[新功能] “角色 / 召唤兽”页拆成两组（游戏里用 @actor_id 区分，>20 的是召唤兽）
  * 人物表：门派/等级/经验/HP/SP/五维/潜力（原有字段）
  * 召唤兽表：等级/成长/忠诚/攻击・防御・体力・法力・速度・躲闪资质/技能数
  * 召唤兽编辑区：等级/经验/HP/SP/五维/潜力/活力/体力 + 成长/忠诚 + 六项资质
  * 召唤兽预设按钮：资质+500、成长+0.1、忠诚100 + 五维+10、HP/SP 填满
[新功能] 召唤兽技能（存档字段 @skills，技能模板读 Data/Skills.rxdata）
  * 显示已学技能（id + 名字，如 高级必杀 / 龙卷雨击 / 五雷咒）
  * 【学会技能】/【忘掉选中】/【清空技能】，带技能搜索框（共 233 个技能）
  * 与游戏一致：学完会按 id 升序（游戏的 learn_skill 也是 push + sort）
[新功能] “全部解析数据”页改成全局搜索
  * 搜字段名或值（所有 19 个顶层对象、所有层级），结果带完整路径
  * 双击结果可跳到左侧树上对应位置（自动逐层展开）
  * 展开数据多时加了滚动条（树 / 详情 / 搜索结果都有）
[修复]
  * 读数据库文件的路径：以前只在存档旁边找 Data/，现在会从存档目录和
    程序目录逐级向上找 —— 靠在 Audio/BGM 下的存档现在能读到
    Data/Skills.rxdata、Data/Items.rxdata 了
  * 召唤兽的 @成长 这类字段是 '@N' 对象链接（共享的 0.0），直接改会失败，
    现在会自动“物化”成独立值
* 保留 0.5 的：物品登记进 $data_items、对象链接整条重写、三个物品容器；
  0.4 的：写入带 @quality、数量至少 1、操作后立即刷新；
  0.3 的：自带 32 位宿主（无 PowerShell、无黑框）、机器码读取。

0.5  2026-09-11
----------------------------------------------------------------
[严重修复] Marshal 对象链接（'@N'）被写坏 —— 这才是“物品无法使用”的真凶
  * 存档里 @pack 第 2 格（佛手）的 @name / @icon_name / @menu_se 等字段是
    “对象链接”，指向第 1 格内部的对象（Marshal 为了省空间，把同一个对象
    在后面的出现写成 “@编号”）
  * 老版本替换第 1 格时，新块内部的对象顺序/数量变了，于是第 2 格的链接
    全部指错 —— 游戏里就是“只改了第 1 格，第 2 格的图标也跟着变”，
    点物品还会弹 TypeError: cannot convert Array into String
  * 现在只要动过物品栏，保存时会**整条重写 $data 流**：所有对象链接都展开
    成独立副本，编号完全自洽，不会再牵连别的格子
[修复] 解析器的对象编号规则与 Ruby 对齐
  * Float / Bignum / UserDef（RPG::Table）以前没有参与对象编号，
    导致它们之后的所有 '@N' 链接整体错位（曾让链接解析不到目标）
[严重修复] 新增的物品游戏不认：“该物品无法使用！再试也不能用，233333”
  * 游戏脚本 0155/0156：新增物品时 `item.id = $data_items.size` 并把实例
    `$data_items.push(item)`；使用物品时用 `$data_items[实例.@id]` 判断
    能不能用（读它的 occasion）。以前我们给新物品随便编了个 @id（1001+），
    又没登记进 $data_items -> 游戏查到 nil，直接判“无法使用”
  * 现在与游戏一致：新物品/换模板时分配新槽号（= $data_items 的长度）并把
    实例登记进去；只改数量/品质则沿用原槽。保存时会整条重写 $data_items
[改进] 物品栏分成游戏里的三个容器：道具 @pack / 行囊 @wallet / 备用 @talisman
  * 每个容器 20 格，都能改数量/换物品/删除/新增
  * 表格增加“登记”列（✔ = 游戏认得这件物品）
  * “搜索物品”框移到“物品 id”上面：先搜索过滤，再从下拉里选
[新增] “一键修复异常格”现在也能识别没登记的物品，按模板重建并登记
  即可救回旧版本写坏的档

0.4  2026-09-11
----------------------------------------------------------------
[修复] 写入物品后游戏提示"该物品无法使用"
  * 根因：物品模板（Data/Items.rxdata）里只有 25 个字段，@standard 和
    @quality 是**实例专有**字段。以前写入时如果不指定品质就不会补
    @quality，游戏读到 nil 按 0 处理 —— 品质 0 的物品点不动
  * 现在写入物品一定会带上 @quality（默认 100）、@standard 和新的 @id
[修复] 往空格写入时数量变成 0
  * 原因是把字符串 "0" 当成了有效输入；现在数量小于 1 一律按 1 处理
[改进] 物品栏：格子 / 数量 / 物品id / 品质 四个输入框，
  配合「写入 · 修改该格」和「删除该格」两个按钮
  * 空的格子 = 新建（自动分配新实例 id）；已有物品的格子 = 重建
    （沿用原来的实例 id，品质默认 100，数量默认 1）
  * 每次操作后立刻刷新物品栏和概览，不用手工重新载入
[新增] 「全部解析数据」页可以右键修改：对着任意标量字段（整数 / 大整数 /
  布尔 / 文本 / 浮点 / nil）点右键 ->「修改这个值…」，改完马上显示
[新增] 物品栏「一键修复异常格」：扫出缺品质字段 / 数量异常 / 缺 @standard 的
  格子，按模板重建（数量至少 1、品质默认 100）
[说明] 如果 0.3 已经把某格写坏了（缺 @quality），选中那一格点一次
  「写入 · 修改该格」也能按模板重建好

0.3  2026-09-11
----------------------------------------------------------------
[加解密]
  * 新增自带的 32 位宿主 XJCodec32.exe（7 KB，随程序分发）：
      - 不再弹出 PowerShell 黑框（子进程完全静默运行）
      - 打开存档从"每次 1~3 秒"降到"毫秒级"
      - 不再依赖系统里的 PowerShell；找不到宿主时才回退（同样是静默的）
[修复]
  * 修好"当前机器机器码"读取：0.2 的 PowerShell 桥漏了加载 Socket.dll，
    导致 GetID 一直返回空。现在能正确显示本机机器码，可直接用于修改存档
[物品栏]
  * 修正物品栏来源：游戏实际用的是 System::Data 的 @pack（20 格），
    不是 $game_party.@items。每格 = [ RPG::Item 实例, 数量 ]
  * 界面现在显示：格子、物品名、模板 id（对应 data_items）、实例 id、
    数量、品质、说明
[修改功能]
  * 金钱（元宝，LockNumber 6 组校验一起重算）、声望、仓库金额、步数
  * 角色：等级（自动同步经验）、经验、HP/SP、活力/体力、五维、潜力、附加属性
  * 物品栏：改数量、删除、新增、更换模板
  * 开关、变量、存档机器码
  * 保存前自动备份 sy.ogg.bak；写回后重新解密回读校验，并做结构自检
[当时修的边界问题]
  * 同一个字段改两次（金钱先改 100 再改 200）不再报错，以最后一次为准
  * 改回原来的值会被识别成"没有改动"
  * 开关原来是 nil 的，改成 true 后界面不再显示 nil

0.2  2026-09-11
----------------------------------------------------------------
  * 打包成独立 exe，依赖的 TP.dll / Socket.dll 随程序携带，不再有路径依赖
  * 打开程序后自行选择存档
  * 把能解析的内容 + 机制说明完整显示在界面上（概览/全部解析数据/角色/
    背包/开关变量/说明），可导出解析报告与解密后的明文
  * 只读，不改文件

0.1  2026-09-11
----------------------------------------------------------------
  * 首个版本：逆向出存档格式（伪装的 Audio/BGM/sy.ogg、TP.dll DS1/DS2 加密、
    Ruby Marshal 数据流、LockNumber 数字防作弊、机器码校验）
  * 可读可写的编辑器（Python，需在游戏目录内运行）
"""


class Doc(object):
    """一份已解密的存档。"""

    def __init__(self, path, bridge, log=None):
        self.log = log or (lambda s: None)
        self.path = os.path.abspath(path)
        self.bridge = bridge
        with open(self.path, 'rb') as f:
            self.blob = f.read()
        self.file_size = len(self.blob)
        self.md5 = hashlib.md5(self.blob).hexdigest().upper()
        self.container = C.peek_container(self.blob)
        if not self.container[0]:
            raise C.CodecError('这个文件不是本作存档：开头不是 %s\n（真正的 sy.ogg 是存档，'
                               '不是 ogg 音乐）' % C.MAGIC.hex(' ').upper())
        self.plain = bridge.decrypt(self.blob)
        if self.plain[:2] != b'\x04\x08':
            raise C.CodecError('解密结果不是 Ruby Marshal 数据流，存档格式可能已变化')
        self.entries = M.parse_stream(self.plain)
        self.nodes = [e['node'] for e in self.entries]
        self._cache = {}
        self._pe = None                # 写入用的补丁引擎（惰性创建）
        # @pack / @wallet / @talisman 动过（增/删/换物品）-> 保存时整条重写 $data：
        # 因为容器后面的格子和 $data 其它字段可能是 '@N' 对象链接，
        # 直接替换一格的字节会让后面的链接指错对象
        self._pack_dirty = False
        # $data_items 动过（新增登记项）-> 保存时也要整条重写 $data_items
        self._tpl_dirty = False
        # 角色/召唤兽的技能数组动过（长度变化）-> 整条重写 $game_actors / $game_party
        self._actors_dirty = False

    # ---------------- 基础 ----------------
    def node(self, name):
        if name in TOP_NAMES:
            i = TOP_NAMES.index(name)
            if i < len(self.nodes):
                return self.nodes[i]
        return None

    def ivar(self, name, key, default=None):
        obj = self.node(name)
        v = obj.get(key) if hasattr(obj, 'get') else None
        return default if v is None else v

    def top_list(self):
        out = []
        for i, e in enumerate(self.entries):
            nm = TOP_NAMES[i] if i < len(TOP_NAMES) else '对象%d' % i
            out.append({'index': i, 'name': nm, 'desc': TOP_DESC.get(nm, ''),
                        'node': e['node'], 'start': e['node'].start,
                        'end': e['node'].end,
                        'size': e['node'].end - e['node'].start})
        return out

    # ---------------- 概览 ----------------
    def frames(self):
        v = M.value_of(self.node('frame_count'))
        return int(v) if isinstance(v, int) else 0

    def gold(self):
        cash = self.node('data').get('@cash')
        if isinstance(cash, M.ObjNode) and cash.cls == 'LockNumber':
            return self.lock_value(cash)
        return M.value_of(cash)

    def lock_value(self, lock_obj):
        key = id(lock_obj)
        if key in self._cache:
            return self._cache[key]
        vals = [M.value_of(x) for x in lock_obj.get('@value').items]
        k3 = [M.value_of(x) for x in lock_obj.get('@key3').items]
        k1 = [M.value_of(x) for x in lock_obj.get('@key1').items]
        k2 = [M.value_of(x) for x in lock_obj.get('@key2').items]
        try:
            v = C.lock_decode(vals, k3, k1, k2)
        except C.LockNumberError as e:
            v = '校验失败：%s' % e
        self._cache[key] = v
        return v

    def machine_ids(self):
        node = self.node('存档id')
        out = []
        if isinstance(node, M.ArrayNode):
            for it in node.items:
                v = M.value_of(it)
                out.append(v.decode('utf-8', 'replace') if isinstance(v, bytes) else v)
        return out

    def machine_id_now(self):
        """当前机器的机器码（尽力而为，失败返回 None）。"""
        try:
            mid = self.bridge.machine_id()
            return mid or None
        except Exception:
            return None

    def _pet_summary(self):
        """概览页里的召唤兽一行（顺便报名字异常 —— 那会让游戏直接报错）。"""
        try:
            pets = self.actors_pet()
            all_pets = self.actors_pet(include_unowned=True)
            dead = len(all_pets) - len(pets)
            bad = self.pet_name_problems()
            s = '%d 只（另有 %d 只无主/已放生）' % (len(pets), dead)
            if bad:
                s += '   ⚠ 有 %d 只名字不在 $pet 表里（游戏打开召唤兽会报 ' \
                     'NoMethodError）→ 到「角色 / 召唤兽」页点【一键修复名字】' % len(bad)
            return s
        except Exception as e:
            return '读取失败：%s' % e

    def summary(self):
        gs = self.node('game_system')
        party = self.node('game_party')
        sysd = self.node('data')
        f = self.frames()
        ok, magic, declared, real = self.container
        rows = [
            ('存档文件', self.path),
            ('文件大小', '%d 字节' % self.file_size),
            ('文件 MD5', self.md5),
            ('', ''),
            ('容器魔数', magic + ('  ✔ 是本作存档' if ok else '  ✘')),
            ('声明密文长度', '%d 字节' % declared),
            ('zlib 解出密文', ('%d 字节' % real) if real is not None else '解析失败'),
            ('解出明文', '%d 字节' % len(self.plain)),
            ('顶层对象', '%d 个' % len(self.entries)),
            ('', ''),
            ('游戏时间', '%d 小时 %d 分 %d 秒' % (f // 216000, f // 3600 % 60, f // 60 % 60)),
            ('总帧数', str(f)),
            ('保存次数', str(M.value_of(gs.get('@save_count')) if gs else '?')),
            ('金钱（元宝）', str(self.gold()) + '   ← LockNumber 6 组校验'),
            ('声望 @fame', str(M.value_of(sysd.get('@fame')) if sysd else '?')),
            ('仓库金额 @store_cash', str(M.value_of(sysd.get('@store_cash')) if sysd else '?')),
            ('队伍人数', str(len(party.get('@actors').items)) if party else '?'),
            ('步数', str(M.value_of(party.get('@steps')) if party else '?')),
            ('物品栏占用', '%s（共 %d 格）'
             % ('，'.join('%s %d/%d' % (label, used, size)
                          for _k, label, used, size, _r in self.containers()),
                self.PACK_SIZE * len(CONTAINERS))),
            ('召唤兽', self._pet_summary()),
            ('存档记录机器码', '  '.join(str(x) for x in self.machine_ids())),
            ('当前机器机器码', str(self.machine_id_now() or '（取不到，可手动填写）')),
        ]
        return rows

    # ---------------- 名称表 ----------------
    def _search_bases(self):
        """
        找游戏文件的起点目录（按优先级）：

          1. 环境变量 ``XJ_GAME``（用户/开发时手动指定游戏目录）
          2. ``xj_env.game_dir()``（向上找 Game.exe；源码仓库在游戏目录外时靠它）
          3. 存档所在目录
          4. 当前工作目录
          5. 程序目录

        每个起点都会**逐级向上**找 ``<某层>/Data/<文件>``，
        这样存档被挪到别处、或工具放在游戏目录外都能找到数据库。
        """
        bases = []
        env = os.environ.get('XJ_GAME')
        if env:
            bases.append(env)
        try:
            import xj_env                     # 开发/源码运行时存在
            bases.append(xj_env.game_dir())
        except Exception:
            pass
        bases += [os.path.dirname(self.path), os.getcwd(), C.app_dir()]
        out = []
        for b in bases:
            if b and b not in out:
                out.append(b)
        return out

    def _data_file(self, name):
        """
        在游戏 Data 目录里找一个数据库文件（Skills.rxdata / Items.rxdata …）。

        存档通常在 <游戏根>/Audio/BGM/sy.ogg，但也有玩家把存档拷到别处，
        所以从存档目录、程序目录分别往上逐级找 <某层>/Data/<name>。
        """
        for base in self._search_bases():
            cur = base
            for _ in range(7):
                for cand in (os.path.join(cur, 'Data', name),
                             os.path.join(cur, name)):
                    if os.path.exists(cand):
                        return cand
                nxt = os.path.dirname(cur)
                if nxt == cur:
                    break
                cur = nxt
        return None

    def _db(self, which, fallback):
        if which not in self._cache:
            node = self.node(which)
            arr = None
            if isinstance(node, M.ArrayNode):
                arr = node.items                 # 存档里有这个顶层对象
            else:
                p = self._data_file(fallback)    # 否则去游戏 Data 目录里找
                if p:
                    with open(p, 'rb') as f:
                        ent = M.parse_stream(f.read())
                    if ent and isinstance(ent[0]['node'], M.ArrayNode):
                        arr = ent[0]['node'].items
            self._cache[which] = arr or []
        return self._cache[which]

    def _name(self, which, fallback, idx):
        arr = self._db(which, fallback)
        if 0 <= idx < len(arr) and isinstance(arr[idx], M.ObjNode):
            n = arr[idx].get('@name')
            if isinstance(n, M.StrNode):
                s = n.str()
                # 0045：装备名被重载为 "名字,HP,SP,等级"
                if which in ('data_weapons', 'data_armors'):
                    s = s.split(',')[0]
                return s
        return '?'

    def item_name(self, i):
        return self._name('data_items', 'Items.rxdata', i)

    def weapon_name(self, i):
        return self._name('data_weapons', 'Weapons.rxdata', i)

    def armor_name(self, i):
        return self._name('data_armors', 'Armors.rxdata', i)

    def actor_name(self, i):
        return self._name('data_actors', 'Actors.rxdata', i)

    def class_name(self, i):
        return self._name('data_classes', 'Classes.rxdata', i)

    # ---------------- 注释列（"全部解析数据"页） ----------------
    def note_of(self, label, node, parent=None, path=''):
        """
        给树里的一行返回一句注释。

        label  —— 树里显示的名字（顶层是 "#3 game_system"，数组元素是 "[12]"）
        node   —— 这一行的节点
        parent —— 父节点（用来判断"这个字段属于什么对象"）
        path   —— 父节点的路径（如 'game_actors.@data'）
        任何异常都不该影响界面，所以整体兜底。
        """
        try:
            return self._note_of(str(label), node, parent, path or '')
        except Exception:
            return ''

    def _note_of(self, lab, node, parent, path):
        pcls = getattr(parent, 'cls', None)

        # ---- 顶层对象 ----
        if lab.startswith('#'):
            parts = lab.split(None, 1)
            nm = parts[1] if len(parts) > 1 else ''
            return TOP_DESC.get(nm, '')

        # ---- RPG::Table 等不透明数据 ----
        if isinstance(node, M.UserDefNode):
            return '%s 二进制数据（%d 字节，工具不动它）' % (node.cls, len(node.data))

        # ---- 特定数组的元素（先判元素，因为元素本身也可能是 '@N' 链接）----
        if lab.startswith('['):
            try:
                idx = int(lab.strip('[]'))
            except ValueError:
                idx = -1
            n = self._note_array_elem(path, idx, node)
            if n:
                if isinstance(node, M.LinkNode):
                    n += '（这里是对象链接）'
                return n

        # ---- 对象链接 ----
        if isinstance(node, M.LinkNode):
            return '对象链接：和前面第 %d 个对象是同一个（改一处两边都变）' % node.index

        # ---- 字段名注释 ----
        if pcls == 'Game_Actor' and lab == '@name':
            return ('名字（召唤兽界面显示的是 @new_name，没有才用这个）'
                    if (vof(parent.get('@actor_id'), 0) or 0) > 20 else
                    '名字（游戏里显示的就是它；改它或 @new_name 都行）')
        n = NOTE_FIELD.get(lab)
        if n:
            return n

        # ---- 按类型兜底 ----
        return self._note_by_type(node, parent, lab)

    def _note_array_elem(self, path, idx, node):
        """数组元素（[0] [1] …）的注释。idx = 下标，node = 元素本身。"""
        if path in ('game_actors.@data', 'game_party.@actors'):
            return self._actor_note(deref(node), path == 'game_party.@actors')
        if path == 'data_actors':
            return self._actor_tpl_note(idx, deref(node))
        if path == 'data_items':
            return '物品模板 %d：%s（$data_items 的下标就是实例的 @standard）' \
                   % (idx, self.item_name(idx))
        if path == 'data_skills':
            return '技能模板 %d：%s' % (idx, self.skill_name(idx))
        if path == 'data_classes':
            return '职业 %d：%s' % (idx, self.class_name(idx))
        if path == 'data_weapons':
            return '武器 %d：%s' % (idx, self.weapon_name(idx))
        if path == 'data_armors':
            return '防具 %d：%s' % (idx, self.armor_name(idx))
        if path.endswith(('@pack', '@wallet', '@talisman')):
            return '第 %d 格（从 0 起）：[物品实例, 数量] 或 nil' % idx
        if path.endswith('@skills'):
            sid = vof(node)
            return ('技能 %d（已学）' % sid if not isinstance(sid, int)
                    else ('技能 %d：%s' % (sid, self.skill_name(sid))
                          if sid > 0 else '技能槽 %d（值是 0，游戏里当空）' % idx))
        if path.endswith('@states'):
            return '状态 id %s' % nodestr(node)
        if path.endswith(('@plus_state_set', '@minus_state_set')):
            return '状态 id %s' % nodestr(node)
        if path.endswith('@element_set'):
            return '属性 id %s（26 = 不可叠加）' % nodestr(node)
        if path.endswith('@babys'):
            slot = vof(node)
            tpl = self.pet_slot_map().get(slot) if isinstance(slot, int) else None
            own = self.pet_owner_map().get(slot) if isinstance(slot, int) else None
            return ('召唤兽界面第 %d 个：槽位 %s（模板 %s %s，主人 %s）'
                    % (idx + 1, slot, tpl,
                       self.actor_name(tpl) if isinstance(tpl, int) else '?',
                       self._actor_name_cached(own[0]) if own else '无主'))
        if path.endswith('@exp_list'):
            return '升到第 %d 级需要的累计经验 %s' % (idx, nodestr(node))
        if path.endswith('@原id'):
            return '第 %d 个槽位对应的原始模板 id = %s' % (idx, nodestr(node))
        if path.endswith('@现id'):
            tpl = vof(node)
            return ('第 %d 个槽位 = %s（模板 %s %s）'
                    % (idx, nodestr(node), tpl,
                       self.actor_name(tpl) if isinstance(tpl, int) else '?'))
        if path.endswith('@actors'):
            return ''
        if isinstance(node, M.ObjNode):
            return self._obj_note(node)
        return ''

    def _actor_note(self, node, in_party):
        """$game_actors.@data / $game_party.@actors 里的一个元素。"""
        if not isinstance(node, M.ObjNode):
            return '（空槽位）'
        aid = vof(node.get('@actor_id'))
        nm = stext(node.get('@name'), '?')
        kind = '人物' if (isinstance(aid, int) and aid <= 20) else '召唤兽'
        extra = ''
        if kind == '召唤兽':
            own = self.pet_owner_map().get(aid)
            extra = ('，主人 %s' % self._actor_name_cached(own[0])
                     if own else '，⚠ 没有主人（已放生/残留数据）')
        return '%s %s：%s%s%s' % (kind, aid, nm,
                                  '（队伍副本）' if in_party else '（角色表）', extra)

    def _actor_tpl_note(self, idx, node):
        """$data_actors[idx] 的注释。"""
        if idx < 21:
            return '人物模板 %d：%s' % (idx, self.actor_name(idx))
        tpl = self.pet_slot_map().get(idx)
        if tpl is None:
            nm = stext(node.get('@name'), '') if isinstance(node, M.ObjNode) else ''
            return ('召唤兽模板 %d：%s（还没被当成槽位用过）'
                    % (idx, nm or '空')) if idx < 999 else ''
        own = self.pet_owner_map().get(idx)
        who = self._actor_name_cached(own[0]) if own else '无主（已放生）'
        return ('召唤兽槽位 %d：模板 %d %s —— 主人 %s'
                % (idx, tpl, self.actor_name(tpl), who))

    def _obj_note(self, node):
        if node.cls == 'Game_Actor':
            aid = vof(node.get('@actor_id'))
            nm = stext(node.get('@name'), '?')
            if isinstance(aid, int) and aid > 20:
                tpl = self.pet_slot_map().get(aid)
                own = self.pet_owner_map().get(aid)
                return ('召唤兽 Game_Actor #%s %s（模板 %s，主人 %s）'
                        % (aid, nm, tpl if tpl else '?',
                           self._actor_name_cached(own[0]) if own else '无主'))
            return '人物 Game_Actor #%s %s' % (aid, nm)
        if node.cls == 'RPG::Item':
            std = vof(node.get('@standard'))
            q = vof(node.get('@quality'))
            return ('物品实例「%s」模板 %s 品质 %s 实例id %s'
                    % (stext(node.get('@name'), '?'),
                       self.item_name(std) if isinstance(std, int) else '?',
                       q, vof(node.get('@id'))))
        if node.cls == 'LockNumber':
            return 'LockNumber：金钱等数字的 6 组防作弊编码，工具会一起重算'
        return ''

    def _note_by_type(self, node, parent, lab):
        if node is None or isinstance(node, M.NilNode):
            return '空（nil）'
        if isinstance(node, M.ArrayNode):
            return '数组，%d 项（展开可看每一项）' % len(node.items)
        if isinstance(node, M.HashNode):
            return 'Hash，%d 组键值' % len(node.pairs)
        if isinstance(node, M.ObjNode):
            extra = self._obj_note(node)
            return extra or ('%s 对象' % node.cls)
        if isinstance(node, M.StructNode):
            return 'Struct::%s' % node.cls
        if isinstance(node, M.FloatNode):
            return '浮点数'
        if isinstance(node, M.BignumNode):
            return '大整数'
        if isinstance(node, M.BoolNode):
            return 'true / false'
        if isinstance(node, M.StrNode):
            return '字符串'
        if isinstance(node, M.SymbolNode):
            return '符号'
        if isinstance(node, M.IntNode):
            return '整数'
        return ''

    def _actor_name_cached(self, aid):
        cache = self._cache.setdefault('namecache', {})
        if aid not in cache:
            a = self.actor(aid)
            cache[aid] = stext(a.get('@name'), '?') if a is not None else '?'
        return cache[aid]

    # ---------------- 角色 ----------------
    def actors(self):
        """按 @actor_id 聚合：角色在存档里有两份（角色表 / 队伍）。

        ⚠ 数组元素可能是 **'@N' 对象链接**，不是真的对象。真实案例：
           $game_actors.@data[165] == '@62'，而那个对象就嵌在
           $game_actors.@data[12].@who_attack_me.@who_attack_me 里
           —— 目标是个正常的 Game_Actor(@actor_id=165)，游戏能正常显示，
           但工具以前只认 ObjNode，于是这只召唤兽"消失了"。
        所以这里要顺带解引用：链接的目标才是那个角色对象。
        """
        out = {}
        for src, arr_node in (('角色表', self.ivar('game_actors', '@data')),
                              ('队伍', self.ivar('game_party', '@actors'))):
            if not isinstance(arr_node, M.ArrayNode):
                continue
            for it in arr_node.items:
                if isinstance(it, M.LinkNode):
                    it = it.target          # '@N' -> 真正的对象
                if isinstance(it, M.ObjNode) and it.cls == 'Game_Actor':
                    aid = M.value_of(it.get('@actor_id'))
                    pair = (src, it)
                    if pair not in out.setdefault(aid, []):
                        out[aid].append(pair)
        return out

    def _actor_nodes_sorted(self, aid):
        """一个角色的两份副本，**队伍那份排前面**（游戏界面用的就是它）。"""
        d = self.actors().get(aid) or []
        return sorted(d, key=lambda p: 0 if p[0] == '队伍' else 1)

    def _person_order(self):
        """人物顺序：先出战队伍里的（照 @actors 顺序），再是剩下的按 id。"""
        order = []
        party = self.ivar('game_party', '@actors')
        if isinstance(party, M.ArrayNode):
            for it in party.items:
                if isinstance(it, M.ObjNode):
                    aid = M.value_of(it.get('@actor_id'))
                    if isinstance(aid, int) and aid <= 20 and aid not in order:
                        order.append(aid)
        for aid in sorted(k for k in self.actors()
                          if isinstance(k, int) and k <= 20):
            if aid not in order:
                order.append(aid)
        return order

    def pet_owner_map(self):
        """
        召唤兽槽位 -> (主人 @actor_id, 在主人 @babys 里的下标)。

        这就是游戏"召唤兽"界面的顺序：
            0143 Sys::Window_Baby#refresh -> @actor.babys.each { |i| @data.push($game_actors[i]) }
        没出现在任何人物 @babys 里的槽位 = 已经放生（或残留数据），不在里面。
        """
        if 'petowners' in self._cache:
            return self._cache['petowners']
        out = {}
        for aid in self._person_order():
            for _src, node in self._actor_nodes_sorted(aid):
                b = node.get('@babys')
                if not isinstance(b, M.ArrayNode):
                    continue
                for k, it in enumerate(b.items):
                    slot = vof(it)
                    if isinstance(slot, int) and slot not in out:
                        out[slot] = (aid, k)
        self._cache['petowners'] = out
        return out

    def pet_slot_map(self):
        """召唤兽槽位 -> 原始模板 id（$game_party 的 @现id / @原id 映射表）。"""
        if 'petslots' in self._cache:
            return self._cache['petslots']
        out = {}
        gp = self.node('game_party')
        x = gp.get('@现id') if gp is not None else None
        y = gp.get('@原id') if gp is not None else None
        if isinstance(x, M.ArrayNode) and isinstance(y, M.ArrayNode):
            for k, it in enumerate(x.items):
                slot = vof(it)
                tpl = vof(y.items[k]) if k < len(y.items) else None
                if isinstance(slot, int) and slot not in out:
                    out[slot] = tpl if isinstance(tpl, int) else None
        self._cache['petslots'] = out
        return out

    def pet_slot_state(self, slot):
        """槽位的状态文字：已放生 / 在队伍 / 无主。"""
        return ('有主' if slot in self.pet_owner_map() else '无主（已放生/残留）')

    # ---- $pet 名字表（脚本 0011）------------------------------------------
    #
    #   $pet = { "宠物名" => [攻击资质,防御资质,体力资质,法力资质,速度资质,闪躲资质,
    #                          [成长…], 参战等级], ... }
    #
    # 游戏这些地方**没有 nil 判断**地索引它：
    #   0163 Sys <召唤兽> 第 147 行 : $pet["#{baby.name}"][7]   ← 用户实测崩溃这行
    #   0163 第 436/439 行          : $pet[@baby_window.baby.name][7]
    #   0121 第 572 行              : $pet[@baby_window.baby.name][7]
    #   0164 第 231/242 行          : zz = $pet[baby.name]
    # 而 Game_Actor#name 就是 @name（0044 setup：@name = actor.name.split(/【/)[0]），
    # 所以把召唤兽的 @name 改成表外的名字 -> $pet[名字] 是 nil -> nil[7] ->
    # NoMethodError: undefined method '[]' for nil:NilClass（召唤兽界面直接打不开）。
    def pet_name_table(self):
        """$pet 名字表：名字 -> ([六项资质], [成长…], 参战等级)。

        优先现场解析游戏脚本 Try/scripts/0011_*.rb；找不到就用随程序带的
        pet_table.py（由 gen_pet_table.py 从同一脚本生成）。
        """
        if 'pettable' in self._cache:
            return self._cache['pettable']
        table, src = {}, ''
        p = self._pet_script_file()
        if p:
            try:
                table = parse_pet_table(p)
                src = p
            except Exception:
                table = {}
        if not table and _PET_TABLE_MOD is not None:
            table = {k: (list(v[0]), list(v[1]), v[2])
                     for k, v in _PET_TABLE_MOD.TABLE.items()}
            src = '内置表 pet_table.py（%s）' % getattr(
                _PET_TABLE_MOD, 'SOURCE_SCRIPT', '0011')
        self._cache['pettable'] = table
        self._cache['pettable_src'] = src
        return table

    def pet_name_table_source(self):
        self.pet_name_table()
        return self._cache.get('pettable_src', '')

    def _pet_script_file(self):
        """找游戏的 0011 脚本（$pet 表就在里面）。找不到返回 None。"""
        for base in self._search_bases():
            cur = base
            for _ in range(7):
                d = os.path.join(cur, 'Try', 'scripts')
                if os.path.isdir(d):
                    for fn in sorted(os.listdir(d)):
                        if fn.startswith('0011') and fn.endswith('.rb'):
                            return os.path.join(d, fn)
                nxt = os.path.dirname(cur)
                if nxt == cur:
                    break
                cur = nxt
        return None

    def pet_name_ok(self, name):
        """名字在不在 $pet 表里；表拿不到时返回 None（界面就不报警告）。"""
        t = self.pet_name_table()
        if not t:
            return None
        return name in t

    def carry_level(self, name):
        """参战等级（$pet[名字][7]）。"""
        row = self.pet_name_table().get(name)
        return row[2] if row else None

    def pet_table_row(self, name):
        """$pet 里这一行的 (六项资质, 成长, 参战等级)。"""
        return self.pet_name_table().get(name)

    def pet_template_name(self, slot):
        """槽位的模板本名 —— 复刻游戏 0044 Game_Actor#setup 的
        `@name = actor.name.split(/【/)[0]`。"""
        tpl = self.pet_slot_map().get(slot)
        if not isinstance(tpl, int):
            return None
        arr = self.node('data_actors')
        it = arr.items[tpl] if isinstance(arr, M.ArrayNode) and tpl < len(arr.items) \
            else None
        if isinstance(it, M.LinkNode):
            it = it.target
        nm = stext(it.get('@name'), '') if isinstance(it, M.ObjNode) else ''
        nm = nm.split('【')[0].strip()
        return nm or None

    def suggest_pet_name(self, slot):
        """给一个槽位推荐一个"合法的"名字（模板本名优先，其次按资质找）。"""
        nm = self.pet_template_name(slot)
        if nm and self.pet_name_ok(nm):
            return nm, '模板本名'
        if nm:
            return nm, '模板本名（但它也不在 $pet 表里，自己再核对一下）'
        return None, ''

    def pet_name_problems(self, include_unowned=False):
        """名字不在 $pet 表里的召唤兽（会让游戏召唤兽界面崩溃）。"""
        out = []
        if not self.pet_name_table():
            return out
        for r in self.actors_pet(include_unowned=include_unowned):
            if r['name'] not in self.pet_name_table():
                sug, why = self.suggest_pet_name(r['id'])
                out.append({'id': r['id'], 'name': r['name'], 'display': r['display'],
                            'tpl': r['tpl'], 'tpl_name': r['tpl_name'],
                            'owner_name': r['owner_name'], 'suggest': sug, 'why': why})
        return out

    def fix_pet_names(self, include_unowned=False):
        """把名字异常的召唤兽 @name 改回模板本名。返回修复列表。"""
        fixed = []
        for p in self.pet_name_problems(include_unowned=include_unowned):
            if not p['suggest']:
                continue
            self.set_actor_name(p['id'], p['suggest'])
            fixed.append(p)
        return fixed

    def pet_display_order(self, include_unowned=True):
        """召唤兽显示顺序：先界面顺序（主人 × @babys），无主的排到后面。"""
        out = []
        owners = self.pet_owner_map()
        for aid in self._person_order():
            for _src, node in self._actor_nodes_sorted(aid):
                b = node.get('@babys')
                if not isinstance(b, M.ArrayNode):
                    continue
                for it in b.items:
                    slot = vof(it)
                    if isinstance(slot, int) and slot not in out:
                        out.append(slot)
        if include_unowned:
            rest = sorted(k for k in self.actors()
                          if isinstance(k, int) and k > 20 and k not in out)
            out += rest
        return [s for s in out if s in owners or include_unowned]

    def actor_rows(self):
        owners = self.pet_owner_map()
        slots = self.pet_slot_map()
        ptable = self.pet_name_table()
        pets, persons = [], []
        for aid, copies in sorted(self.actors().items(), key=lambda t: (t[0] is None, t[0])):
            main = copies[0][1]
            is_pet = aid > 20
            new_name = stext(main.get('@new_name'), '')
            base = stext(main.get('@name'), '')
            r = {
                'id': aid,
                'is_pet': is_pet,
                'name': base,
                'new_name': new_name,
                # 游戏里真正显示的名字：0040 Game_Battler#custom_name
                'display': new_name or base,
                'class': self.class_name(M.value_of(main.get('@class_id')) or 0),
                'class_id': M.value_of(main.get('@class_id')),
                'level': M.value_of(main.get('@level')),
                'exp': M.value_of(main.get('@exp')),
                'hp': M.value_of(main.get('@hp')),
                'maxhp': self.actor_maxhp(aid),
                'sp': M.value_of(main.get('@sp')),
                'maxsp': self.actor_maxsp(aid),
                'tizhi': M.value_of(main.get('@tizhi')),
                'moli': M.value_of(main.get('@moli')),
                'liliang': M.value_of(main.get('@liliang')),
                'naili': M.value_of(main.get('@naili')),
                'minjie': M.value_of(main.get('@minjie')),
                'latent': M.value_of(main.get('@latent')),
                'vitality': M.value_of(main.get('@vitality')),
                'spirit': M.value_of(main.get('@spirit')),
                'element': self._s(main, '@五行'),
                'where': '/'.join(s for s, _ in copies) + '（%d 份）' % len(copies),
                'copies': len(copies),
                # 召唤兽专有（这些字段可能是 '@N' 对象链接，要用会解引用的 vof）
                'growth': vof(main.get('@成长')),
                'loyal': vof(main.get('@loyal')),
                'zz_attack': vof(main.get('@攻击资质')),
                'zz_defense': vof(main.get('@防御资质')),
                'zz_tili': vof(main.get('@体力资质')),
                'zz_magic': vof(main.get('@法力资质')),
                'zz_speed': vof(main.get('@速度资质')),
                'zz_dodge': vof(main.get('@躲闪资质')),
                'skills': self.actor_skills(aid),
                'node': main,
                # 召唤兽：槽位 / 模板 / 主人 / 是否还被某个角色持有
                'tpl': slots.get(aid) if is_pet else None,
                'owner': owners.get(aid, (None, None))[0] if is_pet else None,
                'owner_pos': owners.get(aid, (None, None))[1] if is_pet else None,
                'owned': (aid in owners) if is_pet else True,
                'party': any(s == '队伍' for s, _ in copies),
                # 名字是否在 $pet 名字表里（不在 → 游戏召唤兽界面会崩）
                'name_ok': (None if (not is_pet or not ptable)
                            else (base in ptable)),
                'carry': (ptable.get(base, (None, None, None))[2]
                          if is_pet else None),
            }
            r['owner_name'] = (self._actor_name_cached(r['owner'])
                               if r['owner'] is not None else '')
            r['tpl_name'] = (self.actor_name(r['tpl'])
                             if isinstance(r['tpl'], int) else '')
            (pets if is_pet else persons).append(r)
        order = {s: i for i, s in enumerate(self.pet_display_order())}
        pets.sort(key=lambda r: order.get(r['id'], 9999))
        for i, r in enumerate(pets):
            r['order'] = i + 1
        for r in persons:
            r['order'] = r['id']
        return persons + pets

    def actors_person(self):
        return [r for r in self.actor_rows() if not r['is_pet']]

    def actors_pet(self, include_unowned=False):
        """召唤兽行，顺序与游戏界面一致；include_unowned=False 时排除已放生的。"""
        rows = [r for r in self.actor_rows() if r['is_pet']]
        if not include_unowned:
            rows = [r for r in rows if r['owned']]
        return rows

    def actor(self, aid):
        d = self.actors().get(aid)
        return d[0][1] if d else None

    def _s(self, obj, key):
        return stext(obj.get(key), nodestr(obj.get(key)))

    def _data_array(self, fname):
        key = 'file:' + fname
        if key not in self._cache:
            p = os.path.join(os.path.dirname(self.path), fname)
            arr = []
            if os.path.exists(p):
                with open(p, 'rb') as f:
                    ent = M.parse_stream(f.read())
                if ent and isinstance(ent[0]['node'], M.ArrayNode):
                    arr = ent[0]['node'].items
            self._cache[key] = arr
        return self._cache[key]

    def _state_rate(self, state_id, field):
        arr = self._data_array('States.rxdata')
        if 0 <= state_id < len(arr) and isinstance(arr[state_id], M.ObjNode):
            v = arr[state_id].get(field)
            if v is not None:
                return M.value_of(v)
        return 100

    def _equip_hp_sp(self, actor_obj, which):
        total = 0
        ids = [('data_weapons', M.value_of(actor_obj.get('@weapon_id')) or 0)]
        ids += [('data_armors', M.value_of(actor_obj.get('@armor%d_id' % i)) or 0)
                for i in range(1, 6)]
        for which_db, i in ids:
            if not i:
                continue
            arr = self._db(which_db, which_db.replace('data_', '').capitalize() + '.rxdata')
            if 0 <= i < len(arr) and isinstance(arr[i], M.ObjNode):
                nm = arr[i].get('@name')
                if isinstance(nm, M.StrNode):
                    parts = nm.str().split(',')
                    idx = 1 if which == 'hp' else 2
                    if len(parts) > idx and parts[idx].strip().lstrip('-').isdigit():
                        total += int(parts[idx])
        return total

    def actor_maxhp(self, aid):
        a = self.actor(aid)
        if a is None:
            return '?'
        if aid > 20:
            return '（召唤兽公式）'
        n = max(1, min(999999, self._equip_hp_sp(a, 'hp') + (M.value_of(a.get('@maxhp_plus')) or 0)))
        st = a.get('@states')
        if isinstance(st, M.ArrayNode):
            for s in st.items:
                n *= self._state_rate(M.value_of(s), '@maxhp_rate') / 100.0
        n += (M.value_of(a.get('@tizhi')) or 0) * 5 + 100 + (M.value_of(a.get('@level')) or 1) * 20
        return max(1, min(999999, int(n)))

    def actor_maxsp(self, aid):
        a = self.actor(aid)
        if a is None:
            return '?'
        if aid > 20:
            return '（召唤兽公式）'
        n = max(0, min(9999, self._equip_hp_sp(a, 'sp') + (M.value_of(a.get('@maxsp_plus')) or 0)))
        st = a.get('@states')
        if isinstance(st, M.ArrayNode):
            for s in st.items:
                n *= self._state_rate(M.value_of(s), '@maxsp_rate') / 100.0
        n += (M.value_of(a.get('@moli')) or 0) * 3
        return max(0, min(9999, int(n)))

    def actor_extra(self, aid):
        """角色面板的补充信息（技能 / 状态 / 装备等）。"""
        a = self.actor(aid)
        if a is None:
            return []
        rows = []

        def arr(key):
            n = a.get(key)
            return [M.value_of(x) for x in n.items] if isinstance(n, M.ArrayNode) else []

        rows.append(('技能 ID', arr('@skills')))
        rows.append(('状态 ID', arr('@states')))
        rows.append(('召唤兽 ID', arr('@babys')))
        for label, key in (('武器 ID', '@weapon_id'), ('装备1 ID', '@armor1_id'),
                           ('装备2 ID', '@armor2_id'), ('装备3 ID', '@armor3_id'),
                           ('装备4 ID', '@armor4_id'), ('装备5 ID', '@armor5_id')):
            rows.append((label, M.value_of(a.get(key))))
        for label, key in (('附加体质', '@add_tizhi'), ('附加魔力', '@add_moli'),
                           ('附加力量', '@add_liliang'), ('附加耐力', '@add_naili'),
                           ('附加敏捷', '@add_minjie'), ('气血上限加成', '@maxhp_plus'),
                           ('法力上限加成', '@maxsp_plus'), ('附加攻击', '@str_plus'),
                           ('附加灵巧', '@dex_plus'), ('附加速度', '@agi_plus'),
                           ('附加灵力', '@int_plus')):
            rows.append((label, M.value_of(a.get(key))))
        rows.append(('当前等级经验', M.value_of(a.get('@exp'))))
        rows.append(('升到下一级需要', exp_for_level(aid, (M.value_of(a.get('@level')) or 1))))
        return rows

    # ---------------- 物品栏：data.@pack（0.3 修正） ----------------
    #
    # 游戏真正的背包是 System::Data 的 @pack（20 格），不是 $game_party.@items！
    # 每格 = [ RPG::Item 实例, 数量 ]，也可能是 nil。
    # 实例里：
    #   @standard —— 指向 data_items 里的模板 id（模板提供基础名字/图标/效果）
    #   @id       —— 该物品实例的唯一编号（1001 起）
    #   @quality  —— 品质（实例被强化后的数值）
    #   @name / @icon_name / @description 等 —— 实例自身的（可能已被改写）
    PACK_SIZE = 20

    # 游戏里的三个 20 格物品容器（脚本 0155 System::Data）
    def container_node(self, key='@pack'):
        """取某个容器的数组节点（@pack 道具 / @wallet 行囊 / @talisman 备用）。"""
        node = self.node('data')
        arr = node.get(key) if node is not None else None
        return arr if isinstance(arr, M.ArrayNode) else None

    def container_slots(self, key='@pack'):
        """某个容器的 20 格：每格 = [RPG::Item 实例, 数量] 或 nil。"""
        out = []
        arr = self.container_node(key)
        if arr is None:
            return out
        for slot, cell in enumerate(arr.items):
            rec = {'slot': slot, 'cell': cell, 'item': None, 'standard': None,
                   'name': '（空）', 'count': 0, 'iid': None, 'quality': None,
                   'icon': '', 'desc': '', 'template_name': '', 'key': key,
                   'registered': False, 'reg_state': ''}
            if isinstance(cell, M.ArrayNode) and len(cell.items) >= 2:
                item = deref(cell.items[0])
                rec['count'] = vof(cell.items[1], 0)
                if isinstance(item, M.ObjNode):
                    rec['item'] = item
                    std = vof(item.get('@standard'))
                    rec['standard'] = std
                    rec['iid'] = vof(item.get('@id'))
                    rec['name'] = stext(item.get('@name'), '?')
                    rec['icon'] = stext(item.get('@icon_name'))
                    rec['desc'] = stext(item.get('@description'))
                    rec['quality'] = vof(item.get('@quality'))
                    if isinstance(std, int):
                        rec['template_name'] = self.item_name(std)
                    if rec['name'] in ('', '?') and rec['template_name']:
                        rec['name'] = rec['template_name']
                    st, msg = self.registration_state(rec['iid'], std)
                    rec['registered'] = (st == 'ok')
                    rec['reg_state'] = msg
            out.append(rec)
        return out

    def containers(self):
        """三个容器的概览（名称 / 已用格数 / 数据）。"""
        out = []
        for key, label in CONTAINERS:
            rows = self.container_slots(key)
            used = sum(1 for r in rows if r['item'] is not None)
            out.append((key, label, used, self.PACK_SIZE, rows))
        return out

    def pack(self):
        """兼容旧调用：道具栏（@pack）。"""
        return self.container_slots('@pack')

    def pack_rows(self):
        """给界面用的行：格 / 名称 / 模板id / 实例id / 数量 / 品质 / 说明"""
        return [(r['slot'], r['name'], r['standard'], r['iid'], r['count'],
                 r['quality'], r['desc']) for r in self.pack()]

    def pack_used(self):
        return sum(1 for r in self.pack() if r['item'] is not None)

    def bag_all(self):
        """兼容旧界面：把 @pack 的内容按统一格式返回。"""
        rows = []
        for r in self.pack():
            if r['item'] is not None:
                rows.append(('物品', r['standard'], r['name'], r['count']))
        return rows

    def item_templates(self):
        """data_items 里的模板列表（id -> 名字），给"新增物品"下拉框用。"""
        out = []
        items = self._db('data_items', 'Items.rxdata')
        for i, it in enumerate(items):
            if isinstance(it, M.ObjNode):
                nm = it.get('@name')
                if isinstance(nm, M.StrNode) and nm.str():
                    out.append((i, nm.str()))
        return out

    def mounts(self):
        party = self.node('game_party')
        h = party.get('@mounts') if party else None
        out = []
        if isinstance(h, M.HashNode):
            for k, v in h.pairs:
                out.append((M.value_of(k), value_text(v, 40)))
        return out

    # ---------------- 开关 / 变量 ----------------
    def switches(self):
        arr = self.ivar('game_switches', '@data')
        out = []
        if isinstance(arr, M.ArrayNode):
            for i, it in enumerate(arr.items):
                out.append((i, M.value_of(it)))
        return out

    def variables(self):
        arr = self.ivar('game_variables', '@data')
        out = []
        if isinstance(arr, M.ArrayNode):
            for i, it in enumerate(arr.items):
                if isinstance(it, M.ObjNode) and it.cls == 'LockNumber':
                    out.append((i, self.lock_value(it), 'LockNumber'))
                else:
                    out.append((i, M.value_of(it), type_text(it)))
        return out

    # ---------------- 修改与保存（0.3 新增） ----------------
    def begin_edit(self):
        if self._pe is None:
            self._pe = E.PatchEngine(self.plain)
        return self._pe

    def is_dirty(self):
        return self._pe is not None and self._pe.has_changes()

    def changed_bytes(self):
        return self._pe.changed_bytes() if self._pe else 0

    # ---- 数值 ----
    def _set_lock(self, lock_obj, value):
        pe = self.begin_edit()
        k1 = [M.value_of(x) for x in lock_obj.get('@key1').items]
        k2 = [M.value_of(x) for x in lock_obj.get('@key2').items]
        vals = lock_obj.get('@value').items
        k3s = lock_obj.get('@key3').items
        for i in range(len(vals)):
            v, k3 = C.lock_encode_pairs(float(value), k1, k2, i)
            pe.set_scalar(vals[i], v)
            pe.set_scalar(k3s[i], k3)
        self._cache.pop(id(lock_obj), None)

    def set_gold(self, value):
        cash = self.node('data').get('@cash')
        if isinstance(cash, M.ObjNode) and cash.cls == 'LockNumber':
            self._set_lock(cash, value)
        else:
            self.begin_edit().set_scalar(cash, int(value))
        return self.gold()

    def set_fame(self, value):
        self.begin_edit().set_scalar(self.node('data').get('@fame'), int(value))
        return value

    def set_store_cash(self, value):
        self.begin_edit().set_scalar(self.node('data').get('@store_cash'), int(value))
        return value

    def set_steps(self, value):
        self.begin_edit().set_scalar(self.node('game_party').get('@steps'), int(value))
        return value

    # ---- 角色 ----
    def actor_nodes(self, aid):
        d = self.actors().get(aid)
        return [n for _, n in d] if d else []

    def _put_ivar(self, obj, ivar, value, pe):
        """
        把 obj 的 ivar 设成 value，返回是否改到了。

        字段值是 '@N' 对象链接时（例如召唤兽的 @成长 指向共享的 0.0），不能就地
        改值 —— 把它**物化**成一个独立标量。物化会往流里多塞一个对象，后面所有
        '@N' 的编号都要 +1，所以顺手标记 _actors_dirty，保存时把 $game_actors /
        $game_party 整条重写（链接全部展开，编号自洽）。
        """
        node = obj.get(ivar)
        if node is None:
            return False
        if isinstance(node, M.LinkNode):
            data = E.scalar_bytes(value)
            new_node = M.parse_stream(b'\x04\x08' + data)[0]['node']
            for i, (k, _v) in enumerate(obj.ivars):
                if k == ivar:
                    obj.ivars[i] = (k, new_node)
                    break
            # 整个对象重写（会多占一个对象编号 -> 置 _actors_dirty 让顶层也重写）；
            # 用 replace_object 登记成根，之后用户继续改这只宠的其它字段就不会冲突
            pe.replace_object(obj)
            self._actors_dirty = True
            return True
        pe.set_scalar(node, value)
        return True

    def set_actor_field(self, aid, ivar, value):
        pe = self.begin_edit()
        hit = 0
        for n in self.actor_nodes(aid):
            if self._put_ivar(n, ivar, value, pe):
                hit += 1
        if not hit:
            raise E.EditError('对象 %s 没有字段 %s' % (aid, ivar))
        return value

    def set_actor_level(self, aid, level):
        lv = max(1, min(175 if aid <= 20 else 180, int(level)))
        exp = exp_for_level(aid, lv)
        self.set_actor_field(aid, '@level', lv)
        self.set_actor_field(aid, '@exp', exp)
        return lv, exp

    def heal_actor(self, aid):
        hp, sp = self.actor_maxhp(aid), self.actor_maxsp(aid)
        if isinstance(hp, int):
            self.set_actor_field(aid, '@hp', hp)
        if isinstance(sp, int):
            self.set_actor_field(aid, '@sp', sp)
        return hp, sp

    def set_actor_name(self, aid, name):
        """改基础名 @name（游戏里显示的名字，召唤兽界面优先用 @new_name）。"""
        name = str(name)
        if not name.strip():
            raise E.EditError('名字不能是空的')
        pe = self.begin_edit()
        hit = 0
        for n in self.actor_nodes(aid):
            if self._put_ivar(n, '@name', name, pe):
                hit += 1
        if not hit:
            raise E.EditError('找不到角色 %s 的 @name 字段' % aid)
        self._cache.pop('namecache', None)
        return name

    # ---- 召唤兽/人物改名（游戏字段 @new_name，脚本 0040 Game_Battler#custom_name）----
    #
    #     游戏显示名 = @new_name 存在 ? @new_name : @name
    #     玩家在游戏里改名（0163 脚本 when 16）就是 @baby.new_name = 输入的文字。
    #     @new_name 平时**不在**存档里（Game_Battler#initialize 不设置它），
    #     所以改名时要往对象里"追加一个字段" —— 对象字节变长，顶层对象里的
    #     对象编号会整体错位，因此标记 _actors_dirty，保存时把 $game_actors /
    #     $game_party 整条重写（所有 '@N' 链接展开成独立副本，编号自洽）。
    def set_actor_custom_name(self, aid, name):
        name = str(name)
        if not name.strip():
            raise E.EditError('新名字不能是空的（要恢复原名请用「清除显示名」）')
        pe = self.begin_edit()
        hit = 0
        for obj in self.actor_nodes(aid):
            node = obj.get('@new_name')
            if node is None:
                obj.ivars.append(('@new_name', M.StrNode(name.encode('utf-8'))))
                pe.replace_object(obj)
            else:
                self._put_ivar(obj, '@new_name', name, pe)
            hit += 1
        if not hit:
            raise E.EditError('找不到角色 %s 的对象' % aid)
        self._actors_dirty = True
        return name

    def clear_actor_custom_name(self, aid):
        """删掉 @new_name，恢复成游戏里的本名。返回清掉了几份副本。"""
        pe = self.begin_edit()
        hit = 0
        for obj in self.actor_nodes(aid):
            kept = [(k, v) for k, v in obj.ivars if k != '@new_name']
            if len(kept) != len(obj.ivars):
                obj.ivars = kept
                pe.replace_object(obj)
                hit += 1
        if not hit:
            raise E.EditError('「%s」本来就没有改过名字' % self.actor_name(aid))
        self._actors_dirty = True
        return hit

    def has_custom_name(self, aid):
        return any(obj.get('@new_name') is not None
                   for obj in self.actor_nodes(aid))

    # ---- 技能（人物与召唤兽通用；@skills 是技能 id 数组）----
    # 游戏脚本 0044：learn_skill -> @skills.push(id); @skills.sort!
    #               forget_skill -> @skills.delete(id)
    def skill_templates(self):
        """技能模板表：(id, 名字, 说明)（存档里没有它，读游戏 Data/Skills.rxdata）。"""
        out = []
        arr = self._db('data_skills', 'Skills.rxdata')
        for i, s in enumerate(arr):
            if isinstance(s, M.ObjNode):
                nm = stext(s.get('@name'), '')
                if nm:
                    out.append((i, nm, self._skill_desc_obj(s)))
        return out

    @staticmethod
    def _skill_desc_obj(s):
        """从技能模板对象里取 @description（多行压成一行）。"""
        d = stext(s.get('@description'), '')
        return ' '.join(d.split())

    def skill_name(self, sid):
        arr = self._db('data_skills', 'Skills.rxdata')
        if isinstance(sid, int) and 0 <= sid < len(arr) \
                and isinstance(arr[sid], M.ObjNode):
            nm = stext(arr[sid].get('@name'), '')
            if nm:
                return nm
        return '技能%d' % sid

    def skill_desc(self, sid):
        """技能说明（Data/Skills.rxdata 的 @description），没有就空串。"""
        arr = self._db('data_skills', 'Skills.rxdata')
        if isinstance(sid, int) and 0 <= sid < len(arr) \
                and isinstance(arr[sid], M.ObjNode):
            return self._skill_desc_obj(arr[sid])
        return ''

    def actor_skills(self, aid):
        """已学技能：[(技能 id, 名字, 说明)]。"""
        obj = self.actor(aid)
        sk = obj.get('@skills') if obj is not None else None
        out = []
        if isinstance(sk, M.ArrayNode):
            for it in sk.items:
                sid = vof(it)
                if isinstance(sid, int):
                    out.append((sid, self.skill_name(sid), self.skill_desc(sid)))
        return out

    def set_actor_skills(self, aid, sids):
        """改写 @skills（升序、去重），所有副本一起改。返回改了几份。

        一律把 @skills 换成一个**全新的数组对象**（不原地改 items）：
        这个数组可能是共享对象（别处也有 '@N' 指着它），原地改会把别人一起改掉。
        """
        pe = self.begin_edit()
        hit = 0
        vals = sorted(set(int(x) for x in sids))
        for n in self.actor_nodes(aid):
            new = M.ArrayNode([M.IntNode(v) for v in vals])
            for i, (k, _v) in enumerate(n.ivars):
                if k == '@skills':
                    n.ivars[i] = (k, new)      # 换新数组（'@N' 链接也顺便物化）
                    break
            else:
                continue                       # 这个对象没有 @skills
            # 整体重写这个 Game_Actor 对象（数组长度变了 + 链接全部展开，编号自洽）。
            # 用 replace_object 而不是 replace_tree，是为了把它登记成"根" ——
            # 否则用户接着改这只宠的等级/资质时会打在更大补丁里面而报错。
            pe.replace_object(n)
            hit += 1
        if hit:
            self._actors_dirty = True
        return hit

    def add_actor_skill(self, aid, sid):
        """学会技能（等价于游戏的 learn_skill）：加进 @skills 并保持升序。"""
        sid = int(sid)
        cur = [s[0] for s in self.actor_skills(aid)]
        if sid in cur:
            raise E.EditError('已经有「%s」了' % self.skill_name(sid))
        if not self.set_actor_skills(aid, cur + [sid]):
            raise E.EditError('这个对象的 @skills 字段不见了')
        return sid

    def remove_actor_skill(self, aid, sid):
        """忘掉技能（等价于游戏的 forget_skill）。"""
        sid = int(sid)
        cur = [s[0] for s in self.actor_skills(aid)]
        if sid not in cur:
            raise E.EditError('没有「%s」这个技能' % self.skill_name(sid))
        self.set_actor_skills(aid, [x for x in cur if x != sid])
        return sid

    def clone_skills(self, src_aid, dst_aid):
        """克隆技能：把 src 的整张 @skills 表复制到 dst（替换 dst 原有的）。

        游戏里学/忘技能就是 `@skills` 数组的增删（0044 learn_skill / forget_skill），
        所以"克隆"= 整表替换，直接走 set_actor_skills（会置 _actors_dirty，
        保存时整条重写 $game_actors/$game_party，编号自洽）。

        源不受影响：即使两边的 @skills 恰好是同一个数组对象（'@N' 共享），
        set_actor_skills 也会给目标换一个**新数组**。
        返回克隆过去的技能 id 列表。
        """
        if src_aid == dst_aid:
            raise E.EditError('源和目标不能是同一个角色')
        if not self.actor_nodes(src_aid):
            raise E.EditError('找不到角色 %s 的对象' % src_aid)
        if not self.actor_nodes(dst_aid):
            raise E.EditError('找不到角色 %s 的对象' % dst_aid)
        sids = [s[0] for s in self.actor_skills(src_aid)]
        if not self.set_actor_skills(dst_aid, sids):
            raise E.EditError('「%s」没有 @skills 字段，改不了' % self.actor_name(dst_aid))
        return sids

    # ---- 物品栏 ----
    def item_db_array(self):
        """$data_items 数组（存档里的那一份；游戏新增物品时会把实例 push 进去）。"""
        return self._db('data_items', 'Items.rxdata')

    def registration_state(self, iid, standard=None):
        """
        检查实例有没有在 $data_items 里登记 —— 游戏用它判断"能不能使用"：

            def item_can_use?(item_id)      # 传进来的就是实例的 @id
              return if $data_items[item_id].nil?      # ← 没登记就是 nil
              occasion = $data_items[item_id].occasion
              ...

        返回 (状态, 说明)：ok / missing / out_of_range / std_mismatch。
        """
        arr = self.item_db_array()
        if not isinstance(iid, int) or iid < 1:
            return 'missing', '实例 id 无效（%s）' % iid
        if iid >= len(arr):
            return 'out_of_range', ('$data_items[%d] 越界（数组只有 %d 项）'
                                    % (iid, len(arr)))
        t = arr[iid]
        if not isinstance(t, M.ObjNode):
            return 'missing', '$data_items[%d] 是空的' % iid
        if standard is not None and M.value_of(t.get('@standard')) != standard:
            return 'std_mismatch', ('$data_items[%d] 登记的是模板 %s'
                                    % (iid, M.value_of(t.get('@standard'))))
        return 'ok', ''

    def item_registered(self, iid, standard=None):
        return self.registration_state(iid, standard)[0] == 'ok'

    def next_item_db_id(self):
        """下一个登记槽号 = $data_items 的长度（游戏 random_item 就是这么分配）。"""
        return len(self.item_db_array())

    def register_item(self, iid, item_node):
        """
        把物品实例登记进 $data_items[iid]，与游戏 random_item 的行为一致：
            item.id = $data_items.size
            $data_items.push(item)
        不登记的话，游戏 `item_can_use?` 直接返回 nil，
        提示“该物品无法使用！再试也不能用，233333”。
        """
        arr = self.item_db_array()
        copy = E.clone_node(item_node)
        E.ensure_ivar(copy, '@id', int(iid))
        E.ensure_ivar(copy, '@quality', E.DEFAULT_QUALITY)
        while len(arr) < iid:
            arr.append(M.NilNode())
        if len(arr) == iid:
            arr.append(copy)
        else:
            arr[iid] = copy
        self._tpl_dirty = True
        return iid

    def pack_slot(self, slot, key='@pack'):
        for r in self.container_slots(key):
            if r['slot'] == slot:
                return r
        return None

    def _touch_pack(self, key='@pack'):
        """容器动过了 —— 保存时需要整条重写 $data（修好对象链接）。"""
        self._pack_dirty = True

    def set_pack_count(self, slot, count, key='@pack'):
        r = self.pack_slot(slot, key)
        if not r or not isinstance(r['cell'], M.ArrayNode):
            raise E.EditError('第 %d 格没有物品，无法改数量' % slot)
        count = int(count)
        if count < 1:
            raise E.EditError('数量至少是 1（要清空这一格请点「删除该格」）')
        self.begin_edit().set_scalar(r['cell'].items[1], count)
        return count

    def pack_delete(self, slot, key='@pack'):
        arr = self.container_node(key)
        if arr is None:
            raise E.EditError('存档里找不到容器 %s' % key)
        r = self.pack_slot(slot, key)
        if not r or not isinstance(r['cell'], M.ArrayNode):
            raise E.EditError('第 %d 格没有物品' % slot)
        self.begin_edit().set_array_element(arr, slot, b'0')      # 置为 nil
        self._touch_pack(key)
        return None

    def next_pack_instance_id(self):
        """旧调用：现在实例 id 就是登记槽号。"""
        return self.next_item_db_id()

    def pack_write(self, slot, standard_id, count=1, quality=None,
                   key='@pack', iid=None):
        """
        把某个容器的第 slot 格写成「模板 id = standard_id，数量 = count，品质 = quality」。

        关于 @id（实例编号）：游戏用 `$data_items[实例.@id]` 判断"能不能使用"，
        所以写入时必须做两件事（与游戏 random_item 完全一致）：
          1. 取一个新槽号（= $data_items 的长度）
          2. 把实例副本登记到 $data_items[新槽号]
        同一件物品（只改数量/品质）且登记正常时沿用原槽号，不浪费槽位。
        """
        slot = int(slot)
        if not (0 <= slot < self.PACK_SIZE):
            raise E.EditError('格子号要在 0 ~ %d 之间' % (self.PACK_SIZE - 1))
        arr = self.container_node(key)
        if arr is None:
            raise E.EditError('存档里找不到容器 %s' % key)
        items = self._db('data_items', 'Items.rxdata')
        sid = int(standard_id)
        if not (0 <= sid < len(items)):
            raise E.EditError('物品 id %s 不存在（可用范围 0 ~ %d）'
                              % (standard_id, len(items) - 1))
        tpl = items[sid]
        if not isinstance(tpl, M.ObjNode):
            raise E.EditError('物品 id %s 不是物品模板' % sid)
        r = self.pack_slot(slot, key)
        old_std = r['standard'] if (r and isinstance(r['standard'], int)) else None
        old_iid = r['iid'] if (r and isinstance(r['iid'], int)) else None
        if iid:
            new_iid = int(iid)
        elif old_iid is not None and old_std == sid \
                and self.item_registered(old_iid, sid):
            new_iid = old_iid                  # 同一件物品，只改数量/品质
        else:
            new_iid = self.next_item_db_id()   # 换模板 / 新增 -> 新登记槽
        count = int(count)
        if count < 1:
            count = 1
        q = int(quality) if quality else E.DEFAULT_QUALITY
        if q < 1:
            q = E.DEFAULT_QUALITY
        cell = E.make_pack_entry(tpl, count, new_instance_id=new_iid,
                                 standard_id=sid, quality=q)
        self.begin_edit().set_array_element(arr, slot, cell)
        self.register_item(new_iid, cell.items[0])
        self._touch_pack(key)
        return {'slot': slot, 'standard': sid, 'count': count, 'iid': new_iid,
                'quality': q, 'template_name': self.item_name(sid),
                'key': key, 'registered': True}

    # 兼容旧调用（测试脚本与界面用的名字）
    def pack_add(self, slot, standard_id, count=1, quality=None, key='@pack'):
        return self.pack_write(slot, standard_id, count, quality, key)

    def pack_set_template(self, slot, standard_id, count=None, quality=None,
                          key='@pack'):
        r = self.pack_slot(slot, key)
        if r is None:
            raise E.EditError('第 %d 格不存在' % slot)
        if count is None:
            count = r['count'] or 1
        return self.pack_write(slot, standard_id, count, quality, key)

    def pack_scan_bad(self):
        """找出"游戏里用不了"的异常格子（逐个容器扫描）。"""
        bad = []
        for key, label in CONTAINERS:
            for r in self.container_slots(key):
                if r['item'] is None:
                    continue
                why = []
                if E.find_ivar(r['item'], '@quality') is None:
                    why.append('缺品质字段（游戏会当成 0）')
                if not isinstance(r['standard'], int):
                    why.append('缺 @standard，认不出模板')
                if not isinstance(r['count'], int) or r['count'] < 1:
                    why.append('数量异常（%s）' % r['count'])
                # 对象链接错位：@name/@icon_name/@description 解出来不是字符串
                for fld in ('@name', '@icon_name', '@description'):
                    node = E.find_ivar(r['item'], fld)
                    if node is None:
                        continue
                    if not isinstance(deref(node), M.StrNode):
                        why.append('%s 不是字符串（对象链接错位）' % fld)
                        break
                # 没在 $data_items 登记 -> 游戏判定"该物品无法使用"
                st, msg = self.registration_state(r['iid'], r['standard'])
                if st != 'ok':
                    why.append('没登记（%s）' % msg)
                if why:
                    bad.append({'slot': r['slot'], 'key': key, 'label': label,
                                'name': r['name'], 'standard': r['standard'],
                                'why': '、'.join(why)})
        return bad

    def pack_fix_all(self):
        """把扫描到的异常格子全部按模板重建（并重新登记），返回修好的清单。"""
        fixed = []
        for b in self.pack_scan_bad():
            if not isinstance(b['standard'], int):
                continue          # 连模板都不知道是哪件，不敢动
            r = self.pack_slot(b['slot'], b['key'])
            q = r['quality'] if isinstance(r['quality'], int) and r['quality'] > 0 else None
            self.pack_write(b['slot'], b['standard'], r['count'], q, b['key'])
            fixed.append((b['key'], b['slot']))
        return fixed

    # ---- 开关 / 变量 ----
    def set_switch(self, idx, value):
        arr = self.ivar('game_switches', '@data')
        self.begin_edit().set_scalar(arr.items[idx], bool(value))
        return bool(value)

    def set_variable(self, idx, value):
        arr = self.ivar('game_variables', '@data')
        node = arr.items[idx]
        if isinstance(node, M.ObjNode) and node.cls == 'LockNumber':
            self._set_lock(node, value)
        else:
            self.begin_edit().set_scalar(node, int(value))
        return value

    # ---- 机器码 ----
    def set_machine_id(self, mid):
        node = self.node('存档id')
        pe = self.begin_edit()
        hit = 0
        for it in node.items:
            if isinstance(it, M.StrNode):
                pe.set_scalar(it, mid)
                hit += 1
        if not hit:
            raise E.EditError('存档里没有可写的机器码字段')
        return mid

    # ---- 通用：直接改一个标量节点（"全部解析数据"页右键修改用） ----
    def can_edit_node(self, node):
        return isinstance(node, (M.IntNode, M.BignumNode, M.BoolNode,
                                 M.StrNode, M.FloatNode, M.NilNode))

    def set_node_value(self, node, value):
        """把一个标量节点改成新值（打补丁，保存时生效）。"""
        if not self.can_edit_node(node):
            raise E.EditError('这个字段是「%s」，只有标量（整数/大整数/布尔/'
                              '文本/浮点/nil）能直接改' % type_text(node))
        self.begin_edit().set_scalar(node, value)
        return value

    # ---- 保存 ----
    def save(self, path=None, backup=True):
        if not self.is_dirty():
            return None
        pe = self.begin_edit()
        if self._tpl_dirty:
            # $data_items 里追加了登记项 -> 整条重写（对象链接全部展开，编号自洽）
            tpl = self.node('data_items')
            self._check_links(tpl)
            n = len(pe.replace_tree(tpl))
            if self.log:
                self.log('已整条重写 $data_items（%d 字节）：新增物品已登记' % n)
        if self._actors_dirty:
            # @skills 数组长度变了 -> 两个顶层对象（角色表/队伍）整条重写，
            # 否则数组后面的 '@N' 链接会因对象数变化而错位
            for name in ('game_actors', 'game_party'):
                nd = self.node(name)
                if nd is None:
                    continue
                self._check_links(nd)
                n = len(pe.replace_tree(nd))
                if self.log:
                    self.log('已整条重写 %s（%d 字节）' % (name, n))
        if self._pack_dirty:
            # 整条 $data 重新序列化：所有 '@N' 链接展开成独立副本，
            # 对象编号完全自洽（不会把后面格子的名字/图标指到别处）
            data = self.node('data')
            self._check_links(data)
            n = len(pe.replace_tree(data))
            if self.log:
                self.log('已整条重写 $data（%d 字节）：对象链接全部展开，编号自洽' % n)
        plain = pe.rebuild()
        path = path or self.path
        E.save_plain(plain, path, self.bridge, backup=backup, log=self.log)
        self.reload(plain)
        return path

    def _check_links(self, root):
        """重写前体检：确保每个 '@N' 都能找到目标，否则拒绝写入（不能写坏存档）。"""
        bad = []
        seen = set()

        def walk(n, depth=0):
            if n is None or depth > 300 or id(n) in seen:
                return
            seen.add(id(n))
            if isinstance(n, M.LinkNode):
                if n.target is None:
                    bad.append(n.index)
                return
            for c in E._kids(n):
                walk(c, depth + 1)

        walk(root)
        if bad:
            raise E.EditError('有 %d 个对象链接解析不到目标（编号 %s），'
                              '为避免写坏存档已中止' % (len(bad), bad[:5]))

    def discard(self):
        """放弃本会话的全部改动：把内存树恢复成"磁盘上的样子"。

        只把 _pe 丢掉是不够的 —— 被整块替换过的子树（@pack 的某一格、某个角色）
        已经被 _tag_new 打过"整块区间"的标记，节点自己的 start/end 不再等于它
        真实的字节范围；继续在旧树上打补丁就会把整块区间写成一两字节
        （真实故障：放弃修改后再改物品数量，保存后数量变成 0）。
        所以这里用原始明文重新解析一遍。
        """
        self.reload(self.plain)

    def reload(self, plain=None):
        if plain is not None:
            self.plain = bytes(plain)
            self.entries = M.parse_stream(self.plain)
            self.nodes = [e['node'] for e in self.entries]
        self._cache = {}
        self._pe = None
        self._pack_dirty = False
        self._tpl_dirty = False
        self._actors_dirty = False

    # ---------------- 导出 ----------------
    def export_text(self, max_items=200):
        """把整棵树导出成文本（大数组按 max_items 截断，避免文件过大）。"""
        lines = []
        lines.append('【画迹1：落日情缘】存档解析报告')
        lines.append('文件：%s' % self.path)
        for k, v in self.summary():
            if k:
                lines.append('%-16s %s' % (k, v))
        lines.append('')
        for t in self.top_list():
            lines.append('=' * 70)
            lines.append('#%d %s  (%d 字节, 偏移 %d..%d)  %s'
                         % (t['index'], t['name'], t['size'], t['start'], t['end'], t['desc']))
            lines.append('=' * 70)
            lines.append('  %s' % value_text(t['node'], 200))
            self._dump(t['node'], lines, 1, max_items)
        return '\n'.join(lines)

    def _dump(self, node, lines, depth, max_items):
        pad = '  ' * depth
        kids = children_of(node)
        if not kids:
            return
        dropped = 0
        if len(kids) > max_items:
            dropped = len(kids) - max_items
            kids = kids[:max_items]
        for k, v in kids:
            extra = '  (&链接 %d，与前面的同一对象)' % v.index if isinstance(v, M.LinkNode) else ''
            lines.append('%s%s : %s%s' % (pad, k, value_text(v), extra))
            self._dump(v, lines, depth + 1, max_items)
        if dropped:
            lines.append('%s... 还有 %d 项（已截断）' % (pad, dropped))

    def tree_children(self, node, limit=None):
        """给界面用的带限量子节点。"""
        kids = children_of(node)
        if limit is None or len(kids) <= limit:
            return kids, 0
        return kids[:limit], len(kids) - limit


def nodestr(n):
    return value_text(n) if n is not None else 'nil'
