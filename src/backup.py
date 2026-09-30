# -*- coding: utf-8 -*-
r"""存档管理：备份 / 删除备份 / 恢复选中 / 恢复最新。

存档是 `Audio\BGM\sy.ogg`（名字看着像背景音乐，其实是加密存档），备份放在**存档旁边**
的子目录里，默认叫 `.huaji1-save-editor`（名字带点，资源管理器里默认是隐藏项）。
老版本用过 `huaji1-save-editor`：那个目录里的备份**照样列出来、照样能恢复/能删**，
只是新备份不再往里写。

命名规矩（都能排序、看得懂）：

    sy.2026-09-30_013245.ogg            手动备份
    sy.2026-09-30_013245.auto.ogg       保存前的自动备份

只做文件层面的复制/删除，不解析存档内容 —— 万一存档坏了，这里也能救。

⚠ 和 `doctree.save()` 的 `sy.ogg.bak` 是两回事：`.bak` 只留**上一次**保存前的那一份
（会被下一保存覆盖），这里是**多份带时间戳**的历史，所以恢复时不会互相盖掉。
"""
import os
import re
import shutil
import time

#: 当前使用的备份目录名（第 0 个），后面的是老版本用过、仍要能读到的
DIR_NAME = '.huaji1-save-editor'
DIR_NAMES = (DIR_NAME, 'huaji1-save-editor')

STAMP_FMT = '%Y-%m-%d_%H%M%S'
KIND_AUTO = 'auto'                    # 自动（保存前）
KIND_MANUAL = 'manual'                # 手动
KIND_BEFORE_RESTORE = 'before-restore'   # 老版本留下的"恢复前"（只读，不再新写）

SUFFIX = '.ogg'                       # 存档后缀（本作固定 sy.ogg）


def backup_dir(save_path, create=True, prefer=None):
    """备份目录 = 存档所在目录 / <DIR_NAME>（始终是当前这个名字）。

    `prefer` 可以显式指定目录名（测试与设置里用得上）。
    """
    root = os.path.dirname(os.path.abspath(save_path))
    p = os.path.join(root, prefer or DIR_NAME)
    if create:
        try:
            os.makedirs(p, exist_ok=True)
        except OSError:
            pass
    return p


def dirs(save_path):
    """实际存在、需要扫描的备份目录（新的在前，含老版本用过的目录）。"""
    root = os.path.dirname(os.path.abspath(save_path))
    return [os.path.join(root, n) for n in DIR_NAMES
            if os.path.isdir(os.path.join(root, n))]


def _stamp(t=None):
    return time.strftime(STAMP_FMT, t or time.localtime())


def parse_name(name):
    """`sy.2026-09-30_013245.auto.ogg` → (来源名, 时间串, 类型)。

    解析不出来就返回 (name, '', 'other')，宁可在列表里显示也不丢。
    """
    if not name.endswith(SUFFIX):
        return name, '', 'other'
    body = name[:-len(SUFFIX)]
    body = re.sub(r'-\d+$', '', body)   # 同一秒里连点两次留下的"-2"后缀
    m = re.match(r'^(?P<src>.+?)\.(?P<t>\d{4}-\d{2}-\d{2}_\d{6})'
                 r'(?:\.(?P<kind>[a-z\-]+))?$', body)
    if not m:
        return body, '', 'other'
    return (m.group('src'), m.group('t'), m.group('kind') or KIND_MANUAL)


def backup(save_path, kind=KIND_MANUAL, note=''):
    """把存档复制进备份目录，返回备份文件路径。"""
    if not os.path.exists(save_path):
        raise IOError('找不到要备份的存档：%s' % save_path)
    d = backup_dir(save_path)
    src_name = os.path.basename(os.path.abspath(save_path))
    base = os.path.splitext(src_name)[0]
    stamp = _stamp()
    name = '%s.%s%s%s' % (base, stamp,
                          '' if kind == KIND_MANUAL else '.' + kind, SUFFIX)
    dst = os.path.join(d, name)
    i = 1
    while os.path.exists(dst):          # 同一秒里连点两次也不覆盖
        i += 1
        dst = os.path.join(d, name[:-len(SUFFIX)] + '-%d%s' % (i, SUFFIX))
    shutil.copyfile(save_path, dst)
    if note:
        try:
            with open(dst + '.txt', 'w', encoding='utf-8') as f:
                f.write(note)
        except OSError:
            pass
    return dst


def list_backups(save_path, prefer=None):
    """列出备份：[{name, path, dir, size, mtime, stamp, kind, src, note}, ...]，新的在前。

    默认把新目录和老目录里的备份**一起**列出来（老备份不会丢）。
    """
    if prefer:
        root = os.path.dirname(os.path.abspath(save_path))
        ds = [os.path.join(root, prefer)]
    else:
        ds = dirs(save_path)
    out = []
    want = os.path.splitext(os.path.basename(save_path))[0]
    for d in ds:
        if not os.path.isdir(d):
            continue
        for n in os.listdir(d):
            p = os.path.join(d, n)
            if not os.path.isfile(p) or not n.endswith(SUFFIX):
                continue
            src, stamp, kind = parse_name(n)
            st = os.stat(p)
            note = ''
            tf = p + '.txt'
            if os.path.exists(tf):
                try:
                    note = open(tf, encoding='utf-8').read().strip()[:120]
                except OSError:
                    note = ''
            out.append({'name': n, 'path': p, 'dir': d, 'size': st.st_size,
                        'mtime': st.st_mtime, 'stamp': stamp, 'kind': kind,
                        'src': src, 'note': note,
                        'is_this_file': src == want})
    out.sort(key=lambda r: (r['mtime'], r['name']), reverse=True)
    return out


def remove(paths):
    """删掉若干备份（连 .txt 备注一起删）。返回删掉的个数。"""
    n = 0
    for p in paths:
        for f in (p, p + '.txt'):
            try:
                if os.path.exists(f):
                    os.remove(f)
                    if f == p:
                        n += 1
            except OSError:
                pass
    return n


def restore(backup_path, save_path):
    """把某个备份恢复成存档（不再额外留"恢复前"那份）。返回用的备份路径。"""
    if not os.path.exists(backup_path):
        raise IOError('找不到备份：%s' % backup_path)
    shutil.copyfile(backup_path, save_path)
    return backup_path


def newest(save_path, prefer=None, this_file=True):
    """最新的一份备份（默认优先"同一存档名"的那份）——「恢复最新」用它。"""
    rows = list_backups(save_path, prefer=prefer)
    if this_file:
        for r in rows:
            if r['is_this_file']:
                return r
    return rows[0] if rows else None


def keep_newest(save_path, prefer=None):
    """「删除非最新」：留最新的一份 + **所有手动备份**，其余全删。

    手动备份是玩家主动留的档，不跟着自动备份一起被清掉。
    返回 (留下的最新那份, 删掉的份数)。
    """
    rows = list_backups(save_path, prefer=prefer)
    if len(rows) < 2:
        return (rows[0] if rows else None), 0
    keep = newest(save_path, prefer=prefer)
    keep_paths = {keep['path']}
    keep_paths.update(r['path'] for r in rows if r['kind'] == KIND_MANUAL)
    gone = [r['path'] for r in rows if r['path'] not in keep_paths]
    return keep, remove(gone)


def set_note(backup_path, note):
    """给备份写/改备注（存在备份文件旁边的 .txt）；传空串就删掉备注。"""
    tf = backup_path + '.txt'
    note = (note or '').strip()
    try:
        if note:
            with open(tf, 'w', encoding='utf-8') as f:
                f.write(note)
        else:
            if os.path.exists(tf):
                os.remove(tf)
    except OSError:
        raise IOError('备注写不进去：%s' % tf)


def auto_backup_once(path, prefer=None, min_gap=90):
    """保存存档前自动留一份，太频繁就跳过（同一份文件 90 秒内只留一次）。"""
    try:
        if not os.path.exists(path):
            return None
        for r in list_backups(path, prefer=prefer)[:5]:
            if r['kind'] == KIND_AUTO and time.time() - r['mtime'] < min_gap:
                return None
        return backup(path, kind=KIND_AUTO, note='')
    except Exception:
        return None
