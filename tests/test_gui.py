# -*- coding: utf-8 -*-
"""0.3 界面冒烟测试：不显示窗口，把 8 个页签全部构建/切换一遍并刷新数据。

目的是确认改过 CHANGELOG / 显示逻辑之后界面不会被"炸掉"，
以及"更新日志"页确实能渲染出版本记录。
"""
# --- 开发期路径引导：让 import xj_* 找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import os
import sys
import tkinter as tk
import tkinter.messagebox as _mb

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import xj_codec as C
import xj_model as MOD
import xj_viewer as V

from xj_env import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
# 源码目录里没有 TP.dll（发行目录才有），测试用游戏根目录里的
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE


def main():
    root = tk.Tk()
    root.withdraw()
    app = V.App(root, save_path=SAVE)
    root.update()
    # 界面是延时自动加载的（root.after(300, …)），这里直接同步加载一次；
    # 顺便把加解密通道指到有 DLL 的目录
    app.log = print
    if app.doc is None:
        app.bridge = C.make_bridge(DLL_DIR, lambda s: print('[codec] %s' % s))
        app.load(SAVE)
        root.update()
    if app.doc is None:
        print('!! 存档没加载成功')
        return 1
    tabs = app.nb.tabs()
    print('页签数：%d' % len(tabs))
    for i, t in enumerate(tabs):
        name = app.nb.tab(t, 'text')
        app.nb.select(t)
        root.update()
        print('  [%d] %-14s OK' % (i, name))
    # 刷新一遍数据
    app.fill_all()
    root.update()
    print('fill_all() OK')

    doc = app.doc
    print('概览：金钱=%s 角色=%d 物品栏=%d/%d'
          % (doc.gold(), len(doc.actor_rows()), doc.pack_used(), doc.PACK_SIZE))
    ch = MOD.CHANGELOG
    print('更新日志页长度：%d 字符，含 1.0/0.7/0.6/0.5/0.4/0.3/0.2/0.1：%s'
          % (len(ch), all(v in ch for v in ('1.0', '0.7', '0.6', '0.5',
                                            '0.4', '0.3', '0.2', '0.1'))))

    # ---- 物品栏：模拟"写入该格"（只在内存里改，不写文件）----
    app.err = print                       # 出错也别弹窗，免得测试卡住
    slot = next(r['slot'] for r in doc.pack() if r['item'] is None)
    app.var_pack_slot.set(str(slot))
    app.var_pack_count.set('0')           # 故意填 0：0.3 就是这样把格子写坏的
    app.var_pack_quality.set('0')         # 故意填 0
    app.var_pack_std.set('87 | 祈福酒肆')
    app.pack_apply()
    root.update()
    row = [app.tv_pack.item(i, 'values') for i in app.tv_pack.get_children()
           if str(app.tv_pack.item(i, 'values')[0]) == str(slot)]
    print('写入第 %d 格后表格显示：%s' % (slot, row[0] if row else '无'))
    ok_tbl = bool(row) and str(row[0][4]) == '1' and str(row[0][5]) == '100'
    print('表格立即刷新（数量 1 / 品质 100）：%s' % ('OK' if ok_tbl else '失败'))
    r = doc.pack_slot(slot)
    print('内存里的值：数量 %s 品质 %s 字段 %d 个（模板 25 + standard + quality）'
          % (r['count'], r['quality'], len(r['item'].ivars)))
    print('异常格扫描：%s' % (doc.pack_scan_bad() or '无异常'))

    # ---- 物品搜索框 ----
    for kw in ('祈福', '87', '包子'):
        app.var_tpl_search.set(kw)
        app.filter_templates()
        root.update()
        vals = list(app.cb_tpl['values'])
        print('搜索「%s」：%s，下拉前 2 项 %s'
              % (kw, app.lb_tpl_info.cget('text'), vals[:2]))
    app.var_tpl_search.set('')
    app.filter_templates()
    root.update()
    print('清空搜索：%s' % app.lb_tpl_info.cget('text'))
    # ---- 角色 / 召唤兽 分离 + 技能 ----
    print('角色页提示：%s' % app.lb_actor_hint.cget('text'))
    app.var_actor_group.set('pet')
    app.on_actor_group_change()
    root.update()
    pets = list(app.pet_rows.values())
    print('切到召唤兽：表中 %d 只（默认不显示已放生的），技能下拉 %s' %
          (len(pets), list(app.cb_skill['values'])[:2]))
    print('召唤兽表（序/槽位/显示名/名字表/模板/主人/携带等级/状态）：')
    for i in app.tv_pet.get_children():
        v = app.tv_pet.item(i, 'values')
        print('    %s %s %s %s %s %s %s %s'
              % (v[0], v[1], v[2], v[4], v[5], v[6], v[8], v[18]))
    dead_before = len(app.tv_pet.get_children())
    app.var_pet_all.set(True)
    app.on_actor_group_change()
    root.update()
    dead_after = len(app.tv_pet.get_children())
    print('勾上「显示无主」：%d -> %d 行（%s）'
          % (dead_before, dead_after,
             'OK' if dead_after > dead_before else '失败'))
    print('提示栏：%s' % app.lb_actor_hint.cget('text'))
    app.var_pet_all.set(False)
    app.on_actor_group_change()
    root.update()
    pets = list(app.pet_rows.values())
    pet_id = pets[0] if pets else None
    if pet_id is not None:
        app.select_actor(pet_id)
        root.update()
        rows = [app.tv_skill.item(i, 'values') for i in app.tv_skill.get_children()]
        print('召唤兽 %s 当前技能 %d 个：%s' % (pet_id, len(rows), rows[:3]))
        print('资质/成长/忠诚回填：%s / %s / %s'
              % (app.pet_vars['@攻击资质'].get(), app.pet_vars['@成长'].get(),
                 app.pet_vars['@loyal'].get()))
        # 学会一个技能（只在内存里改，不保存）
        cand = [v for v in app.cb_skill['values']
                if int(v.split('|')[0]) not in [int(r[0]) for r in rows]]
        if cand:
            app.var_skill_add.set(cand[0])
            app.skill_add()
            root.update()
            after = [app.tv_skill.item(i, 'values') for i in app.tv_skill.get_children()]
            print('学会「%s」后：技能 %d 个 -> %s'
                  % (cand[0], len(after), [r[0] for r in after]))
            app.tv_skill.selection_set(app.tv_skill.get_children()[0])
            app.skill_del()
            root.update()
            print('忘掉第一个后：技能 %d 个' % len(app.tv_skill.get_children()))
        # 改资质
        app.pet_vars['@攻击资质'].set('4000')
        app.apply_actor()
        root.update()
        print('资质改成 4000 后读回：%s' % MOD.vof(doc.actor(pet_id).get('@攻击资质')))
        print('表格里的资质列（第 12 列）：%s'
              % [app.tv_pet.item(i, 'values')[11] for i in app.tv_pet.get_children()
                 if app.pet_rows.get(i) == pet_id])
        # ---- 改名 ----
        print('名字栏（未改名前）：%s' % app.lb_name_now.cget('text'))
        app.var_newname.set('测试改名')
        app.apply_custom_name()
        root.update()
        print('设为显示名后：%s' % app.lb_name_now.cget('text'))
        disp = [app.tv_pet.item(i, 'values')[2] for i in app.tv_pet.get_children()
                if app.pet_rows.get(i) == pet_id]
        print('表格显示名列：%s（%s）'
              % (disp, 'OK' if disp and disp[0] == '测试改名' else '失败'))
        app.clear_custom_name()
        root.update()
        print('清除显示名后：%s' % app.lb_name_now.cget('text'))
        disp = [app.tv_pet.item(i, 'values')[2] for i in app.tv_pet.get_children()
                if app.pet_rows.get(i) == pet_id]
        print('表格显示名列：%s（%s）'
              % (disp, 'OK' if disp and disp[0] != '测试改名' else '失败'))
        # ---- 1.0：$pet 名字表校验 + 一键修复名字 ----
        print('名字表校验行：%s' % app.lb_name_check.cget('text')[:70])
        print('名字表列：%s'
              % [app.tv_pet.item(i, 'values')[4]
                 for i in app.tv_pet.get_children()][:3])
        # 把 @name 改成表外的名字，看界面会不会报出来
        doc.set_actor_name(pet_id, '二郎神')
        app.fill_actors()
        app.select_actor(pet_id)
        app.load_actor_edit()
        root.update()
        print('改成表外名字后提示：%s' % app.lb_actor_hint.cget('text')[:80])
        print('名字表校验行：%s' % app.lb_name_check.cget('text')[:70])
        print('该行名字表列：%s'
              % [app.tv_pet.item(i, 'values')[4]
                 for i in app.tv_pet.get_children()
                 if app.pet_rows.get(i) == pet_id])
        # 一键修复（patch 掉确认框）
        _mb.askyesno = lambda *a, **k: True
        _mb.showinfo = lambda *a, **k: None
        app.fix_pet_names_ui()
        root.update()
        print('一键修复后名字：%s，提示：%s'
              % (MOD.stext(doc.actor(pet_id).get('@name'), ''),
                 app.lb_actor_hint.cget('text')[:60]))
        print('一键修复后名字表校验：%s'
              % app.lb_name_check.cget('text')[:60])
    app.var_actor_group.set('person')
    app.on_actor_group_change()
    root.update()
    print('切回人物：表中 %d 个' % len(app.actor_rows))

    # ---- 全局搜索 + 跳转 ----
    for kw in ('二郎', '@skills', '成长'):
        app.var_search.set(kw)
        app.global_search()
        root.update()
        hits = app.tv_search.get_children()
        print('全局搜索「%s」：%d 条%s' % (kw, len(hits),
                                       ('，例：%s' % (app.tv_search.item(hits[0], 'values')[0],))
                                       if hits else ''))
    if app.tv_search.get_children():
        app.tv_search.selection_set(app.tv_search.get_children()[0])
        app.goto_search_hit()
        root.update()
        print('跳转后树上选中：%s' % app.tree.item(app.tree.focus(), 'text'))
    app.clear_search()
    root.update()
    print('清空搜索结果 OK（结果区已隐藏：%s）' % (not app.fr_hits.winfo_ismapped()))

    print('右键菜单项：%s'
          % [app.tree_menu_obj.entrycget(i, 'label')
             for i in range(app.tree_menu_obj.index('end') + 1)
             if app.tree_menu_obj.type(i) != 'separator'])
    # ---- 解析树的注释列 ----
    print('解析树列：%s'
          % [app.tree.heading(c, 'text') for c in ('#0', 'type', 'value', 'note')])
    for i in app.tree.get_children()[:4]:
        v = app.tree.item(i, 'values')
        print('    %-22s %-14s %s' % (app.tree.item(i, 'text'), v[1], v[2]))
    # 展开一个节点，看子行的注释
    first = app.tree.get_children()[7]        # #7 game_actors
    app.tree.item(first, open=True)
    app.tree.focus(first)
    app.on_open()
    root.update()
    kids = app.tree.get_children(first)
    print('展开「%s」：%d 行，前 2 行带注释：%s'
          % (app.tree.item(first, 'text'), len(kids),
             [app.tree.item(k, 'values')[2][:40] for k in kids[:2]]))
    if kids:
        app.tree.focus(kids[0])
        app.tree.selection_set(kids[0])
        app.on_select()
        root.update()
        print('选中行详情片段：%s'
              % app.txt_node.get('1.0', 'end').strip().splitlines()[:4])
    print('非标量字段不可编辑（顶层对象应 False）：%s'
          % doc.can_edit_node(doc.node('data')))
    doc.discard()                         # 丢掉内存改动，不写文件
    print('标题：%s' % app.root.title())
    print('版本：%s' % V.VERSION)
    root.destroy()
    print('===== 界面冒烟测试：通过 =====')
    return 0

if __name__ == '__main__':
    sys.exit(main())
