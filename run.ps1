# 设置当前目录为脚本所在目录
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -Path $scriptPath

Write-Host "Current directory: $PWD" -ForegroundColor Green
Write-Host ""

# 使用项目内置的Python解释器路径
$pythonPath = Join-Path -Path $PWD -ChildPath "python\python.exe"
Write-Host "Using Python: $pythonPath" -ForegroundColor Cyan
Write-Host ""

Write-Host "Installing dependencies..." -ForegroundColor Cyan
& $pythonPath -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
Write-Host ""

Write-Host "Running program..." -ForegroundColor Cyan
& $pythonPath ./app/main.py
Write-Host ""

Write-Host "Completed!" -ForegroundColor Green
Read-Host -Prompt "Press Enter to exit" 