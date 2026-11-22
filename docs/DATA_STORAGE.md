# OpenTune local data storage

This document is updated with each feature release. OpenTune stores metadata
locally under `~/Music/opentune` by default, with small UI/update state files in
the platform's XDG config/cache directories. It does not upload this local
library to OpenTune.

## Persistent files

| File or directory | Stored data | Why | Format / retention | User control |
| --- | --- | --- | --- | --- |
| `Music/opentune/Playlists/index.json` | Playlist IDs, names, and pin state | Reconstruct the playlist pane | JSON; persistent until the user changes/deletes a playlist | Rename/delete user playlists in the UI; system playlists are protected |
| `Music/opentune/Playlists/playlist-*.json` | Song URL, title, duration, uploader, optional genre/channel ID, and optional local path metadata | Preserve user playlists and available relevance metadata | JSON; persistent | Edit songs through the UI or delete the files |
| `Music/opentune/Playlists/downloads.json` | Same metadata for successfully downloaded songs | Track local audio files | JSON; persistent and reconciled with existing files at startup | Delete a Downloads row to delete its audio file too |
| `Music/opentune/Playlists/liked.json` | Song URL, title, duration, uploader, and available genre/channel metadata | Personalise Suggestions | JSON; persistent system playlist | Add/remove songs; the playlist identity cannot be renamed/deleted |
| `Music/opentune/Downloads/` | MP3 files downloaded at the user's request | Offline playback | Persistent binary audio files | Delete from Downloads or remove the directory manually |
| `Music/opentune/history.json` | Recently played track metadata and timestamps | Personalise recommendations and provide the History tab | JSON; up to 200 recent entries, persistent | Delete the file to clear history; no audio is stored here |
| `Music/opentune/liked-cache.json` | A signature and compact artist/title-token summary of Liked Songs, plus metadata snapshot | Avoid reprocessing an unchanged Liked Songs playlist | JSON cache; replaced when Liked Songs changes | Safe to delete; it is rebuilt automatically |
| `Music/opentune/suggestions.json` | Generated recommendation metadata, generation time, and dismissed URLs | Show Suggestions immediately and preserve dismissals | JSON cache plus persistent exclusions; `R` replaces it and clears exclusions | Press `D` to add exclusions; press `R` to clear the old set |
| `${XDG_CONFIG_HOME:-~/.config}/opentune/state.json` | Last installed version shown in the one-time release notice | Avoid showing the same install notice repeatedly | JSON; persistent until manually deleted | Safe to delete |
| `${XDG_CACHE_HOME:-~/.cache}/opentune/update.json` | Latest GitHub release version/URL, check time, and dismissed notification version | Avoid blocking startup and repeated update notices | JSON cache; refreshed by background checks | Safe to delete; rebuilt on the next successful check |

Temporary files are dot-prefixed JSON files in the same directory during atomic
writes and a private temporary directory/socket for the running `mpv` process.
They are removed after a successful write or when OpenTune exits. The playback
queue, current focus, visual selection, and in-memory worker state are
session-only.

## External communication

OpenTune invokes `yt-dlp` for YouTube search, metadata, radio/mix results, and
user-requested downloads. `mpv` then streams the selected URL. These services
receive the search query or selected video URL as required for playback. The
optional update checker makes a version request to the official GitHub Releases
API. Update checking is asynchronous, has a short timeout, and does not send
playlist contents, history, cache files, or dismissed URLs.

If the network is unavailable, cached local data remains usable and the TUI
reports a network/search/playback state instead of treating the failure as a
generic rendering error.
