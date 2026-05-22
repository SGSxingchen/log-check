#!/bin/bash
# systemd 服务安装脚本

echo "================================"
echo "  配置 systemd 系统服务"
echo "================================"
echo ""

# 1. 复制服务文件到 systemd 目录
echo "步骤 1: 安装服务文件..."
sudo cp log-check-web.service /etc/systemd/system/
sudo chmod 644 /etc/systemd/system/log-check-web.service

# 2. 重载 systemd 配置
echo "步骤 2: 重载 systemd 配置..."
sudo systemctl daemon-reload

# 3. 启用服务（开机自启）
echo "步骤 3: 启用开机自启..."
sudo systemctl enable log-check-web.service

# 4. 启动服务
echo "步骤 4: 启动服务..."
sudo systemctl start log-check-web.service

# 5. 检查服务状态
echo ""
echo "================================"
echo "  服务状态"
echo "================================"
sudo systemctl status log-check-web.service

echo ""
echo "================================"
echo "  配置完成！"
echo "================================"
echo ""
echo "常用管理命令:"
echo "  启动服务: sudo systemctl start log-check-web"
echo "  停止服务: sudo systemctl stop log-check-web"
echo "  重启服务: sudo systemctl restart log-check-web"
echo "  查看状态: sudo systemctl status log-check-web"
echo "  查看日志: sudo journalctl -u log-check-web -f"
echo "  开机自启: sudo systemctl enable log-check-web"
echo "  禁用自启: sudo systemctl disable log-check-web"
echo ""
