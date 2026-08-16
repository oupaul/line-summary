"""Internal-network dashboard for line-summary 工作進度模式 reports.

Meant to run on a company-internal Linux host (NOT this LINE-reading Windows
machine). Serves whatever `.md` reports have been synced into REPORTS_ROOT,
rendered as HTML, grouped by report type (日報/客戶進度/週報).

This process only reads files under REPORTS_ROOT; it never talks to LINE, the
MCP server, or the LINE database. Getting reports here is a separate step —
see docs/REPORT_SERVER.md for the sync side.

Run:
    REPORTS_ROOT=/opt/line-summary-reports \
    REPORTS_HOST=0.0.0.0 REPORTS_PORT=8787 \
    REPORTS_AUTH_USER=... REPORTS_AUTH_PASS=... \
    python3 report_server.py

REPORTS_AUTH_USER/PASS are optional but recommended even on an internal
network -- "internal network" often includes guest wifi/contractor VPN scope
wider than intended, and these reports contain real client names and status.
"""
import functools
import os
import secrets
from pathlib import Path

from flask import Flask, Response, abort, render_template_string, request
import markdown as md

REPORTS_ROOT = Path(os.environ.get("REPORTS_ROOT", "/opt/line-summary-reports"))
AUTH_USER = os.environ.get("REPORTS_AUTH_USER")
AUTH_PASS = os.environ.get("REPORTS_AUTH_PASS")

app = Flask(__name__)


def require_auth(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if AUTH_USER and AUTH_PASS:
            auth = request.authorization
            ok = (
                auth is not None
                and secrets.compare_digest(auth.username or "", AUTH_USER)
                and secrets.compare_digest(auth.password or "", AUTH_PASS)
            )
            if not ok:
                return Response(
                    "Authentication required",
                    401,
                    {"WWW-Authenticate": 'Basic realm="line-summary reports"'},
                )
        return view(*args, **kwargs)

    return wrapped


INDEX_TEMPLATE = """
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="60">
<title>工作進度報告</title>
<style>
  body { font-family: -apple-system, "PingFang TC", "Microsoft JhengHei", sans-serif;
         max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }
  h1 { font-size: 1.4rem; }
  h2 { font-size: 1.1rem; margin-top: 2rem; border-bottom: 1px solid #ddd; padding-bottom: .3rem; }
  ul { list-style: none; padding: 0; }
  li { padding: .3rem 0; }
  a { color: #0a7d4c; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .meta { color: #888; font-size: .85rem; }
</style>
</head>
<body>
<h1>工作進度報告</h1>
<p class="meta">每 60 秒自動重新整理，顯示目前已同步到這台伺服器的報告。</p>
{% for section, files in sections.items() %}
<h2>{{ section }}</h2>
<ul>
{% for f in files %}
  <li><a href="/report/{{ section }}/{{ f }}">{{ f }}</a></li>
{% else %}
  <li class="meta">（尚無報告）</li>
{% endfor %}
</ul>
{% endfor %}
{% if not sections %}
<p class="meta">REPORTS_ROOT（{{ root }}）底下還沒有任何子資料夾。</p>
{% endif %}
</body>
</html>
"""

REPORT_TEMPLATE = """
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>{{ filename }}</title>
<style>
  body { font-family: -apple-system, "PingFang TC", "Microsoft JhengHei", sans-serif;
         max-width: 900px; margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; line-height: 1.6; }
  table { border-collapse: collapse; width: 100%; margin: 1rem 0; }
  th, td { border: 1px solid #ddd; padding: .5rem; text-align: left; }
  th { background: #f5f5f5; }
  a.back { display: inline-block; margin-bottom: 1rem; color: #0a7d4c; text-decoration: none; }
</style>
</head>
<body>
<a class="back" href="/">&larr; 回列表</a>
{{ body|safe }}
</body>
</html>
"""


def list_reports():
    sections = {}
    if not REPORTS_ROOT.exists():
        return sections
    for section_dir in sorted(REPORTS_ROOT.iterdir()):
        if not section_dir.is_dir():
            continue
        files = sorted((f.name for f in section_dir.glob("*.md")), reverse=True)
        sections[section_dir.name] = files
    return sections


@app.route("/")
@require_auth
def index():
    return render_template_string(
        INDEX_TEMPLATE, sections=list_reports(), root=str(REPORTS_ROOT)
    )


@app.route("/report/<section>/<filename>")
@require_auth
def report(section, filename):
    # Flask's default <string> converter already rejects "/" in a segment,
    # so this can't escape REPORTS_ROOT via "..%2F..%2F"; the .. check below
    # is just cheap defense-in-depth against a future converter change.
    if ".." in section or ".." in filename or not filename.endswith(".md"):
        abort(400)
    path = REPORTS_ROOT / section / filename
    if not path.is_file():
        abort(404)
    text = path.read_text(encoding="utf-8")
    body = md.markdown(text, extensions=["tables"])
    return render_template_string(REPORT_TEMPLATE, filename=filename, body=body)


if __name__ == "__main__":
    host = os.environ.get("REPORTS_HOST", "127.0.0.1")
    port = int(os.environ.get("REPORTS_PORT", "8787"))
    if not (AUTH_USER and AUTH_PASS):
        print(
            "警告：REPORTS_AUTH_USER / REPORTS_AUTH_PASS 未設定，"
            "這個服務目前沒有登入驗證，任何連得到這個 port 的人都能看到報告內容。"
        )
    app.run(host=host, port=port)
