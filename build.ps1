# AutoClicker 打包腳本：PyInstaller 單檔 + SHA256
# 使用方式：在專案根目錄執行  powershell -ExecutionPolicy Bypass -File build.ps1
# 事前準備（需自行手動安裝，本腳本不會下載任何東西）：
#   pip install pyinstaller
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# 只做本機檢查與打包；無任何網路下載指令（無 Invoke-WebRequest / pip install）
python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "缺少 PyInstaller。請先手動執行：pip install pyinstaller（本腳本不自動下載）"
}

python -m PyInstaller --onefile --windowed --name AutoClicker `
    --add-data "examples;examples" `
    --exclude-module socket --exclude-module urllib `
    --exclude-module subprocess --exclude-module unittest `
    --clean --noconfirm main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 失敗（結束代碼 $LASTEXITCODE）" }

$exe = Join-Path $PSScriptRoot "dist\AutoClicker.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "找不到 $exe" }

# 排除清單驗證：產出檔不得連結網路模組（黑名單掃描）
$bytes = [System.IO.File]::ReadAllBytes($exe)
$text = [System.Text.Encoding]::ASCII.GetString($bytes)
foreach ($bad in @("urllib3", "wininet", "URLDownloadToFile", "InternetOpenA")) {
    if ($text.Contains($bad)) {
        Write-Warning "偵測到可疑字串：$bad（請人工確認是否為誤報）"
    }
}

$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
$hashFile = Join-Path $PSScriptRoot "dist\AutoClicker.exe.sha256"
"$hash  AutoClicker.exe" | Set-Content -LiteralPath $hashFile -Encoding ascii

Write-Host ""
Write-Host "打包完成：$exe"
Write-Host "SHA256  ：$hash"
Write-Host "已寫出  ：$hashFile"
