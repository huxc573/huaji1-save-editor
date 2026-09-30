# -*- coding: utf-8 -*-
"""1.4 附加实测：把 exe 拷到「游戏目录里没有可用的 Data/」的地方跑。

这就是别人报的那条故障场景 —— 技能名去读游戏目录的 `Data\\Skills.rxdata`，
读不了就抛 `MarshalError`、整个召唤兽页打不开。

沙箱里故意放一个**坏掉的** `Data/Skills.rxdata`（老代码读到它必炸），
然后断言打包版**照样给出真技能名**（说明 db_table 真的被打进 exe 了，
而且读文件失败时只降级、不报错）。
"""
import os
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                '..', 'src'))

from paths import game_dir as _game_dir          # noqa: E402

GAME = _game_dir()
REL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   'dist')
EXE = os.path.join(REL, '画迹1存档工具.exe')
SAVE = os.path.join(GAME, 'Audio', 'BGM', 'sy.ogg')

BAD = ('PYTHONHOME', 'PYTHONPATH', 'PYTHONSTARTUP', 'PYTHONEXECUTABLE',
       'VIRTUAL_ENV', 'UV_PROJECT' + '_ENVIRONMENT')

FAILS = []


def check(name, ok, extra=''):
    print('%-46s %s %s' % (name, 'OK' if ok else '失败', extra))
    if not ok:
        FAILS.append(name)


def main():
    for f in (EXE, SAVE):
        if not os.path.exists(f):
            print('缺少文件（先跑 tools/build.py）:', f)
            return 1

    # ---- 沙箱自证：这份坏文件本身确实是"读不了"的 ----
    import marshal_ruby as M
    bad_bytes = b'\xff' * 64
    try:
        M.parse_stream(bad_bytes)
        check('沙箱里的坏 Skills.rxdata 真能读坏（否则这条测试没意义）', False)
    except Exception as e:
        check('沙箱里的坏 Skills.rxdata 真能读坏（否则这条测试没意义）', True,
              type(e).__name__)

    dst = os.path.join(tempfile.gettempdir(), 'xj140_no_data')
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(os.path.join(dst, 'Audio', 'BGM'))
    os.makedirs(os.path.join(dst, 'Data'))
    shutil.copytree(REL, dst, dirs_exist_ok=True)
    shutil.copyfile(SAVE, os.path.join(dst, 'Audio', 'BGM', 'sy.ogg'))
    with open(os.path.join(dst, 'Data', 'Skills.rxdata'), 'wb') as f:
        f.write(bad_bytes)
    # 别让 last_save.txt 把真档指出来（否则测的就不是沙箱了）
    for n in ('last_save.txt', 'selftest_result.txt', 'error.log'):
        p = os.path.join(dst, n)
        if os.path.exists(p):
            os.unlink(p)
    open(os.path.join(dst, 'Game.exe'), 'wb').write(b'MZ')
    print('临时目录（Data/Skills.rxdata 是坏的）:', dst)

    env = dict(os.environ)
    env['XJ_GAME'] = dst
    env['XJ_SELFTEST'] = '1'
    for k in BAD:
        env.pop(k, None)

    # ⚠ 必须跑**沙箱里那份** exe：跑 dist 里那份的话 app_dir() 还是 dist，
    #   上次的 last_save.txt 会把真档指出来，测的就不是沙箱了。
    proc = subprocess.Popen([os.path.join(dst, os.path.basename(EXE)),
                             os.path.join(dst, 'Audio', 'BGM', 'sy.ogg')],
                            stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                            cwd=dst, env=env)
    res = os.path.join(dst, 'selftest_result.txt')
    deadline = time.time() + 180
    while time.time() < deadline and not os.path.exists(res):
        time.sleep(0.5)
    time.sleep(1)
    subprocess.run(['taskkill', '/f', '/t', '/pid', str(proc.pid)],
                   capture_output=True)

    if not os.path.exists(res):
        check('打包版生成了 selftest_result.txt', False)
        el = os.path.join(dst, 'error.log')
        if os.path.exists(el):
            print('---- error.log ----')
            print(open(el, encoding='utf-8', errors='replace').read()[:1200])
        return 1

    txt = open(res, encoding='utf-8', errors='replace').read()
    for ln in txt.splitlines():
        if any(k in ln for k in ('名字表', '技能名自检', '结果:', '存档:')):
            print('   ' + ln)

    check('打包版生成了 selftest_result.txt', True)
    check('自检整体结果 = OK', '结果: OK' in txt)
    # 关键：读到的是沙箱里那份副本，不是真档
    check('读的是沙箱副本（不是真档）',
          os.path.join('xj140_no_data', 'Audio') in txt)
    # 关键：名字来自内置表 —— 老版本这里会抛 MarshalError
    check('技能名 1 = 嗜血追击（内置表）', '技能名自检: 1=嗜血追击' in txt)
    check('技能名 9 = 死亡召唤（内置表）', '9=死亡召唤' in txt)
    check('技能 9 的描述也出得来（内置表）', '9的描述=物理式技能' in txt)
    check('没退化成占位名「技能N」', '技能1 /' not in txt and ' 9=技能9' not in txt)
    check('坏文件被记下来但没让程序崩',
          '名字表: 内置 db_table' in txt)

    print()
    if FAILS:
        print('===== 打包版·无 Data 目录测试：有失败（%d 项）=====' % len(FAILS))
        for f in FAILS:
            print('  -', f)
        return 1
    print('===== 打包版·无 Data 目录测试：通过 =====')
    return 0


if __name__ == '__main__':
    sys.exit(main())
