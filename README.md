# SurgiAnnotate

本地优先的手术视频标注工作台，用于记录手术阶段（Phase）、动作（Task）、评分及关键帧。基于 Python、PyQt5、VLC 和 OpenCV，视频播放、标签选择、时间轴和标注记录集中在一个桌面窗口中。

**核心流程：打开视频 → 选择标签 → 按 `I` 记录开始 → 按 `O` 记录结束 → 自动保存。**

内置模板以眼科手术为例，可导入自己的 TXT 模板用于其他手术流程。视频和标注项目保存在本地，无需登录服务。

## 主要功能

| 功能 | 当前支持 |
| --- | --- |
| 阶段与动作 | 区间标注、重复标签、毫秒时间码、开始/结束提示、标签分组与编辑 |
| 视频定位 | 播放/暂停、倍速播放、逐帧定位、按秒跳转 |
| 多轨时间轴 | 阶段、动作和关键帧分轨显示，缩放、平移，与记录表双向选择 |
| 评分与关键帧 | 点击评分、记录预警时间点、保存当前画面、批量提取标注代表帧 |
| 记录管理 | 按标签/类型/备注筛选，编辑时间、同类标签、备注及审核状态，删除、撤销与重做 |
| 项目保存 | 自动保存、手动保存、上一个版本备份及损坏恢复，按视频指纹隔离病例目录 |
| 质量检查 | 时间范围、重复记录、评分有效性、必填标签、阶段覆盖/空档/重叠/顺序、动作所属阶段及关联画面 |
| 数据交换 | 项目 JSON、CSV、旧版 TXT 导入/导出，以及 LabelMe 画面联动 |
| 外观 | 临床浅色、临床深色、手术室低照度三种主题 |

## 安装与启动

需要 Python 3.8 或更高版本及桌面图形环境。Windows 源码目录附带 VLC 运行时；Python 与 VLC 运行时的架构需要一致。

### Windows：从源码启动

在项目根目录打开 PowerShell，使用独立虚拟环境安装。以下命令不需要激活虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe -m surgui
```

### macOS / Linux：从源码启动

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install .
.venv/bin/python -m surgui
```

这两个平台需要自行提供适配的 VLC/LibVLC 运行时；Qt Media 后备播放器的格式兼容性取决于系统解码器。仓库附带的 Windows DLL 不能用于 macOS 或 Linux。

如果只安装运行依赖，也可在相应 Python 环境执行：

```bash
python -m pip install -r requirements.txt
python -m surgui
```

安装为包后，也可使用 `surgui` 命令启动。播放器优先使用 VLC，无法使用时尝试 Qt Media；当前后端显示在视频工作台上方。

### 可选：LabelMe

在同一个 Python 环境中安装可选依赖：

```bash
python -m pip install ".[labelme]"
```

启动软件时将该环境的脚本目录加入 `PATH`（例如先激活虚拟环境），使程序能找到 `labelme` 命令。选中一条已关联画面的记录后，选择 **质量 → 用 LabelMe 打开选中画面**。普通视频标注不需要安装 LabelMe。

### Windows 便携版

如果拿到已打包的程序，运行 `SurgiAnnotate.exe`；较早的打包名称为 `vidPlayer_working.exe`。保留随包提供的 VLC DLL、`plugins/` 等运行时文件，解压到可写目录后运行。便携版的病例输出默认保存在可执行文件旁的 `outputs/`。

## 第一次标注

1. 选择 **文件 → 打开视频**，或按 `Ctrl+O`。文件选择器列出 MP4、AVI、MOV、MKV、MPEG、MPG 和 WMV，实际解码能力取决于播放器后端。
2. 在右侧“阶段”或“动作”页选择标签。新项目默认加载 `samples/phase.txt`、`samples/task.txt` 和 `samples/assessment.txt`；也可从“模板”菜单导入自己的模板。
3. 播放或定位到区间起点，按 `I`；到达终点后按 `O`。完成的标注进入记录表并触发自动保存。尚未按 `O` 的进行中区间不属于已完成标注。
4. 在“评分”页点击分值；在“关键帧”页记录时间点，或选择同时保存画面。按 `F` 可保存当前画面；当前选中关键帧标签时，会同时建立关联记录。
5. 在记录表中双击或按 `Enter` 编辑标注，可调整时间、同类标签、备注和“草稿 / 待审核 / 已审核”状态。选中时间轴标记也会选中对应记录。
6. 通过 **质量 → 数据检查** 查看问题。顶部进度显示阶段覆盖率和已审核记录数，悬停可查看草稿、待审核、错误和提示数量。
7. 按 `Ctrl+S` 立即保存。默认 `exports/` 会随保存刷新；需要另选导出目录时使用 **文件 → 导出数据**。手动导出遇到数据错误会要求先修复，提示项不会阻止导出。

当前同一时刻只能有一个进行中的区间。需要分别记录 Phase 与 Task 时，可先标完阶段，再回看视频标注动作；同一个标签可以记录多次。

继续上次工作时，可重新打开相同视频并选择继续已有项目，也可用 **文件 → 打开项目** 直接打开项目 JSON。视频移动后，打开项目时可重新选择视频位置。

## 快捷键与时间轴

| 快捷键 | 操作 |
| --- | --- |
| `Ctrl+O` / `Ctrl+Shift+O` | 打开视频 / 打开项目 |
| `Space` | 播放 / 暂停 |
| `←` / `→` | 前一帧 / 后一帧 |
| `Shift+←` / `Shift+→` | 后退 / 前进 1 秒 |
| `Ctrl+←` / `Ctrl+→` | 后退 / 前进 5 秒 |
| `I` / `O` | 记录当前区间的开始 / 结束 |
| `F` | 保存当前画面；选中关键帧标签时同时记录关键帧 |
| `Ctrl+S` | 立即保存 |
| `Ctrl+Z` / `Ctrl+Shift+Z` | 撤销 / 重做 |
| `Ctrl+E` | 导出数据 |
| `Enter` / `Delete` | 编辑 / 删除记录表中选中的标注 |
| `F1` | 查看快捷键 |
| `Ctrl+Q` | 退出 |

时间轴上使用 `Ctrl+滚轮` 缩放、`Shift+滚轮` 平移，也可使用右下方的前后和加减按钮。点击倍率按钮恢复完整时间轴。在输入框、筛选框或备注编辑器中，播放和标注快捷键会让位给文本输入。

## 项目、画面与导出

每个视频按“文件名 + 视频指纹”创建独立病例目录，避免同名视频共用项目：

```text
outputs/
└── video_name_fingerprint/
    ├── project.surgui.json
    ├── project.surgui.previous.json
    ├── images/
    └── exports/
        ├── annotations.csv
        ├── phase.txt
        ├── task.txt
        ├── assessment_scores.txt
        └── surgui_legacy_manifest.json
```

实际 TXT 文件名随项目分类而变化。默认输出位置如下；已通过 **文件 → 更改输出位置** 保存的设置会优先使用：

| 运行方式 | 默认输出位置 |
| --- | --- |
| 源码运行 | 项目根目录的 `outputs/` |
| Windows 便携版 | 可执行文件旁的 `outputs/` |
| pip 安装后在源码目录之外运行（Windows） | `%LOCALAPPDATA%\SurgiAnnotate\outputs\` |
| pip 安装后在源码目录之外运行（macOS） | `~/Library/Application Support/SurgiAnnotate/outputs/` |
| pip 安装后在源码目录之外运行（Linux） | `$XDG_DATA_HOME/SurgiAnnotate/outputs/`，未设置时为 `~/.local/share/SurgiAnnotate/outputs/` |

`project.surgui.json` 是无损项目数据源，包含视频信息、模板、标注、评分、审核状态和操作审计。保存使用原子写入，并保留上一个版本；主文件无法读取时会尝试从备份恢复并提示。项目通过路径引用原始视频，不会把视频嵌入 JSON；备份或转交病例时，应保留病例目录和对应原始视频。

CSV 使用 UTF-8 BOM 编码，一行一条标注，按开始时间排序。字段包括：

```text
project_id, video_file, annotation_id, kind, category, template_id,
label, start_ms, end_ms, start_timecode, end_timecode, frame, score,
status, note, asset_path, created_at, updated_at
```

其中 `kind` 为 `interval`、`point` 或 `rating`；`start_ms` / `end_ms` 以毫秒为单位，显示时间码为 `HH:MM:SS.mmm`；`status` 为 `draft`、`ready` 或 `reviewed`。不同类型的标注允许部分字段为空，画面路径相对于病例目录保存。

**质量 → 批量提取标注关键帧** 会为区间标注提取中间帧，为关键帧标注提取其记录时间处的画面，保存到 `images/` 并关联至记录。已有有效关联画面的记录会跳过；评分不参与提取。

CSV 和旧版 TXT 用于数据交换，不能替代完整项目备份。`surgui_legacy_manifest.json` 保存 TXT 与分类/类型之间的映射，迁移时应与 TXT 一起保留。

## 自定义模板

模板使用 UTF-8 编码的 TXT 文件。导入阶段和动作模板时，选择对应菜单或对应页面底部的“导入”，导入内容会追加到相应分类。

### 阶段 / 动作模板

每行一个标签，可在 `#` 后提供开始和结束提示；单独一行 `--` 表示新分组，`//` 开头的行作为注释：

```text
// 阶段示例
主切口 # 刀尖接触切口位置 # 切口完成
侧切口制作
--
IOL 植入 # 人工晶体进入前房 # 植入完成
```

阶段和动作页支持新增、编辑和删除标签。改名会同步已有标注的显示名称。被历史记录引用的标签不能直接删除；应先删除对应记录，或将记录改为其他同类标签。项目已有标注时不能用“恢复内置模板”覆盖模板，可继续追加导入。

### 评分 / 关键帧模板

```text
手术评分 # 5
视频评分 # 2
预警帧 # 0
```

正整数 `N` 表示可选分值为 `0` 到 `N-1`，因此 `# 5` 提供 0、1、2、3、4 五个选项。`# 0` 表示关键帧/预警标签，显示在“关键帧”页。通过 **模板 → 导入评分/关键帧模板** 导入。

## 从旧版 TXT 迁移

1. 打开对应视频，创建或载入项目，并确认相关标签已存在。
2. 选择 **文件 → 导入旧版 TXT 标注**，选中旧版数据所在目录；若有 manifest 映射文件，一并保留在该目录。
3. 查看迁移报告并核对区间、关键帧和评分。无法匹配的标签或非法时间会报告，不会静默改写。
4. 保存项目并运行数据检查，后续以项目 JSON 继续工作。

## 常见问题

- **没有画面或视频无法播放**：查看视频工作台上方的播放器名称；确认 VLC 运行时和 Python 的架构匹配，Windows 便携版的 DLL 和 `plugins/` 完整，或检查系统 Qt Media 解码器。
- **找不到标注结果**：查看窗口底部的输出路径。默认病例目录包含项目 JSON，`exports/` 包含自动同步的 CSV/TXT；也可在“文件”菜单更改输出位置。
- **已经按 `I`，记录表里还没有条目**：按 `O` 完成区间后才会建立标注；“取消”会放弃当前尚未完成的区间。
- **进度没有达到 100%**：顶部百分比衡量阶段对视频时长的覆盖，并不表示所有标签都已点击；审核状态需在记录编辑中设置。
- **LabelMe 无法打开**：确认选中记录已关联画面，画面文件仍存在，且当前进程的 `PATH` 能找到 `labelme`。

## 开发与验证

代码入口和主要文件：

```text
surgui/
├── __main__.py              # python -m surgui / surgui 命令入口
├── vidPlayer_working.py     # 当前工作台、播放器、时间轴与交互
├── project_store.py         # 项目存储、模板、数据检查与导入/导出
└── theme.py                 # 主题加载、样式与资源路径
samples/                    # 内置模板与示例素材
tests/                      # 存储、主题和界面交互回归测试
DESIGN*.md                  # 三种主题的设计 token
```

安装依赖后，在项目根目录运行现有回归测试与 Python 编译检查：

```bash
python -m unittest discover -s tests -q
python -m compileall -q surgui tests
```

主题通过 **视图 → 外观主题** 切换，权威定义位于 [临床浅色](DESIGN.md)、[临床深色](DESIGN.clinical-dark.md) 和 [手术室低照度](DESIGN.theatre-dim.md)。修改颜色、字体、间距和组件样式时，应同时核对这些定义及相关测试。

## 许可证

项目代码采用 [MIT License](LICENSE.txt)，保留原作者 Babak Namazi 的版权声明。随仓库提供的 VLC 及其他第三方组件遵循各自许可证；分发打包程序时需一并保留相应许可说明。
