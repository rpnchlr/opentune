# OpenTune

OpenTune is a terminal music player for Linux, Termux/Android, and Windows. Search YouTube for a song, choose a result using Vim-style keys, and listen without leaving the terminal.

It is deliberately small: OpenTune streams audio, with optional local downloads,
and does not require a browser, YouTube account, or separate media library.
Playback happens in a full-screen terminal UI (TUI).

## v1.1.0

This release hardens the curses renderer with bounded double-buffered drawing,
fixes empty-search clearing and terminal word-editing sequences, adds explicit
network/search/playback states, persistent listening history, a protected
Liked Songs system playlist, cached personalised Suggestions with persistent
dismissals, asynchronous GitHub update checks, `opentune --update`, best-effort
terminal mouse/touch input, and a Windows PowerShell installer.

## What it can do

- Search YouTube from the command line: `opentune <music name>`
- Show several matching tracks with artist/channel and duration
- Play, pause, go to the next/previous track, seek, and loop a track
- Use Vim-like navigation (`h`, `j`, `k`, `l`) as well as arrow keys
- Create a continuously replenished related mix after you choose a song
- Show the upcoming mix in Queue and cached, Liked-Songs-informed recommendations in Suggestions
- Create persistent playlists in a right-side terminal pane
- Download tracks to a pinned local Downloads playlist
- Search and edit playlist contents without affecting the playback queue
- Mark contiguous songs with visual mode (`v`) for bulk queue/playlist actions
- Prefer downloaded local files automatically when a matching song is played
- Persist listening history and use Liked Songs plus compact preference signals for Suggestions
- Like/unlike songs in the protected **Liked Songs** system playlist
- Dismiss Suggestions persistently until a manual refresh
- Cut, copy, and paste songs between playlists
- Show live music suggestions while editing a search query
- Loop an entire open playlist with `o`
- Display the playing title, elapsed time, total duration, and playback state

## How it works

OpenTune coordinates two established command-line programs:

1. `yt-dlp` searches YouTube and returns video title, channel, duration, and URL.
2. OpenTune shows those results in its terminal UI.
3. When a track is selected, `mpv` opens the YouTube URL and streams the best available audio format.
4. OpenTune controls `mpv` through a private local socket, so pause, seek, loop, and progress updates work while the TUI remains open.
5. In the background, OpenTune asks YouTube for its radio/mix playlist seeded by the selected video, ranks official and contextually related versions, and filters alternate uploads of the same song before filling the queue. If YouTube does not expose a radio playlist, OpenTune falls back to other songs from the selected artist.
6. Suggestions are generated from Liked Songs (with persisted listening history as a fallback), cached locally, and refreshed without blocking startup.

Search, first-time stream playback, and mix generation need an active internet
connection. `d` saves the highlighted song and `Ctrl-d` saves the currently
playing song locally for offline playback. Search prompts support arrow keys,
Ctrl-left/Ctrl-right, Ctrl-Backspace, Home/End, and live suggestions. Pressing
Ctrl+C exits cleanly and restores the terminal.
Searches run in the background, so pane focus, tabs, playback, seeking, and
loop controls remain responsive while YouTube results load.

The header reports `IDLE`, `SEARCHING`, `LOADING`, `PLAYING`, `PAUSED`,
`STOPPED`, `NO RESULTS`, `SEARCH ERROR`, `NETWORK ERROR`, or `PLAYBACK ERROR`
as appropriate. A network failure does not get reported as a generic terminal
rendering error.

## Requirements

Install these before installing OpenTune:

- Python 3.10 or newer
- [`mpv`](https://mpv.io/) — audio playback and YouTube streaming
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) — YouTube search metadata
- `ffmpeg` — required only for `Ctrl-d` audio downloads

Windows also needs the `windows-curses` optional dependency; the included
`install.ps1` installs it through pipx. `mpv`, `yt-dlp`, and `ffmpeg` must be
available on `PATH`.

Examples for common Linux distributions:

```sh
# Arch Linux
sudo pacman -S python mpv yt-dlp ffmpeg

# Debian / Ubuntu
sudo apt install python3 python3-pip mpv yt-dlp ffmpeg

# Fedora
sudo dnf install python3 python3-pip mpv yt-dlp ffmpeg
```

If YouTube changes its site, updating `yt-dlp` is usually the first thing to try when search or playback stops working.

## Installation

On current Arch Linux, do **not** use `pip install --user` for this project. Arch marks its system Python as externally managed (PEP 668), so `pip` correctly refuses to modify it. Choose one of the following isolated installation methods.

### Recommended: install the CLI with pipx

`pipx` installs Python applications into their own virtual environments while exposing their commands on your `PATH`. This is the best option when you want to run `opentune` from any directory.

```sh
# Install pipx once on Arch Linux
sudo pacman -S python-pipx
pipx ensurepath

# Open a new terminal, then install this checkout
cd /path/to/opentune
pipx install .
```

Afterward, use it like any other command:

```sh
opentune "Daft Punk Get Lucky"
opentune --help
```

If `opentune` is not found immediately after `pipx ensurepath`, restart the shell. `pipx` normally adds `~/.local/bin` to your `PATH`.

### Updating an installation from this checkout

`pipx upgrade opentune` checks the package's published source (usually PyPI). It cannot detect edits made only in this local Git checkout, even if the local version number changes. To install the current checkout after pulling or editing code, run this from the project directory:

```sh
pipx install --force .
```

Or use the included shortcut:

```sh
make upgrade
```

Confirm the installed release with:

```sh
opentune --version
```

If a normal upgrade reports that OpenTune is already current but you suspect a
stale or corrupted pip download, retry without pip's cache:

```sh
pipx upgrade opentune --pip-args="--no-cache-dir"
```

This only refreshes the published PyPI package. For changes that exist only in
your local checkout, use `pipx install --force .` (or `make upgrade`) instead.

OpenTune follows semantic versioning: patch releases (for example `0.8.1` → `0.8.2`) contain fixes, while minor releases add backwards-compatible features.

### Alternative: project virtual environment

Use this when developing OpenTune or when you only need the command from this checkout:

```sh
cd /path/to/opentune
python3 -m venv .venv
source .venv/bin/activate
python -m pip install .
opentune "Daft Punk Get Lucky"
```

Important: omit `--user` inside a virtual environment. The virtual environment already isolates the installation, and Python intentionally hides user site-packages from it.

To upgrade OpenTune inside the local virtual environment after pulling new
changes:

```sh
cd /path/to/opentune
source .venv/bin/activate
python -m pip install --upgrade .
opentune --version
```

For development, install the checkout in editable mode so source changes are
available immediately:

```sh
python -m pip install --editable .
```

If OpenTune was previously installed normally in this environment,
`python -m pip install --upgrade .` is sufficient. Do not use `--user` inside
a virtual environment.

While the environment is active, `opentune` works normally. After `deactivate`, either activate it again or run the executable explicitly:

```sh
.venv/bin/opentune "Daft Punk Get Lucky"
```

Do not use `--break-system-packages`; it bypasses Arch's protection for the system Python and is unnecessary for OpenTune.

### Windows PowerShell

From a PowerShell prompt in the checkout, run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
opentune "Daft Punk Get Lucky"
```

The script checks for Python 3.10+, installs/updates pipx, installs the
`windows-curses` extra, and uses `winget` for missing `mpv`, `yt-dlp`, and
`ffmpeg` when available. If your environment manages those tools separately,
run `.\install.ps1 -SkipDependencies` after placing them on `PATH`.

### Install from PyPI

Installation and future upgrades from PyPI work from any directory:

```sh
pipx install opentune
pipx upgrade opentune
```

OpenTune v1.1.0 includes an installer hook for the short thank-you/support
message (direct legacy installs and verbose pip builds show it; standard pip may
hide build-hook output). On the first launch after a new release, the same
message appears in a floating modal;
press `Esc` to dismiss it. The notice is shown once per installed version. A
background GitHub release check may show a separate non-blocking update pane;
use `opentune --update` or `pipx upgrade opentune` only when you choose to
update.

Maintainers can follow [the PyPI release guide](docs/PYPI_RELEASE.md) to configure Trusted Publishing and publish releases.

### Run without installing

For development or a one-off run from this checkout:

```sh
./bin/opentune "Daft Punk Get Lucky"
```

## Usage

Start OpenTune and search immediately:

```sh
opentune "Daft Punk Get Lucky"
```

Words after `opentune` form the search query, so quotes are optional unless your shell needs them:

```sh
opentune Kendrick Lamar
```

Start with an empty player and search from inside the TUI instead:

```sh
opentune
```

Use the standard command help at any time:

```sh
opentune --help
```

## First run

1. Run `opentune <song or artist>`.
2. The **Suggestions** tab is the home tab; a search automatically focuses **Results**.
3. Move with `j`/`k` or `↓`/`↑`.
4. Press `Enter` to start the highlighted result.
5. The title and time appear at the top of the screen.
6. OpenTune prepares and continuously replenishes a YouTube radio-style mix in the background. Press `Tab` to cycle **Suggestions**, **Results**, **Queue**, and **History**, or `Shift+Tab` to move backward.
7. Press `q` to quit. `Esc` cancels prompts/visual mode; press it twice quickly
   in Queue or an open playlist to clear its find query.

## Keybinds

| Key | Action |
| --- | --- |
| `j` or `↓` | Move selection down (wraps from bottom to top) |
| `k` or `↑` | Move selection up (wraps from top to bottom) |
| `g` / `G` | Jump to the top / bottom of the current list |
| `[` / `]` | Move to the previous / next item in the current Results search |
| `Ctrl-b` / `Ctrl-f` | Move half a page up / down |
| `Enter` | Play the selected result or queue item |
| `Space` | Pause or resume playback from any window |
| `h` | Play the previous track, if there is one |
| `l` | Play the next queued track |
| `H` (`Shift+h`) | Rewind 10 seconds |
| `L` (`Shift+l`) | Forward 10 seconds |
| `Ctrl-o` | Toggle looping of the current track from any window |
| `Tab` | Move forward through **Suggestions**, **Results**, **Queue**, and **History** |
| `Shift+Tab` | Move backward through the home tabs |
| `Alt+1` … `Alt+4` | Jump to Suggestions, Results, Queue, or History |
| `R` (Suggestions tab) | Refresh personalised recommendations and clear their dismissals |
| `y` | Add/remove the selected song(s) from **Liked Songs** |
| `/` | Open a search prompt from any window |
| `f` (Queue tab) | Find and highlight a song in the Queue without filtering it |
| `n` / `N` (Queue tab) | Jump to the next / previous match; status shows `[current/total]` |
| `Shift+h/l` or `Shift+Left/Right` | Rewind/forward 10 seconds from any window |
| `a` | Append the focused result/queue track to the Queue without playing it |
| `s` (Queue tab) | Shuffle only the temporary Queue; saved playlists are unchanged |
| `v` | Enter/leave visual selection; extend the selection with `j`/`k` |
| `d` | Download the highlighted result, queue item, suggestion, or playlist song |
| `D` | Delete selected Queue/Suggestions/playlist songs or a playlist after confirmation |
| `c` | Clear the Queue after `y`/`n`/Enter confirmation |
| `u` | Undo the last queue deletion or clear |
| `Ctrl-r` | Redo the last undone queue deletion or clear |
| `pN` | Add the focused result/queue track to user playlist number `N` |
| `pcN` | Add the currently playing track to user playlist number `N` |
| `Ctrl-d` | Download the currently playing track (or focused playlist song if idle) |
| `x` / `y` / `z` | Cut / copy / paste selected songs in an open playlist |
| `P` | Toggle the Playlists pane |
| `Ctrl-h` / `Ctrl-l` or `Ctrl-Left/Right` | Cycle focus between panes (wraps) |
| `Ctrl-Left/Right` in search | Move the cursor by one word |
| `Ctrl-Backspace` in search | Delete the previous word |
| `Ctrl+C` | Stop playback, restore the terminal, and exit cleanly |
| `?` | Open/close the in-player key reference |
| `Esc` in a prompt or visual mode | Cancel the prompt or visual selection |
| `Esc` twice in Queue | Clear the active Queue find query |
| `Esc` twice in an open playlist | Clear the active playlist find query |
| `Esc` in help | Close the floating help overlay or update notice |
| `q` | Quit OpenTune (the only quit key) |

## Results, playback, and the queue

### Results tab

The Results tab contains the latest YouTube search. Each row shows its title, channel/uploader when available, and duration. Press `Enter` to play a result. Use `[` and `]` to move through the current search results without changing the playing track; `h` and `l` remain music navigation. Choosing a new search result replaces the current track and adds the former track to playback history, allowing `h` to go back. While typing in `/`, OpenTune shows matching history immediately and requests additional YouTube music results in the background. Recent matching history entries are marked `[history]`; matching prioritizes song titles and uses the artist only as a fallback. Use Up/Down to choose a suggestion or Tab to complete it.

### Queue tab

Selecting a search result starts a YouTube radio-style mix. OpenTune filters duplicate uploads, alternate versions of the selected song, and obvious non-music results, so the queue should contain different music tracks rather than the same title from several channels. The Queue tab shows the tracks waiting to play. You can:

- Press `l` to start the next queued track.
- Highlight a queued track and press `Enter` to jump directly to it.
- Press `a` on a search result to append it without interrupting playback.
- Press `D` to remove highlighted queue item(s) after a `y`/`n`/Enter confirmation, or `c` to clear the whole queue.
- Press `u` to undo the latest deletion/clear, or `Ctrl-r` to redo it.
- Press `f` to find and highlight a queue song without changing the queue.
- Press `n`/`N` to move to the next/previous match; matches wrap around and
  the status line reports their position as `[current/total]`.
- Use `Tab` to return to Results.

When the queue reaches its end, OpenTune requests another related batch and
continues playback automatically. Quitting with `q` stops replenishment.

### Suggestions tab

The Suggestions tab is the home tab and is separate from Queue. It loads the
cached recommendation set immediately. Liked Songs is the primary source; if
it is empty, persisted listening history is used as a temporary seed. New
recommendations are generated from several seeds in the background and exclude
Liked Songs, dismissed URLs, and duplicate uploads. Selecting a suggestion
does not remove or regenerate the remaining rows. Press `D` to dismiss selected
rows persistently, or `R` to clear dismissals and generate a fresh set.

### History tab

The History tab shows persisted listening history, newest first. It stores
track metadata locally so later Suggestions can learn from previous listening.
It is separate from saved playlists and can be removed by deleting the history
file described in [local data storage](docs/DATA_STORAGE.md).

Undo and redo are intentionally limited to queue deletion and queue clearing.
Playback, search, pause, seeking, looping, and adding tracks are not recorded
in the undo history.

## Playlists window

Press `P` to open or close the Playlists pane. It occupies about 40% of the
terminal width. When open, `Ctrl-h`/`Ctrl-Left` cycles focus left and
`Ctrl-l`/`Ctrl-Right` cycles focus right; focus wraps between the panes. The
pane stays open after starting a playlist track.

The pinned `Downloads` and **Liked Songs** playlists are system playlists.
Liked Songs is created automatically, cannot be renamed or deleted, and can be
fully managed at the song level. Press `y` in a main tab to like/unlike a
selection; opening Liked Songs exposes the same download, delete, queue, and
playlist actions as other playlists. The pinned `Downloads` playlist has no user-playlist index. User-created
playlists are numbered from `1` in the visible list and remain in creation
order (with pinned user playlists grouped first). Playlist files are stored in:

```text
~/Music/opentune/Playlists/
```

Downloaded audio files are stored in:

```text
~/Music/opentune/Downloads/
```

### Playlist list keys

| Key | Action |
| --- | --- |
| `j` / `k` | Move down/up through playlists |
| `Left` / `Right` | Leave / enter a playlist |
| `g` / `G` | Jump to the top / bottom of the playlist list |
| `Ctrl-b` / `Ctrl-f` | Move half a page up / down |
| `l` | Enter the focused playlist |
| `a` | Create a playlist; an empty name becomes `My Playlist #N` |
| `p` | Pin/unpin the focused playlist (Downloads is always pinned) |
| `r` | Rename the focused playlist (system playlists cannot be renamed) |
| `D` | Delete the focused playlist after confirmation (system playlists are protected) |
| `P` | Toggle the pane |
| `Ctrl-h` / `Ctrl-l` or `Ctrl-Left/Right` | Cycle focus between panes |

### Open playlist keys

| Key | Action |
| --- | --- |
| `j` / `k` | Move through songs |
| `g` / `G` | Jump to the first / last song |
| `Ctrl-b` / `Ctrl-f` | Move half a page up / down |
| `v` | Enter/leave visual selection; extend the selection with `j`/`k` |
| `Enter` | Play the focused song and load the playlist into the temporary queue |
| `h` | Leave the current playlist and return to the playlist list |
| `a` | Append the focused song to the temporary Queue without playing it |
| `pN` | Add selected playlist song(s) to another user playlist `N` |
| `pcN` | Add the currently playing track to user playlist `N` |
| `f` | Find and highlight a playlist song by title or uploader (no filtering) |
| `n` / `N` | Jump to the next / previous match; status shows `[current/total]` |
| `d` | Download the focused song |
| `D` (`Shift+d`) | Permanently delete the focused song(s) after `y`/`n`/Enter confirmation |
| `x` / `y` / `z` | Cut / copy / paste selected songs into the open destination playlist |
| `o` | Toggle looping of the current playlist |
| `P` | Toggle the pane without closing the playlist |

The matching text is shown in a secondary color while the selected row keeps
the primary selection color. Press `Esc` twice quickly while a Queue or
playlist find query is active to clear the query. A single `Esc` leaves the
current list unchanged.

Playlist song deletion has no undo/redo. A deleted song must be added again
with `pN` from a main-window search result, queue item, or open playlist song.

Visual mode (`v`) makes `j`/`k` extend a contiguous selection. Press `Esc` to
cancel visual mode without changing anything. Actions such as
queue append/delete, playlist append, and playlist deletion apply to every
selected song. Press `v` again to leave visual mode.

### Adding tracks to a playlist

Focus a search result or queue item in the main window, press `p`, then type its
user-playlist number. For example, `p3` adds the focused track to user playlist
`3`. Inside an open playlist, `p3` adds the selected playlist song(s) to user
playlist `3`; use `pc3` to add the currently playing track. Downloads is not a
numbered target and cannot receive songs through `pN`/`pcN`; it is populated
only by successful `d`/`Ctrl-d` downloads. User playlists store the YouTube URL and
metadata; they do not download the song.

### Downloads

Press `d` on a highlighted song, or `Ctrl-d` for the currently playing song
(and the focused playlist song when idle). OpenTune uses `yt-dlp`
and `ffmpeg` to save an MP3 under `~/Music/opentune/Downloads/` and adds it to
the pinned Downloads playlist. Deleting a Downloads entry after confirmation
also removes its local audio file permanently.

The `a` key creates playlists only when the Playlists pane is focused on the
playlist list. Inside an open playlist it appends the focused song to the
temporary Queue; in the main window it appends the focused result or queue item.

The queue is kept in memory for the current session only. It is cleared when OpenTune exits.

### Looping

`Ctrl-o` loops the currently playing track from either the main window or the
Playlists window. The screen header displays `LOOP` while it is enabled. Turn
it off with `Ctrl-o` again; then, when a track ends, OpenTune advances to the
next item in the queue. In an open playlist, `o` loops the whole playlist and
shows `PLOOP` in the header; it starts the playlist again after its final song.
`Ctrl-h`/`Ctrl-l` (or Ctrl-Left/Right) cycles focus between panes when the
Playlists pane is open.

## Troubleshooting

### `opentune: command not found`

The user-level bin directory is likely not on `PATH`. Run:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Then add it to `~/.zshrc` or your shell's startup file as described above.

### Missing `mpv` or `yt-dlp`

OpenTune checks for both commands at startup. Install the missing package with your distribution's package manager, then run OpenTune again.

### Search or playback fails

- Confirm that the internet connection and YouTube are reachable.
- Update `yt-dlp`; YouTube changes can require a newer version.
- Try the URL in `mpv` directly to distinguish an OpenTune issue from a `mpv`/`yt-dlp` issue:

  ```sh
  mpv --no-video "https://www.youtube.com/watch?v=VIDEO_ID"
  ```

### The terminal UI looks broken

OpenTune needs an interactive terminal with enough space for the player. Enlarge the terminal window and avoid running it through a non-interactive shell or redirected output.

## Project layout

```text
opentune/
├── bin/opentune          # launcher for running from this checkout
├── opentune/__main__.py  # CLI, terminal UI, search, queue, and mpv control
├── tests/                # small automated checks
├── Makefile               # install, local pipx upgrade, and test shortcuts
└── pyproject.toml        # package metadata and installed `opentune` command
```

## Current scope and limitations

OpenTune currently provides persistent playlists, Liked Songs, cached
recommendations, optional downloads, and best-effort terminal mouse/touch
input. Terminal emulators differ in how they expose touchscreen events, so
keyboard controls remain the supported fallback. The Termux MPV linker error
(`CANNOT LINK EXECUTABLE ... __from_chars_floating_point...`) is a known,
deferred compatibility issue; OpenTune does not modify MPV binaries or Android
native libraries to work around it.

See [TUI framework evaluation](docs/TUI_FRAMEWORK_EVALUATION.md),
[local data storage](docs/DATA_STORAGE.md), and
[known issues and platform notes](docs/KNOWN_ISSUES.md) for implementation
status and data-retention details.

## License

Copyright 2026 Rudraksh.

OpenTune is licensed under the [Apache License 2.0](LICENSE). It includes an explicit patent grant; see [NOTICE](NOTICE) for the project attribution notice.
