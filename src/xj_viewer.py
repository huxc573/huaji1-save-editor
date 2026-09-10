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

启动：双击 exe；也可以 python xj_viewer.py [存档路径] [--selftest]
"""
import os
import sys

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

import xj_codec as C
import xj_edit as E
import xj_marshal as M
import xj_model as MOD

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

  ★ 改名：
    游戏显示名 = @new_name 存在 ? @new_name : @name（0040 Game_Battler#custom_name）。
    玩家在游戏里花 30 活力改名，写的就是 @new_name。
    【设为显示名】写 @new_name；【改基础名】写 @name；【清除显示名】把
    @new_name 删掉恢复本名。

  ★★ 召唤兽的 @name 不能乱改（会把游戏搞崩）：
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
      · 【改基础名(@name)】对召唤兽会先校验，不在表里就弹警告（可以强制）
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
  * 名字（人物 / 召唤兽都行）：【设为显示名(@new_name)】/【改基础名(@name)】/
    【清除显示名(恢复原名)】；召唤兽还有【恢复模板本名】/【一键修复名字】
    （@name 必须在游戏的 $pet 名字表里，否则召唤兽界面会报 NoMethodError）
  * 物品栏：道具 @pack / 行囊 @wallet / 备用 @talisman 三个容器切换；
    格子 / 数量 / 物品id / 品质 填好后点「写入 · 修改该格」（新增会登记）；
    「删除该格」清空；「搜索物品」填关键字或编号过滤下拉列表
  * 开关、变量
  * 存档机器码（可一键填入本机机器码）
  * 「全部解析数据」页：字段 / 类型 / 值 / 注释 四列（注释会告诉你这个字段
    是干什么的、技能 id 对应哪个技能、物品实例用的哪个模板…）；
    全局搜索（搜字段名或值，双击结果跳到树上）；
    对着标量字段右键 ->「修改这个值…」
  每次修改后界面立刻刷新；保存时会：自动备份 sy.ogg.bak → 重新加密写回 →
  读回校验。

六、注意
  * 改存档有风险，请先自己另外备份一份 sy.ogg。
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


class App(object):
    def __init__(self, root, save_path=None):
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = root
        self.bridge = None
        self.doc = None
        self.node_of_item = {}
        self.path_of_item = {}
        self.actor_rows = {}
        self.pack_rows = {}

        root.title(TITLE)
        root.geometry('1120x760')

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

        # ---- 1 概览 + 快捷修改 ----
        f1 = ttk.Frame(self.nb, padding=8)
        self.nb.add(f1, text='概览 / 快捷修改')
        self.lb_info = tk.Text(f1, height=13, wrap='none')
        self.lb_info.pack(fill='x')
        self.lb_info.configure(font=('Consolas', 10))

        g = ttk.LabelFrame(f1, text='快捷修改（先点「应用」，再点上面的「保存修改」）',
                           padding=10)
        g.pack(fill='x', pady=8)
        self.var_gold = tk.StringVar()
        self.var_fame = tk.StringVar()
        self.var_store = tk.StringVar()
        self.var_steps = tk.StringVar()
        rows = [('金钱(元宝)', self.var_gold, 'LockNumber 6 组一起重算'),
                ('声望', self.var_fame, ''),
                ('仓库金额', self.var_store, ''),
                ('步数', self.var_steps, '')]
        for i, (label, var, hint) in enumerate(rows):
            ttk.Label(g, text=label, width=10).grid(row=i, column=0, sticky='w', pady=3)
            ttk.Entry(g, textvariable=var, width=20).grid(row=i, column=1, sticky='w')
            if hint:
                ttk.Label(g, text=hint, foreground='#888').grid(row=i, column=2,
                                                                sticky='w', padx=6)
        ttk.Button(g, text='应用', command=self.apply_quick).grid(
            row=len(rows), column=1, sticky='w', pady=8)

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
        self.txt_node = tk.Text(right, wrap='word')
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
        nf = ttk.LabelFrame(f3, text='名字（游戏显示的是 @new_name，没有才用 @name）',
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
        ttk.Button(nf, text='改基础名(@name)',
                   command=self.apply_base_name).grid(row=0, column=3, padx=2)
        ttk.Button(nf, text='清除显示名(恢复原名)',
                   command=self.clear_custom_name).grid(row=0, column=4, padx=2)
        # 召唤兽专用：$pet 名字表校验（名字不在表里游戏会崩）—— 见 xj_model 注释
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
        self.tv_actor.column('where', width=118)
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
        for i, (ivar, label, w) in enumerate(fields):
            r, c = i % 10, (i // 10) * 3
            ttk.Label(e, text=label, width=9).grid(row=r, column=c, sticky='w', pady=2)
            var = tk.StringVar()
            ttk.Entry(e, textvariable=var, width=w).grid(row=r, column=c + 1, sticky='w')
            self.actor_vars[ivar] = var
        btns = ttk.Frame(e)
        btns.grid(row=0, column=6, rowspan=10, sticky='n', padx=8)
        ttk.Button(btns, text='应用人物修改',
                   command=self.apply_actor).pack(fill='x', pady=2)
        ttk.Button(btns, text='一键满级(175/180)',
                   command=lambda: self.actor_preset('max')).pack(fill='x', pady=2)
        ttk.Button(btns, text='HP/SP 填满',
                   command=lambda: self.actor_preset('heal')).pack(fill='x', pady=2)
        ttk.Button(btns, text='五维+10',
                   command=lambda: self.actor_preset('attr')).pack(fill='x', pady=2)
        ttk.Button(btns, text='活力/体力150',
                   command=lambda: self.actor_preset('vital')).pack(fill='x', pady=2)
        self.txt_actor = tk.Text(self.fr_person, height=6, wrap='word')
        vsa = ttk.Scrollbar(self.fr_person, orient='vertical',
                            command=self.txt_actor.yview)
        self.txt_actor.configure(yscrollcommand=vsa.set)
        self.txt_actor.pack(side='left', fill='both', expand=True)
        vsa.pack(side='left', fill='y')

        # ================= 召唤兽 =================
        self.fr_pet = ttk.Frame(f3)
        colsP = ('no', 'slot', 'display', 'name', 'nameok', 'tpl', 'owner', 'level',
                 'carry', 'growth', 'loyal', 'za', 'zd', 'zt', 'zm', 'zs', 'zdd',
                 'skills', 'state')
        headsP = ('序', '槽位', '显示名', '原名', '名字表', '模板', '主人', '等级',
                  '携带等级', '成长', '忠诚', '攻资', '防资', '体资', '法资', '速资',
                  '躲资', '技能', '状态')
        self.tv_pet = ttk.Treeview(self.fr_pet, columns=colsP, show='headings', height=7)
        for c, h, w in zip(colsP, headsP,
                           (34, 52, 96, 84, 60, 120, 78, 44, 66, 50, 50, 48, 48,
                            48, 48, 48, 48, 44, 96)):
            self.tv_pet.heading(c, text=h)
            self.tv_pet.column(c, width=w, anchor='center')
        self.tv_pet.tag_configure('dead', foreground='#999')
        self.tv_pet.tag_configure('badname', foreground='#c00')
        hsp = ttk.Scrollbar(self.fr_pet, orient='horizontal', command=self.tv_pet.xview)
        self.tv_pet.configure(xscrollcommand=hsp.set)
        hsp.pack(side='bottom', fill='x')
        self.tv_pet.pack(fill='x')
        self.tv_pet.bind('<<TreeviewSelect>>', lambda e: self.load_actor_edit())

        e2 = ttk.LabelFrame(self.fr_pet, text='修改选中的召唤兽（资质 / 成长 / 忠诚 / 属性）',
                            padding=8)
        e2.pack(fill='x', pady=6)
        self.pet_vars = {}
        pfields = [('@level', '等级'), ('@exp', '经验'), ('@hp', 'HP'), ('@sp', 'SP'),
                   ('@tizhi', '体质'), ('@moli', '魔力'), ('@liliang', '力量'),
                   ('@naili', '耐力'), ('@minjie', '敏捷'), ('@latent', '潜力'),
                   ('@vitality', '活力'), ('@spirit', '体力'),
                   ('@成长', '成长'), ('@loyal', '忠诚'),
                   ('@攻击资质', '攻击资质'), ('@防御资质', '防御资质'),
                   ('@体力资质', '体力资质'), ('@法力资质', '法力资质'),
                   ('@速度资质', '速度资质'), ('@躲闪资质', '躲闪资质')]
        for i, (ivar, label) in enumerate(pfields):
            r, c = i % 7, (i // 7) * 3
            ttk.Label(e2, text=label, width=10).grid(row=r, column=c, sticky='w', pady=2)
            var = tk.StringVar()
            ttk.Entry(e2, textvariable=var, width=9).grid(row=r, column=c + 1, sticky='w')
            self.pet_vars[ivar] = var
        btns2 = ttk.Frame(e2)
        btns2.grid(row=0, column=9, rowspan=7, sticky='n', padx=10)
        ttk.Button(btns2, text='应用召唤兽修改',
                   command=self.apply_actor).pack(fill='x', pady=2)
        ttk.Button(btns2, text='资质+500',
                   command=lambda: self.pet_preset('zz')).pack(fill='x', pady=2)
        ttk.Button(btns2, text='成长+0.1',
                   command=lambda: self.pet_preset('growth')).pack(fill='x', pady=2)
        ttk.Button(btns2, text='忠诚 100 / 五维+10',
                   command=lambda: self.pet_preset('loyal')).pack(fill='x', pady=2)
        ttk.Button(btns2, text='HP/SP 填满',
                   command=lambda: self.actor_preset('heal')).pack(fill='x', pady=2)

        skf = ttk.LabelFrame(self.fr_pet, text='召唤兽技能（存档字段 @skills）', padding=6)
        skf.pack(fill='both', expand=True)
        skbar = ttk.Frame(skf)
        skbar.pack(fill='x')
        ttk.Label(skbar, text='搜索技能').pack(side='left')
        self.var_skill_search = tk.StringVar()
        ske = ttk.Entry(skbar, textvariable=self.var_skill_search, width=12)
        ske.pack(side='left', padx=4)
        ske.bind('<KeyRelease>', lambda e: self.filter_skill_templates())
        self.var_skill_add = tk.StringVar()
        self.cb_skill = ttk.Combobox(skbar, textvariable=self.var_skill_add, width=30)
        self.cb_skill.pack(side='left')
        ttk.Button(skbar, text='学会技能',
                   command=self.skill_add).pack(side='left', padx=6)
        ttk.Button(skbar, text='忘掉选中',
                   command=self.skill_del).pack(side='left')
        ttk.Button(skbar, text='清空技能',
                   command=self.skill_clear).pack(side='left', padx=6)
        self.lb_skill_info = ttk.Label(skbar, text='', foreground='#888')
        self.lb_skill_info.pack(side='left', padx=6)
        self.tv_skill = ttk.Treeview(skf, columns=('id', 'name'), show='headings',
                                     height=6)
        self.tv_skill.heading('id', text='技能 id')
        self.tv_skill.heading('name', text='技能名（Data/Skills.rxdata）')
        self.tv_skill.column('id', width=80, anchor='center')
        self.tv_skill.column('name', width=300)
        vsk = ttk.Scrollbar(skf, orient='vertical', command=self.tv_skill.yview)
        self.tv_skill.configure(yscrollcommand=vsk.set)
        self.tv_skill.pack(side='left', fill='both', expand=True)
        vsk.pack(side='left', fill='y')
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
                       '每格 = [物品实例, 数量]'
                  ).pack(side='left')
        cols4 = ('slot', 'name', 'std', 'iid', 'count', 'quality', 'reg', 'desc')
        heads4 = ('格', '物品名（实例）', '模板id', '实例id', '数量', '品质', '登记', '说明')
        self.tv_pack = ttk.Treeview(f4, columns=cols4, show='headings', height=13)
        for c, h, w in zip(cols4, heads4, (36, 170, 60, 60, 52, 50, 76, 350)):
            self.tv_pack.heading(c, text=h)
            self.tv_pack.column(c, width=w, anchor='w')
        self.tv_pack.pack(fill='both', expand=True, pady=4)
        self.tv_pack.bind('<<TreeviewSelect>>', lambda e: self.load_pack_edit())

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
        ttk.Button(g4, text='写入 · 修改该格', command=self.pack_apply).grid(
            row=0, column=6, rowspan=3, padx=(14, 4), sticky='ns')
        ttk.Button(g4, text='删除该格', command=self.pack_delete).grid(
            row=0, column=7, rowspan=3, sticky='ns')
        ttk.Label(g4, foreground='#888', justify='left',
                  text='物品 id 可直接填数字（对应 data_items），或先在搜索框里筛（如"祈福"或 87）再从下拉选；\n'
                       '写入时会把实例登记进 $data_items（游戏用它判断能不能使用），并自动分配实例id；\n'
                       '数量小于 1 按 1 算，品质小于 1 按 100 算；每次操作后表格与"概览"立即刷新。\n'
                       '“登记”列显示 ✓ 表示游戏认得这件物品；若显示异常，点【一键修复异常格】。'
                  ).grid(row=3, column=0, columnspan=8, sticky='w', pady=(6, 0))
        ttk.Button(g4, text='一键修复异常格', command=self.pack_fix_bad).grid(
            row=4, column=6, columnspan=2, sticky='w', pady=(4, 0))

        # ---- 5 开关 / 变量 ----
        f5 = ttk.Frame(self.nb, padding=8)
        self.nb.add(f5, text='开关 / 变量')
        lf = ttk.Frame(f5)
        lf.pack(side='left', fill='both', expand=True)
        ttk.Label(lf, text='$game_switches.@data（双击切换）').pack(anchor='w')
        self.tv_sw = ttk.Treeview(lf, columns=('i', 'v'), show='headings', height=20)
        self.tv_sw.heading('i', text='编号')
        self.tv_sw.heading('v', text='值')
        self.tv_sw.column('i', width=80)
        self.tv_sw.column('v', width=90)
        self.tv_sw.pack(fill='both', expand=True)
        self.tv_sw.bind('<Double-1>', lambda e: self.sw_toggle())

        rf = ttk.Frame(f5)
        rf.pack(side='left', fill='both', expand=True, padx=(8, 0))
        ttk.Label(rf, text='$game_variables.@data（双击修改）').pack(anchor='w')
        self.tv_va = ttk.Treeview(rf, columns=('i', 'v'), show='headings', height=20)
        self.tv_va.heading('i', text='编号')
        self.tv_va.heading('v', text='数值')
        self.tv_va.column('i', width=80)
        self.tv_va.column('v', width=280)
        self.tv_va.pack(fill='both', expand=True)
        self.tv_va.bind('<Double-1>', lambda e: self.va_edit())

        # ---- 6 机器码 ----
        f6 = ttk.Frame(self.nb, padding=10)
        self.nb.add(f6, text='机器码')
        self.txt_id = tk.Text(f6, height=8, wrap='word')
        self.txt_id.pack(fill='x')
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

        # ---- 7 说明 ----
        f7 = ttk.Frame(self.nb, padding=8)
        self.nb.add(f7, text='说明 / 机制')
        t7 = tk.Text(f7, wrap='word')
        t7.pack(fill='both', expand=True)
        t7.insert('1.0', HELP_TEXT)
        t7.configure(state='disabled', font=('Microsoft YaHei UI', 10))

        # ---- 8 更新日志 ----
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
                '· 写回后会重新解密读回校验\n\n继续？'
                % (self.doc.path, os.path.basename(self.doc.path)), parent=self.root):
            return
        path = self.doc.path
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
        self.fill_switches()
        self.fill_id()

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

    def apply_base_name(self):
        aid = self.current_actor_id()
        if aid is None or not self.doc:
            self.err('请先在上面选中一个人物或召唤兽')
            return
        txt = self.var_newname.get().strip()
        if not txt:
            self.err('请先在输入框里写上新的名字')
            return
        # 召唤兽的 @name 会被游戏拿去索引 $pet 表（0163 第 147 行），
        # 表里没有的名字会让召唤兽界面直接报 NoMethodError，所以先拦一道
        if aid > 20 and self.doc.pet_name_table() \
                and self.doc.pet_name_ok(txt) is False:
            from tkinter import messagebox
            sug, _why = self.doc.suggest_pet_name(aid)
            if not messagebox.askyesno(
                    '这个名字会让游戏报错',
                    '「%s」不在游戏的 $pet 名字表里。\n\n'
                    '游戏脚本会执行 $pet["#{名字}"][7]，取不到就会抛\n'
                    'NoMethodError: undefined method \'[]\' for nil:NilClass\n'
                    '（召唤兽界面直接打不开）。\n\n'
                    '%s\n\n'
                    '如果你只是想给它换个好听的名字，请改用【设为显示名(@new_name)】，'
                    '那个不影响 $pet 查表。\n\n还要强行改成「%s」吗？'
                    % (txt, ('建议改成模板本名：「%s」' % sug) if sug else '',
                       txt), parent=self.root):
                return
        try:
            self.doc.set_actor_name(aid, txt)
            self._after_rename(aid, '%s 的 @name 已改成「%s」'
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
            self.fill_skills(aid)
            return
        for ivar, var in self.actor_vars.items():
            v = MOD.vof(a.get(ivar))
            var.set('' if v is None else str(v))
        t = ['人物 %d  门派 %s' % (aid, self.doc.class_name(
            MOD.vof(a.get('@class_id')) or 0)),
            'HP 上限 %s / SP 上限 %s（按游戏公式计算）'
            % (self.doc.actor_maxhp(aid), self.doc.actor_maxsp(aid)),
            '已学技能：%s' % ('、'.join(n for _i, n in self.doc.actor_skills(aid))
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
        for i, n in getattr(self, '_skill_tpls', []):
            if not kw or kw in n.lower() or kw == str(i):
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
        if not self.doc:
            return
        if aid is None:
            aid = self.current_actor_id()
        if aid is None:
            return
        for sid, name in self.doc.actor_skills(aid):
            self.tv_skill.insert('', 'end', values=(sid, name))

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
            reg = '' if r['item'] is None else ('✔' if r['registered'] else '✘')
            node = self.tv_pack.insert('', 'end', values=(
                r['slot'], r['name'], '' if r['standard'] is None else r['standard'],
                '' if r['iid'] is None else r['iid'], r['count'],
                '' if r['quality'] is None else r['quality'], reg, r['desc']))
            self.pack_rows[node] = r['slot']

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
            sid = int(txt.split('|')[0].strip())
            cnt = int(self.var_pack_count.get().strip() or '1')
            qty = int(self.var_pack_quality.get().strip() or '100')
        except ValueError:
            self.err('物品 id / 数量 / 品质 都要填数字')
            return
        r0 = self.doc.pack_slot(slot, key)
        had = bool(r0 and r0['item'] is not None)
        try:
            info = self.doc.pack_write(slot, sid, cnt, qty, key)
            self.mark_dirty()
            self.pack_refresh(slot)
            self.set_status('%s%s第 %d 格：%s（物品 id %d）× %d，品质 %d，实例 id %d（已登记）'
                            % ('改写' if had else '新增', self.cur_container(),
                               info['slot'], info['template_name'], info['standard'],
                               info['count'], info['quality'], info['iid']))
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

    def clear_tpl_search(self):
        self.var_tpl_search.set('')
        self.filter_templates()

    def refresh_templates(self):
        if not self.doc:
            return
        try:
            self._tpls = self.doc.item_templates()
        except Exception:
            self._tpls = []
        self.filter_templates()

    def filter_templates(self):
        """按搜索框过滤物品下拉列表（名字关键字或直接填编号）。"""
        kw = ''
        try:
            kw = self.var_tpl_search.get().strip().lower()
        except Exception:
            pass
        out = []
        for i, n in getattr(self, '_tpls', []):
            if not kw or kw in n.lower() or kw == str(i):
                out.append('%d | %s' % (i, n))
        self.cb_tpl['values'] = out[:500]
        try:
            self.lb_tpl_info.configure(text='命中 %d / 共 %d 个物品'
                                       % (len(out), len(getattr(self, '_tpls', []))))
        except Exception:
            pass

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

    # ================= 开关 / 变量 =================
    def fill_switches(self):
        self.tv_sw.delete(*self.tv_sw.get_children())
        self.tv_va.delete(*self.tv_va.get_children())
        if not self.doc:
            return
        for i, v in self.doc.switches():
            self.tv_sw.insert('', 'end', values=(i, v))
        for i, v, t in self.doc.variables():
            self.tv_va.insert('', 'end', values=(i, '%s   [%s]' % (v, t)))

    def sw_toggle(self):
        sel = self.tv_sw.selection()
        if not sel or not self.doc:
            return
        idx, val = self.tv_sw.item(sel[0], 'values')
        try:
            self.doc.set_switch(int(idx), not (str(val) == 'True'))
            self.mark_dirty()
            self.fill_switches()
        except Exception as e:
            self.err(e)

    def va_edit(self):
        from tkinter import simpledialog
        sel = self.tv_va.selection()
        if not sel or not self.doc:
            return
        idx = int(self.tv_va.item(sel[0], 'values')[0])
        cur = self.doc.variables()[idx][1]
        new = simpledialog.askinteger(
            '修改变量', '变量 %d 的新值：' % idx,
            initialvalue=int(cur) if isinstance(cur, (int, float)) else 0,
            parent=self.root)
        if new is None:
            return
        try:
            self.doc.set_variable(idx, new)
            self.mark_dirty()
            self.fill_switches()
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
