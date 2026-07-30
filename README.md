# OpenTune

OpenTune is a terminal music player for Linux/Unix systems. Search YouTube for a song, choose a result using Vim-style keys, and listen without leaving the terminal.

It is deliberately small: OpenTune streams audio; it does not download songs, require a browser, require a YouTube account, or maintain a media library. Playback happens in a full-screen terminal UI (TUI).

## What it can do

- Search YouTube from the command line: `opentune <music name>`
- Show several matching tracks with artist/channel and duration
- Play, pause, go to the next/previous track, seek, and loop a track
- Use Vim-like navigation (`h`, `j`, `k`, `l`) as well as arrow keys
- Create a short related mix after you choose a song
- Show the upcoming mix in a Queue tab
- Create persistent playlists in a right-side terminal pane
- Download tracks to a pinned local Downloads playlist
- Search and edit playlist contents without affecting the playback queue
- Display the playing title, elapsed time, total duration, and playback state

## How it works

OpenTune coordinates two established command-line programs:

1. `yt-dlp` searches YouTube and returns video title, channel, duration, and URL.
2. OpenTune shows those results in its terminal UI.
3. When a track is selected, `mpv` opens the YouTube URL and streams the best available audio format.
4. OpenTune controls `mpv` through a private local socket, so pause, seek, loop, and progress updates work while the TUI remains open.
5. In the background, OpenTune asks YouTube for its radio/mix playlist seeded by the selected video, then filters alternate uploads of the same song before filling the queue. If YouTube does not expose a radio playlist, OpenTune falls back to other songs from the selected artist.

Nothing is downloaded or uploaded by OpenTune. Search, stream playback, and mix generation need an active internet connection.

## Requirements

Install these before installing OpenTune:

- Python 3.10 or newer
- [`mpv`](https://mpv.io/) — audio playback and YouTube streaming
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) — YouTube search metadata
- `ffmpeg` — required only for `Ctrl-d` audio downloads

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

OpenTune follows semantic versioning: patch releases (for example `0.2.0` → `0.2.1`) contain fixes, while minor releases add backwards-compatible features.

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

While the environment is active, `opentune` works normally. After `deactivate`, either activate it again or run the executable explicitly:

```sh
.venv/bin/opentune "Daft Punk Get Lucky"
```

Do not use `--break-system-packages`; it bypasses Arch's protection for the system Python and is unnecessary for OpenTune.

### Install from PyPI

After OpenTune's first PyPI release, installation and future upgrades will work from any directory:

```sh
pipx install opentune
pipx upgrade opentune
```

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
2. A list of YouTube matches appears in the **Results** tab.
3. Move with `j`/`k` or `↓`/`↑`.
4. Press `Enter` to start the highlighted result.
5. The title and time appear at the top of the screen.
6. OpenTune prepares a YouTube radio-style mix in the background. Press `Tab` to view it in the **Queue** tab.
7. Press `q` to quit. `Esc` only cancels an active prompt or closes the help overlay.

## Keybinds

| Key | Action |
| --- | --- |
| `j` or `↓` | Move selection down in Results or Queue |
| `k` or `↑` | Move selection up in Results or Queue |
| `Enter` | Play the selected result or queue item |
| `Space` | Pause or resume playback |
| `h` | Play the previous track, if there is one |
| `l` | Play the next queued track |
| `H` (`Shift+h`) | Rewind 10 seconds |
| `L` (`Shift+l`) | Forward 10 seconds |
| `Ctrl-o` | Toggle looping of the current track from any window |
| `Tab` | Switch between **Results** and **Queue** |
| `/` | Open a search prompt |
| `a` | Append the selected search result to the Queue without playing it |
| `d` | Delete the selected track from the Queue |
| `c` | Clear the Queue |
| `u` | Undo the last queue deletion or clear |
| `Ctrl-r` | Redo the last undone queue deletion or clear |
| `p<N>` | Add the focused result/queue track to user playlist number `N` |
| `Ctrl-d` | Download the current/focused track to Downloads |
| `P` | Toggle the Playlists pane |
| `Ctrl-h` / `Ctrl-l` | Focus the main / Playlists pane when it is open |
| `?` | Open/close the in-player key reference |
| `Esc` in a prompt | Cancel search, playlist creation, rename, or confirmation |
| `Esc` in help | Close the help overlay |
| `q` | Quit OpenTune (the only quit key) |

## Results, playback, and the queue

### Results tab

The Results tab contains the latest YouTube search. Each row shows its title, channel/uploader when available, and duration. Press `Enter` to play a result. Choosing a new search result replaces the current track and adds the former track to playback history, allowing `h` to go back.

### Queue tab

Selecting a search result starts a YouTube radio-style mix. OpenTune filters duplicate uploads, alternate versions of the selected song, and obvious non-music results, so the queue should contain different music tracks rather than the same title from several channels. The Queue tab shows the tracks waiting to play. You can:

- Press `l` to start the next queued track.
- Highlight a queued track and press `Enter` to jump directly to it.
- Press `a` on a search result to append it without interrupting playback.
- Press `d` to remove the highlighted queue item, or `c` to clear the whole queue.
- Press `u` to undo the latest deletion/clear, or `Ctrl-r` to redo it.
- Use `Tab` to return to Results.

Undo and redo are intentionally limited to queue deletion and queue clearing.
Playback, search, pause, seeking, looping, and adding tracks are not recorded
in the undo history.

## Playlists window

Press `P` to open or close the Playlists pane. It occupies about 40% of the
terminal width. When open, `Ctrl-h` focuses the main player and `Ctrl-l` focuses
the Playlists pane. The pane stays open after starting a playlist track.

The pinned `Downloads` playlist has no user-playlist index. User-created
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
| `l` | Enter the focused playlist |
| `a` | Create a playlist; an empty name becomes `My Playlist #N` |
| `p` | Pin/unpin the focused playlist (Downloads is always pinned) |
| `r` | Rename the focused playlist (`Downloads` cannot be renamed) |
| `D` | Delete the focused playlist after confirmation (`Downloads` is protected) |
| `Ctrl-d` | Download the focused song when a playlist is open |
| `P` | Toggle the pane |
| `Ctrl-h` / `Ctrl-l` | Focus the main / Playlists pane |

### Open playlist keys

| Key | Action |
| --- | --- |
| `j` / `k` | Move through songs |
| `Enter` | Play the focused song and load the playlist into the temporary queue |
| `h` | Leave the current playlist and return to the playlist list |
| `a` | Append the focused song to the temporary Queue without playing it |
| `f` | Search the current playlist by title or uploader |
| `D` (`Shift+d`) | Permanently delete the focused song after confirmation |
| `P` | Toggle the pane without closing the playlist |

Playlist song deletion has no undo/redo. A deleted song must be added again
with `p<N>` from a main-window search result or queue item.

### Adding tracks to a playlist

Focus a search result or queue item in the main window, press `p`, then type its
user-playlist number. For example, `p3` adds the focused track to user playlist
`3`. Downloads is not a numbered target and cannot receive songs through
`p<N>`; it is populated only by successful `Ctrl-d` downloads. This stores the
YouTube URL and metadata in user playlists; it does not download the song.

### Downloads

Focus a currently playing track in the main window and press `Ctrl-d`, or open
a playlist, focus one of its songs, and press `Ctrl-d`. OpenTune uses `yt-dlp`
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
next item in the queue. `Ctrl-l` is reserved for focusing the Playlists pane.

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

OpenTune v1 is a streaming player. It does not yet provide persistent playlists, saved favorites, downloads, lyrics, volume controls, or system media-key integration. These are good candidates for later releases, but the current goal is fast terminal search and playback with a lightweight mix queue.

## License

Copyright 2026 Rudraksh.

OpenTune is licensed under the [Apache License 2.0](LICENSE). It includes an explicit patent grant; see [NOTICE](NOTICE) for the project attribution notice.
