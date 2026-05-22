# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

角色对话统计工具，用于分析跑团日志文件并生成详细统计报告。支持5种日志格式，统计每个角色的发言数、字数、场外发言等，并导出为 Excel 和 CSV 格式。

**提供两种使用方式：**
- 💻 **命令行版本** (CLI): 传统命令行交互界面
- 🌐 **Web版本**: 可视化Web界面，支持拖拽上传和在线查看统计结果

## 运行命令

### Web版本（推荐）
```powershell
.\run_web.ps1
```
启动Web服务器后，访问 `http://localhost:5000` 即可使用。

特性：
- ✨ 拖拽上传日志文件
- 📊 可视化统计结果展示
- 📥 一键下载Excel报告
- 📱 响应式设计，支持移动端

详细说明请参考 `web/README.md`

### 命令行版本
```powershell
.\run.ps1
```
自动使用内置 Python 解释器 (`python\python.exe`)、安装依赖并运行程序。

### 直接运行
```bash
# Web版本
python\python.exe web\app.py

# 命令行版本
python\python.exe app/main.py          # 模块化版本（推荐）
python\python.exe app/app_legacy.py    # 单文件版本（备份）
```

### 安装依赖
```bash
# 命令行版本依赖
python\python.exe -m pip install -r requirements.txt

# Web版本依赖
python\python.exe -m pip install -r requirements_web.txt
```
依赖:
- 命令行版本: `openpyxl==3.1.2`
- Web版本: `Flask==3.0.0`, `Werkzeug==3.0.1`, `openpyxl==3.1.2`

## 项目结构（模块化）

```
app/                           # 核心逻辑模块（CLI和Web共用）
├── main.py                    # CLI程序入口
├── app_legacy.py              # 单文件版本备份
├── parser/                    # 日志解析模块
│   ├── format_detector.py     # 格式检测
│   └── log_parser.py          # 日志解析（核心）
├── output/                    # 输出生成模块
│   ├── excel_generator.py     # Excel报表
│   ├── csv_generator.py       # CSV报表
│   └── console_printer.py     # 终端输出
└── utils/                     # 工具函数
    └── text_utils.py          # 文本处理

web/                           # Web应用
├── app.py                     # Flask主应用
├── templates/                 # HTML模板
│   └── index.html             # 主页面
├── uploads/                   # 上传文件临时存储（自动生成）
├── generated/                 # 生成的Excel文件（自动生成）
└── README.md                  # Web版本文档

outputs/                       # CLI版输出文件目录（自动生成）
└── *.csv, *.xlsx              # 生成的统计报表

requirements.txt               # CLI版依赖
requirements_web.txt           # Web版依赖
run.ps1                        # CLI启动脚本
run_web.ps1                    # Web启动脚本
```

## 核心架构

### 日志格式检测（parser/format_detector.py）
支持5种格式自动检测:

- **format1**: `用户名(ID) YYYY-MM-DD HH:MM:SS`
- **format2**: `用户名(ID) YYYY/MM/DD HH:MM:SS`
- **format3**: `HH:MM:SS <用户名>消息内容` (无冒号)
- **format4**: `HH:MM:SS<用户名>:消息内容`
- **format5**: `用户名(ID) HH:MM:SS` (仅时间，无日期，AstralDice系骰子格式)

**特殊处理**：
- format5 自动过滤 `[mirai:` 开头的系统消息

### 字数计算权重（utils/text_utils.py）
- 汉字: 权重 4
- 其他字符: 权重 1

### 场外发言识别
检测括号 `（` 或 `(` 识别 OOC (Out of Character) 场外发言。

### 参与时长统计（parser/log_parser.py）

**支持 Format1/2/5** (带时间戳的格式)

**计算逻辑:**
```
参与时长 = Σ(所有 ≤ 阈值的发言间隔) + 5分钟
```

**详细说明:**
- 遍历所有相邻发言的时间间隔
- 如果间隔 **≤ 休息阈值**,将该间隔累加到参与时长
- 如果间隔 **> 休息阈值**,跳过该间隔(视为休息/离线)
- 最后一条消息额外给予5分钟活跃时间

**配置参数**（`app/parser/log_parser.py` 第12行）:
```python
IDLE_THRESHOLD_MINUTES = 10  # 超过10分钟无发言视为休息/摸鱼
```

**示例说明:**
假设某角色发言时间: 10:00, 10:05, 10:30, 10:35

- **阈值 = 10分钟:**
  - 10:00 → 10:05: 5分钟 (≤10分钟) → ✓ 计入
  - 10:05 → 10:30: 25分钟 (>10分钟) → ✗ 跳过(休息)
  - 10:30 → 10:35: 5分钟 (≤10分钟) → ✓ 计入
  - 最后消息: +5分钟
  - **参与时长 = 5 + 5 + 5 = 15分钟**

- **阈值 = 30分钟:**
  - 10:00 → 10:05: 5分钟 → ✓ 计入
  - 10:05 → 10:30: 25分钟 (≤30分钟) → ✓ 计入
  - 10:30 → 10:35: 5分钟 → ✓ 计入
  - 最后消息: +5分钟
  - **参与时长 = 5 + 25 + 5 + 5 = 40分钟**

**适用场景:**
- **机器人消息**: 自动过滤长时间间隔,只统计实际活跃时段
- **间断发言**: 适合统计有休息间隔的真实参与时间
- **跨天发言**: 自动识别并排除跨天休息时间

**调整建议:**
- `5-10分钟`: 严格模式,只统计连续对话时间
- `15-20分钟`: 标准模式,允许短暂思考/查资料
- `30-60分钟`: 宽松模式,允许较长的摸鱼时间

### 分天逻辑（parser/log_parser.py）

**混合分天策略**（适用于所有格式，解决熬夜开团问题）：

优先级顺序：
1. **分隔符检测**（最高优先级）
   - 检测明确的日志分隔符：`.log off`、`.logoff`、`===日志开始===`、`===日志结束===` 等
   - 支持中文句号变体：`。log off`、`。logoff`
   - 正则匹配：连续3个或以上等号包围的分隔符

2. **长时间间隔检测**
   - 默认阈值：超过 **6小时** 无发言视为新的一天
   - 可配置参数：`TIME_GAP_THRESHOLD_HOURS`（第9行）
   - 自动处理跨天情况（例如 23:00 → 次日 01:00）

**说明**：
- **Format1/2**：不再简单按日期字段变化分天，采用混合策略避免午夜自然跨天导致错误分天
- **Format3/4**：保留原有分隔符检测，新增长时间间隔检测
- **Format5**：采用混合策略，支持分隔符检测和长时间间隔检测

### 自动输出文件命名（main.py）

程序会根据输入日志文件名自动生成对应的输出文件名，并保存到 `outputs/` 文件夹：

**示例**：
- 输入: `logs/Jinbert-传说之路序章5月第1场 2025.05.24.txt`
- 自动生成:
  - `outputs/Jinbert-传说之路序章5月第1场 2025.05.24.csv`
  - `outputs/Jinbert-传说之路序章5月第1场 2025.05.24.xlsx`

**特殊情况**：
- 输入 `log.txt` → 输出 `outputs/对话统计.csv` 和 `outputs/对话统计.xlsx`

**输出文件夹配置**：
- 默认输出文件夹：`outputs/`（可在 `main.py` 第12行修改 `OUTPUT_DIR` 配置）
- 文件夹不存在时会自动创建

### 模块职责

**main.py**
- 程序入口，处理用户交互
- `OUTPUT_DIR`: 输出文件夹配置（默认 `outputs/`）
- `ensure_output_dir()`: 确保输出文件夹存在
- `generate_output_filename()`: 根据输入文件名生成输出文件名
- `find_log_files()`: 自动扫描当前目录和 `logs/` 目录中的 `.txt` 文件
- 支持文件编号快速选择

**parser/log_parser.py** (约550行，核心)
- `parse_log_file()`: 返回 (daily_stats, dialogue_contents)
- 状态机模式处理多行消息
- 混合分天策略：分隔符优先 + 长时间间隔检测
- 辅助函数：
  - `is_separator_line()`: 检测日志分隔符
  - `parse_datetime_format1_2()`: 解析完整日期时间
  - `should_split_day_by_time_gap()`: Format1/2 时间间隔判断
  - `parse_time_format3_4()`: 解析仅时间戳
  - `should_split_day_by_time_gap_format34()`: Format3/4 时间间隔判断
  - `parse_datetime_format5()`: 解析 Format5 时间戳
  - `should_split_day_by_time_gap_format5()`: Format5 时间间隔判断
  - `calculate_participation_time()`: 计算参与时长（扣除休息时间）

**output/excel_generator.py**
- 生成带样式的Excel: 统计表 + 每个角色对话内容工作表
- 场外内容使用黄色背景标识
- Excel工作表名限制: 去除 `[]:\*?/\\`，≤31字符

**output/csv_generator.py**
- 生成CSV统计，自动调用Excel生成器
- 包含总体统计和按日统计

**output/console_printer.py**
- 终端表格输出，正确处理中文显示宽度（汉字占2，其他占1）

**utils/text_utils.py**
- `count_char_weight()`: 汉字权重4，其他1
- `get_display_width()`, `pad_string()`: 中文对齐

## 使用说明

### 基本流程

1. **准备日志文件**
   - 将日志文件（`.txt` 格式）放入项目根目录或 `logs/` 文件夹
   - 支持的格式会自动检测

2. **运行程序**
   ```powershell
   .\run.ps1
   ```

3. **选择日志文件**
   - 程序会列出所有发现的日志文件
   - 输入文件编号（如 `1`、`2`）快速选择
   - 或输入完整文件路径

4. **自动生成报告**
   - CSV 文件：统计数据表格
   - Excel 文件：统计 + 每个角色的完整对话内容
   - 文件名自动使用日志文件名
   - **所有生成的文件保存在 `outputs/` 文件夹中**

### 配置参数

**分天时间阈值**（`app/parser/log_parser.py` 第9行）：
```python
TIME_GAP_THRESHOLD_HOURS = 6  # 超过6小时无发言视为分天
```
可根据实际需求调整，例如：
- `3`：3小时无发言就分天（适合短时段开团）
- `12`：12小时无发言才分天（适合长时段开团）

**参与时长休息阈值**（`app/parser/log_parser.py` 第12行）：
```python
IDLE_THRESHOLD_MINUTES = 10  # 超过10分钟无发言视为休息
```
可根据实际需求调整，例如：
- `5-10`：严格模式,只统计连续对话
- `15-20`：标准模式,允许短暂思考
- `30-60`：宽松模式,允许较长摸鱼

## 文件组织

- `app/`: 模块化代码
- `logs/`: 日志文件目录（输入）
- `outputs/`: 输出文件目录（自动创建，存放生成的 CSV 和 Excel 文件）
- `python/`: 内置Python解释器
- `requirements.txt`: 依赖 (openpyxl)
- `run.ps1`: 启动脚本

## 统计数据字段

### 输出报表包含以下字段:

**基础统计:**
- 角色名
- 总发言数 / 发言数
- 总字数 / 字数
- 平均字数
- 场外次数
- 场外字数

**参与时长** (Format1/2/5):
- 参与时长 (分钟)
- 显示格式: `Xh Ym` (小时+分钟) 或 `Ym` (仅分钟)
- 终端显示: `3h51m`, `14m`
- CSV/Excel: `3小时51分钟`, `14分钟`

## 常见问题

### Windows 编码问题

**问题现象**：
在 Windows 系统（包括 WSL）下运行时，可能遇到以下错误：
```
'gbk' codec can't encode character '\u2022' in position XX: illegal multibyte sequence
```

**原因**：
Windows 系统默认使用 GBK 编码，而 Python 的 `print()` 函数在 Windows 下会使用系统默认编码。当代码中包含特殊 Unicode 字符（如项目符号 •、表情符号等）时，GBK 编码无法表示这些字符，导致报错。

**解决方案**：
已在 **v3.1** 版本中修复，程序会自动检测 Windows 平台并强制使用 UTF-8 编码输出：

```python
# 在 main.py 和 web/app.py 开头自动执行
import sys
import io

if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
```

**手动修复**（针对旧版本）：
1. 在 PowerShell 中设置环境变量：
   ```powershell
   $env:PYTHONIOENCODING="utf-8"
   ```
2. 或在命令提示符中：
   ```cmd
   set PYTHONIOENCODING=utf-8
   ```

**适用环境**：
- Windows 10/11
- WSL (Windows Subsystem for Linux)
- Windows Server

## 更新日志

### v3.1 (2025-10-19)
- 🐛 **修复 Windows 编码问题**
  - 自动检测 Windows 平台并强制使用 UTF-8 编码
  - 修复 GBK 编码无法处理特殊 Unicode 字符的错误
  - 适用于 Windows、WSL 等环境
- 🔧 **修复模块导入问题**
  - 修复 `normalize_speaker_name` 函数导出缺失
  - 完善 `utils/__init__.py` 的导出列表
- 📝 更新文档，添加编码问题解决方案

### v3.0 (2025-10-17)
- ✨ **新增 Web 版本**
  - 基于 Flask 的 Web 应用
  - 支持拖拽上传日志文件
  - 可视化统计结果展示
  - 一键下载 Excel 报告
  - 响应式设计，支持移动端
  - 独立的 Web 文档 (`web/README.md`)
- 🏗️ 项目结构调整，核心逻辑模块 CLI 和 Web 共用
- 📝 更新项目文档，添加 Web 版本说明

### v2.3 (2025-10-17)
- ✨ 新增独立输出文件夹功能
  - 所有生成的文件自动保存到 `outputs/` 文件夹
  - 文件夹不存在时自动创建
  - 输出目录可通过 `OUTPUT_DIR` 配置调整
- 📝 更新文档说明，添加输出文件夹相关说明

### v2.2 (2025-10-17)
- ✨ 新增 Format5 格式支持 (AstralDice系骰子格式)
  - 格式：`用户名(ID) HH:MM:SS`
  - 自动过滤 `[mirai:` 开头的系统消息
  - 支持参与时长统计
  - 支持混合分天策略（分隔符 + 长时间间隔）
- 📝 更新文档说明，添加 Format5 相关配置

### v2.1 (2025-10-17)
- ✨ 新增参与时长统计功能 (仅支持 Format1/2)
  - 自动计算每个角色的实际参与时长
  - 智能扣除休息时间 (可配置阈值)
  - 在终端、CSV、Excel 中显示参与时长
- 📝 完善文档说明,添加参与时长配置说明

### v2.0 (2025-10-17)
- ✨ 新增混合分天策略，解决熬夜开团跨天问题
  - 优先检测日志分隔符
  - 支持长时间间隔自动分天（默认6小时）
- ✨ 自动输出文件命名功能
  - 根据输入日志文件名自动生成 CSV 和 Excel 文件
  - 无需手动输入输出文件名
- 🔧 优化代码结构，提取辅助函数
- 📝 完善文档说明
