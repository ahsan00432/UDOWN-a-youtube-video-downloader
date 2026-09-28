from __future__ import annotations

import copy
import json
import queue
import sys
import threading
import tkinter as tk
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.parse import parse_qs, urlparse

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


ACTIVE_STATES = {"Downloading", "Paused", "Stopping"}


@dataclass
class DownloadTask:
    task_id: str
    url: str
    folder: Path
    media_type: str
    quality: str
    options: dict[str, object]
    status: str = "Queued"
    percent: float = 0
    detail: str = ""
    error: str = ""
    cancel_event: threading.Event = field(default_factory=threading.Event)
    resume_event: threading.Event = field(default_factory=threading.Event)

    def __post_init__(self) -> None:
        self.resume_event.set()


class UDownApp:
    def __init__(self, root: tk.Tk, initial_url: str = "") -> None:
        self.root = root
        self.root.title("udown")
        self.root.geometry("1030x760")
        self.root.minsize(820, 650)
        self.root.configure(background="#f3f5f4")

        self.events: queue.Queue[tuple[str, str, object]] = queue.Queue()
        self.tasks: dict[str, DownloadTask] = {}
        self.queue_running = False
        self.url = tk.StringVar(value=initial_url)
        self.destination = tk.StringVar(value=str(Path.home() / "Videos"))
        self.media_type = tk.StringVar(value="Video")
        self.quality = tk.StringVar(value="Best available")
        self.concurrency = tk.IntVar(value=2)
        self.summary = tk.StringVar(value="Queue is empty")
        self.write_subtitles = tk.BooleanVar(value=False)
        self.embed_metadata = tk.BooleanVar(value=False)
        self.embed_thumbnail = tk.BooleanVar(value=False)
        self.playlist_mode = tk.BooleanVar(value=True)
        self.cookie_file = tk.StringVar()
        self.proxy = tk.StringVar()
        self.advanced_options = "{}"

        self._configure_styles()
        self._build_menu()
        self._build_interface()
        self.root.after(120, self._process_events)

    def _configure_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#f3f5f4")
        style.configure(
            "TLabel", background="#f3f5f4", foreground="#263632",
            font=("Segoe UI", 10),
        )
        style.configure("Muted.TLabel", foreground="#6d7c77", font=("Segoe UI", 9))
        style.configure(
            "TEntry", padding=(10, 8), fieldbackground="#ffffff",
            bordercolor="#d7dfdb", font=("Segoe UI", 10),
        )
        style.configure(
            "TCombobox", padding=(8, 6), fieldbackground="#ffffff",
            bordercolor="#d7dfdb", font=("Segoe UI", 10),
        )
        style.configure(
            "TRadiobutton", background="#f3f5f4", foreground="#263632",
            font=("Segoe UI", 10),
        )
        style.configure(
            "Accent.TButton", background="#087f70", foreground="#ffffff",
            borderwidth=0, padding=(17, 10), font=("Segoe UI", 10, "bold"),
        )
        style.map("Accent.TButton", background=[("active", "#06695d")])
        style.configure(
            "Quiet.TButton", background="#e6ece9", foreground="#263632",
            borderwidth=0, padding=(11, 8), font=("Segoe UI", 9),
        )
        style.map("Quiet.TButton", background=[("active", "#dbe4df")])
        style.configure(
            "Treeview", background="#ffffff", fieldbackground="#ffffff",
            foreground="#263632", rowheight=31, font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading", background="#e6ece9", foreground="#263632",
            font=("Segoe UI", 9, "bold"), padding=(7, 8),
        )
        style.map("Treeview", background=[("selected", "#c8e2da")])

    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self.root)
        options_menu = tk.Menu(menu_bar, tearoff=False)
        options_menu.add_command(label="Download options...", command=self._open_options)
        menu_bar.add_cascade(label="Options", menu=options_menu)
        self.root.configure(menu=menu_bar)

    def _open_options(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("Download options")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("640x590")
        dialog.minsize(560, 480)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)

        ttk.Label(body, text="Download behavior").pack(anchor="w", pady=(0, 7))
        for label, variable in (
            ("Download playlists", self.playlist_mode),
            ("Write subtitles when available", self.write_subtitles),
            ("Embed metadata", self.embed_metadata),
            ("Embed thumbnail (requires FFmpeg)", self.embed_thumbnail),
        ):
            ttk.Checkbutton(body, text=label, variable=variable).pack(anchor="w", pady=2)

        ttk.Label(body, text="Cookies file (optional)").pack(anchor="w", pady=(15, 5))
        cookie_row = ttk.Frame(body)
        cookie_row.pack(fill="x")
        ttk.Entry(cookie_row, textvariable=self.cookie_file).pack(
            side="left", fill="x", expand=True
        )
        ttk.Button(
            cookie_row, text="Browse", style="Quiet.TButton",
            command=self._choose_cookie_file,
        ).pack(side="left", padx=(8, 0))

        ttk.Label(body, text="Proxy URL (optional)").pack(anchor="w", pady=(13, 5))
        ttk.Entry(body, textvariable=self.proxy).pack(fill="x")

        ttk.Label(body, text="Advanced yt-dlp options (JSON object)").pack(
            anchor="w", pady=(15, 5)
        )
        options_text = tk.Text(
            body, height=11, wrap="none", font=("Consolas", 9),
            background="#ffffff", foreground="#263632",
            highlightthickness=1, highlightbackground="#d7dfdb",
        )
        options_text.pack(fill="both", expand=True)
        options_text.insert("1.0", self.advanced_options)
        ttk.Label(
            body,
            text="Options are saved into new queue items. The app manages output path and progress hooks.",
            style="Muted.TLabel", wraplength=580,
        ).pack(anchor="w", pady=(6, 0))

        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(14, 0))

        def save_options() -> None:
            raw = options_text.get("1.0", "end-1c").strip() or "{}"
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as error:
                messagebox.showerror("Invalid JSON", str(error), parent=dialog)
                return
            if not isinstance(parsed, dict):
                messagebox.showerror(
                    "Invalid options", "Advanced options must be a JSON object.",
                    parent=dialog,
                )
                return
            if "progress_hooks" in parsed or "outtmpl" in parsed:
                messagebox.showerror(
                    "Managed option",
                    "The app manages 'progress_hooks' and 'outtmpl'. Remove those keys.",
                    parent=dialog,
                )
                return
            self.advanced_options = json.dumps(parsed, indent=2)
            dialog.destroy()

        ttk.Button(
            actions, text="Save options", style="Accent.TButton", command=save_options,
        ).pack(side="right")
        ttk.Button(
            actions, text="Close", style="Quiet.TButton", command=dialog.destroy,
        ).pack(side="right", padx=(0, 8))

    def _choose_cookie_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Choose cookies file",
            filetypes=(("Cookie files", "*.txt"), ("All files", "*.*")),
        )
        if selected:
            self.cookie_file.set(selected)

    def _build_interface(self) -> None:
        header = tk.Frame(self.root, bg="#183d36", height=102)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(
            header, text="udown", bg="#183d36", fg="#ffffff",
            font=("Segoe UI Semibold", 25),
        ).pack(anchor="w", padx=32, pady=(18, 0))
        tk.Label(
            header, text="DOWNLOAD QUEUE", bg="#183d36", fg="#a9c9bf",
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", padx=35, pady=(0, 0))

        content = ttk.Frame(self.root, padding=(30, 20, 30, 16))
        content.pack(fill="both", expand=True)

        ttk.Label(content, text="Add a video or playlist").pack(anchor="w")
        ttk.Entry(content, textvariable=self.url).pack(fill="x", pady=(7, 14))

        details = ttk.Frame(content)
        details.pack(fill="x", pady=(0, 13))
        ttk.Label(details, text="Save to").grid(row=0, column=0, sticky="w")
        folder_row = ttk.Frame(details)
        folder_row.grid(row=1, column=0, sticky="ew", padx=(0, 20), pady=(6, 0))
        ttk.Entry(
            folder_row, textvariable=self.destination, state="readonly",
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            folder_row, text="Browse", style="Quiet.TButton",
            command=self._choose_folder,
        ).pack(side="left", padx=(8, 0))

        type_column = ttk.Frame(details)
        type_column.grid(row=0, column=1, rowspan=2, sticky="nw")
        ttk.Label(type_column, text="Format").pack(anchor="w")
        choices = ttk.Frame(type_column)
        choices.pack(anchor="w", pady=(6, 0))
        for label, value in (("Video", "Video"), ("MP3 audio", "Audio")):
            ttk.Radiobutton(
                choices, text=label, value=value, variable=self.media_type,
                command=self._update_quality_state,
            ).pack(side="left", padx=(0, 12))

        quality_column = ttk.Frame(details)
        quality_column.grid(row=0, column=2, rowspan=2, sticky="nw", padx=(24, 20))
        ttk.Label(quality_column, text="Quality").pack(anchor="w")
        self.quality_box = ttk.Combobox(
            quality_column, textvariable=self.quality,
            values=("Best available", "1080p max", "720p max", "480p max"),
            state="readonly", width=17,
        )
        self.quality_box.pack(anchor="w", pady=(6, 0))

        concurrency_column = ttk.Frame(details)
        concurrency_column.grid(row=0, column=3, rowspan=2, sticky="nw")
        ttk.Label(concurrency_column, text="At once").pack(anchor="w")
        ttk.Spinbox(
            concurrency_column, from_=1, to=5, width=5,
            textvariable=self.concurrency, command=self._schedule_queue,
        ).pack(anchor="w", pady=(6, 0))
        details.columnconfigure(0, weight=1)

        action_row = ttk.Frame(content)
        action_row.pack(fill="x", pady=(0, 14))
        self.add_button = ttk.Button(
            action_row, text="Add to queue", style="Accent.TButton",
            command=self._add_to_queue,
        )
        self.add_button.pack(side="left")
        ttk.Label(
            action_row, text="Choose how many items can download simultaneously.",
            style="Muted.TLabel",
        ).pack(side="left", padx=(13, 0))

        ttk.Separator(content).pack(fill="x", pady=(0, 13))
        queue_header = ttk.Frame(content)
        queue_header.pack(fill="x", pady=(0, 7))
        ttk.Label(queue_header, text="Downloads").pack(side="left")
        ttk.Label(queue_header, textvariable=self.summary, style="Muted.TLabel").pack(
            side="right"
        )

        table_frame = ttk.Frame(content)
        table_frame.pack(fill="both", expand=True)
        self.download_list = ttk.Treeview(
            table_frame,
            columns=("format", "progress", "status"),
            show="tree headings",
            selectmode="browse",
        )
        self.download_list.heading("#0", text="Download / URL", anchor="w")
        self.download_list.heading("format", text="Format", anchor="w")
        self.download_list.heading("progress", text="Progress", anchor="w")
        self.download_list.heading("status", text="Status", anchor="w")
        self.download_list.column("#0", width=480, minwidth=220, stretch=True)
        self.download_list.column("format", width=125, minwidth=95, stretch=False)
        self.download_list.column("progress", width=120, minwidth=100, stretch=False)
        self.download_list.column("status", width=180, minwidth=120, stretch=False)
        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.download_list.yview,
        )
        self.download_list.configure(yscrollcommand=scrollbar.set)
        self.download_list.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.download_list.bind("<<TreeviewSelect>>", self._selection_changed)
        self.download_list.bind("<Double-1>", lambda _event: self._edit_selected())

        controls = ttk.Frame(content)
        controls.pack(fill="x", pady=(11, 0))
        self.edit_button = ttk.Button(
            controls, text="Edit", style="Quiet.TButton",
            command=self._edit_selected, state="disabled",
        )
        self.edit_button.pack(side="left", padx=(0, 7))
        self.remove_button = ttk.Button(
            controls, text="Remove", style="Quiet.TButton",
            command=self._remove_selected, state="disabled",
        )
        self.remove_button.pack(side="left", padx=(0, 7))
        self.requeue_button = ttk.Button(
            controls, text="Requeue", style="Quiet.TButton",
            command=self._requeue_selected, state="disabled",
        )
        self.requeue_button.pack(side="left", padx=(0, 7))
        self.pause_button = ttk.Button(
            controls, text="Pause", style="Quiet.TButton",
            command=self._toggle_selected_pause, state="disabled",
        )
        self.pause_button.pack(side="left", padx=(0, 7))
        self.stop_button = ttk.Button(
            controls, text="Stop", style="Quiet.TButton",
            command=self._stop_selected, state="disabled",
        )
        self.stop_button.pack(side="left")
        self.start_queue_button = ttk.Button(
            controls, text="Start queue", style="Accent.TButton",
            command=self._start_queue,
        )
        self.start_queue_button.pack(side="right")

        ttk.Label(
            content, text="Edit queued items before starting; active downloads have independent controls.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(10, 0))
        self._update_quality_state()
        if yt_dlp is None:
            self.summary.set("Install yt-dlp to enable downloads")
            self.add_button.configure(state="disabled")
            self.start_queue_button.configure(state="disabled")

    def _choose_folder(self) -> None:
        selected = filedialog.askdirectory(
            initialdir=self.destination.get(), title="Choose download folder",
        )
        if selected:
            self.destination.set(selected)

    def _update_quality_state(self) -> None:
        if self.media_type.get() == "Audio":
            self.quality_box.configure(state="disabled")
        else:
            self.quality_box.configure(state="readonly")

    def _build_download_options(self, media_type: str, quality: str) -> dict[str, object]:
        options: dict[str, object] = {
            "noplaylist": not self.playlist_mode.get(),
            "continuedl": True,
        }
        if media_type == "Audio":
            options["format"] = "bestaudio/best"
            options["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            height = {
                "Best available": None,
                "1080p max": 1080,
                "720p max": 720,
                "480p max": 480,
            }[quality]
            if height is None:
                options["format"] = "bestvideo*+bestaudio/best"
            else:
                options["format"] = (
                    f"bestvideo*[height<={height}]+bestaudio/"
                    f"best[height<={height}]/best"
                )
        if self.write_subtitles.get():
            options.update(writesubtitles=True, writeautomaticsub=True)
        if self.embed_metadata.get():
            options["addmetadata"] = True
        if self.embed_thumbnail.get():
            options["writethumbnail"] = True
            postprocessors = list(options.get("postprocessors", []))
            postprocessors.append({"key": "EmbedThumbnail"})
            options["postprocessors"] = postprocessors
        if self.cookie_file.get().strip():
            options["cookiefile"] = self.cookie_file.get().strip()
        if self.proxy.get().strip():
            options["proxy"] = self.proxy.get().strip()
        options.update(json.loads(self.advanced_options))
        return options

    def _add_to_queue(self) -> None:
        url = self.url.get().strip()
        if not url:
            messagebox.showwarning("URL required", "Paste a URL first.", parent=self.root)
            return
        task = DownloadTask(
            task_id=uuid.uuid4().hex,
            url=url,
            folder=Path(self.destination.get()).expanduser(),
            media_type=self.media_type.get(),
            quality=self.quality.get(),
            options=self._build_download_options(self.media_type.get(), self.quality.get()),
        )
        self.tasks[task.task_id] = task
        self._refresh_task(task)
        self.url.set("")
        self._update_summary()
        if self.queue_running:
            self._schedule_queue()

    def _start_queue(self) -> None:
        if yt_dlp is None:
            return
        if not any(task.status == "Queued" for task in self.tasks.values()):
            self.summary.set("Add or requeue downloads first")
            return
        self.queue_running = True
        self._schedule_queue()

    def _schedule_queue(self) -> None:
        if not self.queue_running:
            return
        try:
            limit = max(1, min(5, int(self.concurrency.get())))
        except (tk.TclError, ValueError):
            limit = 1
        active_count = sum(task.status in ACTIVE_STATES for task in self.tasks.values())
        for task in self.tasks.values():
            if active_count >= limit:
                break
            if task.status != "Queued":
                continue
            task.cancel_event.clear()
            task.resume_event.set()
            task.error = ""
            task.status = "Downloading"
            active_count += 1
            self._refresh_task(task)
            threading.Thread(
                target=self._download_task, args=(task,), daemon=True,
            ).start()
        if not any(
            task.status == "Queued" or task.status in ACTIVE_STATES
            for task in self.tasks.values()
        ):
            self.queue_running = False
        self._update_summary()
        self._selection_changed()

    def _download_task(self, task: DownloadTask) -> None:
        assert yt_dlp is not None
        options = copy.deepcopy(task.options)
        options.update({
            "outtmpl": str(task.folder / "%(title)s.%(ext)s"),
            "quiet": True,
            "no_warnings": True,
            "progress_hooks": [lambda data: self._progress_hook(task, data)],
        })
        try:
            task.folder.mkdir(parents=True, exist_ok=True)
            with yt_dlp.YoutubeDL(options) as downloader:
                result = downloader.download([task.url])
            if result:
                raise yt_dlp.utils.DownloadError(
                    f"yt-dlp reported download failure (code {result})"
                )
            self.events.put((
                task.task_id,
                "stopped" if task.cancel_event.is_set() else "complete",
                None,
            ))
        except Exception as error:
            event = "stopped" if task.cancel_event.is_set() else "error"
            self.events.put((task.task_id, event, str(error)))

    def _progress_hook(self, task: DownloadTask, data: dict[str, object]) -> None:
        while not task.resume_event.wait(timeout=0.15):
            if task.cancel_event.is_set():
                assert yt_dlp is not None
                raise yt_dlp.utils.DownloadError("Download stopped")
        if task.cancel_event.is_set():
            assert yt_dlp is not None
            raise yt_dlp.utils.DownloadError("Download stopped")

        status = data.get("status")
        if status == "downloading":
            downloaded = data.get("downloaded_bytes", 0) or 0
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            percent = downloaded / total * 100 if total else 0
            details = "  ".join(
                part for part in (
                    str(data.get("_speed_str", "")).strip(),
                    f"ETA {data.get('_eta_str')}" if data.get("_eta_str") else "",
                ) if part
            )
            self.events.put((task.task_id, "progress", (percent, details)))

    def _process_events(self) -> None:
        try:
            while True:
                task_id, event, value = self.events.get_nowait()
                task = self.tasks.get(task_id)
                if task is None:
                    continue
                if event == "progress":
                    task.percent, task.detail = value
                    if task.status != "Paused" and task.status != "Stopping":
                        task.status = "Downloading"
                elif event == "complete":
                    task.status = "Complete"
                    task.percent = 100
                    task.detail = ""
                elif event == "stopped":
                    task.status = "Stopped"
                    task.error = ""
                elif event == "error":
                    task.status = "Failed"
                    task.error = str(value)
                self._refresh_task(task)
                self._update_summary()
                self._selection_changed()
                if event in {"complete", "stopped", "error"}:
                    self._schedule_queue()
        except queue.Empty:
            pass
        self.root.after(120, self._process_events)

    def _refresh_task(self, task: DownloadTask) -> None:
        progress = f"{task.percent:.1f}%"
        if task.detail:
            progress = f"{progress}  {task.detail}"
        status = task.status
        if task.status == "Failed" and task.error:
            status = f"Failed: {task.error[:36]}"
        values = (
            "MP3 audio" if task.media_type == "Audio" else task.quality,
            progress,
            status,
        )
        if self.download_list.exists(task.task_id):
            self.download_list.item(task.task_id, text=task.url, values=values)
        else:
            self.download_list.insert(
                "", "end", iid=task.task_id, text=task.url, values=values,
            )

    def _selected_task(self) -> DownloadTask | None:
        selected = self.download_list.selection()
        return self.tasks.get(selected[0]) if selected else None

    def _selection_changed(self, _event: object = None) -> None:
        task = self._selected_task()
        if task is None:
            for button in (
                self.edit_button, self.remove_button, self.requeue_button,
                self.pause_button, self.stop_button,
            ):
                button.configure(state="disabled")
            return
        active = task.status in ACTIVE_STATES
        editable = not active and task.status != "Complete"
        self.edit_button.configure(state="normal" if editable else "disabled")
        self.remove_button.configure(state="disabled" if active else "normal")
        self.requeue_button.configure(
            state="normal" if task.status in {"Stopped", "Failed"} else "disabled"
        )
        self.pause_button.configure(
            state="normal" if task.status in {"Downloading", "Paused"} else "disabled",
            text="Resume" if task.status == "Paused" else "Pause",
        )
        self.stop_button.configure(
            state="normal" if task.status in {"Queued", "Downloading", "Paused"} else "disabled"
        )

    def _edit_selected(self) -> None:
        task = self._selected_task()
        if task is None or task.status in ACTIVE_STATES or task.status == "Complete":
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit queued download")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("590x340")
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)

        url_var = tk.StringVar(value=task.url)
        folder_var = tk.StringVar(value=str(task.folder))
        media_var = tk.StringVar(value=task.media_type)
        quality_var = tk.StringVar(value=task.quality)

        ttk.Label(body, text="URL").pack(anchor="w")
        ttk.Entry(body, textvariable=url_var).pack(fill="x", pady=(5, 12))
        ttk.Label(body, text="Save to").pack(anchor="w")
        folder_row = ttk.Frame(body)
        folder_row.pack(fill="x", pady=(5, 12))
        ttk.Entry(folder_row, textvariable=folder_var).pack(side="left", fill="x", expand=True)

        def choose_folder() -> None:
            selected = filedialog.askdirectory(
                initialdir=folder_var.get(), title="Choose download folder",
                parent=dialog,
            )
            if selected:
                folder_var.set(selected)

        ttk.Button(
            folder_row, text="Browse", style="Quiet.TButton", command=choose_folder,
        ).pack(side="left", padx=(8, 0))
        edit_settings = ttk.Frame(body)
        edit_settings.pack(fill="x", pady=(0, 15))
        ttk.Label(edit_settings, text="Format").grid(row=0, column=0, sticky="w")
        media_box = ttk.Combobox(
            edit_settings, textvariable=media_var, values=("Video", "Audio"),
            state="readonly", width=15,
        )
        media_box.grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Label(edit_settings, text="Quality").grid(row=0, column=1, sticky="w", padx=(18, 0))
        quality_box = ttk.Combobox(
            edit_settings, textvariable=quality_var,
            values=("Best available", "1080p max", "720p max", "480p max"),
            state="readonly", width=18,
        )
        quality_box.grid(row=1, column=1, sticky="w", padx=(18, 0), pady=(5, 0))

        def update_quality(_event: object = None) -> None:
            quality_box.configure(state="disabled" if media_var.get() == "Audio" else "readonly")

        media_box.bind("<<ComboboxSelected>>", update_quality)
        update_quality()

        def save_edit() -> None:
            edited_url = url_var.get().strip()
            edited_folder = folder_var.get().strip()
            if not edited_url or not edited_folder:
                messagebox.showwarning(
                    "Required fields", "URL and destination are required.", parent=dialog,
                )
                return
            task.url = edited_url
            task.folder = Path(edited_folder).expanduser()
            task.media_type = media_var.get()
            task.quality = quality_var.get()
            task.options = self._build_download_options(task.media_type, task.quality)
            task.percent = 0
            task.detail = ""
            task.error = ""
            task.status = "Queued"
            self._refresh_task(task)
            self._update_summary()
            dialog.destroy()

        actions = ttk.Frame(body)
        actions.pack(fill="x")
        ttk.Button(
            actions, text="Save changes", style="Accent.TButton", command=save_edit,
        ).pack(side="right")
        ttk.Button(
            actions, text="Cancel", style="Quiet.TButton", command=dialog.destroy,
        ).pack(side="right", padx=(0, 8))

    def _remove_selected(self) -> None:
        task = self._selected_task()
        if task is None or task.status in ACTIVE_STATES:
            return
        self.tasks.pop(task.task_id, None)
        self.download_list.delete(task.task_id)
        self._update_summary()
        self._selection_changed()

    def _requeue_selected(self) -> None:
        task = self._selected_task()
        if task is None or task.status not in {"Stopped", "Failed"}:
            return
        task.status = "Queued"
        task.error = ""
        task.cancel_event.clear()
        task.resume_event.set()
        self._refresh_task(task)
        self._update_summary()
        if self.queue_running:
            self._schedule_queue()
        self._selection_changed()

    def _toggle_selected_pause(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        if task.status == "Downloading":
            task.resume_event.clear()
            task.status = "Paused"
        elif task.status == "Paused":
            task.resume_event.set()
            task.status = "Downloading"
        else:
            return
        self._refresh_task(task)
        self._update_summary()
        self._selection_changed()

    def _stop_selected(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        if task.status == "Queued":
            task.status = "Stopped"
        elif task.status in {"Downloading", "Paused"}:
            task.status = "Stopping"
            task.cancel_event.set()
            task.resume_event.set()
        else:
            return
        self._refresh_task(task)
        self._update_summary()
        self._selection_changed()

    def _update_summary(self) -> None:
        counts = {status: 0 for status in ("Downloading", "Paused", "Queued", "Complete", "Failed", "Stopped")}
        for task in self.tasks.values():
            status = task.status
            if status == "Stopping":
                status = "Downloading"
            if status in counts:
                counts[status] += 1
        self.summary.set(
            f"{counts['Downloading']} active  |  {counts['Queued']} queued  |  "
            f"{counts['Complete']} complete  |  {counts['Failed']} failed"
            if self.tasks else "Queue is empty"
        )


def launch_url_from_argument(argument: str) -> str:
    if argument.startswith(("udown://", "ytdlp-gui://")):
        return parse_qs(urlparse(argument).query).get("url", [""])[0]
    if argument.startswith(("http://", "https://")):
        return argument
    return ""


def resource_path(relative_path: str) -> Path:
    base_path = Path(getattr(sys, "_MEIPASS", Path(__file__).parent))
    return base_path / relative_path


def main() -> None:
    initial_url = launch_url_from_argument(sys.argv[1] if len(sys.argv) > 1 else "")
    root = tk.Tk()
    try:
        root.iconbitmap(str(resource_path("assets/udown.ico")))
    except tk.TclError:
        pass
    UDownApp(root, initial_url=initial_url)
    root.mainloop()


if __name__ == "__main__":
    main()