# AutoClicker 打包腳本：PyInstaller 單檔 + SHA256
# 使用方式：在專案根目錄執行  powershell -ExecutionPolicy Bypass -File build.ps1
# 事前準備（需自行手動安裝，本腳本不會下載任何東西）：
#   pip install -r requirements-build.txt
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

# 只做檢查，不自動安裝／下載任何相依套件。
python -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    throw "缺少 PyInstaller，請先手動安裝：pip install -r requirements-build.txt（本腳本不會自動下載任何東西）"
}

# 不可加上 --exclude-module urllib / socket / subprocess 等排除參數：
# PyInstaller 6.x 的 runtime hook（pyi_rth_inspect 等）會 import urllib，
# 一旦排除，產物啟動時會直接出現「No module named 'urllib'」而開不了 GUI。
# 原始碼本身零網路、零程序執行呼叫，由 tests/test_security.py 的 AST 掃描把關。
python -m PyInstaller --onefile --windowed --name AutoClicker `
    --add-data "examples;examples" `
    --clean --noconfirm main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller 建置失敗（退出碼 $LASTEXITCODE）" }

$exe = Join-Path $PSScriptRoot "dist\AutoClicker.exe"
if (-not (Test-Path -LiteralPath $exe)) { throw "找不到 $exe" }

# 產物內容檢查（僅提示，不阻擋）：確認未混入常見的網路下載字串。
$bytes = [System.IO.File]::ReadAllBytes($exe)
$text = [System.Text.Encoding]::ASCII.GetString($bytes)
foreach ($bad in @("urllib3", "wininet", "URLDownloadToFile", "InternetOpenA")) {
    if ($text.Contains($bad)) {
        Write-Warning "產物內含字串：$bad（程式碼本身不使用網路 API）"
    }
}

$hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash
$hashFile = Join-Path $PSScriptRoot "dist\AutoClicker.exe.sha256"
"$hash  AutoClicker.exe" | Set-Content -LiteralPath $hashFile -Encoding ascii

Write-Host ""
Write-Host "產物路徑：$exe"
Write-Host "SHA256 ：$hash"
Write-Host "校驗檔 ：$hashFile"
