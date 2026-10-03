# -*- coding: utf-8 -*-
r"""发 GitHub Release：按 `build.py` 里的命名规则准备好附件，再交给 `gh`。

    python tools/release.py                 # 创建/更新 v<当前版本> 的 Release
    python tools/release.py --upload-only   # Release 已存在，只重传附件
    python tools/release.py --dry           # 只打印要做什么，不动手

附件（**唯一来源在 tools/build.py 的 RELEASE_ASSETS**，别在这儿手敲）：
    huaji1-save-editor-vX.Y.Z.zip   一个包，里面是：
        画迹1存档工具.exe           主程序（本地产物固定叫这个名，不带版本号）
        XJCodec32.exe               32 位加解密宿主，缺了读不了存档
        TP.dll / Socket.dll         游戏自带库（版权归游戏原作者）
        使用说明.txt
    ⚠ 只传一个 zip：以前拆成 5 个附件，总有人只下 exe、漏了 XJCodec32.exe。

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
    """CHANGELOG 里本版本的那一段 + 两行下载说明（别啰嗦，附件本来就在 Assets 顶部）。"""
    body = ''
    path = os.path.join(ROOT, 'CHANGELOG.md')
    if os.path.exists(path):
        text = open(path, encoding='utf-8').read()
        head = text.find('## ' + TAG)
        if head >= 0:
            nxt = text.find('\n## ', head + 1)
            body = text[head:nxt if nxt > 0 else len(text)].rstrip()
    zipname = b.RELEASE_ASSETS[0][1]
    # 正文 = 更新总结打头（去掉 “## vX.Y.Z · 日期” 标题行），尾部免责 + 一行下载说明
    lines = body.split('\n')
    while lines and (lines[0].startswith('## ') or not lines[0].strip()):
        lines.pop(0)
    summary = '\n'.join(lines).strip()
    while summary.endswith('---'):
        summary = summary[:-3].rstrip()
    tail = (
        '\n---\n\n'
        '> ⚠️ 使用前请先自己备份 `Audio\\BGM\\sy.ogg`。本工具是第三方工具，'
        '与游戏作者无关；游戏本体及其素材版权归原作者所有。\n\n'
        '下载：只下 Assets 里的 **`%s`**（唯一附件），解压后双击 `%s` 即可；'
        '别只把 exe 单独拖出来，依赖要跟它在同一目录。\n'
        % (zipname, b.EXE_NAME + '.exe')
    )
    return (summary + '\n' if summary else '') + tail


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
