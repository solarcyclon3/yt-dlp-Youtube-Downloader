from __future__ import annotations

import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from flask import Flask, after_this_request, jsonify, render_template_string, request, send_file

try:
    import yt_dlp
except ImportError:  # pragma: no cover - surfaced in the web UI
    yt_dlp = None


APP_ROOT = Path(__file__).resolve().parent
DOWNLOAD_ROOT = APP_ROOT / "downloads"
DOWNLOAD_ROOT.mkdir(exist_ok=True)
DOWNLOAD_JOBS: dict[str, dict[str, Any]] = {}
DOWNLOAD_LOCK = threading.Lock()

app = Flask(__name__)


PAGE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>yt-dlp Youtube Downloader</title>
  <style>
    :root {
      color-scheme: dark;
      --bg: #101114;
      --panel: rgba(255, 255, 255, 0.075);
      --panel-strong: rgba(255, 255, 255, 0.12);
      --text: #f4f5f7;
      --muted: #b5bac5;
      --line: rgba(255, 255, 255, 0.16);
      --accent: #36c2a1;
      --accent-2: #f6c85f;
      --danger: #ff6b6b;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      background:
        radial-gradient(circle at 12% 12%, rgba(54, 194, 161, 0.18), transparent 34rem),
        radial-gradient(circle at 86% 18%, rgba(246, 200, 95, 0.16), transparent 30rem),
        linear-gradient(135deg, #101114 0%, #1a1b20 52%, #111419 100%);
      color: var(--text);
    }

    header {
      position: fixed;
      inset: 0 0 auto 0;
      z-index: 10;
      height: 72px;
      display: flex;
      align-items: center;
      padding: 0 clamp(18px, 5vw, 64px);
      border-bottom: 1px solid var(--line);
      background: rgba(16, 17, 20, 0.62);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
    }

    .logo {
      font-size: clamp(1.05rem, 2.4vw, 1.45rem);
      font-weight: 800;
      letter-spacing: 0;
      white-space: nowrap;
    }

    main {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 112px 0 48px;
    }

    .search {
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 12px;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: 0 24px 80px rgba(0, 0, 0, 0.24);
    }

    input, select, button {
      min-height: 46px;
      border: 1px solid var(--line);
      border-radius: 8px;
      color: var(--text);
      background: rgba(255, 255, 255, 0.08);
      font: inherit;
    }

    input {
      width: 100%;
      padding: 0 14px;
      outline: none;
    }

    input:focus, select:focus {
      border-color: rgba(54, 194, 161, 0.72);
      box-shadow: 0 0 0 3px rgba(54, 194, 161, 0.16);
    }

    button {
      cursor: pointer;
      padding: 0 18px;
      font-weight: 750;
      background: var(--accent);
      border-color: transparent;
      color: #06231c;
    }

    button.secondary {
      background: var(--accent-2);
      color: #2b2105;
    }

    button:disabled {
      cursor: wait;
      opacity: 0.65;
    }

    .status {
      min-height: 28px;
      margin: 14px 2px 20px;
      color: var(--muted);
    }

    .status.error { color: var(--danger); }

    .video-title {
      margin: 0 0 18px;
      font-size: clamp(1.35rem, 4vw, 2.15rem);
      line-height: 1.15;
    }

    .sections {
      display: grid;
      gap: 22px;
    }

    section {
      border-top: 1px solid var(--line);
      padding-top: 20px;
    }

    h2 {
      margin: 0 0 12px;
      font-size: 1rem;
      color: var(--muted);
      font-weight: 750;
    }

    .table-wrap {
      overflow-x: auto;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.055);
    }

    table {
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
    }

    th, td {
      padding: 12px 14px;
      text-align: left;
      border-bottom: 1px solid rgba(255, 255, 255, 0.1);
      vertical-align: middle;
      font-size: 0.92rem;
    }

    th {
      color: var(--muted);
      font-size: 0.78rem;
      text-transform: uppercase;
      font-weight: 800;
    }

    tr:last-child td { border-bottom: 0; }
    tbody tr:hover { background: rgba(255, 255, 255, 0.055); }

    .pick { width: 44px; }
    .download-bar {
      display: flex;
      justify-content: flex-end;
      margin-top: 14px;
    }

    .progress-panel {
      margin-top: 14px;
      padding: 16px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.06);
    }

    .progress-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
      color: var(--muted);
      font-weight: 750;
    }

    .progress-track {
      height: 12px;
      overflow: hidden;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.12);
    }

    .progress-fill {
      width: 0%;
      height: 100%;
      border-radius: inherit;
      background: linear-gradient(90deg, var(--accent), var(--accent-2));
      transition: width 180ms ease;
    }

    .progress-grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }

    .progress-stat {
      min-width: 0;
      padding: 10px;
      border: 1px solid rgba(255, 255, 255, 0.1);
      border-radius: 8px;
      background: rgba(255, 255, 255, 0.045);
    }

    .progress-stat span {
      display: block;
      color: var(--muted);
      font-size: 0.76rem;
      font-weight: 750;
      text-transform: uppercase;
    }

    .progress-stat strong {
      display: block;
      margin-top: 4px;
      overflow-wrap: anywhere;
      font-size: 0.96rem;
    }

    .progress-actions {
      display: flex;
      justify-content: flex-end;
      margin-top: 14px;
    }

    .hidden { display: none; }

    @media (max-width: 680px) {
      header { height: 64px; }
      main { padding-top: 92px; }
      .search { grid-template-columns: 1fr; }
      .progress-grid { grid-template-columns: 1fr 1fr; }
      button { width: 100%; }
    }
  </style>
</head>
<body>
  <header>
    <div class="logo">yt-dlp Youtube Downloader</div>
  </header>

  <main>
    <form class="search" id="formatForm">
      <input id="url" type="url" placeholder="Paste a YouTube link and press Enter" autocomplete="off" required>
      <button id="loadButton" type="submit">Download</button>
    </form>

    <div id="status" class="status"></div>

    <div id="results" class="hidden">
      <h1 id="videoTitle" class="video-title"></h1>

      <div class="sections">
        <section>
          <h2>Video</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th class="pick"></th>
                  <th>ID</th>
                  <th>Quality</th>
                  <th>Extension</th>
                  <th>Resolution</th>
                  <th>FPS</th>
                  <th>Size</th>
                  <th>Video</th>
                  <th>Audio</th>
                  <th>Download</th>
                </tr>
              </thead>
              <tbody id="videoRows"></tbody>
            </table>
          </div>
        </section>

        <section>
          <h2>Audio (mp3, webm, m4a, or original)</h2>
          <div class="table-wrap">
            <table>
              <thead>
                <tr>
                  <th class="pick"></th>
                  <th>ID</th>
                  <th>Quality</th>
                  <th>Download As</th>
                  <th>Extension</th>
                  <th>Bitrate</th>
                  <th>Size</th>
                  <th>Audio Codec</th>
                </tr>
              </thead>
              <tbody id="audioRows"></tbody>
            </table>
          </div>
        </section>
      </div>

      <form id="downloadForm" class="download-bar">
        <input type="hidden" name="url" id="downloadUrl">
        <input type="hidden" name="kind" id="downloadKind">
        <input type="hidden" name="format_id" id="downloadFormat">
        <input type="hidden" name="audio_ext" id="downloadAudioExt">
        <button class="secondary" type="submit">Download Selected</button>
      </form>

      <div id="progressPanel" class="progress-panel hidden">
        <div class="progress-head">
          <div id="progressPhase">Preparing download...</div>
          <div id="progressPercent">0%</div>
        </div>
        <div class="progress-track" aria-label="Download progress">
          <div id="progressFill" class="progress-fill"></div>
        </div>
        <div class="progress-grid">
          <div class="progress-stat">
            <span>Total size</span>
            <strong id="progressTotal">Unknown</strong>
          </div>
          <div class="progress-stat">
            <span>Downloaded</span>
            <strong id="progressDownloaded">0 B</strong>
          </div>
          <div class="progress-stat">
            <span>Time</span>
            <strong id="progressTime">0s</strong>
          </div>
          <div class="progress-stat">
            <span>Remaining</span>
            <strong id="progressEta">Unknown</strong>
          </div>
        </div>
        <div class="progress-actions">
          <button id="downloadAnotherButton" class="secondary hidden" type="button">Download Another Video</button>
        </div>
      </div>
      <iframe id="downloadFrame" class="hidden" title="download"></iframe>
    </div>
  </main>

  <script>
    const form = document.querySelector("#formatForm");
    const loadButton = document.querySelector("#loadButton");
    const statusBox = document.querySelector("#status");
    const results = document.querySelector("#results");
    const videoRows = document.querySelector("#videoRows");
    const audioRows = document.querySelector("#audioRows");
    const title = document.querySelector("#videoTitle");
    const downloadForm = document.querySelector("#downloadForm");
    const progressPanel = document.querySelector("#progressPanel");
    const progressPhase = document.querySelector("#progressPhase");
    const progressPercent = document.querySelector("#progressPercent");
    const progressFill = document.querySelector("#progressFill");
    const progressTotal = document.querySelector("#progressTotal");
    const progressDownloaded = document.querySelector("#progressDownloaded");
    const progressTime = document.querySelector("#progressTime");
    const progressEta = document.querySelector("#progressEta");
    const downloadAnotherButton = document.querySelector("#downloadAnotherButton");
    const downloadFrame = document.querySelector("#downloadFrame");
    let activeJobId = null;
    let pollTimer = null;
    let fileDownloadStarted = false;

    function setStatus(message, isError = false) {
      statusBox.textContent = message;
      statusBox.classList.toggle("error", isError);
    }

    function sizeLabel(bytes) {
      if (!bytes) return "Unknown";
      const units = ["B", "KB", "MB", "GB"];
      let value = bytes;
      let index = 0;
      while (value >= 1024 && index < units.length - 1) {
        value /= 1024;
        index += 1;
      }
      return `${value.toFixed(value >= 10 || index === 0 ? 0 : 1)} ${units[index]}`;
    }

    function timeLabel(seconds) {
      if (seconds === null || seconds === undefined || Number.isNaN(Number(seconds))) return "Unknown";
      let remaining = Math.max(0, Math.round(Number(seconds)));
      const hours = Math.floor(remaining / 3600);
      remaining -= hours * 3600;
      const minutes = Math.floor(remaining / 60);
      const secs = remaining - minutes * 60;
      if (hours) return `${hours}h ${minutes}m ${secs}s`;
      if (minutes) return `${minutes}m ${secs}s`;
      return `${secs}s`;
    }

    function cell(text) {
      const td = document.createElement("td");
      td.textContent = text || "Unknown";
      return td;
    }

    function pickCell(name, formatId, kind, totalBytes) {
      const td = document.createElement("td");
      const input = document.createElement("input");
      input.type = "radio";
      input.name = "formatPick";
      input.value = formatId;
      input.dataset.kind = kind;
      input.dataset.totalBytes = totalBytes ? String(totalBytes) : "";
      td.append(input);
      return td;
    }

    function resetProgress() {
      activeJobId = null;
      fileDownloadStarted = false;
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      progressPanel.classList.add("hidden");
      downloadAnotherButton.classList.add("hidden");
      progressPhase.textContent = "Preparing download...";
      progressPercent.textContent = "0%";
      progressFill.style.width = "0%";
      progressTotal.textContent = "Unknown";
      progressDownloaded.textContent = "0 B";
      progressTime.textContent = "0s";
      progressEta.textContent = "Unknown";
      downloadFrame.removeAttribute("src");
    }

    function updateProgress(job) {
      const percent = Number(job.percent);
      const hasPercent = Number.isFinite(percent);
      const displayPercent = hasPercent ? Math.max(0, Math.min(100, percent)) : 0;
      progressFill.style.width = `${displayPercent}%`;
      progressPercent.textContent = hasPercent ? `${displayPercent.toFixed(displayPercent >= 10 ? 0 : 1)}%` : "Working";
      progressPhase.textContent = job.phase || job.status || "Working...";
      progressTotal.textContent = sizeLabel(job.total_bytes);
      progressDownloaded.textContent = sizeLabel(job.downloaded_bytes);
      progressTime.textContent = timeLabel(job.elapsed_seconds);
      progressEta.textContent = job.status === "finished" ? "0s" : timeLabel(job.eta);

      if (job.status === "finished") {
        progressFill.style.width = "100%";
        progressPercent.textContent = "100%";
        progressPhase.textContent = "Download ready";
        downloadAnotherButton.classList.remove("hidden");
        if (!fileDownloadStarted && job.download_url) {
          fileDownloadStarted = true;
          downloadFrame.src = job.download_url;
        }
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }

      if (job.status === "error") {
        activeJobId = null;
        downloadAnotherButton.classList.remove("hidden");
        downloadForm.classList.remove("hidden");
        setStatus(job.error || "Download failed.", true);
        if (pollTimer) {
          clearInterval(pollTimer);
          pollTimer = null;
        }
      }
    }

    async function pollProgress(jobId) {
      const response = await fetch(`/api/downloads/${encodeURIComponent(jobId)}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "Could not read download progress.");
      updateProgress(data);
    }

    function renderRows(items, target, kind) {
      target.replaceChildren();
      if (!items.length) {
        const tr = document.createElement("tr");
        const td = document.createElement("td");
        td.colSpan = kind === "video" ? 10 : 8;
        td.textContent = `No ${kind} formats found.`;
        tr.append(td);
        target.append(tr);
        return;
      }

      items.forEach((item, index) => {
        const tr = document.createElement("tr");
        const downloadFormat = kind === "video" && item.needs_audio
          ? `${item.format_id}+bestaudio/best`
          : item.format_id;
        const totalBytes = item.download_filesize || item.filesize || item.filesize_approx;
        tr.append(pickCell("formatPick", downloadFormat, kind, totalBytes));
        tr.append(cell(item.format_id));
        tr.append(cell(item.format_note || item.resolution || item.format_id));

        if (kind === "video") {
          tr.append(cell(item.ext));
          tr.append(cell(item.resolution));
          tr.append(cell(item.fps ? String(item.fps) : ""));
          tr.append(cell(sizeLabel(totalBytes)));
          tr.append(cell(item.vcodec));
          tr.append(cell(item.acodec));
          tr.append(cell(item.needs_audio ? "Merge with best audio" : "Ready"));
        } else {
          const selectTd = document.createElement("td");
          const select = document.createElement("select");
          select.dataset.formatId = item.format_id;
          ["mp3", "webm", "m4a", "original"].forEach((ext) => {
            const option = document.createElement("option");
            option.value = ext;
            option.textContent = ext;
            select.append(option);
          });
          selectTd.append(select);
          tr.append(selectTd);
          tr.append(cell(item.ext));
          tr.append(cell(item.abr ? `${item.abr} kbps` : ""));
          tr.append(cell(sizeLabel(item.filesize || item.filesize_approx)));
          tr.append(cell(item.acodec));
        }

        target.append(tr);
        if (index === 0 && kind === "video") {
          tr.querySelector("input").checked = true;
        }
      });
    }

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const url = document.querySelector("#url").value.trim();
      if (!url) return;

      loadButton.disabled = true;
      results.classList.add("hidden");
      resetProgress();
      setStatus("Reading available formats...");

      try {
        const response = await fetch("/api/formats", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ url })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not read formats.");

        title.textContent = data.title || "Available downloads";
        renderRows(data.video_formats, videoRows, "video");
        renderRows(data.audio_formats, audioRows, "audio");
        document.querySelector("#downloadUrl").value = url;
        results.classList.remove("hidden");
        setStatus("Choose a format, then download.");
      } catch (error) {
        setStatus(error.message, true);
      } finally {
        loadButton.disabled = false;
      }
    });

    downloadForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (activeJobId) return;

      const selected = document.querySelector("input[name='formatPick']:checked");
      if (!selected) {
        setStatus("Select one video or audio row first.", true);
        return;
      }

      document.querySelector("#downloadKind").value = selected.dataset.kind;
      document.querySelector("#downloadFormat").value = selected.value;
      const extSelect = selected.dataset.kind === "audio"
        ? document.querySelector(`select[data-format-id="${CSS.escape(selected.value)}"]`)
        : null;
      document.querySelector("#downloadAudioExt").value = extSelect ? extSelect.value : "";

      activeJobId = "starting";
      fileDownloadStarted = false;
      downloadForm.classList.add("hidden");
      progressPanel.classList.remove("hidden");
      downloadAnotherButton.classList.add("hidden");
      setStatus("Preparing your download...");
      updateProgress({
        status: "queued",
        phase: "Queued",
        percent: 0,
        total_bytes: Number(selected.dataset.totalBytes) || null,
        downloaded_bytes: 0,
        elapsed_seconds: 0,
        eta: null
      });

      try {
        const response = await fetch("/api/downloads", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            url: document.querySelector("#downloadUrl").value,
            kind: selected.dataset.kind,
            format_id: selected.value,
            audio_ext: extSelect ? extSelect.value : "original",
            expected_total_bytes: Number(selected.dataset.totalBytes) || null
          })
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "Could not start download.");

        activeJobId = data.job_id;
        setStatus("Downloading...");
        await pollProgress(activeJobId);
        pollTimer = setInterval(() => {
          pollProgress(activeJobId).catch((error) => {
            setStatus(error.message, true);
            if (pollTimer) {
              clearInterval(pollTimer);
              pollTimer = null;
            }
          });
        }, 800);
      } catch (error) {
        resetProgress();
        downloadForm.classList.remove("hidden");
        setStatus(error.message, true);
      }
    });

    downloadAnotherButton.addEventListener("click", () => {
      resetProgress();
      results.classList.add("hidden");
      downloadForm.classList.remove("hidden");
      document.querySelector("#url").value = "";
      document.querySelector("#downloadUrl").value = "";
      setStatus("");
      document.querySelector("#url").focus();
    });
  </script>
</body>
</html>
"""


def clean_old_downloads(max_age_seconds: int = 60 * 60) -> None:
    now = time.time()
    active_dirs: set[str] = set()
    with DOWNLOAD_LOCK:
        for job_id, job in list(DOWNLOAD_JOBS.items()):
            end_time = job.get("finished_at") or job.get("started_at") or now
            if job.get("status") in {"finished", "error"} and now - end_time > max_age_seconds:
                DOWNLOAD_JOBS.pop(job_id, None)
                continue

            job_dir = job.get("job_dir")
            if job_dir:
                active_dirs.add(str(job_dir))

    for path in DOWNLOAD_ROOT.iterdir():
        try:
            if path.is_dir() and str(path) not in active_dirs and now - path.stat().st_mtime > max_age_seconds:
                shutil.rmtree(path, ignore_errors=True)
        except OSError:
            continue


def ensure_yt_dlp() -> None:
    if yt_dlp is None:
        raise RuntimeError("yt-dlp is not installed. Run: pip install -r requirements.txt")


def format_size(item: dict[str, Any]) -> int | None:
    for key in ("filesize", "filesize_approx"):
        value = item.get(key)
        if value:
            return int(value)
    return None


def compact_format(item: dict[str, Any]) -> dict[str, Any]:
    height = item.get("height")
    width = item.get("width")
    resolution = item.get("resolution")
    if not resolution and width and height:
        resolution = f"{width}x{height}"
    elif not resolution and height:
        resolution = f"{height}p"

    return {
        "format_id": item.get("format_id"),
        "format_note": item.get("format_note") or item.get("format"),
        "ext": item.get("ext"),
        "resolution": resolution,
        "height": height or 0,
        "fps": item.get("fps"),
        "filesize": item.get("filesize"),
        "filesize_approx": item.get("filesize_approx"),
        "download_filesize": format_size(item),
        "vcodec": item.get("vcodec"),
        "acodec": item.get("acodec"),
        "abr": item.get("abr"),
        "needs_audio": item.get("acodec") == "none",
    }


def job_snapshot(job_id: str) -> dict[str, Any] | None:
    with DOWNLOAD_LOCK:
        job = DOWNLOAD_JOBS.get(job_id)
        if not job:
            return None

        snapshot = {
            "id": job_id,
            "status": job.get("status"),
            "phase": job.get("phase"),
            "percent": job.get("percent"),
            "downloaded_bytes": job.get("downloaded_bytes"),
            "total_bytes": job.get("total_bytes"),
            "elapsed_seconds": job.get("elapsed_seconds"),
            "eta": job.get("eta"),
            "speed": job.get("speed"),
            "error": job.get("error"),
        }
        if job.get("status") == "finished":
            snapshot["download_url"] = f"/download/{job_id}"
        return snapshot


def update_job(job_id: str, **changes: Any) -> None:
    with DOWNLOAD_LOCK:
        job = DOWNLOAD_JOBS.get(job_id)
        if job:
            job.update(changes)


def make_progress_hook(job_id: str):
    def progress_hook(data: dict[str, Any]) -> None:
        now = time.time()
        status = data.get("status")
        with DOWNLOAD_LOCK:
            job = DOWNLOAD_JOBS.get(job_id)
            if not job:
                return

            started_at = job.get("started_at") or now
            job["elapsed_seconds"] = max(0, now - started_at)

            if status == "downloading":
                filename = str(data.get("filename") or data.get("tmpfilename") or "")
                previous_filename = job.get("current_filename")
                if previous_filename and filename and filename != previous_filename:
                    job["completed_bytes"] = int(job.get("completed_bytes") or 0) + int(
                        job.get("current_downloaded") or 0
                    )
                    job["current_downloaded"] = 0
                    job["current_total"] = None

                if filename:
                    job["current_filename"] = filename

                current_downloaded = int(data.get("downloaded_bytes") or 0)
                current_total_raw = data.get("total_bytes") or data.get("total_bytes_estimate")
                current_total = int(current_total_raw) if current_total_raw else None
                completed_bytes = int(job.get("completed_bytes") or 0)
                downloaded_bytes = completed_bytes + current_downloaded
                expected_total = job.get("expected_total_bytes")
                total_bytes = expected_total or (completed_bytes + current_total if current_total else None)
                speed = data.get("speed") or 0
                eta = data.get("eta")
                if speed and total_bytes:
                    eta = max(0, (total_bytes - downloaded_bytes) / speed)

                job.update(
                    {
                        "status": "downloading",
                        "phase": "Downloading",
                        "downloaded_bytes": downloaded_bytes,
                        "total_bytes": total_bytes,
                        "current_downloaded": current_downloaded,
                        "current_total": current_total,
                        "speed": speed,
                        "eta": eta,
                    }
                )
                if total_bytes:
                    job["percent"] = min(99.0, max(0.0, downloaded_bytes * 100 / total_bytes))

            elif status == "finished":
                current_downloaded = int(data.get("downloaded_bytes") or job.get("current_downloaded") or 0)
                current_total_raw = (
                    data.get("total_bytes")
                    or data.get("total_bytes_estimate")
                    or job.get("current_total")
                    or current_downloaded
                )
                finished_bytes = int(current_total_raw or current_downloaded)
                completed_bytes = int(job.get("completed_bytes") or 0) + finished_bytes
                expected_total = job.get("expected_total_bytes")
                total_bytes = expected_total or completed_bytes

                job.update(
                    {
                        "status": "processing",
                        "phase": "Processing file...",
                        "completed_bytes": completed_bytes,
                        "current_filename": None,
                        "current_downloaded": 0,
                        "current_total": None,
                        "downloaded_bytes": min(completed_bytes, total_bytes),
                        "total_bytes": total_bytes,
                        "eta": 0,
                    }
                )
                if total_bytes:
                    job["percent"] = min(99.0, max(0.0, completed_bytes * 100 / total_bytes))

    return progress_hook


def make_postprocessor_hook(job_id: str):
    def postprocessor_hook(data: dict[str, Any]) -> None:
        status = data.get("status")
        postprocessor = data.get("postprocessor") or "Post-processing"
        if status not in {"started", "processing"}:
            return

        phase = "Merging audio and video..." if "Merger" in postprocessor else "Processing file..."
        update_job(job_id, status="processing", phase=phase, eta=0)

    return postprocessor_hook


def downloaded_file(job_dir: Path) -> Path | None:
    files = [path for path in job_dir.iterdir() if path.is_file() and not path.name.endswith(".part")]
    if not files:
        return None
    return max(files, key=lambda path: path.stat().st_mtime)


def run_download_job(job_id: str, url: str, kind: str, format_id: str, audio_ext: str, job_dir: Path) -> None:
    output_template = str(job_dir / "%(title).180B [%(id)s].%(ext)s")
    options: dict[str, Any] = {
        "format": format_id,
        "outtmpl": output_template,
        "noplaylist": True,
        "quiet": True,
        "restrictfilenames": True,
        "progress_hooks": [make_progress_hook(job_id)],
        "postprocessor_hooks": [make_postprocessor_hook(job_id)],
    }

    if kind == "audio" and audio_ext != "original":
        options["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_ext,
                "preferredquality": "0",
            }
        ]

    try:
        update_job(job_id, status="downloading", phase="Starting download...")
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([url])

        file_path = downloaded_file(job_dir)
        if not file_path:
            raise RuntimeError("Download finished, but no output file was found.")

        file_size = file_path.stat().st_size
        update_job(
            job_id,
            status="finished",
            phase="Download ready",
            percent=100.0,
            downloaded_bytes=file_size,
            total_bytes=file_size,
            eta=0,
            speed=0,
            file_path=file_path,
            finished_at=time.time(),
        )
    except Exception as exc:
        shutil.rmtree(job_dir, ignore_errors=True)
        update_job(
            job_id,
            status="error",
            phase="Download failed",
            error=f"yt-dlp download failed: {exc}",
            eta=0,
            finished_at=time.time(),
        )


@app.get("/")
def index():
    clean_old_downloads()
    return render_template_string(PAGE)


@app.post("/api/formats")
def formats():
    clean_old_downloads()
    ensure_yt_dlp()

    url = str((request.json or {}).get("url") or "").strip()
    if not url:
        return jsonify({"error": "Paste a YouTube link first."}), 400

    options = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        return jsonify({"error": f"yt-dlp could not read this link: {exc}"}), 400

    raw_formats = info.get("formats") or []
    audio_source_formats = [
        item
        for item in raw_formats
        if item.get("vcodec") == "none" and item.get("acodec") != "none" and item.get("format_id")
    ]
    best_audio = max(audio_source_formats, key=lambda item: item.get("abr") or item.get("tbr") or 0, default=None)
    best_audio_size = format_size(best_audio) if best_audio else None

    video_formats = []
    for item in raw_formats:
        if item.get("vcodec") == "none" or not item.get("format_id"):
            continue

        video_format = compact_format(item)
        video_size = format_size(item)
        if video_format["needs_audio"] and video_size and best_audio_size:
            video_format["download_filesize"] = video_size + best_audio_size
        video_formats.append(video_format)

    audio_formats = [compact_format(item) for item in audio_source_formats]

    video_formats.sort(key=lambda item: (item.get("height") or 0, item.get("fps") or 0), reverse=True)
    audio_formats.sort(key=lambda item: item.get("abr") or 0, reverse=True)

    return jsonify(
        {
            "title": info.get("title"),
            "video_formats": video_formats,
            "audio_formats": audio_formats,
        }
    )


@app.post("/api/downloads")
def start_download():
    clean_old_downloads()
    ensure_yt_dlp()

    payload = request.json or {}
    url = str(payload.get("url") or "").strip()
    kind = str(payload.get("kind") or "").strip()
    format_id = str(payload.get("format_id") or "").strip()
    audio_ext = str(payload.get("audio_ext") or "original").strip()
    expected_total = payload.get("expected_total_bytes")
    try:
        expected_total_bytes = int(expected_total) if expected_total else None
    except (TypeError, ValueError):
        expected_total_bytes = None

    if not url or not format_id or kind not in {"video", "audio"}:
        return jsonify({"error": "Missing download selection."}), 400

    job_dir = DOWNLOAD_ROOT / str(uuid.uuid4())
    job_dir.mkdir(parents=True, exist_ok=True)
    job_id = job_dir.name
    with DOWNLOAD_LOCK:
        DOWNLOAD_JOBS[job_id] = {
            "status": "queued",
            "phase": "Queued",
            "percent": 0.0,
            "downloaded_bytes": 0,
            "total_bytes": expected_total_bytes,
            "expected_total_bytes": expected_total_bytes,
            "elapsed_seconds": 0,
            "eta": None,
            "speed": 0,
            "error": None,
            "job_dir": job_dir,
            "file_path": None,
            "started_at": time.time(),
            "finished_at": None,
            "completed_bytes": 0,
            "current_filename": None,
            "current_downloaded": 0,
            "current_total": None,
        }

    thread = threading.Thread(
        target=run_download_job,
        args=(job_id, url, kind, format_id, audio_ext, job_dir),
        daemon=True,
    )
    thread.start()

    return jsonify({"job_id": job_id})


@app.get("/api/downloads/<job_id>")
def download_progress(job_id: str):
    snapshot = job_snapshot(job_id)
    if not snapshot:
        return jsonify({"error": "Download job was not found."}), 404
    return jsonify(snapshot)


@app.get("/download/<job_id>")
def download(job_id: str):
    snapshot = job_snapshot(job_id)
    if not snapshot:
        return "Download job was not found.", 404
    if snapshot.get("status") != "finished":
        return "Download is not ready yet.", 409

    with DOWNLOAD_LOCK:
        job = DOWNLOAD_JOBS.get(job_id) or {}
        file_path = job.get("file_path")
        job_dir = job.get("job_dir")

    if not file_path or not Path(file_path).exists():
        return "Download file was not found.", 404

    @after_this_request
    def touch_job_dir(response):
        if job_dir:
            Path(job_dir).touch(exist_ok=True)
        return response

    file_path = Path(file_path)
    return send_file(file_path, as_attachment=True, download_name=file_path.name)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
