## AutoClicker {{TAG}}

### 變更摘要

{{CHANGES}}

### 實測數據（GitHub Actions windows-latest）

- onefile 檔案大小：{{ONEFILE_MB}}
- onefile 冷啟動（行程啟動到視窗出現）：{{START}}
- onefile 閒置記憶體（視窗出現後 5 秒）：{{MEM}}
- onedir 檔案大小：{{ONEDIR_SIZE_MB}}
- onedir 冷啟動：{{ONEDIR_START}}
- onedir 閒置記憶體：{{ONEDIR_MEM}}
- {{ONEDIR_NOTE}}

### 下載後校驗

PowerShell：

```powershell
Get-FileHash .\AutoClicker.exe -Algorithm SHA256
Get-Content .\AutoClicker.exe.sha256
```

兩者雜湊值應一致（`AutoClicker.exe.sha256` 內含檔名，比對第一欄）。

來源證明（需安裝 GitHub CLI 並登入）：

```powershell
gh attestation verify .\AutoClicker.exe --repo {{REPO}}
```

### 重要警告

- 此 exe **未經程式碼簽章**。Windows SmartScreen 或 Smart App Control
  可能阻擋或警告；請先確認 SHA256 與來源證明再決定是否執行。
- 若無法執行或不想繞過系統警告，建議改用原始碼：下載 Source code、
  安裝 Python 3.10+，執行 `start.bat` 或 `python main.py`。

### 遊戲使用風險

本工具會注入滑鼠/鍵盤輸入。部分遊戲的防作弊系統（EAC、BattlEye 等）
可能偵測、封鎖或懲罰使用輸入注入的帳號；使用前請自行確認並遵守
目標遊戲與服務條款，風險自負。
