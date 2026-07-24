# OpenTune

OpenTune is a small Linux terminal music player that searches and streams audio from YouTube. It uses `yt-dlp` for discovery and `mpv` for playback; it never downloads tracks.

## Requirements

- Python 3.10+
- [mpv](https://mpv.io/)
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)

## Run

From this checkout:

```sh
python3 -m opentune "Daft Punk Get Lucky"
```

Or install the command locally:

```sh
python3 -m pip install --user .
opentune "Daft Punk Get Lucky"
```

Use `opentune` without a query and press `/` to search from the player.

## Keys

| Key | Action |
| --- | --- |
| `j` / `↓`, `k` / `↑` | Move through results or the queue |
| `Enter` | Play the selected result/queue item |
| `Space` | Pause or resume |
| `h`, `l` | Previous, next |
| `H`, `L` | Rewind/forward 10 seconds |
| `Ctrl-l` | Toggle track loop |
| `Tab` | Switch Results / Queue tab |
| `/` | Search |
| `q` | Quit |

Selecting a search result starts it immediately and builds a short YouTube-based mix queue from its artist/title. The Queue tab shows what will play next.

## Notes

Search and mix generation need network access. If a track cannot start, OpenTune will display the `mpv`/`yt-dlp` error in its status bar.
