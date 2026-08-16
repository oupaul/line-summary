# 環境重建手冊：全新 Windows VM

在一台全新的 Windows 機器上，從零重建這個 line-summary 工具 + Claude Code +
Tailscale 遠端連線的完整環境。照順序做，最後有驗證清單。

版本基準（本文件寫成時，這台機器實測可用的版本）：
Git 2.55.0、Python 3.12.10、Claude Code 2.1.233、Windows 10.0.26200。

## 目錄放置提醒（吃過虧的教訓）

**不要把 repo clone 到 `C:\Windows\System32\` 之類的系統保護目錄底下。**
一般使用者帳號在那裡只有讀取權限（RX），沒有寫入權限，之後任何 `git commit`、
改程式碼都會失敗，得整包搬到使用者自己的目錄（例如 `C:\Users\<you>\line-summary`）
才能繼續。一開始就 clone 到你自己的使用者目錄，省掉這個麻煩。

---

## 1. 安裝 Git

到 https://git-scm.com/downloads/win 下載安裝，或用 winget：

```powershell
winget install --id Git.Git -e --source winget
```

裝完開一個新的終端機視窗確認：

```powershell
git --version
```

## 2. 安裝 Python 3.11+

到 https://www.python.org/downloads/windows/ 下載安裝，安裝時記得勾選
「Add python.exe to PATH」。或用 winget：

```powershell
winget install --id Python.Python.3.12 -e --source winget
```

確認：

```powershell
python --version
```

## 3. Clone 這個 repo

```powershell
cd $env:USERPROFILE
git clone https://github.com/oupaul/line-summary.git
cd line-summary
```

## 4. 安裝 Python 相依套件

```powershell
pip install -r requirements.txt
```

`requirements.txt` 裡的東西：

```
mcp>=1.0.0,<2                    # MCP server框架
apsw-sqlite3mc>=3.50             # LINE用wxSQLite3加密，靠這個解密（不是Zetetic sqlcipher3）
pywin32                          # Windows API存取（金鑰擷取要用ReadProcessMemory）
pytest / pytest-asyncio / pytest-cov   # 測試
```

一般情況這幾個套件在Windows上都有現成的wheel，直接pip裝就會過。如果
`apsw-sqlite3mc` 安裝失敗，通常是缺 Microsoft Visual C++ Redistributable，
去微軟官網裝最新版的 VC++ Redistributable (x64) 再重試。

裝完用內建（不需要真的連LINE）的測試確認環境沒問題：

```powershell
python -m pytest -m "not integration" -q
```

## 5. 安裝 LINE 電腦版

到LINE官網下載電腦版，安裝後**保持登入、保持執行**（可以縮到最小化）。這個
工具的金鑰擷取（`key_extractor.py`）是對著本機正在跑的 `LINE.exe` 做
`ReadProcessMemory`，LINE沒開沒登入就完全抓不到金鑰。

目前這個工具只在 **LINE電腦版 26.3**（用wxSQLite3的aes128cbc加密）上驗證過，
LINE改版可能需要重新確認加密方式（README裡「動不了的時候」那段有說明）。

## 6. 安裝 Claude Code CLI

官方原生安裝（Windows PowerShell，不需要系統管理員權限）：

```powershell
irm https://claude.ai/install.ps1 | iex
```

裝完會在 `%USERPROFILE%\.local\bin\claude.exe`，原生安裝會自動背景更新。

替代方式：

```powershell
# WinGet
winget install Anthropic.ClaudeCode

# npm（需要 Node.js 22+）
npm install -g @anthropic-ai/claude-code
```

確認安裝：

```powershell
claude --version
claude doctor
```

**建議額外裝 Git for Windows**（上面第1步如果裝的是官方Git for Windows就已經有了）：
有裝的話Claude Code的Bash工具會走Git Bash；沒裝則退回用PowerShell工具，兩種都能用，
但這份文件裡的操作記錄是以Git Bash為主。

第一次執行 `claude` 會開瀏覽器要你登入 Claude 帳號（需要Pro/Max/Team/Enterprise
方案，免費的claude.ai方案不能用Claude Code）。

## 7. 註冊 line MCP server

repo裡已經附了 `.mcp.json`（相對路徑），只要在 `line-summary` 這個資料夾裡開
Claude Code：

```powershell
cd $env:USERPROFILE\line-summary
claude
```

第一次會問你要不要信任這個資料夾的MCP設定，選同意即可，會自動載入名叫
`line` 的MCP server。

想在任何資料夾都叫得到（全域註冊），路徑要換成clone下來的實際位置：

```powershell
claude mcp add line --scope user -- python C:\Users\<你的帳號>\line-summary\line_mcp_server.py
```

## 8. 第一次呼叫（金鑰擷取）

在Claude Code裡問任何跟LINE聊天記錄有關的問題（例如「幫我列出LINE聊天室」），
第一次呼叫大約要等 **80秒**，它在掃LINE.exe的記憶體找解密金鑰。找到後同一個
session後面都很快。金鑰不落地、不存檔，換一個新session（重開Claude Code）
就要重新掃一次——這是刻意的安全設計，用時間換金鑰不留在硬碟上。

---

## 9. （選用）Tailscale + OpenSSH：從別的裝置遠端操作這台機器

如果想從另一台電腦（例如Mac）遠端SSH進來操作這台Windows跑Claude Code，走下面
這段。**這兩步都需要系統管理員權限**，要用「以系統管理員身分執行」開PowerShell。

### 9.1 安裝並登入 Tailscale

```powershell
winget install tailscale.tailscale
tailscale up
```

`tailscale up` 會跳出瀏覽器要你登入（跟其他要連進來的裝置用同一個Tailscale
帳號，這樣才會在同一個tailnet裡）。記下這台的Tailscale IP：

```powershell
tailscale ip -4
```

選Tailscale而不是直接把SSH開在公網上，是因為SSH port完全不會曝露在公網，
只有登入同一個tailnet的裝置才連得到，不用處理動態IP/port forwarding，也不用
擔心SSH被公網掃描/暴力破解。

### 9.2 安裝 OpenSSH Server

```powershell
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
```

確認防火牆規則（安裝OpenSSH Server通常會自動加一條，保險起見check）：

```powershell
Get-NetFirewallRule -Name *ssh*
```

沒看到的話手動加：

```powershell
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22
```

**建議**把SSH連進來的預設shell改成PowerShell（不然預設是舊的cmd.exe）：

```powershell
New-ItemProperty -Path "HKLM:\SOFTWARE\OpenSSH" -Name DefaultShell -Value "C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe" -PropertyType String -Force
```

### 9.3 另一台裝置（例如Mac）連進來

裝Tailscale App，用同一個帳號登入，然後：

```bash
ssh <你的Windows帳號>@<這台的Tailscale IP>
```

第一次會問Windows登入密碼。連上之後就是這台的PowerShell，`cd` 到
`line-summary` 資料夾，打 `claude` 繼續用。

> 如果這個Windows帳號本身是本機系統管理員群組成員，想改用SSH金鑰登入
> （不用每次打密碼）的話，`authorized_keys` 檔案路徑跟一般帳號不一樣，是
> `C:\ProgramData\ssh\administrators_authorized_keys`（且ACL要鎖到只有
> SYSTEM和Administrators能寫），不是常見的 `~\.ssh\authorized_keys`。

---

## 10. 快速指令

repo裡 `.claude/commands/` 已經附了三個工作進度查詢指令，在
`line-summary` 資料夾裡開Claude Code就能直接用：

| 指令 | 用途 |
|---|---|
| `/日報 [日期]` | 今天(或指定日)所有客戶群組工作進度 |
| `/客戶進度 <名稱> [範圍]` | 單一客戶深入查（自動找旁支/供應商群組） |
| `/週報 [範圍]` | 全公司完整掃描，不限群組命名，背景執行 |

用之前記得先在 `skills/line-summary/local-context.md` 填好你自己公司的
LINE 群組命名前綴和內部人員姓名模式（範本見同資料夾的
`local-context.example.md`；這個檔案已加入 `.gitignore`，不會被 commit）。
詳細方法論在 `skills/line-summary/SKILL.md` 的「工作進度模式」章節。

---

## 驗證清單

全部裝完後，照順序檢查：

- [ ] `git --version` 有輸出
- [ ] `python --version` 是3.11以上
- [ ] `cd line-summary && python -m pytest -m "not integration" -q` 全過
- [ ] LINE電腦版正在跑、已登入
- [ ] `claude --version` 有輸出；`claude doctor` 沒有紅字錯誤
- [ ] 在 `line-summary` 資料夾開 `claude`，同意信任專案MCP設定
- [ ] 問一句LINE相關問題，第一次呼叫等~80秒後成功回傳資料（金鑰擷取成功）
- [ ] （選用）`tailscale status` 看得到這台機器；`tailscale ip -4` 有輸出
- [ ] （選用）`Get-Service sshd` 顯示 `Running`
- [ ] （選用）從另一台已登入同tailnet的裝置 `ssh <帳號>@<tailscale ip>` 連得進來
- [ ] 打 `/日報` 測試斜線指令能正常運作

## 安全提醒（沿用 README 的設計原則）

- 金鑰只存在LINE.exe的記憶體裡，這個工具不寫檔、不寫log、不送上任何網路。
- 群組和開放聊天室裡有別人的訊息，自己整理來看沒問題，要公開之前先想一下。
- `output/`、`settings.json`、真實聊天匯出檔都已經在 `.gitignore` 裡，不會被
  意外commit上去；staged前還是養成習慣看一眼 `git status` 有沒有奇怪的檔案。
- Tailscale/SSH是為了讓「你自己」遠端操作這台機器，金鑰跟解密後的DB內容
  不應該透過網路傳輸出去——運算（擷取金鑰、解密、彙整）一律留在這台機器上
  做，遠端連線只是操作介面。
