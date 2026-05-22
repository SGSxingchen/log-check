@echo off
chcp 65001 >nul
echo ================================
echo   角色对话统计工具 - Web版
echo ================================
echo.

echo 正在安装依赖...
python\python.exe -m pip install -q Flask==3.0.0 Werkzeug==3.0.1
echo.

echo ================================
echo   正在启动 Web 服务器...
echo ================================
echo.
echo 访问地址: http://localhost:5000
echo 按 Ctrl+C 停止服务器
echo.

python\python.exe web\app.py

pause
