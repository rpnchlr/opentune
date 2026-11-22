# TUI framework evaluation for v1.1.0

## Decision

OpenTune continues to use Python's standard-library `curses` implementation.
The current UI already has a working Vim-style key model, two-pane focus model,
background workers, playlist editing, and `mpv` integration. A full migration
would introduce a large interaction and packaging risk without being necessary
to address the reported flicker.

The renderer now uses bounded drawing helpers, catches terminal resize and
wide-character edge errors, renders all windows with `noutrefresh()`, and
commits one frame with `curses.doupdate()`. This is the rendering pattern
recommended by the [Python curses documentation](https://docs.python.org/3/library/curses.html) and avoids issuing independent
full-screen refreshes for the base screen and overlays.

## Alternatives considered

| Option | Strengths | Trade-offs for OpenTune | Decision |
| --- | --- | --- | --- |
| `curses` | No runtime dependency; already supports the existing key model, panes, Unix terminals, and small installations | Manual layout and terminal edge cases | Keep, with a safer double-buffered renderer |
| [Textual](https://github.com/Textualize/textual) ([docs](https://textual.textualize.io/)) | Reactive widgets, CSS layout, built-in keyboard/mouse events, easier modal composition | New dependency, complete widget/layout migration, different focus semantics, more work for Termux/Windows packaging | Re-evaluate after a measured prototype, not in v1.1.0 |
| [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) ([docs](https://python-prompt-toolkit.readthedocs.io/)) | Strong input editing, full-screen applications, mouse support, redraw scheduling | Better suited to prompt/editor-centric layouts; existing multi-pane renderer and Vim selection model still need migration | Do not add only for search editing; keep as a future prototype |
| Bubble Tea | Mature event/update model | Go rewrite would discard the Python package and increase platform/install complexity | Explicitly rejected |

## Flicker and `addnwstr()` status

The previous implementation called `refresh()` on the base window and then
again for an overlay, while also allowing writes to reach the terminal's last
cell. v1.1.0 addresses both causes:

1. The base screen and overlays use one `noutrefresh()`/`doupdate()` commit.
2. Text writes are clamped to current window bounds.
3. Unicode drawing retries with an ASCII-safe representation when a terminal
   rejects a wide glyph.
4. A resize between measurement and drawing is treated as a frame miss; the
   next frame redraws using the new dimensions.

This fix is in OpenTune's rendering boundary and is not specific to Ghostty.
Ghostty may expose the error more readily because its terminal size and Unicode
handling make the edge condition visible, but the invalid write was an
application-side condition.

## Touch and mouse input

OpenTune enables terminal mouse reporting when the terminal supports it. A tap
reported as a mouse event can focus a pane and select a row. Terminal emulators
are not required to expose Android touchscreen gestures as mouse events, so
keyboard bindings remain the reliable interface in Termux.
