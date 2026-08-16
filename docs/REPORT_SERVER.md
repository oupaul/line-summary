# 工作進度報告 內部網站部署手冊

把 `/日報`、`/客戶進度`、`/週報` 存到這台 Windows 機器 `output/` 底下的報告，
同步到公司內部的 Linux 伺服器，用瀏覽器在公司內網看，不對公網開放。

架構：

```
Windows（LINE讀取機）--scp/rsync(SSH金鑰)--> Linux內部伺服器
                                              └─ tools/report_server.py
                                                 （Flask，只讀本機檔案，
                                                  不碰LINE/資料庫）
```

兩台機器分工清楚：LINE 的金鑰/資料庫解密永遠只在 Windows 這台做；Linux 伺服器
只負責把已經整理好的 markdown 報告渲染成網頁，不會、也不需要碰任何 LINE 資料。

---

## 1. 伺服器端：安裝 report_server.py

在 Linux 伺服器上（自己登入操作）：

```bash
sudo mkdir -p /opt/line-summary-reports-app /opt/line-summary-reports
sudo chown $USER:$USER /opt/line-summary-reports-app /opt/line-summary-reports
```

把這個 repo 的 `tools/report_server.py` 和 `tools/report_server_requirements.txt`
複製到 `/opt/line-summary-reports-app/`（用 `scp`、`git clone` 這個 repo 再複製，
或直接貼內容都行）。

```bash
cd /opt/line-summary-reports-app
python3 -m venv venv
source venv/bin/activate
pip install -r report_server_requirements.txt
```

先手動試跑一次確認能動：

```bash
REPORTS_ROOT=/opt/line-summary-reports \
REPORTS_HOST=127.0.0.1 REPORTS_PORT=8787 \
REPORTS_AUTH_USER=admin REPORTS_AUTH_PASS='挑一個強密碼' \
python3 report_server.py
```

另開一個 terminal 用 `curl -u admin:密碼 http://127.0.0.1:8787/` 確認有回應（此時
`/opt/line-summary-reports` 應該還是空的，頁面會顯示「尚無報告」，這是正常的，
下一步同步過去後就會出現）。

確認沒問題後 Ctrl+C 停掉，改用 systemd 常駐：

```bash
cp line-summary-reports.service.example /tmp/line-summary-reports.service
# 編輯 /tmp/line-summary-reports.service，把 <...> 佔位符都填成實際值
sudo mv /tmp/line-summary-reports.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now line-summary-reports
sudo systemctl status line-summary-reports
```

**REPORTS_HOST 建議設定**：如果伺服器有多張網卡（例如同時接公網跟內網），
`REPORTS_HOST` 綁定到內網那張卡的 IP（而不是 `0.0.0.0`），從網路層面就確保
公網連不到，不要只靠帳密擋。實際要綁哪個 IP、防火牆規則怎麼設，你們公司
內網架構你比較清楚，這邊沒辦法幫你判斷。

## 2. Windows 端：產生用來同步的 SSH 金鑰

在這台 Windows 機器上（跟平常操作 LINE 摘要工具一樣，在 Claude Code 或
PowerShell 裡）：

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\line-summary-reports" -N '""'
```

這會產生一組**專門給同步報告用**的金鑰（跟你平常登入用的金鑰分開，就算外洩
影響範圍也只有「能把報告檔案 scp 上去」，不是完整登入權限）。

把公鑰內容（`line-summary-reports.pub`）加到伺服器那個同步帳號的
`~/.ssh/authorized_keys`。建議：
- 用一個**權限受限的專用帳號**（例如 `reports-sync`）收報告，不要用有 sudo
  權限的帳號。
- 在 `authorized_keys` 那一行前面加限制，只允許這把金鑰執行 scp/rsync，例如：
  `command="rsync --server ...",restrict ssh-ed25519 AAAA... line-summary-reports`
  （確切語法看你用 scp 還是 rsync；細節可以問你們 IT 或之後我再幫你查）。

## 3. 設定本機 local-context.md

打開 `skills/line-summary/local-context.md`（沒有的話先照
`local-context.example.md` 建立），補上：

```markdown
## 報告同步伺服器（選用）
- SSH 目標：reports-sync@<伺服器內網IP或主機名>
- 遠端報告根目錄：/opt/line-summary-reports
- SSH 金鑰路徑：~/.ssh/line-summary-reports
```

之後 `/日報`、`/客戶進度`、`/週報` 存檔完會自動多一步：讀到這個設定就用 `scp`
把剛存的檔案同步過去；沒設定就照舊只存本機，不會出錯也不會問。

## 4. 驗證

1. 在 Windows 端跑一次 `/日報`。
2. 回覆裡應該會多一行同步結果（成功會顯示同步到的路徑；失敗——例如金鑰沒設好、
   伺服器連不到——會照實講失敗原因，不會假裝成功）。
3. 瀏覽器開 `http://<伺服器內網IP>:8787/`（要先連上公司內網/VPN），輸入
   `REPORTS_AUTH_USER`/`REPORTS_AUTH_PASS`，應該看得到剛剛那份日報。

## 安全提醒

- 這個網站只做「內網可達」+「帳密驗證」兩層，沒有做 HTTPS。如果內網本身不是
  完全信任的環境（例如訪客 wifi 橋接在同一段），帳密會用明碼傳輸——建議之後
  加一層 nginx reverse proxy + 自簽或內部CA憑證做 HTTPS，或至少限制能連到
  這個 port 的來源 IP 範圍。
- `REPORTS_AUTH_USER`/`REPORTS_AUTH_PASS` 目前是寫在 systemd unit 檔的環境變數
  裡（明碼），unit 檔案權限預設只有 root 可讀，正常情況下夠用；如果要更嚴謹，
  可以改用 systemd 的 `EnvironmentFile=` 指向一個權限鎖 600 的獨立檔案。
- 同步用的 SSH 金鑰只給「把檔案傳上去」的最小權限帳號使用，不要用管理員帳號。
