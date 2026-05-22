# 角色对话统计工具 - Web版启动脚本
# 设置控制台编码为UTF-8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "================================" -ForegroundColor Cyan
Write-Host "  角色对话统计工具 - Web版" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

# 设置Python路径
$pythonPath = ".\python\python.exe"

# 检查Python是否存在
if (-Not (Test-Path $pythonPath)) {
    Write-Host "错误: 未找到 Python 解释器" -ForegroundColor Red
    Write-Host "请确保 python\python.exe 存在" -ForegroundColor Yellow
    pause
    exit 1
}

Write-Host "使用 Python: $pythonPath" -ForegroundColor Green
Write-Host ""

# 检查requirements_web.txt是否存在
if (-Not (Test-Path "requirements_web.txt")) {
    Write-Host "错误: 未找到 requirements_web.txt" -ForegroundColor Red
    pause
    exit 1
}

# 安装/更新依赖
Write-Host "正在安装依赖..." -ForegroundColor Yellow
try {
    & $pythonPath -m pip install -q -r requirements_web.txt
    if ($LASTEXITCODE -eq 0) {
        Write-Host "依赖安装成功" -ForegroundColor Green
    } else {
        Write-Host "警告: 依赖安装可能存在问题，但将继续运行..." -ForegroundColor Yellow
    }
} catch {
    Write-Host "警告: 依赖安装出错，但将继续运行..." -ForegroundColor Yellow
    Write-Host $_.Exception.Message -ForegroundColor Red
}

Write-Host ""

# 检查web/app.py是否存在
if (-Not (Test-Path "web\app.py")) {
    Write-Host "错误: 未找到 web\app.py" -ForegroundColor Red
    pause
    exit 1
}

# 启动Web服务器
Write-Host "================================" -ForegroundColor Cyan
Write-Host "  正在启动 Web 服务器..." -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "访问地址: http://localhost:5000" -ForegroundColor Green
Write-Host "按 Ctrl+C 停止服务器" -ForegroundColor Yellow
Write-Host ""

# 运行Flask应用
try {
    & $pythonPath web\app.py
} catch {
    Write-Host ""
    Write-Host "错误: 服务器启动失败" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    pause
    exit 1
}

Write-Host ""
Write-Host "服务器已停止" -ForegroundColor Yellow
pause
