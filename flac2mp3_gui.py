import json
import queue
import subprocess
import sys
import threading
import tkinter as tk
import customtkinter as ctk
from pathlib import Path
from tkinter import filedialog

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


# ---- Framework Setup ----
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class FileRow(ctk.CTkFrame):
    """A single file row inside the scrollable file list.

    Contains a checkbox (checked by default), the file name label,
    and the relative-path label.
    """

    def __init__(self, master, flac_path: Path, rel_path: str, **kwargs):
        super().__init__(master, **kwargs, corner_radius=0)
        self.flac_path = flac_path
        self.rel_path_str = rel_path

        self.checkbox = ctk.CTkCheckBox(self, text="", corner_radius=50, checkbox_width=18, checkbox_height=18)
        self.checkbox.deselect()
        self.checkbox.grid(row=0, column=0, padx=(8, 8), pady=2, sticky="w")

        name_label = ctk.CTkLabel(self, text=flac_path.name, anchor="w")
        name_label.grid(row=0, column=1, padx=(8, 4), pady=2, sticky="w")

        rel_label = ctk.CTkLabel(self, text=rel_path, anchor="w")
        rel_label.grid(row=0, column=3, padx=(8, 4), pady=2, sticky="w")

        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(3, weight=3)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("FLAC to MP3")
        self.geometry("900x720")
        self.minsize(800, 600)

        self.source_var = ctk.StringVar()
        self.dest_var = ctk.StringVar()
        self.bitrate_var = ctk.StringVar(value="320k")
        self.delete_var = ctk.BooleanVar(value=False)

        self.msgq = queue.Queue()
        self.worker = None
        self.stop_flag = threading.Event()
        self.proc = None

        # File selection state
        self.file_rows = []  # List of FileRow widgets currently displayed
        self.row_map = {}  # Maps absolute file path (str) -> FileRow widget, for dynamic removal

        self.build_ui()
        self.update_idletasks()
        self.load_config()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.poll)

    def build_ui(self):
        root = self
        root.grid_columnconfigure(0, weight=1)

        # Lock all top control rows
        root.grid_rowconfigure(0, weight=0)
        root.grid_rowconfigure(1, weight=0)
        root.grid_rowconfigure(2, weight=0)
        root.grid_rowconfigure(3, weight=0)
        # ONLY list_container expands
        root.grid_rowconfigure(4, weight=1)
        # Lock bottom elements
        root.grid_rowconfigure(5, weight=0) # Progress
        root.grid_rowconfigure(6, weight=0) # Button Row
        root.grid_rowconfigure(7, weight=0) # Log Box
        root.grid_rowconfigure(8, weight=0) # Empty/Buffer

        # ---- Source & Destination rows ----
        source_frame = ctk.CTkFrame(root, corner_radius=0)
        source_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=4)

        ctk.CTkLabel(source_frame, text="Source folder").pack(anchor="w", padx=4)
        self.source_entry = ctk.CTkEntry(source_frame, placeholder_text="Select source folder containing FLAC files", textvariable=self.source_var)
        self.source_entry.pack(fill="x", pady=4, padx=4)
        self.source_entry.bind("<KeyRelease>", lambda e: self.on_source_change())

        browse_btn = ctk.CTkButton(source_frame, text="Browse", command=self.pick_source, corner_radius=50)
        browse_btn.pack(anchor="e", padx=4, pady=4)

        dest_frame = ctk.CTkFrame(root, corner_radius=0)
        dest_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=4)

        ctk.CTkLabel(dest_frame, text="Destination folder").pack(anchor="w", padx=4)
        self.dest_entry = ctk.CTkEntry(dest_frame, placeholder_text="Select destination folder for MP3 files", textvariable=self.dest_var)
        self.dest_entry.pack(fill="x", pady=4, padx=4)
        self.dest_entry.pack_propagate(False)

        dest_browse = ctk.CTkButton(dest_frame, text="Browse", command=self.pick_dest, corner_radius=50)
        dest_browse.pack(anchor="e", padx=4, pady=4)

        # Auto-refresh file list when source path changes
        self._source_var_trace = self.source_var.trace_add("write", self.on_source_change)

        # ---- Options row ----
        opts_frame = ctk.CTkFrame(root, corner_radius=0)
        opts_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=4)

        ctk.CTkLabel(opts_frame, text="Bitrate:").pack(side="left", padx=(4, 8))
        self.bitrate_cb = ctk.CTkComboBox(opts_frame, values=BITRATES, state="readonly", width=120)
        self.bitrate_cb.set(self.bitrate_var.get())
        self.bitrate_cb.bind("<<ComboboxSelected>>", lambda e: self.bitrate_var.set(self.bitrate_cb.get()))
        self.bitrate_cb.pack(side="left", padx=4)

        self.delete_cb = ctk.CTkCheckBox(opts_frame, text="Delete original FLAC after successful conversion", corner_radius=50, checkbox_width=18, checkbox_height=18)
        self.delete_cb.pack(side="left", padx=16)
        self.delete_cb.bind("command", lambda: self.delete_var.set(self.delete_cb.get()))
        self.delete_cb.configure(state="normal")
        self.delete_cb.deselect()
        self.delete_var.set(False)

        # ---- Toolbar row ----
        toolbar = ctk.CTkFrame(root, corner_radius=0)
        toolbar.grid(row=3, column=0, sticky="ew", padx=20, pady=4)

        ctk.CTkButton(toolbar, text="⟳ Refresh", command=self.refresh_files, width=100, corner_radius=50).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Select All", command=self.select_all, width=100, corner_radius=50).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="Deselect All", command=self.deselect_all, width=100, corner_radius=50).pack(side="left", padx=4)
        self.file_counter = ctk.CTkLabel(toolbar, text="Selected: 0 / Total: 0")
        self.file_counter.pack(side="left", padx=16)

        # ---- File listing (custom dual-scroll canvas) ----
        list_container = ctk.CTkFrame(root, corner_radius=0)
        list_container.grid(row=4, column=0, sticky="nsew", padx=20, pady=4)
        list_container.grid_rowconfigure(0, weight=0)  # header row: fixed height
        list_container.grid_rowconfigure(1, weight=1)  # canvas row: fills remaining vertical space
        list_container.grid_rowconfigure(2, weight=0)
        list_container.grid_columnconfigure(0, weight=1)

        list_header = ctk.CTkFrame(list_container, corner_radius=0)
        list_header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        list_header.grid_columnconfigure(0, weight=0)
        list_header.grid_columnconfigure(1, weight=1)
        list_header.grid_columnconfigure(2, weight=0)
        list_header.grid_columnconfigure(3, weight=2)

        header_name = ctk.CTkLabel(list_header, text="File Name", anchor="w")
        header_name.grid(row=0, column=1, padx=(8, 4), sticky="w")

        header_divider = ctk.CTkFrame(list_header, width=2, height=1, fg_color=["gray70", "gray30"])
        header_divider.grid(row=0, column=2, sticky="ns", padx=(8, 0), pady=2)

        header_rel = ctk.CTkLabel(list_header, text="Subfolder / Relative Path", anchor="w")
        header_rel.grid(row=0, column=3, padx=(8, 4), sticky="w")

        self.canvas = tk.Canvas(list_container, highlightthickness=0, bg="#2b2b2b")
        self.canvas.grid(row=1, column=0, sticky="nsew")

        self.file_vscroll = ctk.CTkScrollbar(list_container, orientation="vertical", command=self.canvas.yview)
        self.file_vscroll.grid(row=1, column=1, sticky="ns")

        self.file_hscroll = ctk.CTkScrollbar(list_container, orientation="horizontal", command=self.canvas.xview)
        self.file_hscroll.grid(row=2, column=0, columnspan=2, sticky="ew")

        self.canvas.configure(yscrollcommand=self.file_vscroll.set, xscrollcommand=self.file_hscroll.set)

        self.inner_frame = ctk.CTkFrame(self.canvas, corner_radius=0)
        self.inner_frame.grid_columnconfigure(0, weight=0)
        self.inner_frame.grid_columnconfigure(1, weight=1)
        self.inner_frame.grid_columnconfigure(2, weight=0)
        self.inner_frame.grid_columnconfigure(3, weight=2)
        self.file_divider = ctk.CTkFrame(self.inner_frame, width=2, height=1, fg_color=["gray70", "gray30"])
        self.file_divider.grid(row=0, column=2, rowspan=9999, sticky="ns", padx=(8, 0), pady=2)
        self.canvas_window = self.canvas.create_window((0, 0), window=self.inner_frame, anchor="nw")
        self.inner_frame.bind("<Configure>", self._update_canvas_scrollregion)
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfig(self.canvas_window, width=event.width))

        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))
        self.canvas.bind_all("<Shift-MouseWheel>", lambda e: self.canvas.xview_scroll(int(-1 * (e.delta / 120)), "units"))

        self.list_inner_frame = self.inner_frame
        self.file_canvas = self.canvas

        # ---- Progress bar & status ----
        self.progress = ctk.CTkProgressBar(root)
        self.progress.grid(row=5, column=0, sticky="ew", padx=20, pady=4)
        self.progress.grid_remove()
        self.progress.set(0.0)

        # ---- Controls buttons ----
        btn_row = ctk.CTkFrame(root, corner_radius=0)
        btn_row.grid(row=6, column=0, sticky="ew", padx=20, pady=8)

        self.convert_btn = ctk.CTkButton(btn_row, text="Convert", command=self.start, corner_radius=50)
        self.convert_btn.pack(side="left", padx=4)
        self.stop_btn = ctk.CTkButton(btn_row, text="Stop", command=self.stop, state="disabled", corner_radius=50)
        self.stop_btn.pack(side="left", padx=4)
        ctk.CTkButton(btn_row, text="Clear log", command=self.clear_log, corner_radius=50).pack(side="left", padx=4)

        # ---- Console log (CTkTextbox) ----
        self.log = ctk.CTkTextbox(root, height=60, font=("Consolas", 9))
        self.log.grid(row=7, column=0, sticky="nsew", padx=20, pady=(0, 20))
        self.log.configure(state="disabled", border_width=0, wrap="none")

        self._update_file_counter()

    def on_source_change(self, *args):
        """Validate source path and auto-refresh file list"""
        source_entry = self.source_var.get().strip()
        source = Path(source_entry)
        if source.is_dir():
            self.refresh_files()

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

    def _update_canvas_scrollregion(self, event=None):
        self.file_canvas.configure(scrollregion=self.file_canvas.bbox("all"))

    def _on_mousewheel(self, event):
        self.file_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_shift_mousewheel(self, event):
        self.file_canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")

    def refresh_files(self):
        """Recursively scan the source directory and populate the file list.
        All files default to checked (selected)."""
        source = Path(self.source_var.get().strip())

        # Clear existing rows
        for row in self.file_rows:
            row.destroy()
        self.file_rows.clear()
        self.row_map.clear()

        if not source.is_dir():
            self.write_log("No FLAC files found in the source folder.")
            self.file_counter.configure(text="Selected: 0 / Total: 0")
            return

        files = sorted(source.rglob("*.flac"))
        total = len(files)

        for index, flac in enumerate(files):
            rel_path = str(flac.relative_to(source))
            row = FileRow(self.list_inner_frame, flac, rel_path)
            row.checkbox.deselect()
            row.grid(row=index, column=0, columnspan=3, sticky="ew", padx=4, pady=1)
            self.file_rows.append(row)
            # Map absolute file path to row widget for dynamic removal
            self.row_map[str(flac.absolute())] = row

        self.file_divider.lift()
        self.list_inner_frame.grid_columnconfigure(0, weight=1)
        self.list_inner_frame.grid_columnconfigure(2, weight=1)
        self._update_canvas_scrollregion()
        self.write_log(f"Found {total} files.")
        self._update_file_counter()

    def select_all(self):
        """Mark all listed files as checked."""
        for row in self.file_rows:
            row.checkbox.select()
        self._update_file_counter()

    def deselect_all(self):
        """Clear all selections."""
        for row in self.file_rows:
            row.checkbox.deselect()
        self._update_file_counter()

    def _update_file_counter(self):
        total = len(self.file_rows)
        selected = sum(1 for row in self.file_rows if row.checkbox.get())
        self.file_counter.configure(text=f"Selected: {selected} / Total: {total}")

    def get_checked_files(self):
        """Return a list of Path objects for files that are currently checked."""
        return [row.flac_path for row in self.file_rows if row.checkbox.get()]

    def _center_window(self, window, width, height):
        self.update_idletasks()
        window.update_idletasks()

        parent_x = self.winfo_x()
        parent_y = self.winfo_y()
        parent_width = self.winfo_width()
        parent_height = self.winfo_height()

        x = int(parent_x + (parent_width / 2) - (width / 2))
        y = int(parent_y + (parent_height / 2) - (height / 2))

        window.geometry(f"{width}x{height}+{x}+{y}")

    def show_error(self, title, message):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        self._center_window(dialog, 300, 150)
        dialog.grab_set()
        dialog.resizable(False, False)

        label = ctk.CTkLabel(dialog, text=message, wraplength=250, pady=20)
        label.pack()

        ctk.CTkButton(dialog, text="OK", command=dialog.destroy, corner_radius=50).pack(pady=(0, 10))

    def show_info(self, title, message):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        self._center_window(dialog, 300, 150)
        dialog.grab_set()
        dialog.resizable(False, False)

        label = ctk.CTkLabel(dialog, text=message, wraplength=250, pady=20)
        label.pack()

        # We use wait_window so the UI pauses before refreshing the list
        btn = ctk.CTkButton(dialog, text="OK", command=dialog.destroy, corner_radius=50)
        btn.pack(pady=(0, 10))
        self.wait_window(dialog)

    def ask_yes_no(self, title, message):
        result = [False]

        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        self._center_window(dialog, 300, 150)
        dialog.grab_set()
        dialog.resizable(False, False)

        label = ctk.CTkLabel(dialog, text=message, wraplength=250, pady=20)
        label.pack()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=(0, 10))

        def on_yes():
            result[0] = True
            dialog.destroy()

        def on_no():
            result[0] = False
            dialog.destroy()

        ctk.CTkButton(btn_frame, text="Yes", width=70, command=on_yes, corner_radius=50).pack(side="left", padx=10)
        ctk.CTkButton(btn_frame, text="No", width=70, command=on_no, corner_radius=50).pack(side="left", padx=10)

        self.wait_window(dialog)
        return result[0]

    def start(self):
        source = Path(self.source_var.get().strip())
        dest = Path(self.dest_var.get().strip())

        if not source.is_dir():
            self.show_error("FLAC to MP3", "Pick a valid source folder.")
            return
        if not dest.is_dir():
            self.show_error("FLAC to MP3", "Pick a valid destination folder.")
            return
        if self.delete_var.get():
            ok = self.ask_yes_no(
                "Delete originals",
                "Source FLAC files will be deleted after each successful conversion. Continue?",
            )
            if not ok:
                return

        checked = self.get_checked_files()
        if not checked:
            self.show_error("FLAC to MP3", "Select at least one FLAC file to convert.")
            return

        self.save_config()
        self.stop_flag.clear()
        self.convert_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress.grid(row=5, column=0, sticky="ew", padx=20, pady=4)
        self.progress.set(0.0)

        self.worker = threading.Thread(
            target=self.run_job,
            args=(checked, dest, self.bitrate_var.get(), self.delete_var.get()),
            daemon=True,
        )
        self.worker.start()

    def stop(self):
        self.stop_flag.set()
        self.write_log("Stopping after current file...")
        self.progress.grid_remove()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()

    def run_job(self, checked_files, dest, bitrate, delete_originals):
        post = self.msgq.put

        if not checked_files:
            post(("log", "No FLAC files selected for conversion."))
            post(("done", "Done"))
            return

        post(("total", len(checked_files)))
        # Discovery count logging stays in refresh_files(); the worker should not emit it again.
        post(("log", f"Encoding {len(checked_files)} file(s) at {bitrate}."))

        converted = failed = skipped = 0

        for index, flac in enumerate(checked_files, start=1):
            if self.stop_flag.is_set():
                post(("log", "Stopped by user."))
                break

            post(("status", f"[{index}/{len(checked_files)}] {flac.name}"))
            post(("progress", index / len(checked_files)))
            out = dest / f"{flac.stem}.mp3"

            if out.exists():
                skipped += 1
                post(("log", f"SKIP  {flac.name} (destination file already exists)"))
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
                # Signal main thread to remove this row from the UI
                post(("remove_row", str(flac.absolute())))
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
                    self.progress.set(0.0)
                elif kind == "progress":
                    self.progress.set(value)
                elif kind == "status":
                    self.write_log(value)
                elif kind == "done":
                    self.convert_btn.configure(state="normal")
                    self.stop_btn.configure(state="disabled")
                    self.progress.grid_remove()
                    # value contains the summary string generated in run_job
                    self.show_info("Conversion Complete", value)
                    self.refresh_files()
                elif kind == "remove_row":
                    self._remove_file_row(value)
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def _remove_file_row(self, file_path: str):
        """Remove a file row from the UI by its absolute path.

        Locates the row frame in the row_map dictionary, destroys the widget,
        cleans up the dictionary and file_rows list, and updates counters."""
        row = self.row_map.get(file_path)
        if row is None:
            return
        # Destroy the widget from the UI
        row.destroy()
        # Remove from the active file rows list
        try:
            self.file_rows.remove(row)
        except ValueError:
            pass
        # Delete the dictionary key to clear the reference from memory
        del self.row_map[file_path]
        # Recalculate active UI metric counters to prevent visual desync
        self._update_file_counter()

    def load_config(self):
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        self.source_var.set(data.get("source", ""))
        self.dest_var.set(data.get("dest", ""))
        if data.get("bitrate") in BITRATES:
            self.bitrate_var.set(data["bitrate"])
            self.bitrate_cb.set(data["bitrate"])
        self.delete_var.set(bool(data.get("delete_originals", False)))
        self.delete_cb.set(self.delete_var.get())
        # Refresh files if a saved source exists
        self.refresh_files()

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
            if not self.ask_yes_no("FLAC to MP3", "A conversion is running. Quit anyway?"):
                return
            self.stop()
        self.save_config()
        self.destroy()


if __name__ == "__main__":
    App().mainloop()