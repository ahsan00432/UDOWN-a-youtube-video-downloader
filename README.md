# udown

udown is a Windows desktop downloader for videos, playlists, or MP3 audio, powered by yt-dlp.

## Run

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python udown.py
```

If `py` is not available, use your Python installation's executable in its place.

## Standalone build

Run `.\build.ps1` in PowerShell. It creates `dist\udown.exe` with a custom download icon and `dist\udown-browser-extension.zip`. The executable bundles Python and yt-dlp. FFmpeg is still external and must be installed for MP3 conversion, thumbnail embedding, or merging separate audio/video streams.

## Chrome or Edge extension

1. Run `.\register_protocol.ps1` in PowerShell after building. This registers the `udown://` handler for your Windows user and keeps the previous `ytdlp-gui://` alias working.
2. In Chrome or Edge, open Extensions, enable Developer mode, and choose **Load unpacked**.
3. Select the `browser_extension` folder in this project. Alternatively, unzip the extension archive and load the extracted folder.

The extension sends the current tab URL to udown. Browser confirmation may appear the first time it opens the app.

## Options

The **Options** menu includes playlist, subtitle, metadata, thumbnail, cookies-file, and proxy controls. The advanced JSON field accepts yt-dlp Python API options; output naming and progress hooks remain managed by the app. Pause waits between transfer progress callbacks. Stop retains partial files for yt-dlp's resume behavior when the same URL is started again.

Use downloads only when you have the right to do so and in accordance with the source site's terms.