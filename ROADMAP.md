# Roadmap

This document outlines the planned features and future directions for the Noterun project.

## Short-term Goals
- [ ] **Parameter Customization**: Add command-line arguments to allow customization of parameters (e.g., configuring the 180MB limit in `SPLIT_LARGE_MEDIA.py`).
- [ ] **Logging Improvements**: Enhance error handling and logging across all scripts to make debugging easier.
- [ ] **Dry-Run Mode**: Add dry-run capabilities to `RENAME_FILES.py` and `MOVE_PARENT.py` to preview changes before applying them.

## Medium-term Goals
- [ ] **Unified CLI**: Implement a single Command Line Interface entry point (e.g., `noterun.py <command>`) to execute the different tools instead of running individual scripts.
- [ ] **Configuration File**: Introduce a configuration file (`config.json` or `.env`) for managing default directories, file size limits, and other user preferences.
- [ ] **Extended Media Operations**: Add support for additional media operations like compression or format conversion via `ffmpeg`.

## Long-term Goals
- [ ] **Executable Distribution**: Provide pre-compiled binaries (e.g., via PyInstaller) so Python and dependencies do not need to be installed on the host system.
- [ ] **Graphical User Interface**: Develop a simple GUI or a local dashboard for easier interactions by non-technical users.
- [ ] **Plugin System**: Implement plugin support to allow users to load custom Python scripts into the Noterun execution flow.
