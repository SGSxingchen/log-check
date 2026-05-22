#!/bin/bash
# 角色对话统计工具 - Web版启动脚本 (Linux/macOS)

echo "================================"
echo "  角色对话统计工具 - Web版"
echo "================================"
echo ""

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3"
    echo "请先安装 Python 3.8 或更高版本"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo "使用 Python: $PYTHON_VERSION"
echo ""

# 检查requirements_web.txt是否存在
if [ ! -f "requirements_web.txt" ]; then
    echo "错误: 未找到 requirements_web.txt"
    exit 1
fi

# 安装/更新依赖
echo "正在安装依赖..."
python3 -m pip install -q -r requirements_web.txt

if [ $? -eq 0 ]; then
    echo "依赖安装成功"
else
    echo "警告: 依赖安装可能存在问题，但将继续运行..."
fi

echo ""

# 检查web/app.py是否存在
if [ ! -f "web/app.py" ]; then
    echo "错误: 未找到 web/app.py"
    exit 1
fi

# 启动Web服务器
echo "================================"
echo "  正在启动 Web 服务器..."
echo "================================"
echo ""
echo "访问地址: http://localhost:5000"
echo "按 Ctrl+C 停止服务器"
echo ""

# 运行Flask应用
python3 web/app.py
