# 画迹1：落日情缘 存档工具（huaji1-save-editor）

> 一个针对 RPG Maker XP 游戏《画迹1：落日情缘》的**存档查看 / 修改器**。
> 直接解密游戏存档、用界面改金钱/角色/召唤兽/物品栏/开关变量，再加密写回。
>
> 作者 **[@huxc573](https://github.com/huxc573)** · 开源协议 **MIT** ·
> 最新版本 **v1.1**

<!-- 徽章位（发布后可按需补上） -->
![platform](https://img.shields.io/badge/platform-Windows%20x64-lightgrey)
![python](https://img.shields.io/badge/python-3.10%2B-blue)
![license](https://img.shields.io/badge/license-MIT-green)

---

## 目录

* [这是什么](#这是什么)
* [功能一览](#功能一览)
* [下载与使用](#下载与使用)
* [常见问题](#常见问题)
* [它怎么工作的](#它怎么工作的)
* [从源码构建](#从源码构建)
* [仓库结构](#仓库结构)
* [文档](#文档)
* [版本历史](#版本历史)
* [免责声明](#免责声明)

---

## 这是什么

《画迹1：落日情缘》是 RPG Maker XP 做的游戏。它的存档是：

```
<游戏目录>\Audio\BGM\sy.ogg      ← 名字伪装成背景音乐，其实是加密存档
```

本工具把这份存档解密成明文（19 个 Ruby Marshal 对象），让你在图形界面里查看、
修改，然后重新加密写回。**不需要安装 Ruby、不需要懂脚本、不需要改游戏文件。**

技术要点：

* 容器 = `0D 0F 3E 03` 魔数 + 4 字节长度 + zlib(密文)，密文由游戏自带的
  `TP.dll`（导出 `DS1`/`DS2`）加解密；
* `TP.dll` / `Socket.dll` 是 **32 位**库，程序随包带一个自写的 32 位宿主
  `XJCodec32.exe` 中转，所以 **64 位系统上也不弹黑框、不用 PowerShell**；
* 写入时只重编码"改动过的字段"的字节区间，其余原样保留 —— 不会破坏
  Ruby Marshal 的对象链接（`@N`）和 `RPG::Table` 之类的二进制块。

## 功能一览

| 页签 | 能做什么 |
|---|---|
| **概览 / 快捷修改** | 存档概况（格式/大小/MD5/游戏时间/机器码）；金钱（元宝）、声望、仓库金额、步数 |
| **全部解析数据** | 19 个顶层对象**全量**树形浏览：字段 / 类型 / 值 / **注释** 四列；<br>全局搜索（搜字段名或值）→ 双击结果**跳到树上**；右键改任意标量字段 |
| **角色 / 召唤兽** | **人物**：等级（自动同步经验）、经验、HP/SP、活力/体力、五维、潜力、附加属性；<br>**召唤兽**：成长 / 忠诚 / 六项资质 / 携带等级 / 技能（学会·忘掉·清空・**克隆**，带搜索，**表格显示技能描述**）<br>改名：【设为显示名(@new_name)】【改基础名(@name)】【恢复模板本名】<br>召唤兽列表顺序**与游戏界面一致**，已放生的默认隐藏（可勾选显示） |
| **物品栏 (道具/行囊/备用)** | 游戏里的三个 20 格容器（`@pack` / `@wallet` / `@talisman`）；<br>格子 / 数量 / 物品id / 品质 一体写入；搜索过滤物品；<br>新物品会**自动登记进 `$data_items`**（不登记游戏会提示"该物品无法使用"）；<br>「一键修复异常格」救回被写坏的格子 |
| **开关 / 变量** | 双击切换 `$game_switches` / `$game_variables` |
| **机器码** | 查看存档机器码 & 本机机器码；换电脑时一键填入本机（否则读档会提示"存档的主人不是你"） |
| **说明 / 机制** | 内置的格式与机制说明 |
| **更新日志** | 各版本改了什么 |

写回时会：**自动备份** `sy.ogg.bak` → 重新加密写回 → **重新解密读回校验**。

## 下载与使用

1. 到 [Releases](../../releases/latest) 下载全部 5 个附件：

   | 下载文件名（ASCII） | 页面显示名 | 说明 |
   |---|---|---|
   | `huaji1-save-editor-v1.1.exe` | 画迹1存档工具v1.1.exe | 主程序 |
   | `XJCodec32.exe` | XJCodec32.exe | 必需的 32 位加解密宿主 |
   | `TP.dll` / `Socket.dll` | 同名 | 游戏自带库（版权归游戏原作者），也可从自己游戏根目录复制 |
   | `USAGE.txt` | 使用说明.txt | 中文说明书 |

   > Release 附件的**文件名只能是 ASCII**（GitHub 会把非 ASCII 字符剔掉，
   > 中文名放在页面的 Label 一列）。下载后改名不影响使用。
2. 把这 5 个文件放到同一个文件夹；
3. 先**自己备份**一份 `Audio\BGM\sy.ogg`；
4. **退出游戏**，双击 exe → 【选择存档…】选中 `Audio\BGM\sy.ogg`；
5. 改完点【保存修改(Ctrl+S)】→ 进游戏确认。

> 程序启动时会自动找"上次打开过的存档"，所以第二次用一般直接就有内容。
> 也可以把 exe 直接丢进游戏根目录旁边用，程序会向上找 `Audio/BGM/sy.ogg`。

**系统要求**：Windows 10/11 x64。不需要安装 Python 或任何运行库。

## 常见问题

| 现象 | 原因 / 解决 |
|---|---|
| 保存失败 | 游戏还开着，文件被占用 → 先退出游戏 |
| 打开报"找不到 TP.dll" | 把游戏根目录的 `TP.dll`、`Socket.dll` 复制到程序旁边 |
| 读档提示"存档的主人不是你" | 换电脑了 → 【机器码】页点【填入本机机器码】再保存 |
| 游戏里打开**召唤兽**界面弹 `NoMethodError: undefined method '[]' for nil:NilClass` | 召唤兽的 `@name` 被改成了 `$pet` 名字表外的值。到【角色 / 召唤兽】页点【一键修复名字】 |
| 游戏里点物品提示"该物品无法使用！再试也不能用，233333" | 物品实例没登记进 `$data_items`。到物品栏点【一键修复异常格】 |
| 改了第 1 格物品，第 2 格图标也变了 | 旧版本（0.4 及以前）的对象链接 bug。用 0.5+ 重写一次物品栏即可 |

更详细的排查过程见 [`docs/排错指南.md`](docs/排错指南.md)。

## 它怎么工作的

```
sy.ogg
  └─ 去掉容器头(0D 0F 3E 03 + 长度) → zlib 解压 → 密文
        └─ TP.dll!DS2(文件, 口令 "xjy.11") → 明文
              └─ 19 个 Ruby Marshal 对象首尾相接：
                 characters, frame_count, $game_system, $game_switches,
                 $game_variables, $game_self_switches, $game_screen,
                 $game_actors, $game_party, $game_troop, $game_map,
                 $game_player, $data_items, $data_classes, $data_weapons,
                 $data_armors, $data_actors, $data, $存档id
```

修改流程（**只打差分补丁**，最大程度不动原字节）：

```
解析（记录每个字段在明文里的字节区间）
  → 改某个字段时只把那个区间重新编码
  → 按原始偏移升序重放回明文
  → 整体重写（物品格 / 角色对象）时把对象链接全部展开成独立副本，编号自洽
  → TP.dll!DS1 加密写回 → 重新解密读回逐字节校验
```

三处最容易写坏存档的坑（都在代码注释里写清楚了原因）：

1. **Marshal 对象链接 `@N`** —— 同一个对象第二次出现只写一个编号；
   动了一个对象内部的成员数量，后面所有编号都会错位 →
   凡是"整块替换"都用 `PatchEngine.replace_tree` / `replace_object` 重写。
2. **物品必须登记进 `$data_items`** —— 游戏用实例的 `@id` 去查 `occasion`，
   查不到就判"该物品无法使用"。
3. **召唤兽的 `@name` 必须在游戏的 `$pet` 名字表里** ——
   游戏 5 处无 nil 判断地执行 `$pet["#{名字}"][7]`。

## 从源码构建

```powershell
# 1) 依赖：Python 3.10+、PyInstaller；（可选）想让测试跑起来还需要 uv/venv
pip install pyinstaller

# 2) 让脚本知道游戏在哪（游戏目录 = 含 Game.exe 的那层）
$env:XJ_GAME = "D:\Games\画迹1：落日情缘"

# 3) 打包（会自动用 csc.exe 编译 32 位宿主，再从游戏目录复制 TP.dll/Socket.dll）
python tools/build.py

# 只看产物准备、不打包：
python tools/build.py --nopack
```

产物在 `dist/`。运行测试：

```powershell
$env:XJ_GAME = "D:\Games\画迹1：落日情缘"
python tests/test_pets.py      # 召唤兽：顺序 / 放生 / 改名 / $pet 名字表
python tests/test_skills.py    # 技能增删
python tests/test_pack.py      # 物品栏
python tests/test_registry.py  # 物品登记（$data_items）
python tests/test_link_safe.py # Marshal 对象链接安全
python tests/test_edit.py      # 端到端编辑 + 结构对比
python tests/test_gui.py       # 界面冒烟（8 个页签全建一遍）
```

> 测试会**复制**一份存档到临时文件再改，不会动你的 `sy.ogg`。

## 仓库结构

```
huaji1-save-editor/
├─ src/                     应用本体（PyInstaller 的入口也在这里）
│  ├─ xj_viewer.py          tkinter 界面（8 页签）
│  ├─ xj_model.py           游戏语义层 Doc：角色/召唤兽/物品栏/开关/保存 + 字段注释表
│  ├─ xj_edit.py            写入引擎：区间补丁、整块重写、物品实例构造
│  ├─ xj_marshal.py         Ruby Marshal 解析/序列化（对象编号规则与 Ruby 对齐）
│  ├─ xj_codec.py           容器解析、TP.dll 加解密、32 位宿主桥、LockNumber
│  ├─ xj_env.py             开发期辅助：定位游戏目录、sys.path 引导
│  ├─ pet_table.py          $pet 名字表（由 tools/gen_pet_table.py 从游戏脚本生成）
│  ├─ XJCodec32.cs/.exe     32 位加解密宿主（源码 + 预编译）
├─ tools/                   构建与维护脚本
│  ├─ build.py              一键打包
│  ├─ build_host.py         只编译 32 位宿主
│  ├─ gen_pet_table.py      从游戏脚本重新生成 pet_table.py
│  └─ repair_pet_names.py   一次性修复：把召唤兽 @name 改回模板本名
├─ tests/                   pytest 风格的独立测试脚本（自带断言与统计）
├─ probes/                  逆向探针：扫脚本关键词、对比存档结构、导出物品表
├─ docs/                    开发辅助文档（见下）
├─ 使用说明.txt             随 exe 分发的说明书
├─ CHANGELOG.md             0.1 ~ 1.0 的完整变更记录
├─ LICENSE                  MIT（只覆盖本仓库自己写的代码）
├─ NOTICE.md                授权范围与例外：游戏素材 / 反编译脚本 / 附带的 dll
└─ README.md
```

## 文档

| 文档 | 内容 |
|---|---|
| [`docs/开发指南.md`](docs/开发指南.md) | 环境搭建、模块职责、数据流、加新功能的步骤、打包踩坑 |
| [`docs/存档格式.md`](docs/存档格式.md) | 容器 / 加密 / Marshal 4.8 / 对象链接 / LockNumber / 机器码 / 19 个顶层对象 |
| [`docs/机制笔记-物品栏.md`](docs/机制笔记-物品栏.md) | 三个 20 格容器、物品实例字段、`$data_items` 登记、不可叠加判定 |
| [`docs/机制笔记-角色与召唤兽.md`](docs/机制笔记-角色与召唤兽.md) | 人物 vs 召唤兽、`@babys` 顺序、放生、技能、**`$pet` 名字表**、改名 |
| [`docs/排错指南.md`](docs/排错指南.md) | 游戏报错的行号怎么换算、`nil[...]` 怎么追、常见坑速查 |
| [`docs/逆向过程与工具.md`](docs/逆向过程与工具.md) | 怎么拿到脚本明文、怎么写探针、`probes/` 里每个脚本干什么 |

## 版本历史

> 0.1 ~ 0.7 是开发期的内部迭代（当时用的是 v1.0 ~ v1.2.5 的编号），
> **v1.0 是整理后对外发布的第一个版本**。完整记录见 [`CHANGELOG.md`](CHANGELOG.md)。

| 版本 | 主要变化 |
|---|---|
| **1.3.1** | 修 v1.3 的【克隆技能…】报 `TclError: bad window path name`（按钮回调里同步销毁窗口） |
| **1.3** | 新功能：召唤兽**技能克隆**（把一只的整张技能表复制给另一只，源不变） |
| **1.2** | 修召唤兽列表少一只（`$game_actors.@data[槽位]` 可能是 `'@N'` 链接）；召唤兽技能表新增「技能描述」列，搜索技能也能按描述搜 |
| **1.1** | 修 3 个真 bug：改金钱报 `未知类型 't'`；负数被读错导致改名/改技能时静默改坏存档；有循环引用的存档改名/改技能报「序列化嵌套过深」 |
| **1.0** | 召唤兽改名安全阀：`$pet` 名字表校验 + 一键修复；修掉"整体重写对象后再改内部字段报错" |
| 0.7 | 召唤兽按游戏界面顺序、隐藏已放生、可改名；解析页加注释列 |
| 0.6 | 人物 / 召唤兽分开；召唤兽技能增删；解析页全局搜索 + 双击跳转 |
| 0.5 | 修掉"物品无法使用"的真凶（对象链接错位）；物品登记进 `$data_items`；三个容器 |
| 0.4 | 修好物品缺 `@quality` 导致"无法使用"；操作后立即刷新 |
| 0.3 | 自带 32 位宿主（不再用 PowerShell）；上线修改功能 |
| 0.2 | 独立只读查看器 exe |
| 0.1 | 首个可读可写编辑器（需在游戏目录内跑） |

## 免责声明

* 本工具是**第三方**存档编辑器，与游戏作者、发行方**无关**，也未获其授权。
* 游戏本体及任何素材（`Game.exe`、`*.dll`、`Audio/`、`Graphics/`、`Data/*.rxdata` 等）
  的版权归游戏原作者所有；本仓库**不含**这些文件（Release 里附带的
  `TP.dll` / `Socket.dll` 仅为本作运行所必需，请自行判断是否取用）。
* 游戏脚本的反编译产物版权同样归原作者，本仓库不包含它们，
  文档里只记录**我们自己分析得出的结论**。
* 修改存档有风险（可能损坏存档或触发游戏内的异常），请务必先备份。
  作者不对任何数据丢失或后果负责。
* 本仓库**自己编写的代码**以 [MIT 协议](LICENSE) 开源，欢迎 issue / PR。
  授权范围与例外（游戏素材、反编译脚本、附带的 dll）见 [`NOTICE.md`](NOTICE.md)。
