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
- Display the playing title, elapsed time, total duration, and playback state

## How it works

OpenTune coordinates two established command-line programs:

1. `yt-dlp` searches YouTube and returns video title, channel, duration, and URL.
2. OpenTune shows those results in its terminal UI.
3. When a track is selected, `mpv` opens the YouTube URL and streams the best available audio format.
4. OpenTune controls `mpv` through a private local socket, so pause, seek, loop, and progress updates work while the TUI remains open.
5. In the background, OpenTune searches again using the selected track's title/channel to create a short related queue.

Nothing is downloaded or uploaded by OpenTune. Search, stream playback, and mix generation need an active internet connection.

## Requirements

Install these before installing OpenTune:

- Python 3.10 or newer
- [`mpv`](https://mpv.io/) — audio playback and YouTube streaming
- [`yt-dlp`](https://github.com/yt-dlp/yt-dlp) — YouTube search metadata

Examples for common Linux distributions:

```sh
# Arch Linux
sudo pacman -S python mpv yt-dlp

# Debian / Ubuntu
sudo apt install python3 python3-pip mpv yt-dlp

# Fedora
sudo dnf install python3 python3-pip mpv yt-dlp
```

If YouTube changes its site, updating `yt-dlp` is usually the first thing to try when search or playback stops working.

## Installation

Clone or enter this project, then install it for your user:

```sh
cd /path/to/opentune
python3 -m pip install --user .
```

`--user` means “install only for my current Linux user.” It avoids `sudo` and does not modify the system Python installation. The `opentune` executable is normally installed at `~/.local/bin/opentune`.

If your shell cannot find the command afterward, add that directory to your `PATH`:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

For zsh, make that permanent by adding the same line to `~/.zshrc`, then open a new terminal or run:

```sh
source ~/.zshrc
```

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
6. OpenTune prepares related tracks in the background. Press `Tab` to view them in the **Queue** tab.
7. Press `q` or `Esc` to quit.

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
| `Ctrl+l` | Toggle looping of the current track |
| `Tab` | Switch between **Results** and **Queue** |
| `/` | Open a search prompt |
| `?` | Open/close the in-player key reference |
| `q` or `Esc` | Quit OpenTune (or close the `?` help overlay) |

## Results, playback, and the queue

### Results tab

The Results tab contains the latest YouTube search. Each row shows its title, channel/uploader when available, and duration. Press `Enter` to play a result. Choosing a new search result replaces the current track and adds the former track to playback history, allowing `h` to go back.

### Queue tab

Selecting a search result starts a short related mix. The Queue tab shows the tracks waiting to play. You can:

- Press `l` to start the next queued track.
- Highlight a queued track and press `Enter` to jump directly to it.
- Use `Tab` to return to Results.

The queue is kept in memory for the current session only. It is cleared when OpenTune exits.

### Looping

`Ctrl+l` loops the currently playing track. The screen header displays `LOOP` while it is enabled. Turn it off with `Ctrl+l` again; then, when a track ends, OpenTune advances to the next item in the queue.

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
└── pyproject.toml        # package metadata and installed `opentune` command
```

## Current scope and limitations

OpenTune v1 is a streaming player. It does not yet provide persistent playlists, saved favorites, downloads, lyrics, volume controls, or system media-key integration. These are good candidates for later releases, but the current goal is fast terminal search and playback with a lightweight mix queue.
