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

## 1. 伺服器端（Ubuntu 24.04）：安裝 report_server.py

以下指令在 Linux 伺服器上執行（自己登入操作，非 root 帳號用 `sudo`）。

### 1.1 系統套件

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

Ubuntu 24.04 內建 Python 3.12。`python3-venv` 要另外裝——後面一定要用虛擬環境
裝套件，不要對系統 Python 直接 `pip install`：Ubuntu 24.04 的系統 Python 預設
是 PEP 668「externally-managed-environment」，直接 `pip install` 會直接報錯
拒絕，這是刻意設計，用 venv 是正規解法，不要用 `--break-system-packages` 繞過。

### 1.2 建立專用低權限帳號（同步 + 跑服務都用這個）

```bash
sudo useradd -m -s /bin/bash reports-sync
sudo mkdir -p /home/reports-sync/.ssh
sudo chmod 700 /home/reports-sync/.ssh
sudo chown reports-sync:reports-sync /home/reports-sync/.ssh
```

這個帳號**不要加進 sudo/adm 群組**，只用來收報告檔案跟跑 Flask 服務，權限
影響範圍限制在它自己的 home 目錄跟等下建立的 `/opt/line-summary-reports`。

把 Windows 端產生的公鑰（下一步會給你）貼進去：

```bash
echo '<Windows端貼過來的公鑰內容，一整行>' | sudo tee /home/reports-sync/.ssh/authorized_keys
sudo chown reports-sync:reports-sync /home/reports-sync/.ssh/authorized_keys
sudo chmod 600 /home/reports-sync/.ssh/authorized_keys
```

公鑰那行前面加 `restrict,`（停用 port-forward/X11/pty，scp/rsync都不需要這些，
但不會擋你要的檔案傳輸），例如：

```
restrict ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFozqb6FnsNrEThlAG3Wy17dzjWGPgubU4ZtRigQ5FHC line-summary-reports-sync
```

（想更嚴格鎖到「只能上傳檔案、不能執行任何其他指令」，可以改用 OpenSSH 的
`ChrootDirectory` + `ForceCommand internal-sftp` 做 SFTP-only chroot，但設定
較繁瑣、容易一次設錯就把自己鎖在外面，這邊先用「低權限帳號 + restrict」這個
好設定、風險小很多的版本；之後要加固可以再問我或找IT。）

### 1.3 安裝 report_server.py

```bash
sudo mkdir -p /opt/line-summary-reports-app /opt/line-summary-reports
sudo chown reports-sync:reports-sync /opt/line-summary-reports-app /opt/line-summary-reports
```

把這個 repo 的 `tools/report_server.py` 和 `tools/report_server_requirements.txt`
複製到 `/opt/line-summary-reports-app/`（`scp`、`git clone` 這個 repo 再複製，
或直接貼內容都行）。

```bash
sudo -u reports-sync -i bash -c '
  cd /opt/line-summary-reports-app
  python3 -m venv venv
  source venv/bin/activate
  pip install -r report_server_requirements.txt
'
```

先手動試跑一次確認能動：

```bash
sudo -u reports-sync -i bash -c '
  cd /opt/line-summary-reports-app
  source venv/bin/activate
  REPORTS_ROOT=/opt/line-summary-reports \
  REPORTS_HOST=127.0.0.1 REPORTS_PORT=8787 \
  REPORTS_AUTH_USER=admin REPORTS_AUTH_PASS="挑一個強密碼" \
  python3 report_server.py
'
```

另開一個 terminal 用 `curl -u admin:密碼 http://127.0.0.1:8787/` 確認有回應（此時
`/opt/line-summary-reports` 應該還是空的，頁面會顯示「尚無報告」，這是正常的，
下一步同步過去後就會出現）。

確認沒問題後 Ctrl+C 停掉，改用 systemd 常駐：

```bash
cd /opt/line-summary-reports-app
cp line-summary-reports.service.example /tmp/line-summary-reports.service
# 編輯 /tmp/line-summary-reports.service，把 <...> 佔位符都填成實際值
# （User=reports-sync、WorkingDirectory=/opt/line-summary-reports-app、
#   ExecStart 記得指到 venv 裡的 python：
#   /opt/line-summary-reports-app/venv/bin/python3 /opt/line-summary-reports-app/report_server.py）
sudo mv /tmp/line-summary-reports.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now line-summary-reports
sudo systemctl status line-summary-reports
```

### 1.4 防火牆（ufw）

Ubuntu 24.04 預設用 ufw。先確認 SSH（22）已放行，再加內網才能連的規則，
**順序很重要，先允許 SSH 再啟用 ufw，不然會把自己鎖在外面**：

```bash
sudo ufw status                      # 先看目前狀態，若尚未 enable 就先做下面兩行
sudo ufw allow OpenSSH                # 確保先放行 SSH
sudo ufw allow from <公司內網CIDR，例如192.168.1.0/24> to any port 8787 proto tcp
sudo ufw enable                       # 若本來就是 active 就跳過這行
sudo ufw status numbered
```

`<公司內網CIDR>` 要填你們實際的內網網段，這個我不知道，要問你們 IT 或看
伺服器的 `ip addr` 自己判斷。

**REPORTS_HOST 建議設定**：如果伺服器有多張網卡（例如同時接公網跟內網），
`REPORTS_HOST`（在 systemd unit 裡）綁定到內網那張卡的 IP（而不是
`0.0.0.0`），從網路層面就確保公網連不到，不要只靠 ufw + 帳密擋。

## 2. Windows 端：同步用的 SSH 金鑰

已經幫你在這台 Windows 機器上產生好了：

```
私鑰：~/.ssh/line-summary-reports
公鑰：~/.ssh/line-summary-reports.pub
```

這組是**專門給同步報告用**的金鑰（跟你平常登入用的金鑰分開，就算外洩，
影響範圍也只有「能把報告檔案傳到 reports-sync 這個低權限帳號」，不是完整
登入權限）。公鑰內容就是上面 1.2 步驟要貼進伺服器 `authorized_keys` 的那行。

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

## 5. 疑難排解：TCP連得上，但送出HTTP請求後被reset

實際部署遇過的狀況：從 Windows 端 `ssh`（22）完全正常，但直接瀏覽器/curl連
`http://<伺服器IP>:8787/` 時，TCP三向交握會成功，送出HTTP請求後卻立刻被斷線
（`Recv failure: Connection was reset`）。

判斷方法：
1. 先在伺服器本機用 `curl http://<伺服器IP>:8787/` 測試——如果這樣測得到
   `401`（沒帶帳密）或 `200`，代表 Flask 服務本身跟 bind 位址都正常，問題
   在網路路徑上，不是這個服務的設定錯誤。
2. 檢查 `sudo ufw status`——如果是 `inactive` 或已經有放行規則，就不是 Ubuntu
   這台主機自己在擋。
3. 剩下的可能性通常是**兩個網段之間的網路設備**（公司防火牆、資安閘道、
   L7 IPS 之類）只放行少數已知 port（例如22），對其他 port 做內容檢查後
   reset——這已經超出這台伺服器能自己解決的範圍，需要請網路/資安團隊確認
   來源網段到目的網段、這個 port 的規則。

**暫時的替代方案**：SSH 本身既然是通的，可以用 SSH local port-forward 開一條
臨時通道，繞過中間那段直連的網路路徑：

```bash
ssh -i <部署用私鑰> -L 8787:<伺服器內網IP>:8787 -N <部署帳號>@<伺服器內網IP>
```

跑起來之後瀏覽器改連 `http://127.0.0.1:8787/` 就看得到，帳密不變。這只是
繞過網路限制的臨時手段，不是長期解法；長期還是要請網路團隊放行這個 port，
或改把服務接到已經放行的 port（例如常見的 80/443，但那樣通常要另外處理
root 權限綁定低於1024的 port，或前面加 nginx reverse proxy）。

## 安全提醒

- 這個網站只做「內網可達」+「帳密驗證」兩層，沒有做 HTTPS。如果內網本身不是
  完全信任的環境（例如訪客 wifi 橋接在同一段），帳密會用明碼傳輸——建議之後
  加一層 nginx reverse proxy + 自簽或內部CA憑證做 HTTPS，或至少限制能連到
  這個 port 的來源 IP 範圍。
- `REPORTS_AUTH_USER`/`REPORTS_AUTH_PASS` 目前是寫在 systemd unit 檔的環境變數
  裡（明碼），unit 檔案權限預設只有 root 可讀，正常情況下夠用；如果要更嚴謹，
  可以改用 systemd 的 `EnvironmentFile=` 指向一個權限鎖 600 的獨立檔案。
- 同步用的 SSH 金鑰只給「把檔案傳上去」的最小權限帳號使用，不要用管理員帳號。
