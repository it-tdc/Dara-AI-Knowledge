#!/usr/bin/env python3
"""Dynamic progress dashboard for the Dara AI Knowledge project.

Run:
    python .dashboard/knowledge_dashboard.py

The dashboard scans the knowledge base folder on every request, so the pie chart
updates automatically whenever file contents change.
"""

from __future__ import annotations

import html
import json
import mimetypes
import os
import threading
import webbrowser
from collections import Counter, defaultdict
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
HOST = "127.0.0.1"
PORT = 0  # choose a free port automatically
REFRESH_MS = 2500

# Hidden tooling folders and other non-knowledge folders are excluded from the scan.
EXCLUDED_DIRS = {
    ".dashboard",
    ".git",
    ".hermes",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "node_modules",
}

TEXT_EXTENSIONS = {
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".py",
    ".js",
    ".ts",
    ".html",
    ".css",
}

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Dara AI Knowledge Dashboard</title>
  <style>
    :root {
      --bg: #0f172a;
      --panel: #111827;
      --panel-2: #1f2937;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --complete: #22c55e;
      --incomplete: #ef4444;
      --accent: #38bdf8;
      --border: #334155;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: Inter, Segoe UI, system-ui, -apple-system, BlinkMacSystemFont, sans-serif;
      background: radial-gradient(circle at top, #1e293b 0%, var(--bg) 60%);
      color: var(--text);
      min-height: 100vh;
    }
    .wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 28px;
    }
    .hero {
      display: flex;
      gap: 20px;
      align-items: stretch;
      flex-wrap: wrap;
      margin-bottom: 20px;
    }
    .card {
      background: rgba(17, 24, 39, 0.9);
      border: 1px solid var(--border);
      border-radius: 18px;
      box-shadow: 0 10px 30px rgba(0,0,0,.25);
    }
    .summary {
      flex: 1 1 360px;
      padding: 24px;
      min-width: 320px;
    }
    h1 {
      margin: 0 0 10px;
      font-size: 28px;
      line-height: 1.2;
    }
    .subtitle {
      color: var(--muted);
      margin-bottom: 18px;
    }
    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 18px;
    }
    .stat {
      background: rgba(31, 41, 55, 0.8);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
    }
    .stat .label {
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: .08em;
      margin-bottom: 6px;
    }
    .stat .value {
      font-size: 26px;
      font-weight: 700;
    }
    .stat .small {
      color: var(--muted);
      margin-top: 4px;
      font-size: 12px;
    }
    .chart-card {
      flex: 0 0 360px;
      padding: 24px;
      display: flex;
      flex-direction: column;
      justify-content: center;
      align-items: center;
      min-width: 320px;
    }
    .donut {
      width: 260px;
      height: 260px;
      border-radius: 50%;
      position: relative;
      display: grid;
      place-items: center;
      background: conic-gradient(var(--complete) 0deg, var(--complete) 0deg, var(--incomplete) 0deg 360deg);
      transition: background 0.6s ease;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.06);
    }
    .donut::after {
      content: "";
      width: 150px;
      height: 150px;
      border-radius: 50%;
      background: linear-gradient(180deg, #0f172a, #111827);
      border: 1px solid var(--border);
      box-shadow: inset 0 0 40px rgba(0,0,0,.18);
    }
    .donut-center {
      position: absolute;
      text-align: center;
      z-index: 1;
      width: 150px;
      pointer-events: none;
    }
    .donut-center .percent {
      font-size: 42px;
      font-weight: 800;
      line-height: 1;
    }
    .donut-center .caption {
      color: var(--muted);
      margin-top: 6px;
      font-size: 13px;
    }
    .legend {
      display: flex;
      gap: 16px;
      margin-top: 18px;
      flex-wrap: wrap;
      justify-content: center;
      color: var(--muted);
      font-size: 14px;
    }
    .legend span {
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
    .dot {
      width: 12px;
      height: 12px;
      border-radius: 999px;
      display: inline-block;
    }
    .section {
      margin-top: 18px;
      padding: 20px;
    }
    .section h2 {
      margin: 0 0 14px;
      font-size: 20px;
    }
    .folders {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
      gap: 14px;
    }
    .folder {
      background: rgba(31, 41, 55, 0.8);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 14px;
    }
    .folder .name {
      font-weight: 700;
      margin-bottom: 8px;
    }
    .progress {
      height: 10px;
      background: #0b1220;
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid #334155;
      margin: 8px 0 10px;
    }
    .progress > div {
      height: 100%;
      background: linear-gradient(90deg, var(--accent), #22c55e);
      border-radius: inherit;
      transition: width 0.6s ease;
    }
    .folder .meta {
      color: var(--muted);
      font-size: 13px;
      display: flex;
      justify-content: space-between;
      gap: 10px;
    }
    .files {
      margin-top: 16px;
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 14px;
    }
    .filelist {
      max-height: 320px;
      overflow: auto;
      padding-right: 4px;
    }
    .file-item {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      padding: 10px 0;
      border-bottom: 1px solid rgba(148,163,184,.14);
      font-size: 14px;
    }
    .file-item:last-child { border-bottom: 0; }
    .pill {
      border-radius: 999px;
      padding: 4px 10px;
      font-size: 12px;
      font-weight: 700;
      white-space: nowrap;
      align-self: start;
    }
    .done { background: rgba(34,197,94,.15); color: #86efac; }
    .todo { background: rgba(239,68,68,.15); color: #fca5a5; }
    .footer {
      margin-top: 12px;
      color: var(--muted);
      font-size: 12px;
      text-align: right;
    }
    a { color: #93c5fd; }
    @media (max-width: 860px) {
      .stats { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .chart-card { flex-basis: 100%; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="card summary">
        <h1>Dara AI Knowledge Dashboard</h1>
        <div class="subtitle">Live progress monitor for your knowledge base. The chart refreshes automatically every few seconds.</div>
        <div class="stats">
          <div class="stat"><div class="label">Completion</div><div class="value" id="completion">0%</div><div class="small">overall</div></div>
          <div class="stat"><div class="label">Complete</div><div class="value" id="completeCount">0</div><div class="small">files</div></div>
          <div class="stat"><div class="label">Incomplete</div><div class="value" id="incompleteCount">0</div><div class="small">files</div></div>
          <div class="stat"><div class="label">Total</div><div class="value" id="totalCount">0</div><div class="small">files</div></div>
        </div>
        <div class="footer" id="scanInfo">Scanning...</div>
      </div>
      <div class="card chart-card">
        <div class="donut" id="donut">
          <div class="donut-center">
            <div class="percent" id="percentText">0%</div>
            <div class="caption">project complete</div>
          </div>
        </div>
        <div class="legend">
          <span><i class="dot" style="background: var(--complete)"></i>Complete</span>
          <span><i class="dot" style="background: var(--incomplete)"></i>Incomplete</span>
        </div>
      </div>
    </div>

    <div class="card section">
      <h2>Folder Progress</h2>
      <div class="folders" id="folders"></div>
    </div>

    <div class="card section">
      <h2>Recent File Status</h2>
      <div class="files">
        <div class="folder">
          <div class="name">Completed files</div>
          <div class="filelist" id="doneList"></div>
        </div>
        <div class="folder">
          <div class="name">Needs content</div>
          <div class="filelist" id="todoList"></div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const REFRESH_MS = __REFRESH_MS__;

    function esc(text) {
      return String(text)
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&#39;');
    }

    function donutBackground(percent) {
      const completeDeg = Math.max(0, Math.min(360, percent * 3.6));
      return `conic-gradient(var(--complete) 0deg ${completeDeg}deg, var(--incomplete) ${completeDeg}deg 360deg)`;
    }

    function renderList(el, items, emptyText, pillClass) {
      if (!items.length) {
        el.innerHTML = `<div style="color: var(--muted); font-size: 14px; padding: 10px 0;">${emptyText}</div>`;
        return;
      }
      el.innerHTML = items.map(item => `
        <div class="file-item">
          <div>${esc(item.relative_path)}</div>
          <div class="pill ${pillClass}">${pillClass === 'done' ? 'done' : 'todo'}</div>
        </div>
      `).join('');
    }

    function renderFolders(folders) {
      const root = document.getElementById('folders');
      root.innerHTML = folders.map(folder => `
        <div class="folder">
          <div class="name">${esc(folder.name)}</div>
          <div class="progress"><div style="width:${folder.percent}%"></div></div>
          <div class="meta"><span>${folder.complete} / ${folder.total} complete</span><span>${folder.percent}%</span></div>
        </div>
      `).join('');
    }

    async function loadData() {
      try {
        const res = await fetch('/api/progress', { cache: 'no-store' });
        const data = await res.json();

        document.getElementById('completion').textContent = `${data.summary.percent}%`;
        document.getElementById('percentText').textContent = `${data.summary.percent}%`;
        document.getElementById('completeCount').textContent = data.summary.complete;
        document.getElementById('incompleteCount').textContent = data.summary.incomplete;
        document.getElementById('totalCount').textContent = data.summary.total;
        document.getElementById('scanInfo').textContent = `Last scanned: ${data.scanned_at} • Root: ${data.root}`;
        document.getElementById('donut').style.background = donutBackground(data.summary.percent);

        renderFolders(data.folders);
        renderList(document.getElementById('doneList'), data.completed_files.slice(0, 20), 'No completed files yet.', 'done');
        renderList(document.getElementById('todoList'), data.incomplete_files.slice(0, 20), 'Nothing left to write. Nice!', 'todo');
      } catch (error) {
        document.getElementById('scanInfo').textContent = `Error loading dashboard: ${error}`;
      }
    }

    loadData();
    setInterval(loadData, REFRESH_MS);
  </script>
</body>
</html>
"""

HTML_PAGE = HTML_TEMPLATE.replace("__REFRESH_MS__", str(REFRESH_MS))

def is_excluded(path: Path) -> bool:
    parts = set(path.relative_to(ROOT).parts)
    return bool(parts.intersection(EXCLUDED_DIRS))


def is_text_candidate(path: Path) -> bool:
    if path.is_dir() or is_excluded(path):
        return False
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    # Include extensionless markdown-ish files if present.
    return path.suffix == "" and path.name.isascii()


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def classify_file(path: Path) -> dict:
    text = read_text(path).strip()
    placeholder = not text or text == path.name or text == path.stem
    relative = str(path.relative_to(ROOT)).replace(os.sep, "/")
    folder = path.relative_to(ROOT).parts[0] if len(path.relative_to(ROOT).parts) > 1 else "."
    return {
        "path": str(path),
        "relative_path": relative,
        "folder": folder,
        "placeholder": placeholder,
        "complete": not placeholder,
        "size": path.stat().st_size,
    }


def scan_project() -> dict:
    files = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIRS]
        current = Path(dirpath)
        if is_excluded(current):
            continue
        for name in filenames:
            path = current / name
            if is_excluded(path):
                continue
            if not is_text_candidate(path):
                continue
            files.append(classify_file(path))

    files.sort(key=lambda item: item["relative_path"].lower())
    total = len(files)
    complete = sum(1 for item in files if item["complete"])
    incomplete = total - complete
    percent = round((complete / total * 100) if total else 0, 1)

    folder_totals: dict[str, list[dict]] = defaultdict(list)
    for item in files:
        folder_totals[item["folder"]].append(item)

    folders = []
    for folder_name in sorted(folder_totals.keys(), key=lambda x: (x == ".", x.lower())):
        items = folder_totals[folder_name]
        folder_complete = sum(1 for item in items if item["complete"])
        folder_total = len(items)
        folders.append(
            {
                "name": folder_name,
                "total": folder_total,
                "complete": folder_complete,
                "percent": round((folder_complete / folder_total * 100) if folder_total else 0, 1),
            }
        )

    completed_files = [item for item in files if item["complete"]]
    incomplete_files = [item for item in files if not item["complete"]]

    return {
        "root": str(ROOT),
        "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "summary": {
            "total": total,
            "complete": complete,
            "incomplete": incomplete,
            "percent": percent,
        },
        "folders": folders,
        "completed_files": completed_files,
        "incomplete_files": incomplete_files,
    }


class DashboardHandler(BaseHTTPRequestHandler):
    server_version = "DaraKnowledgeDashboard/1.0"

    def log_message(self, format: str, *args) -> None:  # noqa: A003 - matching BaseHTTPRequestHandler API
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - matching BaseHTTPRequestHandler API
        route = urlparse(self.path).path
        if route in {"/", "/index.html"}:
            self._send(200, HTML_PAGE.encode("utf-8"), "text/html; charset=utf-8")
            return

        if route == "/api/progress":
            payload = scan_project()
            self._send(200, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), "application/json; charset=utf-8")
            return

        if route == "/health":
            self._send(200, b"ok", "text/plain; charset=utf-8")
            return

        self._send(404, b"not found", "text/plain; charset=utf-8")


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    actual_port = server.server_address[1]
    url = f"http://{HOST}:{actual_port}"

    print(f"Knowledge dashboard scanning: {ROOT}")
    print(f"Serving on: {url}")
    print("Open the URL in your browser. The pie chart refreshes automatically.")

    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
