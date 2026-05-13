# yt-dlp Youtube Downloader Web UI

Small Flask web interface for choosing yt-dlp video and audio formats.

## Setup

```powershell
cd python-server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in your browser.

Install FFmpeg and make sure it is available on your `PATH`. It is used for audio conversion and for merging high-quality video-only YouTube streams with audio.

If yt-dlp prints a warning about no supported JavaScript runtime, install Deno or another runtime supported by yt-dlp. Without it, YouTube may hide or break some formats.
