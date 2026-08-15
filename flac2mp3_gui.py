import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

CONFIG_PATH = Path.home() / ".flac2mp3_gui.json"
BITRATES = ["128k", "192k", "256k", "320k"]
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
EXE_NAME = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def find_ffmpeg():
    """Prefer a bundled or side-by-side ffmpeg, then fall back to PATH."""
    candidates = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(Path(bundle) / EXE_NAME)
        candidates.append(Path(sys.executable).parent / EXE_NAME)
    else:
        candidates.append(Path(__file__).parent / EXE_NAME)
    for path in candidates:
        if path.is_file():
            return str(path)
    return "ffmpeg"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("FLAC to MP3")
        self.geometry("760x560")
        self.minsize(640, 460)

        self.source_var = tk.StringVar()
        self.dest_var = tk.StringVar()
        self.bitrate_var = tk.StringVar(value="320k")
        self.delete_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Idle")

        self.msgq = queue.Queue()
        self.worker = None
        self.stop_flag = threading.Event()
        self.proc = None

        self.build_ui()
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.poll)

    def build_ui(self):
        root = ttk.Frame(self, padding=12)
        root.pack(fill="both", expand=True)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(6, weight=1)

        ttk.Label(root, text="Source folder").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Entry(root, textvariable=self.source_var).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(root, text="Browse", command=self.pick_source).grid(row=0, column=2)

        ttk.Label(root, text="Destination folder").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(root, textvariable=self.dest_var).grid(row=1, column=1, sticky="ew", padx=8)
        ttk.Button(root, text="Browse", command=self.pick_dest).grid(row=1, column=2)

        opts = ttk.Frame(root)
        opts.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(12, 4))
        ttk.Label(opts, text="Bitrate").pack(side="left")
        ttk.Combobox(
            opts,
            textvariable=self.bitrate_var,
            values=BITRATES,
            state="readonly",
            width=8,
        ).pack(side="left", padx=(6, 24))
        ttk.Checkbutton(
            opts,
            text="Delete original FLAC after successful conversion",
            variable=self.delete_var,
        ).pack(side="left")

        buttons = ttk.Frame(root)
        buttons.grid(row=3, column=0, columnspan=3, sticky="ew", pady=8)
        self.convert_btn = ttk.Button(buttons, text="Convert", command=self.start)
        self.convert_btn.pack(side="left")
        self.stop_btn = ttk.Button(buttons, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=8)
        ttk.Button(buttons, text="Clear log", command=self.clear_log).pack(side="left")

        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", pady=4)

        ttk.Label(root, textvariable=self.status_var).grid(
            row=5, column=0, columnspan=3, sticky="w", pady=(0, 6)
        )

        logframe = ttk.Frame(root)
        logframe.grid(row=6, column=0, columnspan=3, sticky="nsew")
        logframe.rowconfigure(0, weight=1)
        logframe.columnconfigure(0, weight=1)
        self.log = tk.Text(logframe, height=12, wrap="none", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(logframe, orient="vertical", command=self.log.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=bar.set)

    def pick_source(self):
        path = filedialog.askdirectory(title="Select folder containing FLAC files")
        if path:
            self.source_var.set(path)

    def pick_dest(self):
        path = filedialog.askdirectory(title="Select destination folder for MP3 files")
        if path:
            self.dest_var.set(path)

    def write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def start(self):
        source = Path(self.source_var.get().strip())
        dest = Path(self.dest_var.get().strip())

        if not source.is_dir():
            messagebox.showerror("FLAC to MP3", "Pick a valid source folder.")
            return
        if not dest.is_dir():
            messagebox.showerror("FLAC to MP3", "Pick a valid destination folder.")
            return
        if self.delete_var.get():
            ok = messagebox.askyesno(
                "Delete originals",
                "Source FLAC files will be deleted after each successful conversion. Continue?",
            )
            if not ok:
                return

        self.save_config()
        self.stop_flag.clear()
        self.convert_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.configure(value=0, maximum=1)

        self.worker = threading.Thread(
            target=self.run_job,
            args=(source, dest, self.bitrate_var.get(), self.delete_var.get()),
            daemon=True,
        )
        self.worker.start()

    def stop(self):
        self.stop_flag.set()
        self.status_var.set("Stopping after current file...")
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def run_job(self, source, dest, bitrate, delete_originals):
        post = self.msgq.put
        files = sorted(source.rglob("*.flac"))

        if not files:
            post(("log", "No FLAC files found in the source folder."))
            post(("done", "Idle"))
            return

        post(("total", len(files)))
        post(("log", f"Found {len(files)} FLAC file(s). Encoding at {bitrate}."))

        converted = failed = skipped = 0

        for index, flac in enumerate(files, start=1):
            if self.stop_flag.is_set():
                post(("log", "Stopped by user."))
                break

            post(("status", f"[{index}/{len(files)}] {flac.name}"))
            out = dest / f"{flac.stem}.mp3"

            if out.exists():
                skipped += 1
                post(("log", f"SKIP  {flac.name} (destination file already exists)"))
                post(("progress", index))
                continue

            command = [
                find_ffmpeg(),
                "-nostdin",
                "-loglevel", "error",
                "-i", str(flac),
                "-c:a", "libmp3lame",
                "-b:a", bitrate,
                "-write_xing", "0",
                "-map_metadata", "0",
                "-id3v2_version", "3",
                str(out),
            ]

            try:
                self.proc = subprocess.Popen(
                    command,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    creationflags=NO_WINDOW,
                    text=True,
                )
                _, err = self.proc.communicate()
                code = self.proc.returncode
            except FileNotFoundError:
                post(("log", "ffmpeg was not found on PATH. Install it or add it to PATH."))
                post(("done", "ffmpeg not found"))
                self.proc = None
                return
            finally:
                self.proc = None

            if code == 0:
                converted += 1
                if delete_originals:
                    try:
                        flac.unlink()
                        post(("log", f"OK    {flac.name} -> {out.name} (source deleted)"))
                    except OSError as exc:
                        post(("log", f"OK    {flac.name} -> {out.name} (delete failed: {exc})"))
                else:
                    post(("log", f"OK    {flac.name} -> {out.name}"))
            else:
                failed += 1
                if out.exists():
                    try:
                        out.unlink()
                    except OSError:
                        pass
                detail = (err or "").strip().splitlines()
                reason = detail[-1] if detail else f"ffmpeg exit code {code}"
                post(("log", f"FAIL  {flac.name}: {reason}"))

            post(("progress", index))

        summary = f"Done. {converted} converted, {failed} failed, {skipped} skipped."
        post(("log", summary))
        post(("done", summary))

    def poll(self):
        try:
            while True:
                kind, value = self.msgq.get_nowait()
                if kind == "log":
                    self.write_log(value)
                elif kind == "total":
                    self.progress.configure(maximum=value, value=0)
                elif kind == "progress":
                    self.progress.configure(value=value)
                elif kind == "status":
                    self.status_var.set(value)
                elif kind == "done":
                    self.status_var.set(value)
                    self.convert_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def load_config(self):
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.source_var.set(data.get("source", ""))
        self.dest_var.set(data.get("dest", ""))
        if data.get("bitrate") in BITRATES:
            self.bitrate_var.set(data["bitrate"])
        self.delete_var.set(bool(data.get("delete_originals", False)))

    def save_config(self):
        data = {
            "source": self.source_var.get(),
            "dest": self.dest_var.get(),
            "bitrate": self.bitrate_var.get(),
            "delete_originals": self.delete_var.get(),
        }
        try:
            CONFIG_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except OSError:
            pass

    def on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("FLAC to MP3", "A conversion is running. Quit anyway?"):
                return
            self.stop()
        self.save_config()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
