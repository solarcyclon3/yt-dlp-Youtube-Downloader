@echo off
cls
set /p link="Enter video link: "
set "link=%link:&list=*%"
echo.

yt-dlp --list-formats "%link%"
set /p quality="Enter video quality (default=137+bestaudio/136+bestaudio/135+bestaudio/bestvideo+bestaudio/best): " || set "quality=137+bestaudio/136+bestaudio/135+bestaudio/bestvideo+bestaudio/best"
set /p choice="Video or Audio: (type v or a) "

if /i "%choice%"=="v" (
    yt-dlp "%link%" --no-continue --format "%quality%" -o "_0_0_Download/%%(title)s.%%(ext)s"
) else if /i "%choice%"=="a" (
    yt-dlp "%link%" --no-continue -f bestaudio --extract-audio --audio-format mp3 --audio-quality 192K --embed-thumbnail --add-metadata -o "_0_0_Download/%%(title)s.%%(ext)s"
)