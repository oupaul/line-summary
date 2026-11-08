#!/bin/bash
# 雙擊啟動「維護記錄單產生器」：開瀏覽器 -> 選聊天室與日期 -> 按鈕產出 Excel
cd "$(dirname "$0")" || exit 1
if ! python3 -c "import openpyxl" 2>/dev/null; then
  echo "第一次使用需安裝 openpyxl，執行：pip3 install openpyxl"
  read -n 1 -s -r -p "按任意鍵關閉"; exit 1
fi
if ! command -v claude >/dev/null 2>&1 && [ ! -x "$HOME/.local/bin/claude" ]; then
  echo "找不到 claude 指令，請先安裝並登入 Claude Code。"
  read -n 1 -s -r -p "按任意鍵關閉"; exit 1
fi
python3 tools/maintenance_gui.py
