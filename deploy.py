#!/usr/bin/env python3
"""
自动部署脚本 - 角色对话统计工具 Web 版
使用 paramiko 库进行 SSH 连接和文件传输
"""

import os
import sys
import time

try:
    import paramiko
    from scp import SCPClient
except ImportError:
    print("错误: 缺少必要的库")
    print("请先安装: pip install paramiko scp")
    sys.exit(1)

# 服务器配置
SERVER = "156.238.228.118"
PORT = 61149
USER = "root"
PASSWORD = os.environ.get("LOG_CHECK_DEPLOY_PASSWORD", "")
DEPLOY_DIR = "/root/log_check"

def create_ssh_client():
    """创建 SSH 客户端"""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        print(f"正在连接到服务器 {SERVER}:{PORT}...")
        if not PASSWORD:
            raise RuntimeError("请先设置环境变量 LOG_CHECK_DEPLOY_PASSWORD")
        client.connect(SERVER, port=PORT, username=USER, password=PASSWORD, timeout=10)
        print("✓ SSH 连接成功")
        return client
    except Exception as e:
        print(f"✗ SSH 连接失败: {e}")
        sys.exit(1)

def exec_command(client, command, description=""):
    """执行远程命令"""
    if description:
        print(f"  {description}")
    stdin, stdout, stderr = client.exec_command(command)
    exit_code = stdout.channel.recv_exit_status()

    output = stdout.read().decode('utf-8')
    error = stderr.read().decode('utf-8')

    if output:
        print(output)
    if error and exit_code != 0:
        print(f"错误: {error}")
        return False
    return True

def upload_files(client):
    """上传项目文件"""
    print("\n步骤 2/5: 上传项目文件...")

    # 需要上传的文件和目录
    files_to_upload = [
        ('app', True),  # (路径, 是否为目录)
        ('web', True),
        ('requirements.txt', False),
        ('requirements_web.txt', False),
        ('run_web.sh', False),
    ]

    optional_files = [
        ('CLAUDE.md', False),
        ('README.md', False),
    ]

    try:
        with SCPClient(client.get_transport(), progress=lambda x, y, z: None) as scp:
            for file_path, is_dir in files_to_upload:
                if os.path.exists(file_path):
                    print(f"  上传: {file_path}")
                    if is_dir:
                        scp.put(file_path, recursive=True, remote_path=DEPLOY_DIR)
                    else:
                        scp.put(file_path, remote_path=DEPLOY_DIR)
                else:
                    print(f"  警告: 文件不存在 {file_path}")

            # 上传可选文件
            for file_path, is_dir in optional_files:
                if os.path.exists(file_path):
                    print(f"  上传: {file_path}")
                    scp.put(file_path, remote_path=DEPLOY_DIR)

        print("✓ 文件上传完成")
        return True
    except Exception as e:
        print(f"✗ 文件上传失败: {e}")
        return False

def main():
    print("=" * 50)
    print("  开始部署 Web 应用到服务器")
    print("=" * 50)
    print(f"\n服务器: {SERVER}:{PORT}")
    print(f"部署目录: {DEPLOY_DIR}\n")

    # 创建 SSH 连接
    client = create_ssh_client()

    try:
        # 步骤 1: 创建部署目录并检查环境
        print("\n步骤 1/5: 创建部署目录并检查环境...")
        commands = [
            (f"mkdir -p {DEPLOY_DIR}", "创建部署目录"),
            ("python3 --version", "检查 Python 版本"),
            ("which pip3", "检查 pip3"),
        ]

        for cmd, desc in commands:
            if not exec_command(client, cmd, desc):
                print(f"警告: {desc} 失败")

        # 步骤 2: 上传文件
        if not upload_files(client):
            sys.exit(1)

        # 步骤 3: 安装依赖
        print("\n步骤 3/5: 安装 Python 依赖...")
        install_cmds = f"""
cd {DEPLOY_DIR}
python3 -m pip install --upgrade pip -q
python3 -m pip install -r requirements_web.txt -q
echo "✓ 依赖安装完成"
"""
        exec_command(client, install_cmds)

        # 步骤 4: 配置并启动 Web 服务
        print("\n步骤 4/5: 配置并启动 Web 服务...")
        start_service = f"""
cd {DEPLOY_DIR}
# 停止旧进程
pkill -f "web/app.py" 2>/dev/null || true
sleep 2

# 启动服务
nohup python3 web/app.py > web.log 2>&1 &
sleep 3

# 检查进程
if pgrep -f "web/app.py" > /dev/null; then
    echo "✓ Web 服务启动成功"
    echo "进程ID: $(pgrep -f 'web/app.py')"
else
    echo "✗ Web 服务启动失败"
    echo "=== 错误日志 ==="
    tail -n 20 web.log 2>/dev/null || echo "日志文件不存在"
    exit 1
fi
"""
        if not exec_command(client, start_service):
            print("\n请手动检查服务器上的日志文件:")
            print(f"  ssh -p {PORT} {USER}@{SERVER} 'tail -f {DEPLOY_DIR}/web.log'")
            sys.exit(1)

        # 步骤 5: 验证部署
        print("\n步骤 5/5: 验证部署结果...")
        time.sleep(2)

        verify_cmd = f"""
cd {DEPLOY_DIR}
if pgrep -f "web/app.py" > /dev/null; then
    echo "✓ 服务运行中"
    echo "进程: $(ps aux | grep 'web/app.py' | grep -v grep)"
    exit 0
else
    echo "✗ 服务未运行"
    exit 1
fi
"""
        exec_command(client, verify_cmd)

        # 部署完成
        print("\n" + "=" * 50)
        print("  部署完成！")
        print("=" * 50)
        print(f"\n📱 访问地址: http://{SERVER}:5000")
        print(f"\n📋 管理命令:")
        print(f"  查看日志: ssh -p {PORT} {USER}@{SERVER} 'tail -f {DEPLOY_DIR}/web.log'")
        print(f"  停止服务: ssh -p {PORT} {USER}@{SERVER} 'pkill -f web/app.py'")
        print(f"  重启服务: ssh -p {PORT} {USER}@{SERVER} 'cd {DEPLOY_DIR} && nohup python3 web/app.py > web.log 2>&1 &'")
        print(f"  查看进程: ssh -p {PORT} {USER}@{SERVER} 'ps aux | grep web/app.py'")
        print()

    except Exception as e:
        print(f"\n✗ 部署过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        client.close()

if __name__ == "__main__":
    main()
