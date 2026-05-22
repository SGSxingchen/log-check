# 角色对话统计工具 - Web版

基于 Flask 的 Web 应用，提供可视化的日志分析界面。

## 快速开始

### 1. 启动服务器

**Windows 环境（推荐）：**
```batch
run_web.bat
```

或使用PowerShell：
```powershell
.\run_web.ps1
```

或直接运行：
```bash
python\python.exe web\app.py
```

**Linux/macOS 环境：**
```bash
./run_web.sh
```

或直接运行：
```bash
python3 web/app.py
```

### 2. 访问应用

打开浏览器访问: `http://localhost:5000`

### 3. 使用流程

1. **上传日志文件**
   - 点击或拖拽 `.txt` 格式的日志文件到上传区域
   - 支持最大 16MB 的文件

2. **查看统计结果**
   - **总计统计**：所有天的汇总数据（第一个表格）
   - **分天统计**：每一天的详细统计数据
   - 美观的表格展示，支持参与时长显示

3. **下载报告**
   - 点击"下载 Excel 报告"按钮
   - 获取详细的 `.xlsx` 统计报告（含每个角色的完整对话内容）

## 技术栈

- **后端**: Flask 3.0
- **前端**: HTML5 + CSS3 + JavaScript
- **数据处理**: 复用原有的日志解析模块
- **Excel生成**: openpyxl

## 项目结构

```
web/
├── app.py              # Flask 主应用
├── templates/          # HTML 模板
│   └── index.html      # 主页面
├── uploads/            # 上传文件临时存储（自动生成）
└── generated/          # 生成的Excel文件（自动生成）
```

## API 接口

### POST /api/upload
上传并分析日志文件

**请求**:
- Content-Type: multipart/form-data
- 参数: `file` (txt文件)

**响应**:
```json
{
  "success": true,
  "filename": "log.txt",
  "stats": [...],
  "download_id": "uuid",
  "excel_filename": "log.xlsx"
}
```

### GET /api/download/<download_id>/<filename>
下载生成的Excel文件

### POST /api/cleanup/<download_id>/<filename>
清理服务器上的临时文件

## 配置选项

在 `web/app.py` 中可修改：

```python
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 最大文件大小
```

## 功能特性

✅ 拖拽上传支持
✅ 总计统计 + 分天统计
✅ 实时处理进度提示
✅ 响应式设计，支持移动端
✅ 美观的渐变色界面
✅ 自动文件清理
✅ 错误处理和提示
✅ 支持参与时长统计（Format1/2/5）

## 部署说明

### Windows 部署

已包含内置Python解释器，直接运行启动脚本即可。

### Linux/macOS 部署

需要系统已安装 Python 3.8+：

```bash
# 安装依赖
pip3 install -r requirements_web.txt

# 启动服务器
./run_web.sh
```

### Docker 部署

```bash
# 构建镜像
docker build -t log-stats-web .

# 运行容器
docker run -d -p 5000:5000 log-stats-web
```

### 生产环境部署

使用 Gunicorn + Nginx：

```bash
# 安装 Gunicorn
pip3 install gunicorn

# 启动（4个worker进程）
gunicorn -w 4 -b 0.0.0.0:5000 web.app:app
```

## 注意事项

- 上传的文件会在处理后自动删除
- 生成的Excel文件在下载后需要手动清理（点击"重新上传"按钮）
- 服务器默认运行在 `0.0.0.0:5000`，可在局域网内访问
- 生产环境建议使用 Nginx 反向代理和 Gunicorn

## 依赖安装

**Windows:**
```bash
python\python.exe -m pip install -r requirements_web.txt
```

**Linux/macOS:**
```bash
pip3 install -r requirements_web.txt
```

依赖包:
- Flask==3.0.0
- Werkzeug==3.0.1
- openpyxl==3.1.2
