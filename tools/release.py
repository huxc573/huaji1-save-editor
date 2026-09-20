# -*- coding: utf-8 -*-
r"""发 GitHub Release：按 `build.py` 里的命名规则准备好附件，再交给 `gh`。

    python tools/release.py                 # 创建/更新 v<当前版本> 的 Release
    python tools/release.py --upload-only   # Release 已存在，只重传附件
    python tools/release.py --dry           # 只打印要做什么，不动手

附件命名（**唯一来源在 tools/build.py 的 RELEASE_ASSETS**，别在这儿手敲）：
    huaji1-save-editor-v1.3.1.exe   主程序（本地产物固定叫 画迹1存档工具.exe，不带版本号）
    XJCodec32.exe                   32 位加解密宿主，缺了读不了存档
    TP.dll / Socket.dll             游戏自带库（版权归游戏原作者）
    USAGE.txt                       使用说明

Release 正文 = CHANGELOG.md 里对应版本的那一段 + 一段固定的下载说明。
需要本机装了 `gh` 且已登录（`gh auth status`）；git 推送另说。
"""
import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.stdout.reconfigure(errors='replace')

spec = importlib.util.spec_from_file_location('huaji1build', os.path.join(HERE, 'build.py'))
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)

TAG = 'v' + b.APP_VERSION


def stage_dir():
    r"""附件暂存目录。

    ⚠ 不能用仓库里的目录：本机仓库路径带 `[]`（`【画迹1…】[正式版+资料片]`）和中文，
    而 `gh release upload` 把文件参数当 **glob** 解析，方括号会被当字符类 →
    报 `no matches found`。丢到系统临时目录（纯 ASCII）就没这事。
    """
    d = os.path.join(tempfile.gettempdir(), 'huaji1_release_' + b.APP_VERSION)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)
    return d


def stage_assets():
    """把 dist 里的文件复制成 Release 用的 ASCII 名。"""
    stage = stage_dir()
    out = []
    for src_name, asset_name in b.RELEASE_ASSETS:
        src = os.path.join(b.EXE_DIR, src_name)
        if not os.path.exists(src):
            raise SystemExit('缺少 %s —— 先跑 python tools/build.py' % src)
        dst = os.path.join(stage, asset_name)
        shutil.copyfile(src, dst)
        out.append(dst)
        print('  准备 %-36s <- %s' % (asset_name, src_name))
    return out


def notes_text():
    """CHANGELOG 里本版本的那一段 + 下载说明。"""
    body = ''
    path = os.path.join(ROOT, 'CHANGELOG.md')
    if os.path.exists(path):
        text = open(path, encoding='utf-8').read()
        head = text.find('## ' + TAG)
        if head >= 0:
            nxt = text.find('\n## ', head + 1)
            body = text[head:nxt if nxt > 0 else len(text)].rstrip()
    names = [a for _, a in b.RELEASE_ASSETS]
    exe, host, tp, socket, usage = names
    extra = (
        '## 下载 / 用法\n\n'
        '5 个附件都下，放在**同一个目录**里：\n\n'
        '* `%s` —— 主程序（双击即开，免安装）\n'
        '* `%s` —— **必须和主程序放一起**：32 位加解密宿主（工具自带的，非游戏文件）\n'
        '* `%s` / `%s` —— 游戏自带的 32 位库，也可从自己游戏根目录复制\n'
        '* `%s` —— 使用说明\n\n'
        '> 附件名只能是 ASCII（GitHub 会剔除中文），跟仓库名 + 版本号保持一致；\n'
        '> 本地 dist\\ 里的 `%s` 是同一个文件。下载后改名不影响使用。\n'
        % (exe, host, tp, socket, usage, os.path.basename(b.RELEASE_ASSETS[0][0]))
    )
    return extra + ('\n---\n\n' + body + '\n' if body else '')


def main():
    argv = sys.argv[1:]
    dry = '--dry' in argv
    upload_only = '--upload-only' in argv
    print('版本 %s → tag %s' % (b.APP_VERSION, TAG))
    files = stage_assets()
    # notes 也放临时目录：仓库路径里的 `[]` 会让 gh 把 --notes-file 当 glob 处理
    notes = os.path.join(os.path.dirname(files[0]), '_notes.md')
    open(notes, 'w', encoding='utf-8').write(notes_text())

    if upload_only:
        cmd = ['gh', 'release', 'upload', TAG] + files + ['--clobber']
    else:
        cmd = ['gh', 'release', 'create', TAG,
               '--title', '%s —— 见下方更新日志' % TAG,
               '--notes-file', notes] + files
    print('将执行：gh release %s %s …' % ('upload' if upload_only else 'create', TAG))
    if dry:
        print('--dry，未执行')
        return 0
    p = subprocess.run(cmd, cwd=ROOT)
    if p.returncode != 0:
        print('[NG] gh 返回 %d（Release 已存在就加 --upload-only）' % p.returncode)
    return p.returncode


if __name__ == '__main__':
    sys.exit(main())
