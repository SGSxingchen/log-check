#!/bin/bash
# 自动部署脚本 - 角色对话统计工具 Web 版

SERVER="156.238.228.118"
PORT="61149"
USER="root"
PASSWORD="kijtLQWT1542"
DEPLOY_DIR="/root/log_check"

echo "================================"
echo "  开始部署 Web 应用到服务器"
echo "================================"
echo ""
echo "服务器: $SERVER:$PORT"
echo "部署目录: $DEPLOY_DIR"
echo ""

# 1. 测试连接并创建目录
echo "步骤 1/5: 创建部署目录..."
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -p $PORT $USER@$SERVER << 'EOF'
mkdir -p /root/log_check
echo "部署目录已创建: /root/log_check"
python3 --version
EOF

if [ $? -ne 0 ]; then
    echo "错误: SSH 连接失败"
    exit 1
fi

echo ""
echo "步骤 2/5: 上传项目文件..."

# 2. 上传必要的文件
# 创建临时目录存放需要上传的文件
TEMP_DIR=$(mktemp -d)
echo "创建临时目录: $TEMP_DIR"

# 复制需要的文件
cp -r app "$TEMP_DIR/"
cp -r web "$TEMP_DIR/"
cp requirements.txt "$TEMP_DIR/"
cp requirements_web.txt "$TEMP_DIR/"
cp run_web.sh "$TEMP_DIR/"
cp CLAUDE.md "$TEMP_DIR/" 2>/dev/null || true
cp README.md "$TEMP_DIR/" 2>/dev/null || true

# 上传文件
sshpass -p "$PASSWORD" scp -o StrictHostKeyChecking=no -P $PORT -r "$TEMP_DIR"/* $USER@$SERVER:$DEPLOY_DIR/

if [ $? -ne 0 ]; then
    echo "错误: 文件上传失败"
    rm -rf "$TEMP_DIR"
    exit 1
fi

echo "文件上传成功"
rm -rf "$TEMP_DIR"

echo ""
echo "步骤 3/5: 安装 Python 依赖..."

# 3. 安装依赖
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -p $PORT $USER@$SERVER << 'EOF'
cd /root/log_check
python3 -m pip install --upgrade pip
python3 -m pip install -r requirements_web.txt
echo "依赖安装完成"
EOF

echo ""
echo "步骤 4/5: 配置 Web 服务..."

# 4. 创建 systemd 服务文件（可选）或使用 screen/nohup
sshpass -p "$PASSWORD" ssh -o StrictHostKeyChecking=no -p $PORT $USER@$SERVER << 'EOF'
cd /root/log_check

# 停止已有的进程
pkill -f "web/app.py" 2>/dev/null || true
sleep 2

# 使用 nohup 后台运行
nohup python3 web/app.py > web.log 2>&1 &
echo "Web 服务已启动（后台运行）"
echo "日志文件: /root/log_check/web.log"

# 等待服务启动
sleep 3

# 检查进程
if pgrep -f "web/app.py" > /dev/null; then
    echo "✓ Web 服务运行正常"
    echo "访问地址: http://156.238.228.118:5000"
else
    echo "✗ Web 服务启动失败，请检查日志"
    tail -n 20 web.log
    exit 1
fi
EOF

echo ""
echo "步骤 5/5: 验证部署..."

# 5. 测试服务是否正常
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://156.238.228.118:5000/ > /dev/null 2>&1
HTTP_CODE=$?

echo ""
echo "================================"
echo "  部署完成！"
echo "================================"
echo ""
echo "访问地址: http://156.238.228.118:5000"
echo ""
echo "管理命令:"
echo "  查看日志: ssh -p $PORT $USER@$SERVER 'tail -f $DEPLOY_DIR/web.log'"
echo "  停止服务: ssh -p $PORT $USER@$SERVER 'pkill -f web/app.py'"
echo "  重启服务: ssh -p $PORT $USER@$SERVER 'cd $DEPLOY_DIR && nohup python3 web/app.py > web.log 2>&1 &'"
echo ""
