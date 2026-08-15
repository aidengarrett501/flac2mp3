# Refactoring Tasks for flac2mp3_gui.py

## Goal
Refactor `flac2mp3_gui.py` to add interactive file selection, list refreshing, and a Material-inspired UI theme. Preserve all existing FFmpeg process handling, config saving/loading, and threading safety.

---

## Tasks

### 1. Visual & Layout Modernization (Material Design)
- [ ] Apply a clean Material design aesthetic via `ttk.Style()` using standard `Segoe UI` fonts, a modern flat color palette (e.g., Material Blue `#1976D2`/`#2196F3` accents, neutral `#F5F5F7` or dark slate surfaces), and padded inputs.
- [ ] Modernize the progress bar to a flat accent style and format status indicators cleanly.
- [ ] Replace raw text log appearance with a clean, borderless monospace console pane.

### 2. File Selection Panel & Controls
- [ ] Insert a file listing widget (a `ttk.Treeview` or scrollable list with checkbox indicators) located above the execution buttons.
- [ ] Display columns: Checkbox/Status, File Name, and Subfolder/Relative Path.
- [ ] Add a toolbar row above the file list with:
  - [ ] "Refresh" button (with a `⟳` icon/symbol) to rescan the selected source directory.
  - [ ] "Select All" button to mark all listed files as checked.
  - [ ] "Deselect All" button to clear all selections.
  - [ ] File counter label showing: `Selected: X / Total: Y`.

### 3. File Discovery & State Logic
- [ ] Extract the recursive directory scan out of `run_job` into a dedicated `refresh_files()` method.
- [ ] Automatically trigger `refresh_files()` whenever a new source path is selected via `pick_source` or when the text in `source_var` is validated.
- [ ] Default new scans to all files checked (`True`).

### 4. Transcoding Pipeline Execution
- [ ] Update `start()` to validate that at least one file is checked before launching the thread.
- [ ] Modify `run_job()` to accept and process only the list of checked `Path` objects instead of calling `source.rglob("*.flac")` directly.
- [ ] Ensure progress bar scaling and status messages map directly to the count of selected files.

---

**Note:** All existing FFmpeg process handling, config saving/loading, and threading safety must be preserved throughout the refactoring.