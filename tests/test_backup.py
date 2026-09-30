# -*- coding: utf-8 -*-
"""「存档管理」测试：src/backup.py 全部函数 + 界面上那一页的按钮。

⚠ 全程只在 **临时目录里的存档副本** 上干活。
   备份目录是建在「存档旁边」的（.huaji1-save-editor），拿游戏里那份真档来跑就会在
   Audio\\BGM 里堆出一串备份 —— 那目录旁边躺着 225 个真 BGM 文件，绝不能污染。
   真档在这里只被**读一次**（复制两副本出来当素材），全程不写。

跑法（要 Py3.12，因为要用 tkinter）：
    D:/Dev/Python/Env/Python312/python.exe tests/test_backup.py
"""
# --- 开发期路径引导：让 import 项目模块找到 ../src ----------------------------
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))
# -------------------------------------------------------------------------

import shutil
import tempfile
import time
import tkinter as tk
import tkinter.messagebox as _mb

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import backup
import codec as C
import huaji1_save_editor as V

from paths import game_dir as _game_dir          # 游戏目录 = XJ_GAME 或向上找 Game.exe
GAME = _game_dir()
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')
DLL_DIR = GAME if os.path.exists(os.path.join(GAME, 'TP.dll')) else HERE

#: 测试工作目录（固定路径，每次跑先清空 —— 免得上一轮被中断后留下的备份把断言弄崩）
WORK = os.path.join(tempfile.gettempdir(), 'huaji1_backup_test')

FAILS = []


def chk(label, cond, extra=''):
    if not cond:
        FAILS.append(label)
    print('  [%s] %s%s' % ('ok ' if cond else 'FAIL', label,
                           ('  %s' % (extra,)) if extra else ''))
    return bool(cond)


def _wipe(d):
    """清掉上次跑剩下的东西（只删这个测试目录里的）。"""
    if not os.path.isdir(d):
        return
    for name in os.listdir(d):
        p = os.path.join(d, name)
        try:
            if os.path.isfile(p):
                os.remove(p)
            elif os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
        except OSError:
            pass


def _touch(path, t):
    """把 mtime 定死，免得同一秒里建好几份、排序变成看文件名。"""
    os.utime(path, (t, t))


# ============================================================ 1 backup.py
def test_module(work):
    print('--- backup.py（存档副本 = %s）' % work)
    src_size = os.path.getsize(work)

    d = backup.backup_dir(work, create=False)
    chk('备份目录 = 存档旁边/.huaji1-save-editor',
        os.path.basename(d) == '.huaji1-save-editor', d)
    chk('没备份过就不建目录', not os.path.isdir(d))
    chk('空目录列出来是 0 份', backup.list_backups(work) == [])
    chk('newest() 空目录返回 None', backup.newest(work) is None)

    # ---- 手动备份 ----
    p1 = backup.backup(work, backup.KIND_MANUAL)
    chk('手动备份已落盘', os.path.exists(p1), os.path.basename(p1))
    chk('这一步才建出目录', os.path.isdir(d))
    chk('备份与存档同大小', os.path.getsize(p1) == src_size)
    chk('备份内容与存档逐字节相同',
        open(p1, 'rb').read() == open(work, 'rb').read())
    src, stamp, kind = backup.parse_name(os.path.basename(p1))
    chk('文件名 = sy.<时间戳>.ogg', os.path.basename(p1) == 'sy.%s.ogg' % stamp,
        os.path.basename(p1))
    chk('解析出 来源/时间/类型', (src, kind) == ('sy', 'manual'), (src, kind))
    chk('时间戳能被 strptime 认出来',
        bool(time.strptime(stamp, backup.STAMP_FMT)))

    rows = backup.list_backups(work)
    chk('列出 1 份', len(rows) == 1)
    chk('标记成“就是这份存档的备份”', bool(rows) and rows[0]['is_this_file'] is True)
    chk('src 对得上存档名', bool(rows) and rows[0]['src'] == 'sy')

    # ---- 备注 ----
    backup.set_note(p1, '改金钱之前')
    chk('备注写进 .txt', os.path.exists(p1 + '.txt'))
    chk('列表能读到备注', backup.list_backups(work)[0]['note'] == '改金钱之前')
    backup.set_note(p1, '   ')
    chk('备注留空 = 删掉', not os.path.exists(p1 + '.txt'))
    chk('列表里备注变空', backup.list_backups(work)[0]['note'] == '')

    # ---- 自动备份（保存前触发，90 秒去重）----
    _touch(p1, 1000.0)
    a1 = backup.auto_backup_once(work)
    chk('auto_backup_once 产出自动备份', bool(a1), os.path.basename(a1 or ''))
    chk('类型是 auto', backup.parse_name(os.path.basename(a1))[2] == 'auto')
    chk('90 秒内再来一次被跳过', backup.auto_backup_once(work) is None)

    _touch(p1, 1000.0)
    _touch(a1, 2000.0)
    chk('newest() 给的是最新的那份', backup.newest(work)['path'] == a1)
    _touch(a1, 500.0)                     # 把它改成“更旧”
    chk('newest() 挑 mtime 最大的', backup.newest(work)['path'] == p1)
    _touch(a1, 2000.0)

    # ---- parse_name 的兜底 ----
    chk('认不出的文件名不丢、标成 other',
        backup.parse_name('乱七八糟.txt') == ('乱七八糟.txt', '', 'other'))
    chk('“-2”后缀也能解析回来',
        backup.parse_name('sy.2026-09-30_013245.auto-2.ogg')[1:] ==
        ('2026-09-30_013245', 'auto'))

    # ---- 恢复 ----
    good = open(a1, 'rb').read()
    with open(work, 'wb') as f:
        f.write('被改坏的存档'.encode('utf-8') * 10)
    backup.restore(a1, work)
    chk('restore 把存档换回备份的内容', open(work, 'rb').read() == good)

    # ---- 老目录（huaji1-save-editor）里的备份也要能读到 ----
    old_d = os.path.join(os.path.dirname(work), 'huaji1-save-editor')
    os.makedirs(old_d, exist_ok=True)
    old_p = os.path.join(old_d, 'sy.2020-01-02_030405.ogg')
    shutil.copyfile(work, old_p)
    chk('老目录被算进 dirs()', old_d in backup.dirs(work))
    chk('老目录里的备份也列出来',
        old_p in [r['path'] for r in backup.list_backups(work)])

    # ---- 删除非最新：留最新 + 所有手动 ----
    m2 = backup.backup(work, backup.KIND_MANUAL, note='手动留档')
    a2 = backup.backup(work, backup.KIND_AUTO)
    a3 = backup.backup(work, backup.KIND_AUTO)
    for i, p in enumerate((old_p, p1, a1, m2, a2, a3)):
        _touch(p, 3000.0 + i)                 # 越靠后越新
    before = backup.list_backups(work)
    n_auto = sum(1 for r in before if r['kind'] == 'auto')
    n_man = sum(1 for r in before if r['kind'] == 'manual')
    print('    清理前：%d 份（自动 %d / 手动 %d / 其它 %d）'
          % (len(before), n_auto, n_man, len(before) - n_auto - n_man))
    keep_want = {r['path'] for r in before if r['kind'] == 'manual'}
    keep_want.add(before[0]['path'])          # 最新的一份（列表已按新->旧排好）
    gone_want = [r['path'] for r in before if r['path'] not in keep_want]
    kept, n = backup.keep_newest(work)
    after = backup.list_backups(work)
    chk('keep_newest 删掉的份数对得上', n == len(gone_want), 'n=%d' % n)
    chk('留下的正好是「最新 + 所有手动」',
        sorted(r['path'] for r in after) == sorted(keep_want),
        '%d 份' % len(after))
    chk('手动备份一份没少',
        sum(1 for r in after if r['kind'] == 'manual') == n_man)
    chk('最新的那份还在', before[0]['path'] in [r['path'] for r in after])

    # ---- remove ----
    gone = [r['path'] for r in after[:1]]
    chk('remove 返回删除份数', backup.remove(gone) == 1)
    chk('删完列表少一份', len(backup.list_backups(work)) == len(after) - 1)
    chk('remove 对不存在的路径不炸', backup.remove(['不存在的文件']) == 0)

    # ---- 异常路径 ----
    for label, fn in (('备份不存在的存档要报错',
                       lambda: backup.backup(work + '.nope')),
                      ('恢复不存在的备份要报错',
                       lambda: backup.restore(work + '.nope', work))):
        try:
            fn()
            chk(label, False)
        except IOError:
            chk(label, True)
        except Exception as e:
            chk(label, False, type(e).__name__)


# ============================================================ 2 界面
def test_gui(work):
    """界面：页签在不在、按钮真点下去会不会崩、表格刷不刷新。

    弹窗全换成假的、也不弹真的备注窗口（`wait_window` 换掉）——
    测试不抢前台、不等人点。
    """
    print('--- 「存档管理」页（存档副本 = %s）' % work)
    root = tk.Tk()
    root.withdraw()

    _mb.askyesno = lambda *a, **k: True
    _mb.showinfo = lambda *a, **k: None
    _mb.showerror = lambda *a, **k: None

    notes = []                      # 假的备注输入，每次“弹窗”取一个

    class FakeNoteDialog(object):
        def __init__(self, master, cur='', title='编辑备注', label=None):
            self.result = notes.pop(0) if notes else None

    V.NoteDialog = FakeNoteDialog
    root.wait_window = lambda w=None: None

    app = V.App(root, save_path=work)
    root.update()
    if app.doc is None:
        app.bridge = C.make_bridge(DLL_DIR, lambda s: None)
        app.load(work)
        root.update()
    if app.doc is None:
        FAILS.append('存档没加载成功')
        print('!! 存档没加载成功')
        root.destroy()
        return

    names = [app.nb.tab(t, 'text') for t in app.nb.tabs()]
    chk('页签里有「存档管理」', '存档管理' in names, ' / '.join(names))
    chk('它排在「概览 / 快捷修改」后面',
        names.index('存档管理') == 1, '第 %d 个' % (names.index('存档管理') + 1))
    app.nb.select(app.tab_saves)
    root.update()

    app.err = lambda e: FAILS.append('err(): %s' % e)     # 出错别弹窗、直接记账

    app.saves_refresh()
    chk('打开后表格是空的（这份副本还没备份过）',
        app.tv_saves.get_children() == () and app.save_rows == [])
    chk('提示行写着 0 份', '共 0 份' in app.var_saves_info.get(),
        app.var_saves_info.get().splitlines()[-1])
    chk('saves_dir() 指向存档旁边', app.saves_dir() == backup.backup_dir(work))

    # 立即备份（备注走假弹窗）
    notes.append('测试备注')
    app.saves_backup()
    root.update()
    chk('立即备份 -> 列表多一行', len(app.tv_saves.get_children()) == 1)
    chk('备注显示在表格里',
        '测试备注' in str(app.tv_saves.item(app.tv_saves.get_children()[0],
                                            'values')))
    chk('类型列写「手动」',
        app.tv_saves.item(app.tv_saves.get_children()[0], 'values')[2] == '手动')

    # 编辑备注
    notes.append('改过的备注')
    app.tv_saves.selection_set(app.tv_saves.get_children()[0])
    app.saves_edit_note()
    root.update()
    chk('编辑备注后列表跟着变',
        app.save_rows[0]['note'] == '改过的备注', app.save_rows[0]['note'])
    chk('刷新没把选中弄丢（下一步才能接着「恢复选中」）',
        bool(app.tv_saves.selection()))

    # 恢复选中（内容没变，但要走完“覆盖 + 重新载入”这条链）
    n_before = len(app.save_rows)
    app.saves_restore()
    root.update()
    chk('恢复选中后还能重新载入', app.doc is not None)
    chk('恢复后列表没被弄丢', len(app.save_rows) == n_before)
    chk('状态栏有“已恢复”', '已恢复' in app.var_status.get(), app.var_status.get())

    # 恢复最新
    app.saves_restore_newest()
    root.update()
    chk('恢复最新不炸', app.doc is not None)

    # 删除非最新：只有一份 -> 提示“不用清理”，不动手
    app.saves_delete_old()
    root.update()
    chk('只有 1 份时「删除非最新」不动手', len(app.save_rows) == 1)

    # 删除选中
    app.tv_saves.selection_set(app.tv_saves.get_children()[0])
    app.saves_delete()
    root.update()
    chk('删除选中 -> 列表空', app.save_rows == []
        and app.tv_saves.get_children() == ())

    # 删除无备注 / 刷新
    app.saves_delete_no_note()
    root.update()
    app.saves_refresh()
    root.update()
    chk('刷新后仍是 0 份', app.save_rows == [])

    # 没打开存档时的提示
    keep_doc = app.doc
    app.doc = None
    app.saves_refresh()
    root.update()
    chk('没打开存档时提示行会给出来', '还没打开存档' in app.var_saves_info.get(),
        app.var_saves_info.get())
    app.doc = keep_doc

    # 保存时那句自动备份
    p_before = len(backup.list_backups(work))
    backup.auto_backup_once(app.doc.path)
    chk('auto_backup_once 给存档管理留了一份',
        len(backup.list_backups(work)) == p_before + 1)

    root.destroy()


# ============================================================
def main():
    if not os.path.exists(SAVE):
        print('!! 找不到游戏存档：%s' % SAVE)
        return 1
    _wipe(WORK)
    work1 = os.path.join(WORK, 'sy.ogg')
    work2 = os.path.join(WORK, 'gui', 'sy.ogg')
    os.makedirs(os.path.dirname(work2), exist_ok=True)
    shutil.copyfile(SAVE, work1)
    shutil.copyfile(SAVE, work2)

    # 界面测试会写 src/last_save.txt（记住上次打开的存档）—— 备份好再还原
    last = os.path.join(os.path.dirname(os.path.abspath(V.__file__)),
                        'last_save.txt')
    old_last = (open(last, encoding='utf-8').read()
                if os.path.exists(last) else None)
    try:
        test_module(work1)
        n_mod = len(FAILS)
        print('--- 模块测试：%d 项失败' % n_mod)
        test_gui(work2)
        print('--- 界面测试：%d 项失败' % (len(FAILS) - n_mod))
    finally:
        if old_last is not None:
            try:
                with open(last, 'w', encoding='utf-8') as f:
                    f.write(old_last)
            except OSError:
                pass

    print('===== 存档管理测试：%s =====' % ('通过' if not FAILS else '有失败'))
    for x in FAILS:
        print('   %s' % x)
    print('（测试全在副本上：%s，真档没动）' % WORK)
    return 0 if not FAILS else 1


if __name__ == '__main__':
    sys.exit(main())
