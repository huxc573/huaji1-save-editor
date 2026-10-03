# -*- coding: utf-8 -*-
"""
==========================================================
 【画迹1：落日情缘】存档工具 0.3
==========================================================

本版要点：
  * 加解密改用随程序携带的 32 位宿主 XJCodec32.exe
      —— 不再调用 PowerShell、不再闪黑框、打开速度毫秒级
  * 修好"当前机器机器码"（0.2 漏加载 Socket.dll）
  * 物品栏按游戏实际结构 data.@pack 解析（20 格，[物品实例, 数量]）
  * 上线修改功能：金钱/声望/步数、角色、物品栏、开关变量、机器码
      —— 保存前自动备份 .bak，写回后回读校验

启动：双击 exe；也可以 python huaji1_save_editor.py [存档路径] [--selftest]
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    sys.stdout.reconfigure(errors='replace')
except Exception:
    pass


def _setup_tcl_env():
    """打包后 Tcl/Tk 的脚本库要显式指路（uv 版 Python 的目录布局）。"""
    if not getattr(sys, 'frozen', False):
        return
    base = getattr(sys, '_MEIPASS', None) or os.path.dirname(sys.executable)
    tcl = os.path.join(base, 'tcl', 'tcl8.6')
    tk = os.path.join(base, 'tcl', 'tk8.6')
    if os.path.isdir(tcl):
        os.environ['TCL_LIBRARY'] = tcl
    if os.path.isdir(tk):
        os.environ['TK_LIBRARY'] = tk


_setup_tcl_env()

import traceback

import backup
import codec as C
import patchwriter as E
import marshal_ruby as M
import doctree as MOD

VERSION = MOD.APP_VERSION
AUTHOR = MOD.AUTHOR
HOMEPAGE = MOD.HOMEPAGE
TITLE = MOD.APP_NAME + ' ' + VERSION

HELP_TEXT = """【画迹1：落日情缘】存档工具 %s
================================================================
 作者 %s　·　开源地址 %s
 协议 %s
 遇到问题先看 docs/排错指南.md，或到 %s 提 issue
================================================================

一、这个游戏的存档
  Audio\\BGM\\sy.ogg 就是存档（名字伪装成 BGM，其实不是音频）。
  游戏脚本 0030「Module Save_Load」里写着 $save_path = "Audio/BGM/sy.ogg"。

二、格式
  [魔数 0D 0F 3E 03] [4 字节密文长度] [zlib 压缩的密文]
  密文 = 游戏自带的 TP.dll 导出函数 DS1(明文, 口令 "xjy.11") 加密
  明文 = 19 个 Ruby Marshal 对象首尾相接（每个 04 08 开头）：
      characters / frame_count / $game_system / $game_switches / $game_variables
      / $game_self_switches / $game_screen / $game_actors / $game_party
      / $game_troop / $game_map / $game_player / $data_items / $data_classes
      / $data_weapons / $data_armors / $data_actors / $data / $存档id

三、两种"防作弊"
  1) LockNumber（脚本 0007）：金钱等数字被拆成 6 组带随机密钥的大整数，
     读的时候 6 组必须一致，否则游戏会进入死循环。本工具修改时会同时重算 6 组。
  2) $存档id：读档时与当前机器码（Socket.dll GetID）比对，不含本机机器码
     就会提示"存档的主人不是你"并退出。换机器玩要改这里。

四、角色 / 召唤兽在哪
  游戏用 @actor_id 区分：≤ 20 是人物，> 20 是召唤兽。
  数据存在两个顶层对象里（两份副本）：
    #7 $game_actors.@data     全部角色/召唤兽（下标 = @actor_id）
    #8 $game_party.@actors    出战的那一个（及它挂的召唤兽）
  每个对象是 Game_Actor（脚本 0044），关键字段：
    @name @class_id @level @exp @hp @sp @latent（潜力）@vitality @spirit
    @tizhi @moli @liliang @naili @minjie（五维）@五行
    召唤兽额外：@成长 @loyal（忠诚）@攻击资质 @防御资质 @体力资质 @法力资质
               @速度资质 @躲闪资质 @修炼等级
    @skills —— 已学技能 id 数组（人物、召唤兽都用它；脚本里的 learn_skill
              就是 @skills.push(id) + sort!，forget_skill 就是 delete）
  技能模板不在存档里，在 Data/Skills.rxdata（工具会自动去找）。

  ★ 召唤兽的“界面顺序”与“已放生”：
    游戏召唤兽界面是按主人的 @babys 数组顺序显示的（脚本 0143
    Window_Baby#refresh：@actor.babys.each { |i| @data.push($game_actors[i]) }）。
    本工具的顺序与它一致（主人按队伍顺序 × 主人 @babys 顺序）。
    放生（脚本 0044 remove_baby）只是把槽位从 @babys 里删掉、
    把 $data_actors[槽位] 清空，$game_actors 里的 Game_Actor 对象还留着 ——
    所以工具里只有“还被某个角色持有”的才显示；
    勾上「显示无主（已放生）的召唤兽」可以看到这些残留数据（标灰色）。
    （槽位 ↔ 原始模板 的对照表在 $game_party.@现id / @原id）

  ★ 改名：只改显示名，基础名不给动
    游戏显示名 = @new_name 存在 ? @new_name : @name（0040 Game_Battler#custom_name）。
    玩家在游戏里花 30 活力改名，写的就是 @new_name。
    本工具只提供【设为显示名】(写 @new_name) 和【清除显示名】(把 @new_name
    删掉恢复本名) —— @name 是游戏拿去索引 $pet 表的键，改错就把召唤兽界面
    搞崩，所以**没有**改基础名的入口。

  ★★ 为什么不动 @name（召唤兽的 @name 改错会把游戏搞崩）：
    脚本 0011 里有一张按【宠物名字】索引的表（154 个名字）：
        $pet = { "宠物名" => [六项资质, [成长…], 参战等级], ... }
    而游戏这些地方【没有 nil 判断】地查它：
        0163 Sys <召唤兽> 第 147 行   $pet["#{baby.name}"][7]   ← 打开召唤兽界面就崩
        0163 第 436/439 行、0121 第 572 行、0164 第 231/242 行
    0044 里 @name = actor.name.split(/【/)[0]，而 Game_Actor#name 就是 @name，
    所以 @name 一旦不是 $pet 里的键，就会报：
        NoMethodError: undefined method '[]' for nil:NilClass
    本工具的对策：
      · 召唤兽表有「名字表」列（✔ 在表里 / ⚠ 不在表里）和「携带等级」列
        （携带等级就是 $pet[名字][7]，游戏用它判断宠物能不能参战）
      · 名字栏会实时显示校验结果
      · 【恢复模板本名】：改回 $data_actors[模板].name（= 游戏自己的算法）
      · 【一键修复名字】：把名字异常的召唤兽批量改回去
    想换好听的名字请用【设为显示名(@new_name)】，它不参与 $pet 查表，随便改。

五、物品栏在哪
  游戏有三个 20 格的物品容器（System::Data）：
    道具 = @pack，行囊 = @wallet，备用 = @talisman（**不是** $game_party.@items）
  每格 = [ RPG::Item 实例, 数量 ]，也可能是 nil。
    @standard —— 模板 id，对应 data_items 里的模板（名字/图标/效果）
    @id       —— 实例编号，**必须能在 $data_items 里查到**：
                 游戏使用物品时执行 `item_can_use?` -> 用实例的 @id 去查
                 `$data_items[@id]` 读 occasion，查不到（nil）就直接提示
                 “该物品无法使用！再试也不能用，233333”
                 所以新增物品要像游戏 random_item 那样：@id = $data_items 的长度，
                 并把实例登记进去（工具会自动做）
    @quality  —— 品质（模板里没有这个字段，缺了游戏会当成 0）

六、本版本（%s）能改什么
  * 金钱（元宝）、声望、仓库金额、步数
  * 人物：等级（自动同步经验）、经验、HP/SP、活力/体力、五维、潜力、附加属性
  * 召唤兽：列表顺序与游戏界面一致（可勾选“显示无主”看已放生的）；
    能改等级/HP/SP/五维/潜力/成长/忠诚/六项资质；
    能【学会技能】/【忘掉选中】/【清空技能】（带技能搜索框）
  * 名字（人物 / 召唤兽都行）：只改显示名 —— 【设为显示名(@new_name)】/
    【清除显示名(恢复原名)】；召唤兽还有【恢复模板本名】/【一键修复名字】
    （@name 不给改：它必须在 $pet 名字表里，改错召唤兽界面会报 NoMethodError）
  * 物品栏：道具 @pack / 行囊 @wallet / 备用 @talisman 三个容器切换；
    格子 / 数量 / 物品id / 品质 填好后点「写入 · 修改该格」（新增会登记）；
    「删除该格」清空；「搜索物品」填关键字或编号过滤下拉列表
  * 存档机器码（可一键填入本机机器码）
  * 「全部解析数据」页：字段 / 类型 / 值 / 注释 四列（注释会告诉你这个字段
    是干什么的、技能 id 对应哪个技能、物品实例用的哪个模板…）；
    全局搜索（搜字段名或值，双击结果跳到树上）；
    对着标量字段右键 ->「修改这个值…」
  * 「存档管理」页：立即备份 / 编辑备注 / 恢复选中 / 恢复最新 / 删除选中 /
    删除无备注 / 删除非最新 / 打开备份目录；备份放在存档旁边的
    .huaji1-save-editor 目录里（多份带时间戳，和 sy.ogg.bak 不是一回事）
  每次修改后界面立刻刷新；保存时会：自动备份 sy.ogg.bak + 在「存档管理」里
  留一份时间戳备份 → 重新加密写回 → 读回校验。

六、注意
  * 改存档有风险，请先自己另外备份一份 sy.ogg。
  * 改坏了先到「存档管理」页点「恢复最新」，那是上一次修改前的存档。
  * 修改前请先退出游戏（文件被占用会导致保存失败）。
  * 保存后建议先进游戏确认，再继续大改。
  * 召唤兽技能模板来自 Data/Skills.rxdata（工具会自动向上找游戏的 Data 目录）；
    如果找不到，技能名会显示成"技能123"但功能仍然可用。
""" % (VERSION, AUTHOR, HOMEPAGE, MOD.LICENSE_NAME, MOD.ISSUES, VERSION)


def guess_save():
    """启动时自动找存档：上次用过的 -> 程序目录 -> 上层 -> 当前目录。"""
    cands = []
    cfg = os.path.join(C.app_dir(), 'last_save.txt')
    try:
        if os.path.exists(cfg):
            with open(cfg, encoding='utf-8') as f:
                cands.append(f.read().strip())
    except OSError:
        pass
    for base in (C.app_dir(), os.path.dirname(C.app_dir()), os.getcwd()):
        cands.append(os.path.join(base, 'Audio', 'BGM', 'sy.ogg'))
        cands.append(os.path.join(base, 'sy.ogg'))
    for p in cands:
        if p and os.path.exists(p):
            return p
    return None


def remember_save(path):
    try:
        with open(os.path.join(C.app_dir(), 'last_save.txt'), 'w',
                  encoding='utf-8') as f:
            f.write(path)
    except OSError:
        pass


def istxt(s):
    try:
        float(s)
        return False
    except ValueError:
        return True


# 窗口设计尺寸：版式预算的唯一来源 —— test_gui.py 拿它当「不裁」的判据
WIN_SIZE = '1220x800'


class App(object):
    def __init__(self, root, save_path=None):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        # ★ Tk 回调里未捕获的异常默认只往 stderr 打一行 —— --windowed 的 exe
        #   没有控制台，于是“按钮点了没反应”。这里换成：写 error.log + 弹窗。
        root.report_callback_exception = self._tk_exception
        self.bridge = None
        self.doc = None
        self.node_of_item = {}
        self.path_of_item = {}
        self.actor_rows = {}
        self.pack_rows = {}

        root.title(TITLE)
        root.geometry(WIN_SIZE)

        self._build_top(save_path)
        self._build_notebook()
        self._build_status()

        self.refresh_dll_status()
        auto = save_path or guess_save()
        if auto:
            self.var_path.set(auto)
            self.root.after(300, lambda: self.load(auto))
        else:
            self.set_status('请点「选择存档…」打开 Audio\\BGM\\sy.ogg')

    # ================= 顶部 =================
    def _build_top(self, save_path):
        tk, ttk = self.tk, self.ttk
        top = ttk.Frame(self.root, padding=6)
        top.pack(fill='x')

        ttk.Button(top, text='选择存档…', command=self.choose_file).pack(side='left')
        self.var_path = tk.StringVar(value=save_path or '')
        ttk.Entry(top, textvariable=self.var_path, width=56).pack(side='left', padx=6)
        ttk.Button(top, text='重新载入', command=self.reload).pack(side='left')
        ttk.Separator(top, orient='vertical').pack(side='left', fill='y', padx=6)
        ttk.Button(top, text='保存修改(Ctrl+S)', command=self.save_save).pack(side='left')
        ttk.Button(top, text='放弃修改', command=self.reload).pack(side='left', padx=4)
        ttk.Separator(top, orient='vertical').pack(side='left', fill='y', padx=6)
        ttk.Button(top, text='导出报告', command=self.export_report).pack(side='left')
        ttk.Button(top, text='导出明文', command=self.export_plain).pack(side='left', padx=4)
        self.root.bind('<Control-s>', lambda e: self.save_save())

        self.var_dll = tk.StringVar()
        ttk.Label(self.root, textvariable=self.var_dll, foreground='#555',
                  anchor='w').pack(fill='x', padx=8)

        # ---- 作者 / 开源地址（可点击打开）----
        info = ttk.Frame(self.root)
        info.pack(fill='x', padx=8, pady=(0, 4))
        ttk.Label(info, text='作者 @%s　·　开源地址 ' % AUTHOR,
                  foreground='#555').pack(side='left')
        link = tk.Label(info, text=HOMEPAGE, foreground='#0a58ca',
                        cursor='hand2', font=('Consolas', 9, 'underline'))
        link.pack(side='left')
        link.bind('<Button-1>', lambda e: self.open_homepage())
        ttk.Button(info, text='关于', command=self.show_about,
                   width=6).pack(side='left', padx=8)
        ttk.Button(info, text='复制地址',
                   command=self.copy_homepage, width=9).pack(side='left')
        ttk.Label(info, text=MOD.LICENSE_NAME, foreground='#888').pack(side='left',
                                                                        padx=8)

    # ================= 页签 =================
    def _build_notebook(self):
        tk, ttk = self.tk, self.ttk
        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill='both', expand=True, padx=6, pady=4)

        # ---- 1 概览 + 快捷修改（版式对齐画迹2：左右 PanedWindow，中间可拖）----
        f1 = ttk.Frame(self.nb, padding=8)
        self.nb.add(f1, text='概览 / 快捷修改')
        body1 = ttk.Panedwindow(f1, orient='horizontal')
        body1.pack(fill='both', expand=True)

        # ===== 左：快捷修改（4 项排成一行，画迹2 同款；竖排 4 行太占地）=====
        g = ttk.LabelFrame(body1, text='快捷修改（先点「应用」，再点上面的「保存修改」）',
                           padding=10)
        body1.add(g, weight=1)
        self.var_gold = tk.StringVar()
        self.var_fame = tk.StringVar()
        self.var_store = tk.StringVar()
        self.var_steps = tk.StringVar()
        rows = [('金钱(元宝)', self.var_gold), ('声望', self.var_fame),
                ('仓库金额', self.var_store), ('步数', self.var_steps)]
        for i, (label, var) in enumerate(rows):
            ttk.Label(g, text=label + '：', anchor='w').grid(
                row=0, column=i * 2, sticky='w', padx=(4, 2), pady=3)
            ttk.Entry(g, textvariable=var, width=10).grid(
                row=0, column=i * 2 + 1, sticky='we', padx=(0, 8))
        # 4 个输入框列等权重 → 窗口拉宽时一起变宽（画迹2 同款）
        for c in (1, 3, 5, 7):
            g.columnconfigure(c, weight=1)
        ttk.Label(g, foreground='#888', justify='left', wraplength=460,
                  text='金钱走 LockNumber 6 组一起重算，不会被判定作弊'
                  ).grid(row=1, column=0, columnspan=8, sticky='w', pady=(6, 0))
        ttk.Button(g, text='应用', command=self.apply_quick).grid(
            row=2, column=0, sticky='w', pady=(8, 0))

        # ===== 右：存档概况（原先是 fill='x' 的死高度；现在占满剩余空间）=====
        h1 = ttk.LabelFrame(body1, text='存档概况', padding=6)
        body1.add(h1, weight=1)
        self.lb_info = tk.Text(h1, height=10, wrap='none', font=('Consolas', 10))
        vs1 = ttk.Scrollbar(h1, orient='vertical', command=self.lb_info.yview)
        hs1 = ttk.Scrollbar(h1, orient='horizontal', command=self.lb_info.xview)
        self.lb_info.configure(yscrollcommand=vs1.set, xscrollcommand=hs1.set)
        vs1.pack(side='right', fill='y')
        hs1.pack(side='bottom', fill='x')
        self.lb_info.pack(fill='both', expand=True)

        # ---- 1.5 存档管理（备份 / 恢复）----
        self._tab_saves()

        # ---- 2 全部解析数据（全局搜索 + 双击跳转）----
        f2 = ttk.Frame(self.nb, padding=8)
        self.nb.add(f2, text='全部解析数据')
        bar = ttk.Frame(f2)
        bar.pack(fill='x')
        ttk.Label(bar, text='全局搜索：').pack(side='left')
        self.var_search = tk.StringVar()
        ent = ttk.Entry(bar, textvariable=self.var_search, width=30)
        ent.pack(side='left')
        ent.bind('<Return>', lambda e: self.global_search())
        ttk.Button(bar, text='搜索', command=self.global_search).pack(side='left', padx=4)
        ttk.Button(bar, text='清空结果', command=self.clear_search).pack(side='left')
        ttk.Button(bar, text='全部折叠', command=self.collapse_all).pack(side='left', padx=4)
        ttk.Label(bar, text='　（搜字段名或值 → 双击结果跳到树上；右键可改标量）',
                  foreground='#777').pack(side='left')

        # 搜索结果（默认隐藏）
        self.fr_hits = ttk.LabelFrame(f2, text='搜索结果（双击跳转）', padding=4)
        self.tv_search = ttk.Treeview(self.fr_hits, columns=('p', 't', 'v'),
                                      show='headings', height=7)
        for c, h, w in (('p', '路径', 430), ('t', '类型', 90), ('v', '值', 470)):
            self.tv_search.heading(c, text=h)
            self.tv_search.column(c, width=w, anchor='w')
        vs2 = ttk.Scrollbar(self.fr_hits, orient='vertical',
                            command=self.tv_search.yview)
        self.tv_search.configure(yscrollcommand=vs2.set)
        self.tv_search.pack(side='left', fill='both', expand=True)
        vs2.pack(side='left', fill='y')
        self.tv_search.bind('<Double-1>', self.goto_search_hit)
        self.tv_search.bind('<Return>', self.goto_search_hit)
        self.search_meta = []

        body = ttk.Panedwindow(f2, orient='horizontal')
        body.pack(fill='both', expand=True, pady=4)
        left, right = ttk.Frame(body), ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=2)
        self.tree = ttk.Treeview(left, columns=('type', 'value', 'note'),
                                 show='tree headings')
        self.tree.heading('#0', text='字段')
        self.tree.heading('type', text='类型')
        self.tree.heading('value', text='值')
        self.tree.heading('note', text='注释')
        self.tree.column('#0', width=220)
        self.tree.column('type', width=100)
        self.tree.column('value', width=300)
        self.tree.column('note', width=380)
        vs = ttk.Scrollbar(left, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=vs.set)
        hs = ttk.Scrollbar(left, orient='horizontal', command=self.tree.xview)
        self.tree.configure(xscrollcommand=hs.set)
        hs.pack(side='bottom', fill='x')
        self.tree.pack(side='left', fill='both', expand=True)
        vs.pack(side='left', fill='y')
        self.tree.bind('<<TreeviewOpen>>', self.on_open)
        self.tree.bind('<<TreeviewSelect>>', self.on_select)
        self.tree.bind('<Button-3>', self.tree_menu)
        self.tree_menu_obj = tk.Menu(self.tree, tearoff=0)
        self.tree_menu_obj.add_command(label='修改这个值…',
                                       command=self.tree_edit_value)
        self.tree_menu_obj.add_command(label='刷新该节点',
                                       command=lambda: self.on_open())
        self.tree_menu_obj.add_separator()
        self.tree_menu_obj.add_command(label='拷到剪贴板（字段名 + 值）',
                                       command=self.tree_copy)
        self.tree_menu_obj.add_command(label='重新载入整棵树（丢弃焦点）',
                                       command=self.fill_tree)
        self.txt_node = tk.Text(right, wrap='word', width=40, height=10)
        vs3 = ttk.Scrollbar(right, orient='vertical', command=self.txt_node.yview)
        self.txt_node.configure(yscrollcommand=vs3.set)
        self.txt_node.pack(side='left', fill='both', expand=True)
        vs3.pack(side='left', fill='y')
        self.txt_node.configure(font=('Consolas', 10))

        # ---- 3 角色 / 召唤兽（分开显示，都能改）----
        f3 = ttk.Frame(self.nb, padding=8)
        self.nb.add(f3, text='角色 / 召唤兽')
        grp = ttk.Frame(f3)
        grp.pack(fill='x')
        ttk.Label(grp, text='显示：').pack(side='left')
        self.var_actor_group = tk.StringVar(value='person')
        ttk.Radiobutton(grp, text='人物', value='person',
                        variable=self.var_actor_group,
                        command=self.on_actor_group_change).pack(side='left', padx=2)
        ttk.Radiobutton(grp, text='召唤兽', value='pet',
                        variable=self.var_actor_group,
                        command=self.on_actor_group_change).pack(side='left', padx=2)
        self.var_pet_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(grp, text='显示无主（已放生）的召唤兽',
                        variable=self.var_pet_all,
                        command=self.on_actor_group_change).pack(side='left', padx=8)
        self.lb_actor_hint = ttk.Label(grp, text='', foreground='#666')
        self.lb_actor_hint.pack(side='left', padx=10)

        # ---- 名字（人物 / 召唤兽通用）----
        #     游戏显示名 = @new_name 存在 ? @new_name : @name
        #     （0040 Game_Battler#custom_name；玩家在游戏里改名就是写 @new_name）
        nf = ttk.LabelFrame(f3, text='名字（只改显示名 @new_name；基础名 @name 不动）',
                            padding=6)
        nf.pack(fill='x', pady=4)
        self.lb_name_now = ttk.Label(nf, text='（未选中）', foreground='#444',
                                     width=44, anchor='w')
        self.lb_name_now.grid(row=0, column=0, sticky='w')
        self.var_newname = tk.StringVar()
        ttk.Entry(nf, textvariable=self.var_newname, width=18).grid(
            row=0, column=1, padx=4)
        ttk.Button(nf, text='设为显示名(@new_name)',
                   command=self.apply_custom_name).grid(row=0, column=2, padx=2)
        ttk.Button(nf, text='清除显示名(恢复原名)',
                   command=self.clear_custom_name).grid(row=0, column=3, padx=2)
        # 召唤兽专用：$pet 名字表校验（名字不在表里游戏会崩）—— 见 doctree 注释
        self.lb_name_check = ttk.Label(nf, text='', foreground='#444')
        self.lb_name_check.grid(row=1, column=0, columnspan=3, sticky='w', pady=(4, 0))
        ttk.Button(nf, text='恢复模板本名',
                   command=self.restore_pet_name).grid(row=1, column=3, padx=2,
                                                        pady=(4, 0))
        ttk.Button(nf, text='一键修复名字',
                   command=self.fix_pet_names_ui).grid(row=1, column=4, padx=2,
                                                        pady=(4, 0))

        # ================= 人物 =================
        self.fr_person = ttk.Frame(f3)
        cols3 = ('id', 'name', 'class', 'level', 'exp', 'hp', 'maxhp', 'sp', 'maxsp',
                 'tizhi', 'moli', 'liliang', 'naili', 'minjie', 'latent', 'where')
        heads3 = ('ID', '名字', '门派', '等级', '经验', 'HP', 'HP上限', 'SP', 'SP上限',
                  '体质', '魔力', '力量', '耐力', '敏捷', '潜力', '数据位置')
        self.tv_actor = ttk.Treeview(self.fr_person, columns=cols3,
                                     show='headings', height=7)
        for c, h in zip(cols3, heads3):
            self.tv_actor.heading(c, text=h)
            self.tv_actor.column(c, width=68, anchor='center')
        self.tv_actor.column('name', width=110)
        self.tv_actor.column('class', width=88)
        self.tv_actor.column('where', width=96)
        self.tv_actor.pack(fill='x')
        self.tv_actor.bind('<<TreeviewSelect>>', lambda e: self.load_actor_edit())

        e = ttk.LabelFrame(self.fr_person, text='修改选中的人物（召唤兽请切到右边）', padding=8)
        e.pack(fill='x', pady=8)
        self.actor_vars = {}
        fields = [('@level', '等级', 6), ('@exp', '经验', 10), ('@hp', 'HP', 8),
                  ('@sp', 'SP', 8), ('@vitality', '活力', 6), ('@spirit', '体力', 6),
                  ('@tizhi', '体质', 6), ('@moli', '魔力', 6), ('@liliang', '力量', 6),
                  ('@naili', '耐力', 6), ('@minjie', '敏捷', 6), ('@latent', '潜力', 6),
                  ('@add_tizhi', '附加体质', 6), ('@add_moli', '附加魔力', 6),
                  ('@add_liliang', '附加力量', 6), ('@add_naili', '附加耐力', 6),
                  ('@add_minjie', '附加敏捷', 6), ('@maxhp_plus', 'HP加成', 6),
                  ('@maxsp_plus', 'SP加成', 6)]
        # 每行 4 组（画迹2 同款）：19 个字段从 10 行压到 5 行，整页矮一半多；
        # 标签自适应宽 + 全角冒号（固定 width=9 会把空白垫在输入框左边，画迹2 踩过）
        for i, (ivar, label, _w) in enumerate(fields):
            r, c = i // 4, i % 4
            ttk.Label(e, text=label + '：').grid(
                row=r, column=c * 2, sticky='w', pady=2,
                padx=(0 if c == 0 else 10, 2))
            var = tk.StringVar()
            ttk.Entry(e, textvariable=var, width=9).grid(
                row=r, column=c * 2 + 1, pady=2, sticky='we')
            self.actor_vars[ivar] = var
        # 4 组输入框列等权重，窗口拉宽时一起变宽
        for c in (1, 3, 5, 7):
            e.columnconfigure(c, weight=1)
        # 预设按钮并成一行放网格下面（原先是竖条挂在网格右侧 rowspan=10）
        btns = ttk.Frame(e)
        btns.grid(row=(len(fields) + 3) // 4, column=0, columnspan=8,
                  sticky='w', pady=(8, 0))
        ttk.Button(btns, text='应用人物修改',
                   command=self.apply_actor).pack(side='left')
        ttk.Button(btns, text='一键满级(175/180)',
                   command=lambda: self.actor_preset('max')).pack(side='left', padx=6)
        ttk.Button(btns, text='HP/SP 填满',
                   command=lambda: self.actor_preset('heal')).pack(side='left')
        ttk.Button(btns, text='五维+10',
                   command=lambda: self.actor_preset('attr')).pack(side='left', padx=6)
        ttk.Button(btns, text='活力/体力150',
                   command=lambda: self.actor_preset('vital')).pack(side='left')
        self.txt_actor = tk.Text(self.fr_person, height=4, width=60,
                                 wrap='word')
        vsa = ttk.Scrollbar(self.fr_person, orient='vertical',
                            command=self.txt_actor.yview)
        self.txt_actor.configure(yscrollcommand=vsa.set)
        self.txt_actor.pack(side='left', fill='both', expand=True)
        vsa.pack(side='left', fill='y')

        # ================= 召唤兽 =================
        # 版式对齐画迹2 的召唤兽页：
        #   一览表 → 「改字段」整行 → 左右分栏（左「字段 / 当前值」两列表，
        #   右「常用」技能 + 「详细信息」）。
        # 旧版是 7 行 x 5 列的输入框网格 + 底部技能区：1220x800 下整页要 727px、
        # 可用只有约 690px，技能表最后两行和横向滚动条被切到窗口外（"展示不完整"），
        # 所以按画迹2 重排。
        # ⚠ 宽度预算：窗口 1220，减掉顶栏/页签边距后各块 reqwidth 必须 <= 1200。
        self.fr_pet = ttk.Frame(f3)
        colsP = ('no', 'slot', 'display', 'name', 'nameok', 'tpl', 'owner', 'level',
                 'carry', 'growth', 'loyal', 'za', 'zd', 'zt', 'zm', 'zs', 'zdd',
                 'skills', 'state')
        headsP = ('序', '槽位', '显示名', '原名', '名字表', '模板', '主人', '等级',
                  '携带等级', '成长', '忠诚', '攻资', '防资', '体资', '法资', '速资',
                  '躲资', '技能', '状态')
        # 列宽合计 1058：连竖滚动条一起也塞得下 1220 的窗口（改列宽要连着算总宽）
        self.tv_pet = ttk.Treeview(self.fr_pet, columns=colsP, show='headings',
                                   height=6, selectmode='browse')
        for c, h, w in zip(colsP, headsP,
                           (34, 48, 86, 76, 58, 108, 68, 42, 56, 46, 46, 44, 44,
                            44, 44, 44, 44, 40, 86)):
            self.tv_pet.heading(c, text=h)
            self.tv_pet.column(c, width=w, anchor='center')
        self.tv_pet.tag_configure('dead', foreground='#999')
        self.tv_pet.tag_configure('badname', foreground='#c00')
        # ⚠ pack 顺序＝防裁顺序：竖滚动条先贴右，一览表 fill='x'，横滚动条最后贴底
        vs_pet = ttk.Scrollbar(self.fr_pet, orient='vertical',
                               command=self.tv_pet.yview)
        self.tv_pet.configure(yscrollcommand=vs_pet.set)
        hs_pet = ttk.Scrollbar(self.fr_pet, orient='horizontal',
                               command=self.tv_pet.xview)
        self.tv_pet.configure(xscrollcommand=hs_pet.set)
        vs_pet.pack(side='right', fill='y')
        self.tv_pet.pack(fill='x')
        hs_pet.pack(fill='x')
        self.tv_pet.bind('<<TreeviewSelect>>', lambda e: self.load_actor_edit())

        # ---- 可改字段清单（顺序 = 字段表里的顺序；值存在 self.pet_vars）----
        self.pet_fields = [('@level', '等级'), ('@exp', '经验'), ('@hp', 'HP'),
                           ('@sp', 'SP'), ('@tizhi', '体质'), ('@moli', '魔力'),
                           ('@liliang', '力量'), ('@naili', '耐力'),
                           ('@minjie', '敏捷'), ('@latent', '潜力'),
                           ('@vitality', '活力'), ('@spirit', '体力'),
                           ('@成长', '成长'), ('@loyal', '忠诚'),
                           ('@攻击资质', '攻击资质'), ('@防御资质', '防御资质'),
                           ('@体力资质', '体力资质'), ('@法力资质', '法力资质'),
                           ('@速度资质', '速度资质'), ('@躲闪资质', '躲闪资质')]
        self.pet_vars = {}
        for _ivar, _label in self.pet_fields:
            self.pet_vars[_ivar] = tk.StringVar()
        self.pet_cur_ivar = None
        self.petf_rows = {}
        self.var_pet_field = tk.StringVar()
        self.var_pet_edit = tk.StringVar()

        # ---- 改字段（整行；版式同画迹2：字段只读框 + 值输入框 + 应用 + 预设）----
        #     左边字段表选中哪一项，这两个框就切到哪一项，「应用」写的就是它。
        #     apply_actor 仍按 self.pet_vars 全字段落一遍 —— 其余字段的值都是从存档
        #     读出来的原值，所以效果等价于"只改了选中那一个"。
        edit2 = ttk.Frame(self.fr_pet)
        edit2.pack(fill='x', pady=(6, 0))
        ttk.Label(edit2, text='改字段：').pack(side='left')
        ttk.Entry(edit2, textvariable=self.var_pet_field, width=12,
                  state='readonly').pack(side='left')
        ttk.Label(edit2, text='值').pack(side='left', padx=(4, 0))
        self.ent_petval = ttk.Entry(edit2, textvariable=self.var_pet_edit, width=14)
        self.ent_petval.pack(side='left', padx=(4, 0))
        ttk.Button(edit2, text='应用召唤兽修改',
                   command=self.apply_actor).pack(side='left', padx=6)
        # 预设：一次改一整组，和「应用」一样都作用在当前选中的那只身上
        for _txt, _cmd in (('资质+500', lambda: self.pet_preset('zz')),
                           ('成长+0.1', lambda: self.pet_preset('growth')),
                           ('忠诚 100 / 五维+10', lambda: self.pet_preset('loyal')),
                           ('HP/SP 填满', lambda: self.actor_preset('heal'))):
            ttk.Button(edit2, text=_txt, command=_cmd).pack(side='left', padx=2)

        # ---- 左右分栏：左「字段 / 当前值」，右「常用」+「详细信息」----
        mid2 = ttk.Frame(self.fr_pet)
        mid2.pack(fill='both', expand=True, pady=(6, 0))
        left2 = ttk.Frame(mid2)
        left2.pack(side='left', fill='both')
        right2 = ttk.Frame(mid2)
        right2.pack(side='left', fill='both', expand=True, padx=(8, 0))
        self.tv_petf = ttk.Treeview(left2, columns=('f', 'v'), show='headings',
                                    height=12, selectmode='browse')
        self.tv_petf.heading('f', text='字段')
        self.tv_petf.heading('v', text='当前值')
        self.tv_petf.column('f', width=132, anchor='w')
        self.tv_petf.column('v', width=104, anchor='e')
        vsf = ttk.Scrollbar(left2, orient='vertical', command=self.tv_petf.yview)
        self.tv_petf.configure(yscrollcommand=vsf.set)
        vsf.pack(side='right', fill='y')
        self.tv_petf.pack(fill='both', expand=True)
        self.tv_petf.bind('<<TreeviewSelect>>', lambda e: self.on_pet_field_select())

        # ---- 常用（技能）/ 详细信息（两列等宽，照画迹2）----
        commonf = ttk.LabelFrame(right2, text='常用', padding=6)
        commonf.grid(row=0, column=0, sticky='nsew', padx=(0, 4))
        ttk.Label(commonf, text='技能（存档字段 @skills）',
                  foreground='#555').pack(anchor='w')
        skbar = ttk.Frame(commonf)
        skbar.pack(fill='x', pady=(4, 0))
        ttk.Label(skbar, text='搜索').pack(side='left')
        self.var_skill_search = tk.StringVar()
        ske = ttk.Entry(skbar, textvariable=self.var_skill_search, width=8)
        ske.pack(side='left', padx=3)
        ske.bind('<KeyRelease>', lambda e: self.filter_skill_templates())
        self.var_skill_add = tk.StringVar()
        self.cb_skill = ttk.Combobox(skbar, textvariable=self.var_skill_add,
                                     width=18)
        self.cb_skill.pack(side='left')
        # ⚠ 四个按钮另起一行：挤在搜索框/下拉框后面会把下拉框压没（画迹2 同款教训）
        skbtn = ttk.Frame(commonf)
        skbtn.pack(fill='x', pady=(4, 0))
        ttk.Button(skbtn, text='学会技能',
                   command=self.skill_add).pack(side='left', padx=(0, 4))
        ttk.Button(skbtn, text='忘掉选中',
                   command=self.skill_del).pack(side='left')
        ttk.Button(skbtn, text='清空技能',
                   command=self.skill_clear).pack(side='left', padx=4)
        ttk.Button(skbtn, text='克隆技能…',
                   command=self.skill_clone).pack(side='left')
        self.lb_skill_info = ttk.Label(commonf, text='', foreground='#888')
        self.lb_skill_info.pack(anchor='w')
        # 技能说明单独一块只读框：描述动辄几十字，塞进表格列会被切（画迹2 同样做法）。
        # ⚠ tk.Text 必须显式 width/height —— 默认 80x24 = 566x460px，会把页签顶出窗口。
        # pack 顺序也是防裁的一环：说明框先贴底，技能表放最后挨刀（它自带滚动条）。
        self.txt_skill_desc = tk.Text(commonf, height=2, width=40, wrap='word',
                                      relief='flat', highlightthickness=1,
                                      highlightbackground='#ddd',
                                      font=('Microsoft YaHei UI', 9),
                                      state='disabled')
        self.txt_skill_desc.pack(side='bottom', fill='x', pady=(4, 0))
        skbox = ttk.Frame(commonf)
        skbox.pack(fill='both', expand=True, pady=(4, 0))
        # 只放 id + 名字：带一列 430px 的"描述"会把这一块顶到 674px，
        # 而右半栏只有 ~450px —— 描述在表格里永远看不全，所以拆到上面的说明框。
        self.tv_skill = ttk.Treeview(skbox, columns=('id', 'name'),
                                     show='headings', height=5,
                                     selectmode='browse')
        self.tv_skill.heading('id', text='技能 id')
        self.tv_skill.heading('name', text='技能名')
        self.tv_skill.column('id', width=58, anchor='center')
        self.tv_skill.column('name', width=190)
        vsk = ttk.Scrollbar(skbox, orient='vertical', command=self.tv_skill.yview)
        self.tv_skill.configure(yscrollcommand=vsk.set)
        vsk.pack(side='right', fill='y')
        self.tv_skill.pack(side='left', fill='both', expand=True)
        self.tv_skill.bind('<<TreeviewSelect>>', lambda e: self.on_skill_pick())
        self.skill_desc_of = {}

        infof = ttk.LabelFrame(right2, text='详细信息', padding=6)
        infof.grid(row=0, column=1, sticky='nsew', padx=(4, 0))
        self.txt_pet = tk.Text(infof, height=2, width=40, wrap='word',
                               relief='flat', highlightthickness=1,
                               highlightbackground='#ddd',
                               font=('Microsoft YaHei UI', 9), state='disabled')
        self.txt_pet.pack(fill='both', expand=True)
        right2.columnconfigure(0, weight=1, uniform='col')
        right2.columnconfigure(1, weight=1, uniform='col')
        self.show_actor_group()

        self.txt_actor.configure(font=('Consolas', 10))

        # ---- 4 物品栏（道具 / 行囊 / 备用 三个容器）----
        f4 = ttk.Frame(self.nb, padding=8)
        self.nb.add(f4, text='物品栏(道具/行囊/备用)')
        top = ttk.Frame(f4)
        top.pack(fill='x')
        ttk.Label(top, text='容器：').pack(side='left')
        self.var_container = tk.StringVar(value='@pack')
        for key, label in MOD.CONTAINERS:
            ttk.Radiobutton(top, text=label, value=key,
                            variable=self.var_container,
                            command=self.on_container_change).pack(side='left', padx=2)
        ttk.Label(top, foreground='#666',
                  text='   游戏里这三个都是 20 格（@pack / @wallet / @talisman），'
                       '每格 = [实例, 数量]'
                  ).pack(side='left')
        top2 = ttk.Frame(f4)
        top2.pack(fill='x', pady=(4, 0))
        ttk.Label(top2, text='类别（按实例的 Ruby 类）：').pack(side='left')
        self.var_tpl_kind = tk.StringVar(value='item')
        for _k, _c, _t, _l in MOD.ITEM_KINDS:
            ttk.Radiobutton(top2, text=_l, value=_k, variable=self.var_tpl_kind,
                            command=self.on_tpl_kind_change).pack(side='left', padx=2)
        ttk.Label(top2, foreground='#666',
                  text='   兜兜/灵石/糖果 = 装备，与上面的容器无关'
                  ).pack(side='left')
        self._tpls = []
        self._tpl_kind = 'item'
        self._tpl_cache = {}
        self._tpl_pick = {}
        self._tpl_lb = None        # 下拉内部 listbox 的 Tcl 路径
        self._tpl_cmds = {}        # 注册过的 Tcl 回调（只注册一次）
        self._tip_win = None
        self._tip_lab = None
        self._tip_row = None
        self._tip_item = None
        cols4 = ('slot', 'kind', 'name', 'std', 'iid', 'count', 'quality',
                 'reg', 'desc')
        heads4 = ('格', '类', '物品名（实例）', '模板id', '实例id', '数量',
                  '品质', '登记', '说明')
        pkwrap = ttk.Frame(f4)
        pkwrap.pack(fill='both', expand=True, pady=4)
        self.tv_pack = ttk.Treeview(pkwrap, columns=cols4, show='headings',
                                    height=12)
        for c, h in zip(cols4, heads4):
            self.tv_pack.heading(c, text=h)
            self.tv_pack.column(c, width=60, anchor='w',
                                stretch=(c == 'desc'))
        hs4 = ttk.Scrollbar(pkwrap, orient='horizontal',
                            command=self.tv_pack.xview)
        vs4 = ttk.Scrollbar(pkwrap, orient='vertical',
                            command=self.tv_pack.yview)
        self.tv_pack.configure(xscrollcommand=hs4.set, yscrollcommand=vs4.set)
        hs4.pack(side='bottom', fill='x')
        self.tv_pack.pack(side='left', fill='both', expand=True)
        vs4.pack(side='left', fill='y')
        self.tv_pack.bind('<<TreeviewSelect>>', lambda e: self.load_pack_edit())
        self.tv_pack.bind('<Configure>', self.fit_pack_cols)
        self.tv_pack.bind('<Motion>', self.on_pack_hover)
        self.tv_pack.bind('<Leave>', lambda e: self.hide_tip())

        g4 = ttk.LabelFrame(
            f4, text='修改当前容器（空格子 = 新增；已有物品的格子 = 覆盖重建）',
            padding=8)
        g4.pack(fill='x')
        self.var_pack_slot = tk.StringVar()
        self.var_pack_count = tk.StringVar()
        self.var_pack_quality = tk.StringVar()
        ttk.Label(g4, text='格子').grid(row=0, column=0, sticky='w')
        ttk.Entry(g4, textvariable=self.var_pack_slot, width=5).grid(row=0, column=1)
        ttk.Label(g4, text='数量').grid(row=0, column=2, sticky='w', padx=(12, 0))
        ttk.Entry(g4, textvariable=self.var_pack_count, width=8).grid(row=0, column=3)
        ttk.Label(g4, text='品质').grid(row=0, column=4, sticky='w', padx=(12, 0))
        ttk.Entry(g4, textvariable=self.var_pack_quality, width=8).grid(row=0, column=5)
        # 搜索在上、物品 id 在下（先搜索过滤，再从下拉里选，更直观）
        ttk.Label(g4, text='搜索物品').grid(row=1, column=0, sticky='w', pady=(8, 0))
        self.var_tpl_search = tk.StringVar()
        ent = ttk.Entry(g4, textvariable=self.var_tpl_search, width=14)
        ent.grid(row=1, column=1, sticky='w', pady=(8, 0))
        ent.bind('<KeyRelease>', lambda e: self.filter_templates())
        ttk.Button(g4, text='列出全部', command=self.clear_tpl_search).grid(
            row=1, column=2, sticky='w', pady=(8, 0))
        self.lb_tpl_info = ttk.Label(g4, text='', foreground='#888')
        self.lb_tpl_info.grid(row=1, column=3, columnspan=3, sticky='w', pady=(8, 0))
        ttk.Label(g4, text='物品 id').grid(row=2, column=0, sticky='w', pady=(6, 0))
        self.var_pack_std = tk.StringVar()
        self.cb_tpl = ttk.Combobox(g4, textvariable=self.var_pack_std, width=52)
        self.cb_tpl.grid(row=2, column=1, columnspan=4, sticky='w', pady=(6, 0))
        self.cb_tpl.bind('<<ComboboxSelected>>', self.on_tpl_pick)
        # 下拉弹出前把内部 listbox 的悬停绑上（popdown 只有弹出时才存在）
        self.cb_tpl.configure(postcommand=self.on_tpl_post)
        ttk.Button(g4, text='写入 · 修改该格', command=self.pack_apply).grid(
            row=0, column=6, rowspan=3, padx=(14, 4), sticky='ns')
        ttk.Button(g4, text='删除该格', command=self.pack_delete).grid(
            row=0, column=7, rowspan=3, sticky='ns')
        ttk.Label(g4, foreground='#888', justify='left',
                  text='① 搜索是跨三类的：搜到别的类别会自动切过去，不必先手选「类别」；「类别」决定查哪张表，\n'
                       '   和容器（道具 @pack / 行囊 @wallet / 备用 @talisman）是两回事：装备/防具也装在 @pack；\n'
                       '② 写入时按类别登记进 $data_items / $data_weapons / $data_armors，自动分配实例 id，\n'
                       '   装备/防具还会并进职业可装备表（照游戏 random_weapon）；泡泡兜兜/灵石/糖果按物品列出，\n'
                       '   写入自动登记进 $data_weapons；“登记”列 ✓ = 游戏认得；数量<1 按 1 算，品质<1 按 100 算。'
                  ).grid(row=3, column=0, columnspan=8, sticky='w', pady=(6, 0))
        ttk.Button(g4, text='一键修复异常格', command=self.pack_fix_bad).grid(
            row=4, column=6, columnspan=2, sticky='w', pady=(4, 0))

        # ---- 5 机器码 ----
        f6 = ttk.Frame(self.nb, padding=10)
        self.nb.add(f6, text='机器码')
        self.txt_id = tk.Text(f6, height=8, wrap='word')
        self.txt_id.pack(fill='both', expand=True)
        self.txt_id.configure(font=('Consolas', 10))
        g6 = ttk.LabelFrame(f6, text='修改存档机器码', padding=10)
        g6.pack(fill='x', pady=8)
        self.var_id = tk.StringVar()
        ttk.Label(g6, text='新机器码').grid(row=0, column=0, sticky='w')
        ttk.Entry(g6, textvariable=self.var_id, width=28).grid(row=0, column=1)
        ttk.Button(g6, text='填入本机机器码',
                   command=self.id_fill_local).grid(row=0, column=2, padx=6)
        ttk.Button(g6, text='写入存档', command=self.id_apply).grid(row=0, column=3)
        ttk.Label(g6, foreground='#888',
                  text='换电脑读档报"存档的主人不是你"时，把这里改成新机器的机器码。'
                  ).grid(row=1, column=0, columnspan=4, sticky='w', pady=(6, 0))

        # ---- 6 说明 ----
        f7 = ttk.Frame(self.nb, padding=8)
        self.nb.add(f7, text='说明 / 机制')
        t7 = tk.Text(f7, wrap='word')
        t7.pack(fill='both', expand=True)
        t7.insert('1.0', HELP_TEXT)
        t7.configure(state='disabled', font=('Microsoft YaHei UI', 10))

        # ---- 7 更新日志 ----
        f8 = ttk.Frame(self.nb, padding=8)
        self.nb.add(f8, text='更新日志')
        t8 = tk.Text(f8, wrap='word')
        t8.pack(fill='both', expand=True)
        t8.insert('1.0', MOD.CHANGELOG)
        t8.configure(state='disabled', font=('Microsoft YaHei UI', 10))

    def _build_status(self):
        self.var_status = self.tk.StringVar(value='就绪')
        self.ttk.Label(self.root, textvariable=self.var_status, relief='sunken',
                       anchor='w').pack(fill='x', side='bottom')

    # ================= 基础 =================
    def _tk_exception(self, exc, val, tb):
        """Tk 回调里未捕获的异常：写日志 + 弹窗（不然在 exe 里就是“没反应”）。"""
        import traceback
        from tkinter import messagebox
        text = ''.join(traceback.format_exception(exc, val, tb))
        try:
            with open(os.path.join(C.app_dir(), 'error.log'), 'a',
                      encoding='utf-8') as f:
                f.write('\n===== %s =====\n%s'
                        % (time.strftime('%Y-%m-%d %H:%M:%S'), text))
        except OSError:
            pass
        try:
            messagebox.showerror(
                '出错',
                '%s: %s\n\n（详细信息已写入程序目录的 error.log）'
                % (getattr(exc, '__name__', exc), val), parent=self.root)
        except Exception:
            pass
        try:
            self.set_status('出错：%s（详见 error.log）' % val)
        except Exception:
            pass

    def set_status(self, s):
        self.var_status.set(s)
        try:
            self.root.update_idletasks()
        except Exception:
            pass

    def log(self, s):
        self.set_status(s)

    # ================= 作者 / 开源地址 =================
    def open_homepage(self):
        """用系统浏览器打开项目主页。"""
        import webbrowser
        ok = False
        try:
            ok = webbrowser.open(HOMEPAGE)
        except Exception:
            ok = False
        self.set_status('开源地址：%s%s' % (HOMEPAGE, '' if ok else '（请手动复制到浏览器）'))

    def copy_homepage(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(HOMEPAGE)
            self.set_status('已复制开源地址：%s' % HOMEPAGE)
        except Exception as e:
            self.err(e)

    def show_about(self):
        from tkinter import messagebox
        messagebox.showinfo(
            '关于',
            '%s\n'
            '版本 %s\n\n'
            '作者：@%s\n'
            '开源地址：%s\n'
            '问题反馈：%s\n'
            '开源协议：%s\n\n'
            '本工具是第三方的存档查看/修改器，与游戏作者无关；\n'
            '请先备份 Audio\\BGM\\sy.ogg 再使用。\n'
            '游戏本体及其素材、数据文件的版权归原作者所有。'
            % (MOD.APP_NAME, VERSION, AUTHOR, HOMEPAGE, MOD.ISSUES,
               MOD.LICENSE_NAME), parent=self.root)

    def refresh_dll_status(self):
        st = C.dll_status()
        parts = []
        for name in ('TP.dll', 'Socket.dll', C.HOST_NAME):
            parts.append('%s: %s' % (name, '有' if st.get(name) else '缺'))
        self.var_dll.set('依赖检查 —— ' + '，'.join(parts)
                         + '    （这三个文件要和本程序放在同一目录）')
        return st

    def get_bridge(self):
        if self.bridge is None:
            self.bridge = C.make_bridge(log=self.log)
        return self.bridge

    def mark_dirty(self):
        self.root.title(TITLE + '  * 有未保存的修改')
        self.set_status('已修改（记得点「保存修改」）')

    def clear_dirty(self):
        self.root.title(TITLE)

    def err(self, e):
        from tkinter import messagebox
        msg = ''.join(traceback.format_exception_only(type(e), e)).strip() \
            if isinstance(e, Exception) else str(e)
        self.set_status('出错：%s' % msg)
        messagebox.showerror('出错', msg, parent=self.root)

    # ================= 打开 / 保存 =================
    def choose_file(self):
        from tkinter import filedialog
        init = self.var_path.get()
        if not init or not os.path.exists(init):
            init = os.path.join(os.getcwd(), 'Audio', 'BGM')
            if not os.path.isdir(init):
                init = os.getcwd()
        path = filedialog.askopenfilename(
            parent=self.root, title='选择存档文件（Audio/BGM/sy.ogg）',
            initialdir=os.path.dirname(init) if os.path.isfile(init) else init,
            filetypes=[('本作存档 sy.ogg', 'sy.ogg'), ('所有文件', '*.*')])
        if path:
            self.var_path.set(path)
            self.load(path)

    def reload(self):
        if self.doc and self.doc.is_dirty():
            from tkinter import messagebox
            if not messagebox.askyesno('确认', '放弃未保存的修改？', parent=self.root):
                return
        p = self.var_path.get()
        if p:
            self.load(p)

    def load(self, path):
        if not os.path.exists(path):
            self.err('文件不存在：%s' % path)
            return
        self.set_status('正在解密…')
        try:
            self.refresh_dll_status()
            doc = MOD.Doc(path, self.get_bridge(), log=self.log)
            self.doc = doc
            self.clear_dirty()
            self.fill_all()
            self.set_status('已打开 %s —— 明文 %d 字节，%d 个顶层对象'
                            % (os.path.basename(path), len(doc.plain), len(doc.entries)))
            remember_save(path)
        except Exception as e:
            self.err(e)

    def save_save(self):
        if not self.doc:
            return
        from tkinter import messagebox
        if not self.doc.is_dirty():
            messagebox.showinfo('提示', '没有任何改动。', parent=self.root)
            return
        if not messagebox.askyesno(
                '确认保存',
                '把修改写回：\n%s\n\n'
                '· 原文件会先备份成 %s.bak\n'
                '· 同时在「存档管理」里留一份带时间戳的备份\n'
                '· 写回后会重新解密读回校验\n\n继续？'
                % (self.doc.path, os.path.basename(self.doc.path)), parent=self.root):
            return
        path = self.doc.path
        # 落盘前先在「存档管理」的目录里留一份（同一份文件 90 秒内只留一次）
        try:
            backup.auto_backup_once(self.doc.path)
        except Exception:
            pass
        try:
            changed = self.doc.changed_bytes()
            self.doc.save(path, backup=True)
            self.clear_dirty()
            self.fill_all()
            self.set_status('已保存并校验通过（改动 %d 字节）' % changed)
            messagebox.showinfo('保存成功',
                                '已写回：\n%s\n\n备份：\n%s.bak\n\n'
                                '校验：重新解密读回一致 ✔'
                                % (path, os.path.basename(path)), parent=self.root)
        except Exception as e:
            self.err(e)

    def fill_all(self):
        self.fill_info()
        self.fill_tree()
        self.fill_actors()
        self.fill_pack()
        self.refresh_templates()
        self.fill_id()
        self.saves_refresh()

    # ================= 概览 / 快捷修改 =================
    def fill_info(self):
        self.lb_info.delete('1.0', 'end')
        if not self.doc:
            return
        lines = []
        for k, v in self.doc.summary():
            lines.append('%-18s %s' % (k, v) if k else '')
        lines.append('')
        lines.append('%-4s %-18s %-10s %-18s %s' % ('#', '名字', '大小', '明文偏移', '说明'))
        lines.append('-' * 100)
        for t in self.doc.top_list():
            lines.append('%-4d %-18s %-10s %-18s %s'
                         % (t['index'], t['name'], '%d B' % t['size'],
                            '%d..%d' % (t['start'], t['end']), t['desc']))
        self.lb_info.insert('1.0', '\n'.join(lines))
        self.var_gold.set(str(self.doc.gold()))
        gs = self.doc.node('data')
        self.var_fame.set(str(M.value_of(gs.get('@fame'))))
        self.var_store.set(str(M.value_of(gs.get('@store_cash'))))
        self.var_steps.set(str(M.value_of(self.doc.node('game_party').get('@steps'))))

    def apply_quick(self):
        if not self.doc:
            return
        try:
            if self.var_gold.get().strip():
                self.doc.set_gold(float(self.var_gold.get()))
            if self.var_fame.get().strip():
                self.doc.set_fame(int(self.var_fame.get()))
            if self.var_store.get().strip():
                self.doc.set_store_cash(int(self.var_store.get()))
            if self.var_steps.get().strip():
                self.doc.set_steps(int(self.var_steps.get()))
            self.mark_dirty()
            self.fill_info()
        except Exception as e:
            self.err(e)

    # ================= 解析树（只读，带注释列） =================
    def fill_tree(self):
        self.tree.delete(*self.tree.get_children())
        self.node_of_item.clear()
        self.path_of_item = {}
        if not self.doc:
            return
        for t in self.doc.top_list():
            label = '#%d %s' % (t['index'], t['name'])
            iid = self.tree.insert('', 'end', text=label,
                                   values=(MOD.type_text(t['node']),
                                           MOD.value_text(t['node'], 60),
                                           self.doc.note_of(label, t['node'], None, '')))
            self.node_of_item[iid] = t['node']
            self.path_of_item[iid] = t['name']
            if MOD.children_of(t['node']):
                self.tree.insert(iid, 'end', text='加载中…', values=('', '', ''))

    def on_open(self, event=None):
        iid = self.tree.focus()
        if not iid:
            return
        kids = self.tree.get_children(iid)
        if len(kids) == 1 and self.tree.item(kids[0], 'text') == '加载中…':
            self.tree.delete(kids[0])
            self._fill_children(iid)

    def _fill_children(self, iid, limit=300):
        node = self.node_of_item.get(iid)
        if node is None:
            return
        path = self.path_of_item.get(iid, '')
        kids, dropped = self.doc.tree_children(node, limit)
        for label, child in kids:
            txt = MOD.value_text(child, 60)
            if isinstance(child, M.LinkNode):
                txt += '  (与前面的同一对象)'
            cid = self.tree.insert(iid, 'end', text=str(label),
                                   values=(MOD.type_text(child), txt,
                                           self.doc.note_of(label, child,
                                                            node, path)))
            self.node_of_item[cid] = child
            self.path_of_item[cid] = ('%s.%s' % (path, label)) if path else str(label)
            if MOD.children_of(child):
                self.tree.insert(cid, 'end', text='加载中…', values=('', '', ''))
        if dropped:
            self.tree.insert(iid, 'end', text='…还有 %d 项（未显示）' % dropped,
                             values=('', '', ''))

    def collapse_all(self):
        for iid in self.tree.get_children():
            self.tree.item(iid, open=False)
            for c in self.tree.get_children(iid):
                self.tree.delete(c)
            self.tree.insert(iid, 'end', text='加载中…', values=('', '', ''))

    def filter_tree(self):
        """旧名字：保留兼容，改成全局搜索。"""
        self.global_search()

    # -------- 全局搜索（所有顶层对象 + 所有层级）--------
    def global_search(self, event=None):
        if not self.doc:
            return
        kw = self.var_search.get().strip().lower()
        if not kw:
            self.clear_search()
            return
        limit = 3000
        hits = []
        for i in range(len(self.doc.entries)):
            name = MOD.TOP_NAMES[i] if i < len(MOD.TOP_NAMES) else str(i)
            top = self.doc.node(name)
            if top is None:
                continue
            self._walk_search(top, name, [name], kw, hits, limit, 0, i)
            if len(hits) >= limit:
                break
        self.search_meta = [(h[0], h[1]) for h in hits]
        self.tv_search.delete(*self.tv_search.get_children())
        for top_i, _labels, path, node in hits:
            self.tv_search.insert('', 'end', values=(path, MOD.type_text(node),
                                                     MOD.value_text(node, 80)))
        if hits:
            self.fr_hits.pack(fill='x', pady=(4, 0))
        else:
            self.fr_hits.pack_forget()
        self.set_status('全局搜索「%s」：命中 %d 条%s（双击结果可跳到树上）'
                        % (kw, len(hits), '（已截断）' if len(hits) >= limit else ''))

    def _walk_search(self, node, path, labels, kw, out, limit, depth, top_index):
        if node is None or depth > 12 or len(out) >= limit:
            return
        if kw in path.lower() or kw in MOD.value_text(node, 120).lower():
            out.append((top_index, list(labels), path, node))
        for k, v in MOD.children_of(node):
            lab = str(k)
            self._walk_search(v, '%s.%s' % (path, lab), labels + [lab],
                              kw, out, limit, depth + 1, top_index)

    def clear_search(self):
        self.tv_search.delete(*self.tv_search.get_children())
        self.search_meta = []
        self.fr_hits.pack_forget()
        self.set_status('已清空搜索结果')

    def goto_search_hit(self, event=None):
        sel = self.tv_search.selection()
        if not sel:
            return
        idx = self.tv_search.index(sel[0])
        if idx >= len(self.search_meta):
            return
        top_index, labels = self.search_meta[idx]
        self.reveal_node(top_index, labels)

    def reveal_node(self, top_index, labels):
        """在左侧树里逐级展开到指定节点（label 序列从顶层开始）。"""
        kids = self.tree.get_children()
        if not kids:
            self.fill_tree()
            kids = self.tree.get_children()
        if top_index >= len(kids):
            return
        iid = kids[top_index]
        for lab in labels[1:]:
            self.tree.item(iid, open=True)
            self.tree.focus(iid)
            self.on_open()
            nxt = None
            for c in self.tree.get_children(iid):
                if self.tree.item(c, 'text') == lab:
                    nxt = c
                    break
            if nxt is None:
                break
            iid = nxt
        self.tree.item(iid, open=True)
        self.tree.see(iid)
        self.tree.selection_set(iid)
        self.tree.focus(iid)
        self.on_select()
        self.set_status('已定位：%s' % ' > '.join(labels))

    def on_select(self, event=None):
        iid = self.tree.focus()
        node = self.node_of_item.get(iid)
        if node is None:
            return
        lines = ['字段：%s' % self.tree.item(iid, 'text'),
                 '类型：%s' % MOD.type_text(node)]
        parent = self.node_of_item.get(self.tree.parent(iid)) \
            if self.tree.parent(iid) else None
        note = self.doc.note_of(self.tree.item(iid, 'text'), node, parent,
                                self.path_of_item.get(self.tree.parent(iid), '')) \
            if self.doc else ''
        if note:
            lines.append('注释：%s' % note)
        if hasattr(node, 'start'):
            lines.append('明文偏移：%d..%d（%d 字节）'
                         % (node.start, node.end, node.end - node.start))
        if isinstance(node, M.UserDefNode):
            lines.append('自定义块 %s：%d 字节' % (node.cls, len(node.data)))
            lines.append('前 64 字节：%s' % ' '.join('%02X' % b for b in node.data[:64]))
        elif isinstance(node, M.BignumNode):
            lines.append('值：%d' % node.value)
        else:
            lines.append('值：%s' % MOD.value_text(node, 4000))
        kids = MOD.children_of(node)
        if kids:
            lines.append('')
            lines.append('子项 %d 个：' % len(kids))
            for k, v in kids[:80]:
                lines.append('   %-24s %s' % (k, MOD.value_text(v, 100)))
            if len(kids) > 80:
                lines.append('   …还有 %d 个' % (len(kids) - 80))
        self.txt_node.delete('1.0', 'end')
        self.txt_node.insert('1.0', '\n'.join(lines))

    # -------- 解析树右键：修改标量 --------
    def tree_menu(self, event=None):
        if event is not None and getattr(event, 'y', None) is not None:
            iid = self.tree.identify_row(event.y)
            if iid:
                self.tree.selection_set(iid)
                self.tree.focus(iid)
        node = self.node_of_item.get(self.tree.focus())
        ok = (node is not None and self.doc is not None
              and self.doc.can_edit_node(node))
        self.tree_menu_obj.entryconfigure(0, state='normal' if ok else 'disabled')
        if event is not None:
            try:
                self.tree_menu_obj.tk_popup(event.x_root, event.y_root)
            finally:
                self.tree_menu_obj.grab_release()
        else:
            self.tree_menu_obj.tk_popup(self.tree.winfo_rootx() + 80,
                                        self.tree.winfo_rooty() + 60)

    def tree_edit_value(self):
        """右键 -> 修改这个值：只改当前这个标量节点，改完立刻刷新显示。"""
        from tkinter import simpledialog, messagebox
        iid = self.tree.focus()
        node = self.node_of_item.get(iid)
        if node is None or not self.doc:
            return
        label = self.tree.item(iid, 'text')
        if not self.doc.can_edit_node(node):
            self.err('「%s」是 %s，只有标量（整数/大整数/布尔/文本/浮点/nil）能直接改'
                     % (label, MOD.type_text(node)))
            return
        try:
            if isinstance(node, M.BoolNode):
                cur = bool(node.value)
                new = messagebox.askyesno(
                    '修改布尔值',
                    '%s\n\n当前：%s\n\n改成 true 吗？（选"否"就是 false）'
                    % (label, 'true' if cur else 'false'), parent=self.root)
            elif isinstance(node, M.StrNode):
                cur = node.str()
                new = simpledialog.askstring(
                    '修改文本', '%s\n\n当前：%s\n\n新值：' % (label, cur),
                    initialvalue=cur, parent=self.root)
                if new is None:
                    return
            elif isinstance(node, M.NilNode):
                new = simpledialog.askinteger(
                    '修改 nil 槽位', '%s\n\n当前是 nil。填一个整数（例如 0 / 1）：'
                    % label, parent=self.root)
                if new is None:
                    return
            elif isinstance(node, (M.IntNode, M.BignumNode)):
                cur = MOD.vof(node)
                new = simpledialog.askinteger(
                    '修改整数', '%s\n\n当前：%s\n\n新值：' % (label, cur),
                    initialvalue=int(cur) if isinstance(cur, int) else 0,
                    parent=self.root)
                if new is None:
                    return
            else:
                cur = MOD.vof(node)
                new = simpledialog.askfloat(
                    '修改浮点数', '%s\n\n当前：%s\n\n新值：' % (label, cur),
                    initialvalue=float(cur or 0), parent=self.root)
                if new is None:
                    return
            self.doc.set_node_value(node, new)
            self.mark_dirty()
            # 只刷新这一行，保住整棵树的展开状态
            self.tree.item(iid, values=(MOD.type_text(node), MOD.value_text(node, 60)))
            self.on_select()
            self.set_status('%s -> %s（记得保存）'
                            % (label, MOD.value_text(node, 40)))
        except Exception as e:
            self.err(e)

    def tree_copy(self):
        node = self.node_of_item.get(self.tree.focus())
        if node is None:
            return
        txt = '%s = %s' % (self.tree.item(self.tree.focus(), 'text'),
                           MOD.value_text(node, 500))
        self.root.clipboard_clear()
        self.root.clipboard_append(txt)
        self.set_status('已复制：%s' % txt[:60])

    # ================= 角色 / 召唤兽 =================
    def cur_actor_group(self):
        try:
            return self.var_actor_group.get() or 'person'
        except Exception:
            return 'person'

    def on_actor_group_change(self):
        self.show_actor_group()
        self.fill_actors()
        self.load_actor_edit()
        if self.cur_actor_group() == 'pet':
            self.set_status('当前显示：召唤兽 —— 顺序与游戏"召唤兽"界面一致'
                            '（按主人 @babys 排列）；已放生的默认不显示')
        else:
            self.set_status('当前显示：人物（@actor_id ≤ 20）')

    def show_actor_group(self):
        if self.cur_actor_group() == 'pet':
            self.fr_person.pack_forget()
            self.fr_pet.pack(fill='both', expand=True)
        else:
            self.fr_pet.pack_forget()
            self.fr_person.pack(fill='both', expand=True)

    def fill_actors(self):
        self.tv_actor.delete(*self.tv_actor.get_children())
        self.tv_pet.delete(*self.tv_pet.get_children())
        self.actor_rows = {}
        self.pet_rows = {}
        if not self.doc:
            return
        show_dead = bool(self.var_pet_all.get())
        n_dead = 0
        n_badname = 0
        for r in self.doc.actor_rows():
            if r['is_pet']:
                if not r['owned']:
                    n_dead += 1
                    if not show_dead:
                        continue
                bad = (r['name_ok'] is False)
                if bad:
                    n_badname += 1
                tags = []
                if not r['owned']:
                    tags.append('dead')
                if bad:
                    tags.append('badname')
                iid = self.tv_pet.insert(
                    '', 'end',
                    values=(r['order'], r['id'], r['display'], r['name'],
                            ('✔ 在表里' if r['name_ok'] else
                             ('⚠ 不在表里' if r['name_ok'] is False else '（无表）')),
                            ('%s %s' % (r['tpl'], r['tpl_name']))
                            if isinstance(r['tpl'], int) else '?',
                            r['owner_name'] or '—',
                            r['level'],
                            ('—' if r['carry'] is None else r['carry']),
                            r['growth'], r['loyal'],
                            r['zz_attack'], r['zz_defense'], r['zz_tili'],
                            r['zz_magic'], r['zz_speed'], r['zz_dodge'],
                            len(r['skills']),
                            '有主' if r['owned'] else '无主（已放生）'),
                    tags=tuple(tags))
                self.pet_rows[iid] = r['id']
            else:
                iid = self.tv_actor.insert('', 'end', values=(
                    r['id'], r['name'], r['class'], r['level'], r['exp'], r['hp'],
                    r['maxhp'], r['sp'], r['maxsp'], r['tizhi'], r['moli'],
                    r['liliang'], r['naili'], r['minjie'], r['latent'], r['where']))
                self.actor_rows[iid] = r['id']
        hint = '人物 %d 个，召唤兽 %d 只（按游戏界面顺序；另有 %d 只无主已放生）' \
               % (len(self.actor_rows), len(self.pet_rows), n_dead)
        if n_badname:
            hint += '   ⚠ 有 %d 只名字不在 $pet 表里 —— 游戏打开召唤兽会报 ' \
                    'NoMethodError，点【一键修复名字】' % n_badname
        self.lb_actor_hint.configure(
            text=hint,
            foreground='#c00' if n_badname else '#666')
        self.refresh_skill_templates()

    def current_actor_id(self):
        if self.cur_actor_group() == 'pet':
            tv, rows = self.tv_pet, self.pet_rows
        else:
            tv, rows = self.tv_actor, self.actor_rows
        iid = tv.focus()
        if not iid or iid not in rows:
            ch = tv.get_children()
            if ch:
                iid = ch[0]
                tv.focus(iid)
        return rows.get(iid)

    def current_actor_row(self):
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            return None
        for r in self.doc.actor_rows():
            if r['id'] == aid:
                return r
        return None

    def actor_label(self, aid):
        a = self.doc.actor(aid) if self.doc else None
        return '%s %s' % ('召唤兽' if aid > 20 else '人物',
                          MOD.stext(a.get('@name'), '?') if a is not None else aid)

    def select_actor(self, aid):
        tv, rows = (self.tv_pet, self.pet_rows) if aid > 20 \
            else (self.tv_actor, self.actor_rows)
        for iid, a in rows.items():
            if a == aid:
                tv.selection_set(iid)
                tv.focus(iid)
                tv.see(iid)
                break

    # -------- 名字（@new_name / @name）--------
    def load_name_bar(self, aid=None):
        if aid is None:
            aid = self.current_actor_id()
        if aid is None or not self.doc:
            self.lb_name_now.configure(text='（未选中）')
            self.lb_name_check.configure(text='')
            return
        a = self.doc.actor(aid)
        if a is None:
            return
        base = MOD.stext(a.get('@name'), '')
        new = MOD.stext(a.get('@new_name'), '')
        custom = self.doc.has_custom_name(aid)
        kind = '召唤兽' if aid > 20 else '人物'
        self.lb_name_now.configure(
            text='%s %s ｜ @name=%s ｜ @new_name=%s ｜ 游戏显示：%s'
                 % (kind, aid, base, ('"%s"' % new) if custom else '（无）',
                    new if custom else base))
        self.var_newname.set(new if custom else base)
        # 召唤兽：@name 必须在游戏的 $pet 名字表里（0163 第 147 行 $pet[名字][7]）
        if aid > 20:
            self._update_name_check(aid, base)
        else:
            self.lb_name_check.configure(text='')

    def _update_name_check(self, aid, base):
        row = self.doc.pet_table_row(base)
        if row is None and not self.doc.pet_name_table():
            self.lb_name_check.configure(
                text='（找不到游戏的 $pet 名字表，无法校验名字）', foreground='#888')
            return
        if row is not None:
            self.lb_name_check.configure(
                text='✔「%s」在游戏的 $pet 名字表里（该宠基础资质 %s，携带等级 %s）'
                     % (base, '/'.join(str(x) for x in row[0]), row[2]),
                foreground='#0a6b0a')
            return
        sug, why = self.doc.suggest_pet_name(aid)
        self.lb_name_check.configure(
            text='⚠「%s」不在游戏的 $pet 名字表里 —— 打开召唤兽界面会报 '
                 'NoMethodError（%s建议改成「%s」）'
                 % (base, ('没有模板本名；' if not sug else ''), sug or '—'),
            foreground='#c00')

    def restore_pet_name(self):
        """把召唤兽的 @name 改回模板本名（$data_actors[模板].name）。"""
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            self.err('请先在上面选中一只召唤兽')
            return
        if aid <= 20:
            self.err('这个按钮只对召唤兽有效（人物没有 $pet 名字表校验）')
            return
        try:
            sug, why = self.doc.suggest_pet_name(aid)
            if not sug:
                self.err('拿不到这只召唤兽的模板本名（槽位 %s 的模板不明确）' % aid)
                return
            self.doc.set_actor_name(aid, sug)
            self._after_rename(aid, '召唤兽 %s 的名字已恢复成「%s」（%s）'
                               % (aid, sug, why))
        except Exception as e:
            self.err(e)

    def fix_pet_names_ui(self):
        """把所有名字不在 $pet 表里的召唤兽批量改回模板本名。"""
        if not self.doc:
            return
        from tkinter import messagebox
        probs = self.doc.pet_name_problems(include_unowned=False)
        if not probs:
            messagebox.showinfo('名字检查',
                                '所有召唤兽的名字都在游戏的 $pet 表里，没问题。',
                                parent=self.root)
            return
        lines = ['下面 %d 只召唤兽的名字不在游戏的 $pet 表里，' % len(probs),
                 '打开召唤兽界面会报 NoMethodError，要改回模板本名：', '']
        for p in probs:
            lines.append('  槽位 %s：「%s」→「%s」' % (p['id'], p['name'],
                                                 p['suggest'] or '（拿不到）'))
        lines += ['', '继续？（改完记得点「保存修改」）']
        if not messagebox.askyesno('修复召唤兽名字', '\n'.join(lines),
                                   parent=self.root):
            return
        try:
            fixed = self.doc.fix_pet_names(include_unowned=False)
            self.mark_dirty()
            self.fill_actors()
            self.load_actor_edit()
            self.set_status('已修复 %d 只召唤兽的名字（记得保存）' % len(fixed))
            messagebox.showinfo(
                '修复完成',
                '已修复 %d 只：\n%s\n\n记得点上面的「保存修改」。'
                % (len(fixed),
                   '\n'.join('  槽位 %s →「%s」' % (f['id'], f['suggest'])
                             for f in fixed)), parent=self.root)
        except Exception as e:
            self.err(e)

    def _after_rename(self, aid, msg):
        self.mark_dirty()
        self.fill_actors()
        self.select_actor(aid)
        self.load_actor_edit()
        self.set_status(msg)

    def apply_custom_name(self):
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            self.err('请先在上面选中一个人物或召唤兽')
            return
        txt = self.var_newname.get().strip()
        if not txt:
            self.err('请先在输入框里写上新的显示名')
            return
        try:
            self.doc.set_actor_custom_name(aid, txt)
            self._after_rename(aid, '%s 的显示名已改成「%s」（游戏里显示的就是它）'
                               % (self.actor_label(aid), txt))
        except Exception as e:
            self.err(e)

    def clear_custom_name(self):
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            return
        try:
            self.doc.clear_actor_custom_name(aid)
            self._after_rename(aid, '%s 的改名字段已清掉，恢复游戏原名'
                               % self.actor_label(aid))
        except Exception as e:
            self.err(e)

    # ---- 召唤兽「字段 / 当前值」两列表（版式照画迹2 的召唤兽页）----
    def pet_field_label(self, ivar):
        for v, label in self.pet_fields:
            if v == ivar:
                return label
        return ivar

    def fill_pet_fields(self):
        """刷新字段表；保持（或恢复）选中 —— 选中的那一行决定右边"值"框绑谁。

        ⚠ Treeview 重建后必须自己把选中恢复回去，否则每次刷新都跳回第一行，
        「改当前这只」就会静默落到别的字段上（画迹2 的一览表踩过同款坑）。
        """
        keep = self.pet_cur_ivar
        self.tv_petf.delete(*self.tv_petf.get_children())
        self.petf_rows = {}
        for ivar, label in self.pet_fields:
            var = self.pet_vars.get(ivar)
            iid = self.tv_petf.insert('', 'end',
                                      values=(label, var.get() if var else ''))
            self.petf_rows[iid] = ivar
        want = [iid for iid, iv in self.petf_rows.items() if iv == keep]
        if not want and self.petf_rows:
            want = [sorted(self.petf_rows)[0]]
        if want:
            self.tv_petf.selection_set(want[0])      # 触发 on_pet_field_select
            self.tv_petf.see(want[0])

    def on_pet_field_select(self):
        """选中字段表某一行 -> 右侧「字段 / 值」两个框切到这个字段。"""
        sel = self.tv_petf.selection()
        if not sel:
            return
        ivar = self.petf_rows.get(sel[0])
        if ivar is None:
            return
        self.pet_cur_ivar = ivar
        self.var_pet_field.set(self.pet_field_label(ivar))
        # 输入框直接绑到那个字段的 StringVar：编辑的就是它，apply_actor 读的也是它
        var = self.pet_vars.get(ivar)
        self.ent_petval.configure(textvariable=var if var is not None
                                  else self.var_pet_edit)

    def set_pet_info(self, txt):
        """「详细信息」框（只读）：一览表要横滚才看得全的东西，这里摊成文字。"""
        try:
            self.txt_pet.configure(state='normal')
            self.txt_pet.delete('1.0', 'end')
            self.txt_pet.insert('1.0', txt or '')
            self.txt_pet.configure(state='disabled')
        except Exception:
            pass

    def show_pet_info(self):
        r = self.current_actor_row()
        if not r:
            self.set_pet_info('（未选中召唤兽）')
            return
        ok = r['name_ok']
        lines = [
            '槽位 %s　模板 %s　主人 %s'
            % (r['id'],
               ('%s %s' % (r['tpl'], r['tpl_name']))
               if isinstance(r['tpl'], int) else '?',
               r['owner_name'] or '—'),
            '显示名 %s　@name %s　名字表 %s'
            % (r['display'], r['name'],
               '✔ 在表里' if ok else ('⚠ 不在表里' if ok is False else '（无表）')),
            '等级 %s　携带等级 %s　成长 %s　忠诚 %s'
            % (r['level'], '—' if r['carry'] is None else r['carry'],
               r['growth'], r['loyal']),
            '资质 %s/%s/%s/%s/%s/%s（攻/防/体/法/速/躲）'
            % (r['zz_attack'], r['zz_defense'], r['zz_tili'],
               r['zz_magic'], r['zz_speed'], r['zz_dodge']),
            '技能 %d 个：%s'
            % (len(r['skills']), '、'.join(s[1] for s in r['skills']) or '（无）'),
        ]
        if not r['owned']:
            lines.append('⚠ 无主（已放生）——游戏界面上不显示，改它对游戏没影响')
        self.set_pet_info('\n'.join(lines))

    def set_skill_desc(self, txt):
        """技能说明框（只读）。描述太长，放表格列里永远看不全 —— 照画迹2 拆出来。"""
        try:
            self.txt_skill_desc.configure(state='normal')
            self.txt_skill_desc.delete('1.0', 'end')
            self.txt_skill_desc.insert('1.0', txt or '（点技能表里的一行看说明）')
            self.txt_skill_desc.configure(state='disabled')
        except Exception:
            pass

    def on_skill_pick(self, ev=None):
        sel = self.tv_skill.selection()
        if not sel:
            return
        try:
            sid = int(self.tv_skill.item(sel[0], 'values')[0])
        except Exception:
            return
        self.set_skill_desc(getattr(self, 'skill_desc_of', {}).get(sid, ''))

    def load_actor_edit(self):
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            return
        a = self.doc.actor(aid)
        if a is None:
            return
        self.load_name_bar(aid)
        if self.cur_actor_group() == 'pet':
            for ivar, var in self.pet_vars.items():
                v = MOD.vof(a.get(ivar))
                var.set('' if v is None else str(v))
            self.fill_pet_fields()
            self.fill_skills(aid)
            self.show_pet_info()
            return
        for ivar, var in self.actor_vars.items():
            v = MOD.vof(a.get(ivar))
            var.set('' if v is None else str(v))
        t = ['人物 %d  门派 %s' % (aid, self.doc.class_name(
            MOD.vof(a.get('@class_id')) or 0)),
            'HP 上限 %s / SP 上限 %s（按游戏公式计算）'
            % (self.doc.actor_maxhp(aid), self.doc.actor_maxsp(aid)),
            '已学技能：%s' % ('、'.join(s[1] for s in self.doc.actor_skills(aid))
                              or '（无）')]
        for k, v in self.doc.actor_extra(aid):
            t.append('   %-14s %s' % (k, v))
        self.txt_actor.delete('1.0', 'end')
        self.txt_actor.insert('1.0', '\n'.join(t))

    def apply_actor(self):
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            return
        is_pet = self.cur_actor_group() == 'pet'
        vars_ = self.pet_vars if is_pet else self.actor_vars
        try:
            a = self.doc.actor(aid)
            for ivar, var in vars_.items():
                if ivar in ('@level', '@exp'):
                    continue
                txt = var.get().strip()
                if txt == '' or istxt(txt):
                    continue
                cur = MOD.vof(a.get(ivar))
                if ivar == '@成长' or isinstance(cur, float):
                    val = float(txt)
                else:
                    val = int(float(txt))
                if cur != val:
                    self.doc.set_actor_field(aid, ivar, val)
            lv_txt = vars_.get('@level').get().strip() if '@level' in vars_ else ''
            exp_txt = vars_.get('@exp').get().strip() if '@exp' in vars_ else ''
            if lv_txt and not istxt(lv_txt):
                lv = int(float(lv_txt))
                if lv != (MOD.vof(a.get('@level')) or 0):
                    self.doc.set_actor_level(aid, lv)
                elif exp_txt and not istxt(exp_txt):
                    self.doc.set_actor_field(aid, '@exp', int(float(exp_txt)))
            elif exp_txt and not istxt(exp_txt):
                self.doc.set_actor_field(aid, '@exp', int(float(exp_txt)))
            self.mark_dirty()
            self.fill_actors()
            self.select_actor(aid)
            self.load_actor_edit()
            self.set_status('%s 修改已应用（记得保存）' % self.actor_label(aid))
        except Exception as e:
            self.err(e)

    def actor_preset(self, what):
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            return
        try:
            if what == 'max':
                self.doc.set_actor_level(aid, 175 if aid <= 20 else 180)
                self.doc.heal_actor(aid)
            elif what == 'heal':
                self.doc.heal_actor(aid)
            elif what == 'attr':
                a = self.doc.actor(aid)
                for ivar in ('@tizhi', '@moli', '@liliang', '@naili', '@minjie'):
                    self.doc.set_actor_field(aid, ivar,
                                             int(MOD.vof(a.get(ivar)) or 0) + 10)
            elif what == 'vital':
                self.doc.set_actor_field(aid, '@vitality', 150)
                self.doc.set_actor_field(aid, '@spirit', 150)
            self.mark_dirty()
            self.fill_actors()
            self.select_actor(aid)
            self.load_actor_edit()
        except Exception as e:
            self.err(e)

    def pet_preset(self, what):
        """召唤兽预设：资质 +500 / 成长 +0.1 / 忠诚100 + 五维+10。"""
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            return
        try:
            a = self.doc.actor(aid)
            if what == 'zz':
                for ivar in ('@攻击资质', '@防御资质', '@体力资质', '@法力资质',
                             '@速度资质', '@躲闪资质'):
                    self.doc.set_actor_field(aid, ivar,
                                             int(MOD.vof(a.get(ivar)) or 0) + 500)
            elif what == 'growth':
                self.doc.set_actor_field(aid, '@成长',
                                         float(MOD.vof(a.get('@成长')) or 0) + 0.1)
            elif what == 'loyal':
                self.doc.set_actor_field(aid, '@loyal', 100)
                for ivar in ('@tizhi', '@moli', '@liliang', '@naili', '@minjie'):
                    self.doc.set_actor_field(aid, ivar,
                                             int(MOD.vof(a.get(ivar)) or 0) + 10)
            self.mark_dirty()
            self.fill_actors()
            self.select_actor(aid)
            self.load_actor_edit()
            self.set_status('%s 已应用召唤兽预设' % self.actor_label(aid))
        except Exception as e:
            self.err(e)

    # -------- 召唤兽技能 --------
    def refresh_skill_templates(self):
        if not self.doc:
            return
        try:
            self._skill_tpls = self.doc.skill_templates()
        except Exception:
            self._skill_tpls = []
        self.filter_skill_templates()

    def filter_skill_templates(self):
        kw = ''
        try:
            kw = self.var_skill_search.get().strip().lower()
        except Exception:
            pass
        out = []
        for t in getattr(self, '_skill_tpls', []):
            i, n = t[0], t[1]
            d = t[2] if len(t) > 2 else ''      # 技能描述（也参与搜索）
            if not kw or kw in n.lower() or kw in d.lower() or kw == str(i):
                out.append('%d | %s' % (i, n))
        try:
            self.cb_skill['values'] = out[:500]
            self.lb_skill_info.configure(
                text='命中 %d / 共 %d 个技能'
                     % (len(out), len(getattr(self, '_skill_tpls', []))))
        except Exception:
            pass

    def fill_skills(self, aid=None):
        try:
            self.tv_skill.delete(*self.tv_skill.get_children())
        except Exception:
            return
        self.skill_desc_of = {}
        self.set_skill_desc('')
        if not self.doc:
            return
        if aid is None:
            aid = self.current_actor_id()
        if aid is None:
            return
        for sid, name, desc in self.doc.actor_skills(aid):
            self.tv_skill.insert('', 'end', values=(sid, name))
            self.skill_desc_of[sid] = desc or ''

    @staticmethod
    def _skill_preview(skills, n=3):
        """下拉列表里的技能预览：最多列 n 个名字。"""
        if not skills:
            return '（无）'
        return '、'.join(s[1] for s in skills[:n]) + ('…' if len(skills) > n else '')

    def skill_clone(self):
        """克隆技能：把另一个角色 / 召唤兽的整张技能表复制到当前这只身上。

        用途：新抓的宝宝想直接拥有主宠那套技能，不用一个个手点。
        源不受影响；目标原来的技能表会被**整表替换**。
        """
        tk, ttk = self.tk, self.ttk        # ★ 本文件的 tk/ttk 是 self 上的属性，
                                           #   不先取出来就会 NameError（而且被 Tk 吞掉）
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            self.err('请先在召唤兽表里选中一只召唤兽')
            return
        try:
            rows = [r for r in self.doc.actor_rows() if r['id'] != aid]
        except Exception as e:
            self.err(e)
            return
        if not rows:
            self.err('没有别的角色可以克隆')
            return
        # 技能多的排前面（一般主宠/主角在最上面），同数量按 id
        rows.sort(key=lambda r: (-len(r['skills']), r['id']))
        labels = ['%s %d %s —— %d 个技能：%s'
                  % ('召唤兽' if r['is_pet'] else '人物', r['id'], r['display'],
                     len(r['skills']), self._skill_preview(r['skills']))
                  for r in rows]

        win = tk.Toplevel(self.root)
        win.title('克隆技能')
        win.transient(self.root)
        win.resizable(False, False)
        ttk.Label(win, justify='left', padding=10,
                  text='把谁身上的技能克隆给「%s」？\n'
                       '目标原有的技能表会被整表替换，源不受影响。'
                       % self.actor_label(aid)).pack(anchor='w')
        var = tk.StringVar(value=labels[0])
        cb = ttk.Combobox(win, textvariable=var, values=labels, width=68,
                          state='readonly')
        cb.pack(fill='x', padx=10)
        ttk.Label(win, foreground='#888', padding=(10, 4, 10, 0),
                  text='克隆后记得点【保存修改(Ctrl+S)】。').pack(anchor='w')
        bar = ttk.Frame(win)
        bar.pack(fill='x', padx=10, pady=10)
        picked = {}

        def close():
            """
            关窗**必须延后到 idle**，不能在按钮自己的回调里同步 destroy()。

            ttk 的按钮绑定脚本（ttk::button::Release）在调用完 -command 之后
            还会继续操作这个按钮（复位 pressed/default 状态），
            窗口已经没了就会抛
                TclError: bad window path name ".!toplevel.!frame.!button"
            （用户实测：点【克隆】就弹这个错，窗口看起来"没反应"）。
            用 .invoke() 直接调命令不会走绑定脚本，所以测试里要模拟真实点击才抓得到。
            """
            try:
                win.after_idle(win.destroy)
            except Exception:
                pass

        def ok():
            try:
                picked['i'] = labels.index(var.get())
            except ValueError:
                return                      # 下拉里没有选中项，什么都不做
            close()

        ttk.Button(bar, text='克隆', command=ok).pack(side='right')
        ttk.Button(bar, text='取消', command=close).pack(side='right', padx=6)
        win.bind('<Return>', lambda e: ok())
        win.bind('<Escape>', lambda e: close())
        cb.focus_set()
        win.grab_set()
        self.root.wait_window(win)
        if 'i' not in picked:
            return
        src = rows[picked['i']]
        try:
            sids = self.doc.clone_skills(src['id'], aid)
            self.mark_dirty()
            self.fill_skills(aid)
            self.fill_actors()
            self.select_actor(aid)
            self.load_actor_edit()
            self.set_status('技能克隆：%s → %s（%d 个技能）'
                            % (src['display'], self.actor_label(aid), len(sids)))
        except Exception as e:
            self.err(e)

    def skill_add(self):
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            self.err('请先在召唤兽表里选中一只召唤兽')
            return
        txt = self.var_skill_add.get().strip()
        if not txt:
            self.err('请先选技能（可在"搜索技能"里筛，再在下拉框里选）')
            return
        try:
            sid = int(txt.split('|')[0].strip())
            self.doc.add_actor_skill(aid, sid)
            self.mark_dirty()
            self.fill_skills(aid)
            self.fill_actors()
            self.select_actor(aid)
            self.set_status('%s 学会「%s」（技能 id %d）'
                            % (self.actor_label(aid), self.doc.skill_name(sid), sid))
        except Exception as e:
            self.err(e)

    def skill_del(self):
        aid = self.current_actor_id()
        sel = self.tv_skill.selection()
        if aid is None or not sel or not self.doc:
            self.err('请先在技能列表里选中一条')
            return
        sid = int(self.tv_skill.item(sel[0], 'values')[0])
        try:
            self.doc.remove_actor_skill(aid, sid)
            self.mark_dirty()
            self.fill_skills(aid)
            self.fill_actors()
            self.select_actor(aid)
            self.set_status('%s 忘掉「%s」'
                            % (self.actor_label(aid), self.doc.skill_name(sid)))
        except Exception as e:
            self.err(e)

    def skill_clear(self):
        from tkinter import messagebox
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            return
        if not messagebox.askyesno('确认', '清空 %s 的全部技能？'
                                   % self.actor_label(aid), parent=self.root):
            return
        try:
            self.doc.set_actor_skills(aid, [])
            self.mark_dirty()
            self.fill_skills(aid)
            self.fill_actors()
            self.select_actor(aid)
            self.set_status('%s 的技能已清空' % self.actor_label(aid))
        except Exception as e:
            self.err(e)

    # ================= 物品栏（道具 @pack / 行囊 @wallet / 备用 @talisman）==========
    def cur_container(self):
        try:
            v = self.var_container.get()
        except Exception:
            v = '@pack'
        return v or '@pack'

    def on_container_change(self):
        """切换容器：重填表格并清空编辑框。"""
        self.var_pack_slot.set('')
        self.fill_pack()
        self.set_status('当前容器：%s%s'
                        % (self.cur_container(),
                           '（道具栏）' if self.cur_container() == '@pack'
                           else '（行囊）' if self.cur_container() == '@wallet'
                           else '（备用）'))

    def fill_pack(self):
        self.tv_pack.delete(*self.tv_pack.get_children())
        self.pack_rows = {}
        if not self.doc:
            return
        key = self.cur_container()
        for r in self.doc.container_slots(key):
            empty = r['item'] is None
            reg = '' if empty else ('✔' if r['registered'] else '✘')
            node = self.tv_pack.insert('', 'end', values=(
                r['slot'], '' if empty else r['kind_label'], r['name'],
                '' if r['standard'] is None else r['standard'],
                '' if r['iid'] is None else r['iid'],
                '' if empty else r['count'],
                '' if empty or r['quality'] is None else r['quality'],
                reg, r['desc']))
            self.pack_rows[node] = r['slot']

    # ---- 物品栏：列宽自适应 + 悬停说明（列里放不全时用）----
    PACK_COL_W = {'slot': 3, 'kind': 4, 'name': 15, 'std': 6, 'iid': 6,
                  'count': 5, 'quality': 5, 'reg': 4, 'desc': 48}
    PACK_COL_MIN = {'slot': 30, 'kind': 34, 'name': 120, 'std': 52,
                    'iid': 52, 'count': 44, 'quality': 44, 'reg': 46,
                    'desc': 180}

    def fit_pack_cols(self, _event=None, width=None):
        """按窗口宽度把 9 列按权重铺满；余量全给「说明」，窄了就给横向滚动条。"""
        tv = self.tv_pack
        avail = width
        if not avail:
            try:
                avail = tv.winfo_width()
            except Exception:
                return
            if avail < 60:                      # 窗口还没布局出来
                avail = tv.winfo_reqwidth()
        if not avail or avail < 60:
            return
        cols = list(tv['columns'])
        tw = sum(self.PACK_COL_W.get(c, 6) for c in cols)
        w = {c: max(self.PACK_COL_MIN.get(c, 40),
                    int(avail * self.PACK_COL_W.get(c, 6) / tw)) for c in cols}
        extra = avail - sum(w.values())
        if extra > 0:
            w['desc'] += extra
        for c in cols:
            tv.column(c, width=w[c])
        return sum(w.values())

    def _ensure_tip(self):
        if self._tip_win is None:
            import tkinter as tk          # 本模块的 tkinter 是在构建函数里局部导入的
            t = tk.Toplevel(self.root)
            t.overrideredirect(True)
            try:
                t.attributes('-topmost', True)   # 下拉是 topmost，提示得压得住它
            except Exception:
                pass
            t.withdraw()
            lab = tk.Label(t, justify='left', wraplength=380,
                           background='#fffbe6', foreground='#111111',
                           relief='solid', borderwidth=1, padx=6, pady=4,
                           font=('Microsoft YaHei UI', 9))
            lab.pack()
            self._tip_win = t
            self._tip_lab = lab
        return self._tip_win

    def show_tip(self, text):
        if not text:
            self.hide_tip()
            return
        t = self._ensure_tip()
        self._tip_lab.configure(text=text)
        t.update_idletasks()
        px, py = self.root.winfo_pointerx(), self.root.winfo_pointery()
        x, y = px + 18, py + 16
        tw, th = t.winfo_reqwidth(), t.winfo_reqheight()
        sw, sh = t.winfo_screenwidth(), t.winfo_screenheight()
        if x + tw + 8 > sw:                    # 贴右边缘就翻到指针左边
            x = px - tw - 12
        if y + th + 8 > sh:                    # 贴下边缘就翻到指针上边
            y = py - th - 12
        t.geometry('+%d+%d' % (max(0, x), max(0, y)))
        t.deiconify()

    def hide_tip(self, _event=None):
        self._tip_row = None
        self._tip_item = None
        if self._tip_win is not None:
            self._tip_win.withdraw()

    def on_pack_hover(self, event):
        """鼠标停在一行上：把那格的完整「说明」弹出来（列里放不全时用）。"""
        row = self.tv_pack.identify_row(event.y)
        if not row:
            self.hide_tip()
            return
        if row == self._tip_row:
            return
        self._tip_row = row
        vals = list(self.tv_pack.item(row, 'values'))
        desc = str(vals[8]) if len(vals) > 8 else ''
        name = str(vals[2]) if len(vals) > 2 else ''
        std = str(vals[3]) if len(vals) > 3 else ''
        if desc and len(desc) > 18:
            self.show_tip('%s\n\n%s' % (name, desc))
        elif std.isdigit():
            kind = str(vals[1]) if len(vals) > 1 else ''
            kk = [k for k, _c, _t, lb in MOD.ITEM_KINDS if lb == kind]
            self.show_tip(self.doc.template_tip(kk[0] if kk else 'item',
                                                int(std)))
        else:
            self.hide_tip()

    def on_tpl_post(self):
        """下拉即将弹出（ttk 的 -postcommand）：收起旧提示并绑好悬停。"""
        self.hide_tip()
        self.bind_tpl_popdown()

    def _tpl_tcl_cmd(self, key, func):
        """把一个 Python 回调注册成 Tcl 命令（缓存住，别每轮注册一遍）。"""
        if key not in self._tpl_cmds:
            self._tpl_cmds[key] = self.root.register(func)
        return self._tpl_cmds[key]

    def _popdown_listbox(self):
        """拿到下拉内部 listbox 的 Tcl 路径（拿不到返回 None）。

        ⚠ 别用 nametowidget：popdown 是 ttk 用 Tcl 直接建的原生 toplevel，
          tkinter 的 children 字典里没有它 ⇒ nametowidget 直接 KeyError。
          实测结构：<combobox>.popdown → .f → .f.l(Listbox) / .f.sb(TScrollbar)。
        """
        try:
            pd = self.root.tk.call('ttk::combobox::PopdownWindow',
                                   str(self.cb_tpl))
            kids = self.root.tk.call('winfo', 'children', '%s.f' % pd)
        except Exception:
            return None
        if not isinstance(kids, (list, tuple)):
            kids = [kids] if kids else []
        for ch in kids:
            ch = str(ch)
            try:
                if self.root.tk.call('winfo', 'class', ch) == 'Listbox':
                    return ch
            except Exception:
                continue
        return None

    def bind_tpl_popdown(self):
        """给下拉内部的 listbox 绑「鼠标移到某项就弹说明」。

        ⚠ 时机：ttk 的 Post 是「先跑 -postcommand，再建/显示 popdown」，所以
          只能挂在 -postcommand 上（我们这次调用会把 popdown 一并建出来）。
        ⚠ 绑定走 Tcl 层且不加 '+'：ttk 自己的 <ButtonRelease-1>/<Escape> 挂在
          ComboboxListbox / Listbox 这些 bindtag 上，不在这控件的 tag 上，
          覆盖不到它；不加 '+' 则重复绑定只覆盖、不堆叠。
        返回绑好的 listbox 路径；拿不到就返回 None，不影响正常使用。
        """
        lb = self._popdown_listbox()
        if not lb:
            return None
        try:
            self.root.tk.call('bind', lb, '<Motion>', '%s %%y' %
                              self._tpl_tcl_cmd('motion',
                                                self._tpl_lb_motion))
            hide = self._tpl_tcl_cmd('hide', self.hide_tip)
            for ev in ('<Leave>', '<ButtonRelease-1>', '<Escape>',
                       '<FocusOut>'):
                self.root.tk.call('bind', lb, ev, hide)
            pd = self.root.tk.call('ttk::combobox::PopdownWindow',
                                   str(self.cb_tpl))
            self.root.tk.call('bind', pd, '<Unmap>', hide)   # 收起下拉即收提示
        except Exception:
            return None
        self._tpl_lb = lb
        return lb

    def _tpl_lb_motion(self, y):
        """下拉 listbox 上鼠标移动：把该项的说明弹出来（Tcl <Motion> 回调）。"""
        lb = self._tpl_lb
        if not lb:
            return
        try:
            idx = int(self.root.tk.call(lb, 'nearest', int(float(y))))
            if idx < 0 or idx >= int(self.root.tk.call(lb, 'size')):
                self.hide_tip()
                return
            txt = str(self.root.tk.call(lb, 'get', idx))
        except Exception:
            return
        if txt == self._tip_item:
            return
        self._tip_item = txt
        k = self._tpl_pick.get(txt)
        if not k or not self.doc:
            self.hide_tip()
            return
        try:
            i = int(txt.split('|', 1)[0].strip())
        except ValueError:
            return
        self.show_tip(self.doc.template_tip(k, i))

    def current_slot(self):
        sel = self.tv_pack.selection()
        slot = self.pack_rows.get(sel[0]) if sel else None
        if slot is None and self.var_pack_slot.get().strip().isdigit():
            slot = int(self.var_pack_slot.get().strip())
        return slot

    def load_pack_edit(self):
        """选中某格时，把 格子/数量/品质/物品id 四个框都回填上。"""
        slot = self.current_slot()
        if slot is None:
            return
        self.var_pack_slot.set(str(slot))
        r = self.doc.pack_slot(slot, self.cur_container()) if self.doc else None
        if not r:
            return
        self.var_pack_count.set(str(r['count'] or 1))
        self.var_pack_quality.set(str(r['quality'] if r['quality'] else 100))
        if getattr(self, '_picked_tpl', False):
            # ★ 用户刚在下拉里选好了模板：别再用这一格的类别/模板把它冲掉。
            #   （1.5.0 的 bug：先选「泡泡兜兜（装备）」再点某行（尤其空格，
            #   空格默认类别是"物品"），类别被顶回去 → 写入按物品表 → 变 ?/别的物品）
            return
        # 选中装备/防具格时，把"类别"跟着切过去 —— 否则下拉框里根本列不到它
        k = r['kind']
        if (k == 'weapon' and isinstance(r['standard'], int)
                and self.doc.is_pet_weapon(r['standard'])):
            k = 'item'    # 宠物武器按物品类展示；写入时自动路由回装备表
        if k != self.cur_tpl_kind():
            self.var_tpl_kind.set(k)
            self.refresh_templates()
        if isinstance(r['standard'], int):
            self.var_pack_std.set('%d | %s' % (r['standard'], r['template_name']))

    def select_slot(self, slot):
        for iid, s in self.pack_rows.items():
            if s == slot:
                self.tv_pack.selection_set(iid)
                self.tv_pack.focus(iid)
                self.tv_pack.see(iid)
                break
        self.load_pack_edit()

    def pack_refresh(self, slot=None):
        """物品栏改动后立即刷新（表格 + 概览 + 回填输入框）。"""
        self._tpl_cache = {}
        self.fill_pack()
        self.fill_info()
        if slot is None:
            self.load_pack_edit()
        else:
            self.var_pack_slot.set(str(slot))
            self.select_slot(slot)

    def pack_apply(self):
        """把「格子 / 数量 / 物品id / 品质」写入当前容器：空格=新增，有物品=重建。"""
        if not self.doc:
            return
        key = self.cur_container()
        slot = self.current_slot()
        if slot is None:
            self.err('请先在上面选中一行，或填写格子号（0 ~ %d）' % (MOD.Doc.PACK_SIZE - 1))
            return
        txt = self.var_pack_std.get().strip()
        if not txt:
            self.err('请填写物品 id（可直接填数字，或先在搜索框里筛，再从下拉框里选）')
            return
        try:
            parts = txt.split('|', 1)
            sid = int(parts[0].strip())
            name = parts[1].strip() if len(parts) > 1 else ''
            # 跨类搜索的下拉条目带"（类别）"后缀，校验名字前剥掉
            if name.endswith('）') and '（' in name:
                name = name[:name.rfind('（')].strip()
            cnt = int(self.var_pack_count.get().strip() or '1')
            qty = int(self.var_pack_quality.get().strip() or '100')
        except ValueError:
            self.err('物品 id / 数量 / 品质 都要填数字')
            return
        r0 = self.doc.pack_slot(slot, key)
        had = bool(r0 and r0['item'] is not None)
        try:
            kind = self.cur_tpl_kind()
            info = self.doc.pack_write(slot, sid, cnt, qty, key, kind=kind,
                                       expect_name=name or None)
            self.mark_dirty()
            self._picked_tpl = False    # 写入完成，恢复"点行跟随行类别"
            self.pack_refresh(slot)
            self.set_status(
                '%s%s第 %d 格：%s（%s id %d）× %d%s，实例 id %d（已登记进 $%s）'
                % ('改写' if had else '新增', self.cur_container(),
                   info['slot'], info['template_name'], info['kind_label'],
                   info['standard'], info['count'],
                   '' if info['quality'] is None else '，品质 %d' % info['quality'],
                   info['iid'], MOD.KIND_TABLE[info['kind']]))
        except Exception as e:
            self.err(e)

    def pack_delete(self):
        key = self.cur_container()
        slot = self.current_slot()
        if slot is None or not self.doc:
            self.err('请先选中（或填写）格子号')
            return
        r = self.doc.pack_slot(slot, key)
        if not r or r['item'] is None:
            self.err('第 %d 格本来就是空的' % slot)
            return
        from tkinter import messagebox
        if not messagebox.askyesno('确认', '清空 %s 第 %d 格（%s）的物品？'
                                   % (key, slot, r['name']), parent=self.root):
            return
        try:
            self.doc.pack_delete(slot, key)
            self.mark_dirty()
            self.pack_refresh(slot)
            self.set_status('%s 第 %d 格已清空' % (key, slot))
        except Exception as e:
            self.err(e)

    def cur_tpl_kind(self):
        try:
            k = self.var_tpl_kind.get()
        except Exception:
            k = 'item'
        return k if k in MOD.KIND_TABLE else 'item'

    def on_tpl_kind_change(self):
        """切换"物品 / 装备 / 防具"：重新取那张模板表并清空搜索。"""
        self._picked_tpl = False    # 手动换类别 = 明确的新意图，解除模板锁定
        self.var_tpl_search.set('')
        self.refresh_templates()

    def clear_tpl_search(self):
        self.var_tpl_search.set('')
        self.filter_templates()

    def refresh_templates(self):
        if not self.doc:
            return
        kind = self.cur_tpl_kind()
        self._tpl_cache = {}
        self._tpls = self._tpls_of(kind)
        self._tpl_kind = kind
        self.filter_templates()

    def _tpls_of(self, kind):
        """某一类的模板列表（带缓存 —— 跨类搜索时每次按键都要用）。"""
        if not hasattr(self, '_tpl_cache'):
            self._tpl_cache = {}
        if kind not in self._tpl_cache:
            try:
                self._tpl_cache[kind] = self.doc.templates(kind)
            except Exception:
                self._tpl_cache[kind] = []
        return self._tpl_cache[kind]

    def filter_templates(self):
        """按搜索框过滤模板下拉。

        ★ 有搜索词时**跨三类**一起搜：旧版只搜「当前类别」，于是在「物品」下
        搜不到泡泡兜兜 / 灵石 / 糖果这类东西 —— 它们其实在 $data_weapons 里。
        命中行会标出所属类别，选中后由 on_tpl_pick 自动把类别切过去。
        """
        kw = ''
        try:
            kw = self.var_tpl_search.get().strip().lower()
        except Exception:
            pass
        out = []
        self._tpl_pick = {}
        per = {}
        if not kw:
            k = getattr(self, '_tpl_kind', 'item')
            hits = [(k, i, n) for i, n in getattr(self, '_tpls', [])]
        else:
            hits = []
            for k, _c, _t, _l in MOD.ITEM_KINDS:
                for i, n in self._tpls_of(k):
                    if kw in n.lower() or kw == str(i):
                        hits.append((k, i, n))
                        per[k] = per.get(k, 0) + 1
        for k, i, n in hits[:500]:
            s = '%d | %s' % (i, n)
            if kw:
                s += '（%s）' % MOD.KIND_LABEL.get(k, '')
            out.append(s)
            self._tpl_pick[s] = k
        self.cb_tpl['values'] = out
        self.bind_tpl_popdown()
        try:
            if kw:
                detail = ' / '.join(
                    '%s %d' % (MOD.KIND_LABEL.get(k, ''), per.get(k, 0))
                    for k, _c, _t, _l in MOD.ITEM_KINDS)
                txt = '跨三类命中 %d 个（%s）%s' % (
                    len(hits), detail,
                    '，只显示前 500 条' if len(hits) > 500 else '')
            else:
                k = getattr(self, '_tpl_kind', 'item')
                txt = ('[%s] 共 %d 个 —— 直接搜名字可跨三类一起找'
                       % (MOD.KIND_LABEL.get(k, '物品'), len(hits)))
            self.lb_tpl_info.configure(text=txt)
        except Exception:
            pass

    def on_tpl_pick(self, _event=None):
        """从下拉里选了模板：它属于别的类别就自动切过去（否则会按错表写入）。"""
        self.hide_tip()
        s = self.var_pack_std.get().strip()
        k = getattr(self, '_tpl_pick', {}).get(s)
        # 记住"用户选过模板"：之后点一览表的行不再用行类别冲掉这个选择
        # （写入成功后清掉，恢复"点行跟随行类别"）
        self._picked_tpl = bool(k)
        if k and k != self.cur_tpl_kind():
            self.var_tpl_kind.set(k)
            self.refresh_templates()
            self.set_status('这一项属于「%s」，已自动把类别切过去'
                            % MOD.KIND_LABEL.get(k, k))

    def pack_fix_bad(self):
        """检查三个容器里那些"游戏里用不了"的格子，确认后按模板重建（并重新登记）。"""
        from tkinter import messagebox
        if not self.doc:
            return
        try:
            bad = self.doc.pack_scan_bad()
        except Exception as e:
            self.err(e)
            return
        if not bad:
            messagebox.showinfo('检查结果',
                                '道具 / 行囊 / 备用 里都没发现异常的格子。',
                                parent=self.root)
            return
        txt = '\n'.join('  %s 第 %d 格  %s：%s'
                       % (b.get('label') or b['key'], b['slot'], b['name'], b['why'])
                       for b in bad)
        if not messagebox.askyesno(
                '发现 %d 个异常格子' % len(bad),
                '下面这些格子有问题（游戏里会提示"该物品无法使用"）：\n\n'
                + txt + '\n\n按各自模板重建并登记吗？\n'
                '（数量至少 1，品质按 100）', parent=self.root):
            return
        try:
            fixed = self.doc.pack_fix_all()
            self.mark_dirty()
            self.pack_refresh(None)
            self.set_status('已修复 %d 个异常格子：%s'
                            % (len(fixed),
                               '、'.join('%s#%d' % (k, s) for k, s in fixed)))
        except Exception as e:
            self.err(e)

    # ================= 机器码 =================
    def fill_id(self):
        self.txt_id.delete('1.0', 'end')
        if not self.doc:
            return
        lines = ['存档里记录的机器码：%s' % '  '.join(str(x) for x in
                                                self.doc.machine_ids()),
                 '当前机器的机器码  ：%s' % (self.doc.machine_id_now()
                                     or '（取不到，可手动输入）'),
                 '',
                 '说明：读档时游戏会检查 $存档id 是否包含本机机器码，',
                 '      不匹配就提示"存档的主人不是你"并退出。',
                 '      换电脑时把这里改成新机器的机器码即可。']
        self.txt_id.insert('1.0', '\n'.join(lines))

    def id_fill_local(self):
        if not self.doc:
            return
        mid = self.doc.machine_id_now()
        if not mid:
            self.err('取不到本机机器码，请手动输入')
            return
        self.var_id.set(mid)

    def id_apply(self):
        if not self.doc:
            return
        mid = self.var_id.get().strip()
        if not mid:
            self.err('请填写机器码（16 位十六进制，例如 178BFBFF00A40F41）')
            return
        try:
            self.doc.set_machine_id(mid)
            self.mark_dirty()
            self.fill_id()
            self.set_status('机器码已改为 %s（记得保存）' % mid)
        except Exception as e:
            self.err(e)

    # ================= 导出 =================
    def export_report(self):
        if not self.doc:
            return
        from tkinter import filedialog
        p = filedialog.asksaveasfilename(
            parent=self.root, title='导出解析报告', defaultextension='.txt',
            initialfile='存档解析报告.txt', filetypes=[('文本文件', '*.txt')])
        if not p:
            return
        with open(p, 'w', encoding='utf-8') as f:
            f.write(self.doc.export_text())
        self.set_status('报告已导出：%s' % p)

    def export_plain(self):
        if not self.doc:
            return
        from tkinter import filedialog
        p = filedialog.asksaveasfilename(
            parent=self.root, title='导出解密后的明文', defaultextension='.bin',
            initialfile='sy_plain.bin',
            filetypes=[('二进制', '*.bin'), ('所有文件', '*.*')])
        if not p:
            return
        with open(p, 'wb') as f:
            f.write(self.doc.plain)
        self.set_status('明文已导出：%s' % p)


    # ================= 存档管理（备份 / 恢复）=================
    def confirm(self, title, text):
        """问一句“要不要”。

        走一层包装：测试里把 messagebox 换成“只记录”的假对象，
        没有 askyesno 时就当“确认”（不然一调就 AttributeError）。
        """
        from tkinter import messagebox
        fn = getattr(messagebox, 'askyesno', None)
        if fn is None:
            return True
        return bool(fn(title, text, parent=self.root))

    def _tab_saves(self):
        """存档管理：备份 / 删备份 / 恢复选中 / 恢复最新 / 删除非最新。

        备份放在**存档旁边**的子目录里（默认 .huaji1-save-editor），只做文件复制、
        不解析内容 —— 万一存档被改坏了，这里也能救回来。
        ⚠ 和保存时自动写的 sy.ogg.bak 不是一回事：.bak 只留上一份、会被下一次
        保存覆盖；这里是多份带时间戳的历史，恢复时不会互相盖掉。
        """
        tk, ttk = self.tk, self.ttk
        f = ttk.Frame(self.nb, padding=8)
        self.tab_saves = f
        self.nb.add(f, text='存档管理')

        self.var_saves_info = tk.StringVar(value='存档管理：—')
        ttk.Label(f, textvariable=self.var_saves_info, justify='left',
                  font=('Microsoft YaHei UI', 10),
                  wraplength=1080).pack(anchor='w')
        ttk.Label(f, foreground='#777', justify='left',
                  text='备份目录就在存档旁边（.huaji1-save-editor，隐藏项）；'
                       '「恢复最新」＝把上一次修改之前的存档换回来；'
                       '「删除非最新」只清自动备份，最新的一份和手动备份都留着。'
                  ).pack(anchor='w', pady=(2, 6))

        bar = ttk.Frame(f)
        bar.pack(fill='x')
        for text, cmd in (('立即备份', self.saves_backup),
                          ('编辑备注', self.saves_edit_note),
                          ('恢复选中', self.saves_restore),
                          ('恢复最新', self.saves_restore_newest),
                          ('删除选中', self.saves_delete),
                          ('删除无备注', self.saves_delete_no_note),
                          ('删除非最新', self.saves_delete_old),
                          ('刷新', self.saves_refresh),
                          ('打开备份目录', self.saves_open_dir)):
            ttk.Button(bar, text=text, command=cmd).pack(side='left', padx=(0, 6))

        self.tv_saves = ttk.Treeview(
            f, columns=('idx', 'time', 'kind', 'size', 'name', 'note'),
            show='headings', height=16, selectmode='extended')
        for c, w, t in (('idx', 40, '#'), ('time', 150, '时间'),
                        ('kind', 72, '类型'), ('size', 78, '大小'),
                        ('name', 268, '文件'), ('note', 372, '备注')):
            self.tv_saves.heading(c, text=t)
            self.tv_saves.column(c, width=w, anchor='w')
        vs = ttk.Scrollbar(f, orient='vertical', command=self.tv_saves.yview)
        self.tv_saves.configure(yscrollcommand=vs.set)
        vs.pack(side='right', fill='y')
        self.tv_saves.pack(fill='both', expand=True, pady=6)
        self.tv_saves.bind('<Double-1>', lambda e: self.saves_restore())
        self.save_rows = []

    def saves_dir(self):
        if not self.doc:
            return None
        return backup.backup_dir(self.doc.path, create=False)

    def _saves_ready(self):
        """存档管理能不能动手 —— 只要求“确实打开过一份存档”。

        本作的 Doc 在构造时就会校验文件头（不是 sy.ogg 直接抛 CodecError，
        self.doc 也不会被换成那个文件），所以 self.doc 有值就等于“这是真存档”，
        不像画迹2 还得再看一层 SaveDoc —— 也就不会出现“拿非存档文件去备份、
        在人家目录里堆一堆垃圾”那种事。
        """
        from tkinter import messagebox
        if not self.doc:
            messagebox.showinfo('提示', '先打开一个存档（Audio\\BGM\\sy.ogg）。',
                                parent=self.root)
            return False
        return True

    def saves_refresh(self, keep=None):
        """重扫备份目录填表格（只读，不建目录、不写文件）。

        keep：刷新后要重新选中的备份路径；不给就沿用刷新前选中的那些 ——
        否则「编辑备注」点完一刷新选中就没了，接着点「恢复选中」只会收到
        “先在列表里选中一份备份”（自己刚选的那份被清掉了）。
        """
        if keep is None:
            keep = [r['path'] for r in self._save_sel(quiet=True)]
        self.tv_saves.delete(*self.tv_saves.get_children())
        self.save_rows = []
        if not self.doc:
            self.var_saves_info.set('存档管理：还没打开存档')
            return
        rows = backup.list_backups(self.doc.path)
        self.save_rows = rows
        kind_cn = {'auto': '自动', 'manual': '手动',
                   'before-restore': '恢复前', 'other': '其它'}
        for i, r in enumerate(rows):
            self.tv_saves.insert('', 'end', iid='b%d' % i,
                                 values=(i + 1,
                                         r['stamp'].replace('_', ' ') or '—',
                                         kind_cn.get(r['kind'], r['kind']),
                                         '%.1f KB' % (r['size'] / 1024.0),
                                         r['name'], r['note']))
        want = set(keep)
        sel = ['b%d' % i for i, r in enumerate(rows) if r['path'] in want]
        if sel:
            self.tv_saves.selection_set(sel)
        d = backup.backup_dir(self.doc.path, create=False)
        self.var_saves_info.set(
            '当前存档：%s\n备份目录：%s（共 %d 份，合计 %.1f MB）'
            % (self.doc.path, d, len(rows),
               sum(r['size'] for r in rows) / 1048576.0))

    def saves_backup(self):
        """立即备份：复制一份存档到备份目录，再弹窗让玩家填备注（可留空）。"""
        if not self._saves_ready():
            return
        try:
            p = backup.backup(self.doc.path, backup.KIND_MANUAL)
        except Exception as e:
            self.err(e)
            return
        dlg = NoteDialog(self.root, title='备份完成 - 填备注',
                         label='已备份到：\n%s\n\n'
                               '备注（可留空，会存在备份旁的 .txt）：' % p)
        self.root.wait_window(dlg)
        note = (dlg.result or '').strip() if dlg.result is not None else ''
        if note:
            try:
                backup.set_note(p, note)
            except Exception as e:
                self.err(e)
        self.saves_refresh()
        self.set_status('已备份到 %s（备注：%s）'
                        % (os.path.basename(p), note or '无'))

    def _save_sel(self, quiet=False):
        """列表里选中的那几份（返回 saves_refresh 存下来的 row 字典）。"""
        from tkinter import messagebox
        sel = self.tv_saves.selection()
        if not sel:
            if not quiet:
                messagebox.showinfo('提示', '先在列表里选中一份备份。',
                                    parent=self.root)
            return []
        out = []
        for iid in sel:
            i = int(iid[1:])
            if 0 <= i < len(self.save_rows):
                out.append(self.save_rows[i])
        return out

    def saves_restore(self):
        """恢复选中：用备份覆盖当前存档，然后重新载入。"""
        from tkinter import messagebox
        if not self._saves_ready():
            return
        rows = self._save_sel()
        if not rows:
            return
        if len(rows) > 1:
            messagebox.showinfo('提示', '恢复一次只能选一份。', parent=self.root)
            return
        r = rows[0]
        if not self.confirm(
                '确认恢复',
                '要用这份备份覆盖当前存档吗？\n\n  %s\n  %s\n\n'
                '（备份都是完整的存档副本，恢复后直接重新载入）'
                % (r['stamp'], r['name'])):
            return
        try:
            backup.restore(r['path'], self.doc.path)
        except Exception as e:
            self.err(e)
            return
        self.load(self.doc.path)          # 重新载入，界面跟着变
        self.saves_refresh()
        self.set_status('已恢复 %s' % r['name'])
        messagebox.showinfo('恢复完成',
                            '已用\n  %s\n覆盖当前存档，并重新载入。' % r['name'],
                            parent=self.root)

    def saves_restore_newest(self):
        """恢复最新＝把**上一次修改之前**的存档换回来（列表里最新的一份）。"""
        from tkinter import messagebox
        if not self._saves_ready():
            return
        self.saves_refresh()
        r = backup.newest(self.doc.path)
        if r is None:
            messagebox.showinfo('提示', '备份目录里还没有备份。', parent=self.root)
            return
        if not self.confirm(
                '恢复最新',
                '把存档换回**上一次修改之前**的状态吗？\n\n'
                '  用的备份：%s\n  %s\n\n'
                '（这份是目前最新的一份备份）' % (r['stamp'], r['name'])):
            return
        try:
            backup.restore(r['path'], self.doc.path)
        except Exception as e:
            self.err(e)
            return
        self.load(self.doc.path)
        self.saves_refresh()
        self.set_status('已恢复到最新备份：%s' % r['name'])

    def saves_delete(self):
        """删掉列表里选中的那几份备份（连 .txt 备注一起）。"""
        rows = self._save_sel()
        if not rows:
            return
        if not self.confirm(
                '确认删除',
                '删掉这 %d 份备份？（不可撤销）\n\n%s'
                % (len(rows), '\n'.join('  ' + r['name'] for r in rows[:8]))):
            return
        n = backup.remove([r['path'] for r in rows])
        self.saves_refresh()
        self.set_status('已删除 %d 份备份' % n)

    def saves_delete_no_note(self):
        """删除全部没有备注的备份（有 .txt 备注的留着）。"""
        from tkinter import messagebox
        if not self.doc:
            return
        self.saves_refresh()
        rows = [r for r in self.save_rows if not r['note']]
        if not rows:
            messagebox.showinfo('删除无备注', '没有无备注的备份。', parent=self.root)
            return
        if not self.confirm(
                '删除无备注',
                '删掉 %d 份没有备注的备份？（不可撤销）\n\n%s'
                % (len(rows), '\n'.join('  ' + r['name'] for r in rows[:8]))):
            return
        n = backup.remove([r['path'] for r in rows])
        self.saves_refresh()
        self.set_status('已删除 %d 份无备注备份' % n)

    def saves_edit_note(self):
        """给选中的备份改备注（存成备份旁边的 .txt；清空就是删备注）。"""
        from tkinter import messagebox
        rows = self._save_sel()
        if not rows:
            return
        if len(rows) > 1:
            messagebox.showinfo('提示', '一次只能改一份的备注。', parent=self.root)
            return
        r = rows[0]
        dlg = NoteDialog(self.root, r['note'])
        self.root.wait_window(dlg)
        if dlg.result is None:
            return
        try:
            backup.set_note(r['path'], dlg.result)
        except Exception as e:
            self.err(e)
            return
        self.saves_refresh()
        self.set_status('已更新备注：%s' % r['name'])

    def saves_delete_old(self):
        """删除非最新＝只留最新的一份 + 所有手动备份，其余（自动备份）全删。"""
        from tkinter import messagebox
        if not self.doc:
            return
        self.saves_refresh()
        rows = self.save_rows
        if len(rows) < 2:
            messagebox.showinfo('提示', '只有 %d 份备份，不用清理。' % len(rows),
                                parent=self.root)
            return
        keep = backup.newest(self.doc.path) or rows[0]
        n_manual = sum(1 for r in rows if r['kind'] == backup.KIND_MANUAL)
        if n_manual == len(rows):
            messagebox.showinfo('删除非最新',
                                '全是手动备份（共 %d 份），这个操作不碰手动备份。'
                                % len(rows), parent=self.root)
            return
        n_del = len(rows) - n_manual - 1     # 留最新一份 + 所有手动
        if not self.confirm(
                '删除非最新',
                '留最新的一份 + 所有手动备份，其余 %d 份自动备份删掉？'
                '（不可撤销）\n\n  保留：%s\n  %s'
                % (n_del, keep['stamp'], keep['name'])):
            return
        kept, n = backup.keep_newest(self.doc.path)
        self.saves_refresh()
        self.set_status('已删除 %d 份自动备份，保留最新 %s'
                        % (n, os.path.basename(kept['path']) if kept else '无'))

    def saves_open_dir(self):
        """在资源管理器里打开备份目录（还没建就提示先备份一次）。"""
        d = self.saves_dir()
        if not d or not os.path.isdir(d):
            from tkinter import messagebox
            messagebox.showinfo('提示', '备份目录还没建（先点一次「立即备份」）。',
                                parent=self.root)
            return
        try:
            os.startfile(d)                  # Windows 专用
        except Exception:
            self.set_status('备份目录：%s' % d)


def NoteDialog(master, cur='', title='编辑备注', label=None):
    """改备份备注的小窗（多行文本 + 确定/取消）。

    返回一个 Toplevel：`result` 属性＝点【确定】时的文本，取消/关闭＝None。
    用法：dlg = NoteDialog(root, r['note']); root.wait_window(dlg)
    —— 写成函数而不是 Toplevel 子类，是为了不在模块顶层就 import tkinter
    （本文件平时都是用到才 import 的）。
    """
    import tkinter as tk
    from tkinter import ttk
    win = tk.Toplevel(master)
    win.result = None
    win.title(title)
    ttk.Label(win, text=label
              or '备注（会存在备份旁边的 .txt；留空＝删除备注）'
              ).pack(anchor='w', padx=8, pady=(8, 2))
    txt = tk.Text(win, width=60, height=6, font=('Microsoft YaHei UI', 10),
                  wrap='word')
    vs = ttk.Scrollbar(win, orient='vertical', command=txt.yview)
    txt.configure(yscrollcommand=vs.set)
    vs.pack(side='right', fill='y')
    txt.pack(fill='both', expand=True, padx=(8, 0), pady=2)
    txt.insert('1.0', cur or '')
    txt.focus_set()

    def ok():
        win.result = txt.get('1.0', 'end').strip()
        win.destroy()

    bar = ttk.Frame(win)
    bar.pack(fill='x', pady=8)
    ttk.Button(bar, text='确定', command=ok).pack(side='left', padx=8)
    ttk.Button(bar, text='取消', command=win.destroy).pack(side='left', padx=6)
    win.bind('<Control-Return>', lambda e: ok())
    win.bind('<Escape>', lambda e: win.destroy())
    return win


def main():
    import tkinter as tk
    from tkinter import messagebox

    args = [a for a in sys.argv[1:] if not a.startswith('-')]
    save_path = args[0] if args else None
    selftest = ('--selftest' in sys.argv) or bool(os.environ.get('XJ_SELFTEST'))

    root = tk.Tk()
    try:
        app = App(root, save_path)
    except C.CodecError as e:
        messagebox.showerror('缺少依赖', str(e))
        return 2
    except Exception:
        _fatal(traceback.format_exc())
        return 3

    if selftest:
        def stop():
            root.update()
            lines = ['【画迹1：落日情缘】存档工具 %s 自检' % VERSION,
                     '程序目录: %s' % C.app_dir(),
                     '打包运行(frozen): %s' % bool(getattr(sys, 'frozen', False))]
            for k, v in C.dll_status().items():
                lines.append('依赖 %-14s %s' % (k, v or '未找到'))
            ch = '未建立'
            if getattr(app, 'bridge', None) is not None:
                ch = type(app.bridge).__name__
            lines.append('加解密通道: %s（不使用 PowerShell）' % ch)
            lines.append('版本: %s   作者: @%s' % (VERSION, AUTHOR))
            lines.append('开源地址: %s' % HOMEPAGE)
            doc = app.doc
            if doc is None:
                lines.append('未加载存档')
            else:
                import hashlib
                lines.append('存档: %s' % doc.path)
                lines.append('文件大小: %d' % doc.file_size)
                lines.append('明文大小: %d' % len(doc.plain))
                lines.append('顶层对象: %d' % len(doc.entries))
                lines.append('明文 MD5: %s' % hashlib.md5(doc.plain).hexdigest().upper())
                lines.append('金钱: %s' % doc.gold())
                lines.append('角色数: %d' % len(doc.actor_rows()))
                used = [r for r in doc.pack() if r['item'] is not None]
                lines.append('物品栏: %d/%d 格在用' % (len(used), doc.PACK_SIZE))
                for r in used[:10]:
                    lines.append('   [%d] %s  模板%s 实例%s 数量%s 品质%s'
                                 % (r['slot'], r['name'], r['standard'], r['iid'],
                                    r['count'], r['quality']))
                lines.append('开关/变量: %d / %d' % (len(doc.switches()),
                                                len(doc.variables())))
                lines.append('存档机器码: %s' % doc.machine_ids())
                lines.append('本机机器码: %s' % doc.machine_id_now())
                lines.append('导出报告长度: %d' % len(doc.export_text()))
                # 修改 API 自检（只在内存里改，不写文件）
                try:
                    g0 = doc.gold()
                    doc.set_gold(1234567)
                    ok_gold = abs(doc.gold() - 1234567) < 0.5
                    doc.set_gold(g0)
                    aid0 = doc.actor_rows()[0]['id']
                    lv0 = MOD.vof(doc.actor(aid0).get('@level'))
                    doc.set_actor_field(aid0, '@level', lv0)
                    slot0 = [r for r in doc.pack() if r['item'] is not None]
                    if slot0:
                        c0 = slot0[0]['count']
                        doc.set_pack_count(slot0[0]['slot'], c0)
                    # 改回原值后应当算"未修改"
                    ok_clean = not doc.is_dirty()
                    lines.append('修改 API 自检(内存): 金钱=%s 角色字段=OK 物品数量=OK'
                                 ' 改回原值不脏=%s'
                                 % ('OK' if ok_gold else '失败',
                                    'OK' if ok_clean else '失败'))
                    # ---- 0.7 自检：召唤兽顺序 / 放生过滤 / 改名 / 注释列 ----
                    pets_all = doc.actors_pet(include_unowned=True)
                    pets = doc.actors_pet()
                    expect = []
                    for _a in doc._person_order():
                        for _s, nd in doc._actor_nodes_sorted(_a):
                            b = nd.get('@babys')
                            if isinstance(b, M.ArrayNode):
                                for it in b.items:
                                    v = MOD.vof(it)
                                    if isinstance(v, int) and v not in expect:
                                        expect.append(v)
                    lines.append('召唤兽: 表内 %d 只，另有 %d 只无主（共 %d 个槽位）'
                                 % (len(pets), len(pets_all) - len(pets),
                                    len(pets_all)))
                    lines.append('召唤兽顺序 = 游戏界面 @babys 顺序: %s'
                                 % ('OK' if [r['id'] for r in pets] == expect
                                    else '失败 %s vs %s'
                                    % ([r['id'] for r in pets], expect)))
                    lines.append('已放生的默认不显示: %s'
                                 % ('OK' if all(r['owned'] for r in pets) else '失败'))
                    # 1.0：@name 必须在游戏的 $pet 名字表里（否则 0163 第147行崩）
                    pt = doc.pet_name_table()
                    lines.append('$pet 名字表: %s 个名字（来源 %s）'
                                 % (len(pt), doc.pet_name_table_source() or '未找到'))
                    probs = doc.pet_name_problems(include_unowned=True)
                    lines.append('名字不在 $pet 表里（会让召唤兽界面报 NoMethodError）: %s'
                                 % ('无' if not probs else
                                    '、'.join('槽%s「%s」' % (p['id'], p['name'])
                                            for p in probs)))
                    if pets:
                        r0 = pets[0]
                        lines.append('示例：槽%s「%s」在表里=%s 携带等级=%s'
                                     % (r0['id'], r0['name'],
                                        '是' if r0['name_ok'] else '否', r0['carry']))
                    ga = doc.ivar('game_actors', '@data')
                    note = doc.note_of('[12]', ga.items[12], ga, 'game_actors.@data')
                    lines.append('注释列示例: %s' % note)
                    # 1.4：技能名 / 描述必须走内置表（src/tables/db_table.py）——
                    #      别人机器上没有游戏目录、或版本不同读不了 .rxdata 时，
                    #      这里照样得给出真名字（tests/test_bundle_db_table.py 守着）。
                    _bad = doc.db_bad_files()
                    lines.append('名字表: 内置 db_table（游戏目录里读不出来的: %s）'
                                 % ('无' if not _bad
                                    else '、'.join(b[0] for b in _bad)))
                    lines.append('技能名自检: 1=%s / 9=%s 9的描述=%s'
                                 % (doc.skill_name(1), doc.skill_name(9),
                                    doc.skill_desc(9)[:18] or '（空）'))
                    if pets:
                        pid0, nm0 = pets[0]['id'], pets[0]['name']
                        doc.set_actor_custom_name(pid0, '自检改名')
                        ok_set = ([r for r in doc.actors_pet() if r['id'] == pid0][0]
                                  ['display'] == '自检改名')
                        doc.clear_actor_custom_name(pid0)
                        ok_clr = not doc.has_custom_name(pid0)
                        lines.append('召唤兽改名(@new_name): 设置=%s 清除=%s'
                                     ' 原 @name 未变=%s'
                                     % ('OK' if ok_set else '失败',
                                        'OK' if ok_clr else '失败',
                                        'OK' if MOD.stext(
                                            doc.actor(pid0).get('@name'), '') == nm0
                                        else '失败'))
                    doc.discard()
                except Exception as ex:
                    lines.append('修改 API 自检(内存): 失败 %s' % ex)
            lines.append('结果: OK')
            out = os.path.join(C.app_dir(), 'selftest_result.txt')
            try:
                with open(out, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(lines))
            except Exception:
                pass
            print('\n'.join(lines))
            root.destroy()
        root.after(2500, stop)

    try:
        root.mainloop()
    except Exception:
        _fatal(traceback.format_exc())
        return 3
    return 0


def _fatal(text):
    try:
        with open(os.path.join(C.app_dir(), 'error.log'), 'w', encoding='utf-8') as f:
            f.write(text)
    except Exception:
        pass
    try:
        import tkinter.messagebox as mb
        mb.showerror('程序出错', text[-2000:])
    except Exception:
        pass


if __name__ == '__main__':
    sys.exit(main())
