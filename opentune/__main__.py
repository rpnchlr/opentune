from __future__ import annotations

import argparse
import curses
import json
import os
import random
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

from . import __version__


SEARCH_LIMIT = 12
MIX_LIMIT = 10
SUGGESTION_DEBOUNCE = 0.08
PROJECT_URL = "https://github.com/rpnchlr/opentune"
INSTALL_MESSAGE = (
    "Thank you for installing OpenTune! Consider supporting the creator by "
    f"starring or sponsoring the project: {PROJECT_URL}"
)
UPDATE_NOTICE_LINES = (
    "Thank you for using OpenTune!",
    "OpenTune v0.9.1 is now installed.",
    "Consider supporting the creator by starring or sponsoring:",
    PROJECT_URL,
    "",
    "Press Esc to close this message.",
)
NON_MUSIC_TERMS = re.compile(
    r"\b(?:podcast|interview|reaction|review|news|tutorial|gameplay|walkthrough|"
    r"vlog|documentary|trailer|short film|comedy|stand[- ]?up|webinar|lecture|"
    r"how to|unboxing|behind the scenes)\b",
    re.IGNORECASE,
)

HELP_TEXT = """\
OpenTune — stream YouTube music from your terminal

Usage:
  opentune [MUSIC ...]

Examples:
  opentune Daft Punk Get Lucky
  opentune

Options:
  -h, --help     Show this help and exit.

Main window keys:
  j / Down       Select next result or queue track
  k / Up         Select previous result or queue track
  g / G           Jump to top / bottom of the current list
  [ / ]           Previous / next item in the Results search list
  Ctrl-b / Ctrl-f Move half a page up / down
  Enter          Play the selected track
  Space          Pause or resume (works from any window)
  h / l          Previous / next track
  H / L          Rewind / forward 10 seconds
  Shift-Left/Right Rewind / forward 10 seconds
  Ctrl-o         Toggle looping for the current track (any window)
  Tab            Next tab: Results, Queue, Suggestions, History
  Shift-Tab      Previous tab
  /              Search YouTube from any window
  f              Find and highlight a song in the Queue (Queue tab)
  n / N          Next / previous Queue match after using f
  a              Append the focused result/queue track to the Queue
  s              Shuffle the Queue (Queue tab only)
  v              Start/stop visual selection; extend with j/k
  d              Download the highlighted song
  D              Delete selected queue track(s) (confirm with y/n/Enter)
  c              Clear the Queue (confirm with y/n/Enter)
  u              Undo the last queue delete/clear
  Ctrl-r         Redo the last undone queue delete/clear
  pN              Add focused result/queue track to user playlist N
  pcN             Add the currently playing track to user playlist N
  Ctrl-d         Download the currently playing track
  x / y / z      Cut / copy / paste selected songs in an open playlist
  P              Toggle the Playlists window
  Ctrl-h/l or Ctrl-Left/Right Cycle focus between panes (when open)
  ?              Toggle this key reference in the TUI
  Esc            Cancel a prompt/visual selection
  q              Quit OpenTune (the only quit key)

Playlists window keys:
  Ctrl-h / Ctrl-l Cycle focus left / right between panes
  Ctrl-Left/Right Cycle focus left / right between panes
  j / k          Move down / up
  Left / Right    Leave / enter a playlist
  Space          Pause or resume (works from any window)
  H / L          Rewind / forward 10 seconds (works from any window)
  Shift-Left/Right Rewind / forward 10 seconds (works from any window)
  Tab            Next tab; Shift-Tab previous tab (any window)
  /              Search YouTube (works from any window)
  f              Find and highlight a song in the open playlist
  n / N          Next / previous playlist match after using f
  l              Enter the focused playlist (playlist list only)
  h              Leave the open playlist (open playlist only)
  Enter          Play the selected song (open playlist only)
  a              Create a playlist, or append its focused song to Queue
  pN              Add selected open-playlist song(s) to user playlist N
  pcN             Add the currently playing track to user playlist N
  p              Pin/unpin the focused playlist (playlist list only)
  r              Rename the focused playlist
  d              Download the highlighted song
  D              Delete selected song(s), or focused playlist (confirm first)
  Ctrl-d         Download the currently playing song (or the focused playlist
                 song when nothing is playing)
  x / y / z      Cut / copy / paste selected songs between playlists
  Ctrl-o         Toggle looping (works from any window)
  o              Toggle looping of the open playlist
  v              Start/stop visual selection; extend with j/k
  P              Toggle the Playlists window

Playlist notes:
  Downloads has no user-playlist index. pN/pcN target user playlists only.
  Pinned user playlists stay above unpinned playlists.
  Esc cancels prompts, visual selection, or the help overlay; it never quits.
  Deletion prompts accept y, n, or Enter (Enter means yes).
  Press Esc twice quickly in Queue or an open playlist to clear its find query.
  Find matches use a secondary color and show their position as [current/total].
  Visual selections support bulk queue/playlist operations. Undo/redo do not
  apply to playlist song changes.

OpenTune requires mpv and yt-dlp. It streams audio and optionally downloads
tracks with d/Ctrl-d. Selecting a result creates a continuously replenished
YouTube radio-style mix, shown in the Queue tab. Suggestions are based on
your saved listening history. Only music-like results are kept; use `a` to
append a search result without starting it."""


@dataclass(frozen=True)
class Track:
    title: str
    url: str
    duration: int = 0
    uploader: str = ""
    local_path: str = ""

    @property
    def label(self) -> str:
        return f"{self.title} — {self.uploader}" if self.uploader else self.title

    @property
    def source(self) -> str:
        return self.local_path or self.url


def format_time(seconds: float | int | None) -> str:
    total = max(0, int(seconds or 0))
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def fuzzy_score(query: str, candidate: str) -> int | None:
    """Score a small fuzzy match; higher scores are better."""
    query = re.sub(r"\s+", "", query.lower())
    candidate = candidate.lower()
    if not query:
        return 0
    if query in candidate:
        return 1000 - candidate.index(query)
    cursor = -1
    gaps = 0
    first = None
    for character in query:
        position = candidate.find(character, cursor + 1)
        if position < 0:
            return None
        if first is None:
            first = position
        if cursor >= 0:
            gaps += position - cursor - 1
        cursor = position
    return 700 - (first or 0) * 2 - gaps


def song_match_score(query: str, track: Track) -> int | None:
    """Prefer song-title matches and only use artist matches as a fallback."""
    title_score = fuzzy_score(query, track.title)
    if title_score is not None:
        return title_score + 250
    artist_score = fuzzy_score(query, track.uploader)
    return artist_score - 100 if artist_score is not None else None


def require_tools() -> str | None:
    absent = [name for name in ("mpv", "yt-dlp") if not shutil.which(name)]
    return f"Missing required command(s): {', '.join(absent)}" if absent else None


def is_backtab(key: int) -> bool:
    """Recognize Shift-Tab across terminals with different curses values."""
    return key in {getattr(curses, "KEY_BTAB", -999), 353}


class YouTube:
    """Small, deliberately dependency-free yt-dlp adapter."""

    @staticmethod
    def _looks_like_music(entry: dict[str, Any]) -> bool:
        title = str(entry.get("title") or "")
        if not title or NON_MUSIC_TERMS.search(title):
            return False
        if entry.get("is_live") or entry.get("live_status") in {"is_live", "is_upcoming"}:
            return False
        duration = entry.get("duration")
        if duration is not None and (float(duration) < 30 or float(duration) > 2 * 60 * 60):
            return False
        categories = entry.get("categories") or []
        if categories and "music" not in " ".join(str(item) for item in categories).lower():
            # yt-dlp often omits categories for flat search results. When it
            # supplies them, do not accept a known non-music category.
            return False
        return True

    @staticmethod
    def _fetch(target: str, label: str) -> list[Track]:
        command = ["yt-dlp", "--flat-playlist", "--dump-single-json", target]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=25, check=True)
            payload = json.loads(completed.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError) as error:
            raise RuntimeError(f"{label} failed: {error}") from error
        tracks: list[Track] = []
        for entry in payload.get("entries") or []:
            video_id = entry.get("id")
            if not video_id or not YouTube._looks_like_music(entry):
                continue
            tracks.append(Track(
                title=entry.get("title") or "Untitled",
                url=entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                duration=int(entry.get("duration") or 0),
                uploader=entry.get("uploader") or entry.get("channel") or "",
            ))
        return tracks

    @classmethod
    def search(cls, query: str, limit: int = SEARCH_LIMIT) -> list[Track]:
        if not query.strip():
            return []
        return cls._fetch(f"ytsearch{limit}:{query} music", "Search")

    @classmethod
    def suggestions(cls, query: str, limit: int = 5) -> list[Track]:
        """Return only music results whose title or artist matches the query."""
        candidates = cls.search(query, max(limit * 2, 8))
        ranked = [
            (score, index, track)
            for index, track in enumerate(candidates)
            if (score := song_match_score(query, track)) is not None
        ]
        ranked.sort(key=lambda item: (-item[0], item[1]))
        return [track for _, _, track in ranked[:limit]]

    @staticmethod
    def _video_id(url: str) -> str | None:
        parsed = urlparse(url)
        if parsed.netloc in {"youtu.be", "www.youtu.be"}:
            return parsed.path.strip("/") or None
        video_id = parse_qs(parsed.query).get("v", [None])[0]
        return video_id

    @staticmethod
    def _track_key(track: Track) -> str:
        """Create a loose song identity to exclude alternate uploads of a seed."""
        title = track.title.lower()
        if track.uploader:
            title = title.replace(track.uploader.lower(), " ")
        title = re.sub(r"\[[^]]*\]|\([^)]*\)", " ", title)
        title = re.sub(
            r"\b(official|audio|video|lyrics?|visuali[sz]er|music|hd|4k|remaster(?:ed)?)\b",
            " ",
            title,
        )
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", title)).strip()

    @classmethod
    def _unique_mix(cls, seed: Track, candidates: list[Track]) -> list[Track]:
        seed_key = cls._track_key(seed)
        seen: set[str] = set()
        mix: list[Track] = []
        for candidate in candidates:
            key = cls._track_key(candidate)
            same_song = bool(seed_key and (key == seed_key or key.startswith(seed_key + " ") or seed_key.startswith(key + " ")))
            if not key or candidate.url == seed.url or same_song or key in seen:
                continue
            seen.add(key)
            mix.append(candidate)
            if len(mix) == MIX_LIMIT:
                break
        return mix

    @classmethod
    def mix_for(cls, track: Track) -> list[Track]:
        # YouTube's RD playlist is the same radio/mix mechanism exposed by its UI.
        # It produces a varied sequence rather than search matches of the same video.
        video_id = cls._video_id(track.url)
        if video_id:
            try:
                radio = cls._fetch(
                    f"https://www.youtube.com/watch?v={video_id}&list=RD{video_id}",
                    "YouTube mix",
                )
                mix = cls._unique_mix(track, radio)
                if mix:
                    return mix
            except RuntimeError:
                pass

        # Fallback when YouTube does not expose a radio playlist for a video.
        # This remains artist-scoped and passes through the same music filter;
        # it is not a second search for the seed title.
        artist = track.uploader or track.title
        candidates = cls.search(f"{artist} songs", MIX_LIMIT * 3)
        return cls._unique_mix(track, candidates)


class MPV:
    """Controls one headless mpv instance over its JSON IPC socket."""

    def __init__(self, on_finished: callable, on_error: callable) -> None:
        self._on_finished = on_finished
        self._on_error = on_error
        self._directory = tempfile.TemporaryDirectory(prefix="opentune-")
        self._socket_number = 0
        self.socket_path = str(Path(self._directory.name) / "mpv-0.sock")
        self.process: subprocess.Popen[str] | None = None
        self._intentional_stop = False
        self._lock = threading.Lock()

    def play(self, track: Track, loop: bool = False) -> None:
        self.stop()
        self._intentional_stop = False
        self._socket_number += 1
        socket_path = Path(self._directory.name) / f"mpv-{self._socket_number}.sock"
        self.socket_path = str(socket_path)
        command = [
            "mpv", "--no-video", "--force-window=no", "--really-quiet",
            f"--input-ipc-server={self.socket_path}", "--ytdl-format=bestaudio/best", track.source,
        ]
        if loop:
            command.insert(-1, "--loop-file=inf")
        self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        threading.Thread(target=self._watch, args=(self.process, self.socket_path), daemon=True).start()

    def _watch(self, process: subprocess.Popen[str], socket_path: str | None = None) -> None:
        return_code = process.wait()
        error_text = (process.stderr.read().strip() if process.stderr else "")
        is_current = process is self.process
        if is_current:
            self.process = None
        if socket_path:
            try:
                Path(socket_path).unlink(missing_ok=True)
            except OSError:
                pass
        if not self._intentional_stop and is_current:
            if return_code == 0:
                self._on_finished()
            else:
                self._on_error(error_text or f"mpv exited with status {return_code}")

    def command(self, command: list[Any]) -> Any | None:
        if not self.process or self.process.poll() is not None:
            return None
        message = json.dumps({"command": command}) + "\n"
        with self._lock:
            try:
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                client.settimeout(0.25)
                client.connect(self.socket_path)
                client.sendall(message.encode())
                response = client.recv(4096)
                client.close()
                return json.loads(response.decode().splitlines()[0]).get("data")
            except (OSError, json.JSONDecodeError, IndexError):
                return None

    def toggle_pause(self) -> None:
        self.command(["cycle", "pause"])

    def seek(self, seconds: int) -> None:
        self.command(["seek", seconds, "relative+exact"])

    def set_loop(self, enabled: bool) -> None:
        self.command(["set_property", "loop-file", "inf" if enabled else "no"])

    def state(self) -> tuple[float, bool]:
        position = self.command(["get_property", "playback-time"])
        paused = self.command(["get_property", "pause"])
        return float(position or 0), bool(paused)

    def stop(self) -> None:
        if self.process and self.process.poll() is None:
            self._intentional_stop = True
            self.command(["quit"])
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
        self.process = None
        try:
            Path(self.socket_path).unlink(missing_ok=True)
        except OSError:
            pass

    def close(self) -> None:
        self.stop()
        self._directory.cleanup()


@dataclass(frozen=True)
class QueueAction:
    kind: str
    index: int = 0
    track: Track | None = None
    tracks: tuple[Track, ...] = ()
    indices: tuple[int, ...] = ()


class HistoryStore:
    """Persist recent listening history and expose history-based suggestions."""

    def __init__(self, root: Path | None = None) -> None:
        base = Path(root) if root else Path.home() / "Music" / "opentune"
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / "history.json"
        self._entries: list[dict[str, Any]] = []
        self._load()

    @staticmethod
    def _track_from_json(data: dict[str, Any]) -> Track:
        return Track(
            title=str(data.get("title") or "Untitled"),
            url=str(data.get("url") or ""),
            duration=int(data.get("duration") or 0),
            uploader=str(data.get("uploader") or ""),
            local_path=str(data.get("local_path") or ""),
        )

    @staticmethod
    def _track_to_json(track: Track) -> dict[str, Any]:
        return {
            "title": track.title,
            "url": track.url,
            "duration": track.duration,
            "uploader": track.uploader,
            "local_path": track.local_path,
        }

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._entries = [item for item in raw if isinstance(item, dict) and item.get("url")] if isinstance(raw, list) else []

    def _save(self) -> None:
        temporary = self.path.with_name(f".{self.path.name}.tmp")
        try:
            temporary.write_text(json.dumps(self._entries[:200], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            temporary.unlink(missing_ok=True)

    def record(self, track: Track) -> None:
        self._entries = [item for item in self._entries if item.get("url") != track.url]
        self._entries.insert(0, {**self._track_to_json(track), "played_at": int(time.time())})
        self._save()

    def tracks(self) -> list[Track]:
        return [self._track_from_json(item) for item in self._entries]

    def recommendations(self, limit: int = SEARCH_LIMIT) -> list[Track]:
        """Return recent unique listening-history tracks for the Home tab."""
        tracks: list[Track] = []
        seen: set[str] = set()
        for track in self.tracks():
            if track.url not in seen:
                tracks.append(track)
                seen.add(track.url)
            if len(tracks) >= limit:
                break
        return tracks

    def search(self, query: str, limit: int = 5) -> list[Track]:
        """Return history entries matching a search using lightweight fuzzy scoring."""
        ranked: list[tuple[int, int, Track]] = []
        for recency, track in enumerate(self.tracks()):
            score = song_match_score(query, track)
            if score is not None:
                ranked.append((score, -recency, track))
        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [track for _, _, track in ranked[:limit]]


class NoticeState:
    """Remember which release's one-time welcome/update notice was dismissed."""

    def __init__(self, path: Path | None = None) -> None:
        config = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "opentune"
        self.path = Path(path) if path else config / "state.json"

    def last_seen_version(self) -> str:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return str(data.get("last_seen_version") or "")
        except (OSError, json.JSONDecodeError):
            return ""

    def mark_seen(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_name(f".{self.path.name}.tmp")
            temporary.write_text(json.dumps({"last_seen_version": __version__}) + "\n", encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass


class Player:
    def __init__(self) -> None:
        self.current: Track | None = None
        self.queue: list[Track] = []
        self.history: list[Track] = []
        self.loop = False
        self.playlist_loop = False
        self.playlist_tracks: list[Track] = []
        self.track_resolver: Callable[[Track], Track] | None = None
        self.message = "Ready. Press / to search."
        self.playback_failed = False
        self.history_store: HistoryStore | None = None
        self.continuous_queue = True
        self._refill_pending = False
        self._queue_undo: list[QueueAction] = []
        self._queue_redo: list[QueueAction] = []
        self._lock = threading.Lock()
        self.mpv = MPV(self._finished, self._playback_error)

    def resolve_track(self, track: Track) -> Track:
        return self.track_resolver(track) if self.track_resolver else track

    def start(self, track: Track, *, build_mix: bool = True, remember_current: bool = True) -> None:
        track = self.resolve_track(track)
        with self._lock:
            if build_mix:
                self.playlist_loop = False
                self.playlist_tracks = []
            if remember_current and self.current and self.current.url != track.url:
                self.history.append(self.current)
            self.current = track
            self.playback_failed = False
            if self.history_store:
                self.history_store.record(track)
            self.mpv.play(track, self.loop)
            self.message = f"Playing: {track.title}"
        if build_mix:
            threading.Thread(target=self._build_mix, args=(track,), daemon=True).start()

    def _build_mix(self, track: Track) -> None:
        try:
            mix = YouTube.mix_for(track)
            with self._lock:
                if self.current == track:
                    existing = {item.url for item in self.queue}
                    existing_keys = {YouTube._track_key(item) for item in self.queue}
                    for item in mix:
                        key = YouTube._track_key(item)
                        if item.url in existing or (key and key in existing_keys):
                            continue
                        self.queue.append(item)
                        existing.add(item.url)
                        if key:
                            existing_keys.add(key)
                    if mix:
                        self._queue_redo.clear()
                    self.message = f"Mix ready: {len(self.queue)} tracks queued"
        except RuntimeError:
            pass

    def _playback_error(self, detail: str) -> None:
        with self._lock:
            self.playback_failed = True
            compact = " ".join(detail.split())
            self.message = f"Playback failed: {compact[-220:]}"

    def next(self) -> None:
        with self._lock:
            if not self.queue:
                self.message = "Queue is empty"
                return
            next_track = self.queue.pop(0)
            self._queue_redo.clear()
        self.start(next_track, build_mix=False)

    def enqueue(self, track: Track) -> bool:
        track = self.resolve_track(track)
        with self._lock:
            existing_urls = {item.url for item in self.queue}
            existing_keys = {YouTube._track_key(item) for item in self.queue}
            key = YouTube._track_key(track)
            if track.url in existing_urls or (key and key in existing_keys):
                self.message = "That track is already in the Queue"
                return False
            self.queue.append(track)
            self._queue_redo.clear()
            self.message = f"Added to Queue: {track.title}"
            return True

    def shuffle_queue(self) -> bool:
        """Shuffle only the temporary queue; saved playlists are untouched."""
        with self._lock:
            if len(self.queue) < 2:
                self.message = "Queue needs at least two songs to shuffle"
                return False
            random.shuffle(self.queue)
            self._queue_redo.clear()
            self.message = f"Shuffled {len(self.queue)} queued tracks"
            return True

    def remove_queue_at(self, index: int) -> Track | None:
        with self._lock:
            if not 0 <= index < len(self.queue):
                return None
            removed = self.queue.pop(index)
            self._queue_undo.append(QueueAction("delete", index=index, track=removed))
            self._queue_redo.clear()
            self.message = f"Removed from Queue: {removed.title}"
            return removed

    def remove_queue_indices(self, indices: list[int]) -> int:
        with self._lock:
            valid = sorted({index for index in indices if 0 <= index < len(self.queue)})
            if not valid:
                return 0
            removed = tuple(self.queue[index] for index in valid)
            self.queue = [track for index, track in enumerate(self.queue) if index not in set(valid)]
            self._queue_undo.append(QueueAction("delete_many", tracks=removed, indices=tuple(valid)))
            self._queue_redo.clear()
            self.message = f"Removed {len(removed)} tracks from Queue"
            return len(removed)

    def clear_queue(self) -> int:
        with self._lock:
            count = len(self.queue)
            if count:
                self._queue_undo.append(QueueAction("clear", tracks=tuple(self.queue)))
                self._queue_redo.clear()
            self.queue.clear()
            self.message = "Queue cleared" if count else "Queue is already empty"
            return count

    def take_queue_at(self, index: int) -> Track | None:
        """Take a queue item to play without treating playback as undoable."""
        with self._lock:
            if not 0 <= index < len(self.queue):
                return None
            self._queue_redo.clear()
            return self.queue.pop(index)

    def undo_queue_action(self) -> bool:
        with self._lock:
            if not self._queue_undo:
                self.message = "Nothing to undo"
                return False
            action = self._queue_undo.pop()
            if action.kind == "delete" and action.track is not None:
                self.queue.insert(min(action.index, len(self.queue)), action.track)
                self.message = f"Undo: restored {action.track.title}"
            elif action.kind == "delete_many":
                for index, track in zip(action.indices, action.tracks):
                    self.queue.insert(min(index, len(self.queue)), track)
                self.message = f"Undo: restored {len(action.tracks)} queue tracks"
            elif action.kind == "clear":
                self.queue[0:0] = list(action.tracks)
                self.message = f"Undo: restored {len(action.tracks)} queue tracks"
            self._queue_redo.append(action)
            return True

    def redo_queue_action(self) -> bool:
        with self._lock:
            if not self._queue_redo:
                self.message = "Nothing to redo"
                return False
            action = self._queue_redo.pop()
            if action.kind == "delete" and action.track is not None:
                index = action.index if action.index < len(self.queue) else -1
                if index >= 0 and self.queue[index].url == action.track.url:
                    self.queue.pop(index)
                else:
                    for candidate_index, candidate in enumerate(self.queue):
                        if candidate.url == action.track.url:
                            self.queue.pop(candidate_index)
                            break
                self.message = f"Redo: removed {action.track.title}"
            elif action.kind == "delete_many":
                urls = {track.url for track in action.tracks}
                self.queue = [track for track in self.queue if track.url not in urls]
                self.message = f"Redo: removed {len(action.tracks)} queue tracks"
            elif action.kind == "clear":
                self.queue.clear()
                self.message = "Redo: cleared Queue"
            self._queue_undo.append(action)
            return True

    def previous(self) -> None:
        with self._lock:
            if not self.history:
                self.message = "No previous track"
                return
            previous_track = self.history.pop()
            if self.current:
                self.queue.insert(0, self.current)
                self._queue_redo.clear()
        self.start(previous_track, build_mix=False, remember_current=False)

    def _finished(self) -> None:
        if self.loop:
            return
        if self.playlist_loop and not self.queue and self.playlist_tracks:
            current_url = self.current.url if self.current else ""
            self.queue = [track for track in self.playlist_tracks if track.url != current_url]
        if self.queue:
            self.next()
        elif self.playlist_loop and self.current:
            self.start(self.current, build_mix=False)
        elif self.continuous_queue and self.current:
            self._refill_and_continue(self.current)

    def _refill_and_continue(self, seed: Track) -> None:
        """Fetch another radio batch when a continuously generated queue ends."""
        with self._lock:
            if self._refill_pending or not self.continuous_queue:
                return
            self._refill_pending = True

        def worker() -> None:
            try:
                mix = YouTube.mix_for(seed)
                with self._lock:
                    if not self.continuous_queue or self.current is None or self.current.url != seed.url:
                        return
                    existing = {item.url for item in self.queue}
                    existing_keys = {YouTube._track_key(item) for item in self.queue}
                    for item in mix:
                        key = YouTube._track_key(item)
                        if item.url in existing or (key and key in existing_keys):
                            continue
                        self.queue.append(item)
                        existing.add(item.url)
                        if key:
                            existing_keys.add(key)
                    self.message = f"Queue replenished: {len(self.queue)} tracks queued" if mix else "No more songs were found"
                    should_continue = bool(self.queue)
                if should_continue:
                    self.next()
            except RuntimeError:
                pass
            finally:
                with self._lock:
                    self._refill_pending = False

        threading.Thread(target=worker, daemon=True).start()

    def toggle_loop(self) -> None:
        self.loop = not self.loop
        self.mpv.set_loop(self.loop)
        self.message = f"Loop {'on' if self.loop else 'off'}"

    def close(self) -> None:
        self.continuous_queue = False
        self.mpv.close()


    def replace_queue(self, tracks: list[Track], current: Track | None = None) -> None:
        with self._lock:
            current_url = current.url if current else ""
            self.queue = [self.resolve_track(track) for track in tracks if track.url != current_url]
            self._queue_redo.clear()
            self.message = f"Playlist loaded: {len(self.queue) + (1 if current else 0)} tracks"

    def set_playlist_loop(self, tracks: list[Track], enabled: bool) -> None:
        with self._lock:
            self.playlist_loop = enabled
            self.playlist_tracks = [self.resolve_track(track) for track in tracks] if enabled else []
            self.message = f"Playlist loop {'on' if enabled else 'off'}"


@dataclass
class Playlist:
    id: str
    name: str
    tracks: list[Track]
    pinned: bool = False


class PlaylistStore:
    """Persistent playlist storage under ~/Music/opentune."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = Path(root) if root else Path.home() / "Music" / "opentune" / "Playlists"
        self.download_dir = self.root.parent / "Downloads"
        self.manifest_path = self.root / "index.json"
        self.root.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self._playlists: list[Playlist] = []
        self._load()

    @staticmethod
    def _track_from_json(data: dict[str, Any]) -> Track:
        return Track(
            title=str(data.get("title") or "Untitled"),
            url=str(data.get("url") or ""),
            duration=int(data.get("duration") or 0),
            uploader=str(data.get("uploader") or ""),
            local_path=str(data.get("local_path") or ""),
        )

    @staticmethod
    def _track_to_json(track: Track) -> dict[str, Any]:
        return {
            "title": track.title,
            "url": track.url,
            "duration": track.duration,
            "uploader": track.uploader,
            "local_path": track.local_path,
        }

    def _playlist_path(self, playlist_id: str) -> Path:
        return self.root / ("downloads.json" if playlist_id == "downloads" else f"{playlist_id}.json")

    def _load(self) -> None:
        entries: list[dict[str, Any]] = []
        if self.manifest_path.exists():
            try:
                raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
                entries = raw if isinstance(raw, list) else []
            except (OSError, json.JSONDecodeError):
                entries = []
        for entry in entries:
            playlist_id = str(entry.get("id") or "")
            if not playlist_id or playlist_id == "downloads":
                continue
            self._playlists.append(self._load_playlist(
                playlist_id,
                str(entry.get("name") or "Untitled Playlist"),
                bool(entry.get("pinned", False)),
            ))
        downloads = self._load_playlist("downloads", "Downloads", True)
        self._playlists.insert(0, downloads)
        self._atomic_write(
            self._playlist_path("downloads"),
            [self._track_to_json(track) for track in downloads.tracks],
        )
        self._save_manifest()

    def _load_playlist(self, playlist_id: str, name: str, pinned: bool = False) -> Playlist:
        tracks: list[Track] = []
        path = self._playlist_path(playlist_id)
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, list):
                    tracks = [self._track_from_json(item) for item in raw if isinstance(item, dict)]
                    if playlist_id == "downloads":
                        # Downloads is rebuilt only from files that still exist;
                        # old metadata-only entries are intentionally discarded.
                        tracks = [
                            track for track in tracks
                            if track.local_path and Path(track.local_path).is_file()
                        ]
            except (OSError, json.JSONDecodeError):
                tracks = []
        return Playlist(playlist_id, name, tracks, pinned)

    def _save_manifest(self) -> None:
        self._atomic_write(self.manifest_path, [
            {"id": item.id, "name": item.name, "pinned": item.pinned}
            for item in self._playlists
        ])

    @staticmethod
    def _atomic_write(path: Path, data: Any) -> None:
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(path)

    def _save_playlist(self, playlist: Playlist) -> None:
        self._atomic_write(
            self._playlist_path(playlist.id),
            [self._track_to_json(track) for track in playlist.tracks],
        )
        self._save_manifest()

    def all(self) -> list[Playlist]:
        return list(self._playlists)

    def get(self, index: int) -> Playlist | None:
        return self._playlists[index] if 0 <= index < len(self._playlists) else None

    def user_playlists(self) -> list[Playlist]:
        """Return only user-created playlists, excluding Downloads."""
        return [playlist for playlist in self._playlists if playlist.id != "downloads"]

    def get_user(self, index: int) -> Playlist | None:
        playlists = self.user_playlists()
        return playlists[index] if 0 <= index < len(playlists) else None

    def resolve_track(self, track: Track) -> Track:
        """Attach a downloaded local path to matching playlist/search metadata."""
        downloaded = next(
            (item for item in self.get(0).tracks if item.url == track.url),
            None,
        ) if self.get(0) else None
        if not downloaded or not downloaded.local_path or not Path(downloaded.local_path).is_file():
            return track
        if track.local_path == downloaded.local_path:
            return track
        return Track(track.title, track.url, track.duration, track.uploader, downloaded.local_path)

    def is_downloaded(self, track: Track) -> bool:
        return bool(self.resolve_track(track).local_path)

    def create(self, name: str = "") -> Playlist:
        name = name.strip()
        if not name:
            used = {item.name for item in self._playlists}
            number = 1
            while f"My Playlist #{number}" in used:
                number += 1
            name = f"My Playlist #{number}"
        playlist = Playlist(f"playlist-{uuid.uuid4().hex}", name, [])
        self._playlists.append(playlist)
        self._save_playlist(playlist)
        return playlist

    def rename(self, playlist: Playlist, name: str) -> bool:
        name = name.strip()
        if not name or playlist.pinned:
            return False
        playlist.name = name
        self._save_playlist(playlist)
        return True

    def add_track(self, playlist: Playlist, track: Track) -> bool:
        if playlist.id == "downloads":
            return False
        # User playlists store YouTube metadata only; local availability is
        # resolved dynamically from the Downloads playlist when playing.
        track = Track(track.title, track.url, track.duration, track.uploader)
        if any(item.url == track.url for item in playlist.tracks):
            return False
        playlist.tracks.append(track)
        self._save_playlist(playlist)
        return True

    def add_download(self, track: Track) -> bool:
        """Add a track to Downloads only when its local file exists."""
        if not track.local_path or not Path(track.local_path).is_file():
            return False
        return self._add_download_unchecked(track)

    def _add_download_unchecked(self, track: Track) -> bool:
        downloads = self.get(0)
        if downloads is None or any(item.url == track.url for item in downloads.tracks):
            return False
        downloads.tracks.append(track)
        self._save_playlist(downloads)
        return True

    def remove_track(self, playlist: Playlist, index: int) -> Track | None:
        if not 0 <= index < len(playlist.tracks):
            return None
        removed = playlist.tracks.pop(index)
        self._save_playlist(playlist)
        if playlist.pinned and removed.local_path:
            try:
                Path(removed.local_path).unlink(missing_ok=True)
            except OSError:
                pass
        return removed

    def toggle_pin(self, playlist: Playlist) -> bool | None:
        """Toggle a user playlist's pinned state and keep Downloads first."""
        if playlist.id == "downloads" or playlist not in self._playlists:
            return None
        playlist.pinned = not playlist.pinned
        downloads = self._playlists[0]
        custom = self._playlists[1:]
        pinned = [item for item in custom if item.pinned]
        unpinned = [item for item in custom if not item.pinned]
        self._playlists = [downloads, *pinned, *unpinned]
        self._save_manifest()
        return playlist.pinned

    def delete_playlist(self, playlist: Playlist) -> bool:
        """Delete a user playlist and its metadata, never the pinned Downloads list."""
        if playlist.id == "downloads" or playlist not in self._playlists:
            return False
        self._playlists = [item for item in self._playlists if item.id != playlist.id]
        try:
            self._playlist_path(playlist.id).unlink(missing_ok=True)
        except OSError:
            pass
        self._save_manifest()
        return True


class Downloader:
    @staticmethod
    def download(track: Track, directory: Path) -> Track:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("Downloading requires ffmpeg; install it and try again")
        directory.mkdir(parents=True, exist_ok=True)
        output = directory / "%(title)s [%(id)s].%(ext)s"
        command = [
            "yt-dlp", "--no-playlist", "--format", "bestaudio/best",
            "--extract-audio", "--audio-format", "mp3",
            "--output", str(output), "--print", "after_move:filepath", track.url,
        ]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=900, check=True)
        except (subprocess.SubprocessError, OSError) as error:
            raise RuntimeError(f"Download failed: {error}") from error
        candidates = [Path(line.strip()) for line in completed.stdout.splitlines() if line.strip()]
        downloaded = next((path for path in reversed(candidates) if path.exists()), None)
        if downloaded is None:
            raise RuntimeError("Download completed but its output file was not found")
        return Track(track.title, track.url, track.duration, track.uploader, str(downloaded))


class TUI:
    def __init__(self, screen: curses.window, player: Player, initial_query: str = "") -> None:
        self.screen, self.player = screen, player
        self.results: list[Track] = []
        self.result_index = 0
        self.queue_index = 0
        self.tab = 0  # 0 results, 1 queue
        self.running = True
        self.showing_help = False
        curses.curs_set(0)
        screen.nodelay(True)
        screen.keypad(True)
        if initial_query:
            self.search(initial_query)

    def search(self, query: str) -> None:
        self.player.message = f"Searching YouTube for: {query}"
        self.draw()
        try:
            self.results = YouTube.search(query)
            self.result_index = 0
            self.tab = 0
            self.player.message = f"{len(self.results)} results for “{query}”"
        except RuntimeError as error:
            self.player.message = str(error)

    def prompt_search(self) -> None:
        height, _ = self.screen.getmaxyx()
        self.screen.nodelay(False)
        curses.curs_set(1)
        query_chars: list[str] = []
        cancelled = False
        try:
            while True:
                query_text = "".join(query_chars)
                display_width = max(1, self.screen.getmaxyx()[1] - 10)
                visible = query_text[-display_width:]
                self.screen.move(height - 1, 0)
                self.screen.clrtoeol()
                self.screen.addnstr(height - 1, 0, f"Search: {visible}", self.screen.getmaxyx()[1] - 1)
                self.screen.refresh()
                key = self.screen.getch()
                if key in (27, 3):  # Esc/Ctrl-c cancels without changing results.
                    cancelled = True
                    break
                if key in (10, 13, curses.KEY_ENTER):
                    break
                if key in (curses.KEY_BACKSPACE, 8, 127):
                    if query_chars:
                        query_chars.pop()
                elif 32 <= key <= 126:
                    query_chars.append(chr(key))
        finally:
            self.screen.move(height - 1, 0)
            self.screen.clrtoeol()
            self.screen.refresh()
        curses.curs_set(0)
        self.screen.nodelay(True)
        query = "".join(query_chars).strip()
        if cancelled:
            self.player.message = "Search cancelled"
        elif query:
            self.search(query)

    @staticmethod
    def clipped(value: str, width: int) -> str:
        return value if len(value) <= width else value[: max(0, width - 1)] + "…"

    def draw_track_list(self, items: list[Track], selected: int, top: int, height: int, width: int) -> None:
        if not items:
            self.screen.addstr(top, 2, "Nothing here yet.", curses.A_DIM)
            return
        start = max(0, min(selected - height + 1, len(items) - height))
        for line, index in enumerate(range(start, min(len(items), start + height))):
            item = items[index]
            marker = "›" if index == selected else " "
            duration = format_time(item.duration)
            text = f"{marker} {index + 1:2}. {item.label}  [{duration}]"
            attr = curses.A_REVERSE if index == selected else curses.A_NORMAL
            self.screen.addnstr(top + line, 1, self.clipped(text, width - 2), width - 2, attr)

    def draw(self) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        current = self.player.current
        position, paused = self.player.mpv.state() if current else (0, False)
        title = current.title if current else "Nothing playing"
        duration = current.duration if current else 0
        mode = "ERROR" if current and self.player.playback_failed else "PAUSED" if paused else "PLAYING" if current else "IDLE"
        loop = " LOOP" if self.player.loop else " PLOOP" if self.player.playlist_loop else ""
        self.screen.addnstr(0, 1, f" OPENTUNE  ·  {mode}{loop}", width - 2, curses.A_BOLD)
        self.screen.hline(1, 0, curses.ACS_HLINE, width)
        self.screen.addnstr(2, 2, self.clipped(title, width - 4), width - 4, curses.A_BOLD)
        self.screen.addnstr(3, 2, f"{format_time(position)} / {format_time(duration)}", width - 4, curses.A_DIM)
        self.screen.hline(5, 0, curses.ACS_HLINE, width)
        tabs = "[ Results ]" if self.tab == 0 else "  Results  "
        tabs += "     " + ("[ Queue ]" if self.tab == 1 else "  Queue  ")
        self.screen.addnstr(6, 2, tabs, width - 4, curses.A_BOLD)
        list_height = max(1, height - 10)
        if self.showing_help:
            self.draw_help(8, width, list_height)
        elif self.tab == 0:
            self.draw_track_list(self.results, self.result_index, 8, list_height, width)
        else:
            self.draw_track_list(self.player.queue, self.queue_index, 8, list_height, width)
        self.screen.hline(height - 2, 0, curses.ACS_HLINE, width)
        status = self.clipped(self.player.message, width - 4)
        self.screen.addnstr(height - 1, 2, status, width - 4, curses.A_DIM)
        self.screen.refresh()

    def draw_help(self, top: int, width: int, height: int) -> None:
        lines = [
            "KEY REFERENCE  (press ? or Esc to return)",
            "",
            "j / ↓    down       k / ↑    up        Enter    play selection",
            "Space    pause/play h        previous  l        next",
            "H        rewind 10s L        forward 10s Ctrl-o   toggle loop",
            "Tab      Results/Queue       / search   a add to Queue",
            "d download focused song  D delete Queue  c clear Queue (confirm)",
            "Ctrl-r   redo               ?        this help    q        quit",
            "Esc      cancel search (in prompt)",
            "",
            "Selecting a result starts playback and continuously replenishes its radio mix.",
        ]
        for index, line in enumerate(lines[:height]):
            attr = curses.A_BOLD if index == 0 else curses.A_NORMAL
            self.screen.addnstr(top + index, 2, self.clipped(line, width - 4), width - 4, attr)

    def move(self, delta: int) -> None:
        if self.tab == 0:
            self.result_index = max(0, min(len(self.results) - 1, self.result_index + delta))
        else:
            self.queue_index = max(0, min(len(self.player.queue) - 1, self.queue_index + delta))

    def select(self) -> None:
        if self.tab == 0 and self.results:
            self.player.start(self.results[self.result_index])
        elif self.tab == 1 and self.player.queue:
            track = self.player.take_queue_at(self.queue_index)
            if track is None:
                return
            self.queue_index = max(0, min(self.queue_index, len(self.player.queue) - 1))
            self.player.start(track, build_mix=False)

    def append_selected(self) -> None:
        if self.tab == 0 and self.results:
            self.player.enqueue(self.results[self.result_index])
        else:
            self.player.message = "Select a search result to append"

    def delete_selected(self) -> None:
        if self.tab != 1:
            self.player.message = "Switch to Queue to delete a track"
            return
        self.player.remove_queue_at(self.queue_index)
        self.queue_index = max(0, min(self.queue_index, len(self.player.queue) - 1))

    def handle(self, key: int) -> None:
        if self.showing_help:
            if key in (ord("?"), 27):
                self.showing_help = False
                return
            self.showing_help = False
        if key == ord("q"):
            self.running = False
        elif key in (ord("j"), curses.KEY_DOWN):
            self.move(1)
        elif key in (ord("k"), curses.KEY_UP):
            self.move(-1)
        elif key in (9,):
            self.tab = 1 - self.tab
        elif key in (10, 13, curses.KEY_ENTER):
            self.select()
        elif key == ord(" "):
            self.player.mpv.toggle_pause()
        elif key == ord("h"):
            self.player.previous()
        elif key == ord("l"):
            self.player.next()
        elif key == ord("H"):
            self.player.mpv.seek(-10)
        elif key == ord("L"):
            self.player.mpv.seek(10)
        elif key == 15:  # Ctrl-o
            self.player.toggle_loop()
        elif key == ord("/"):
            self.prompt_search()
        elif key == ord("a"):
            self.append_selected()
        elif key == ord("d"):
            self.delete_selected()
        elif key == ord("c"):
            self.player.clear_queue()
            self.queue_index = 0
        elif key == ord("u"):
            self.player.undo_queue_action()
            self.queue_index = max(0, min(self.queue_index, len(self.player.queue) - 1))
        elif key == 18:  # Ctrl-r
            self.player.redo_queue_action()
            self.queue_index = max(0, min(self.queue_index, len(self.player.queue) - 1))
        elif key == ord("?"):
            self.showing_help = True

    def run(self) -> None:
        while self.running:
            self.draw()
            key = self.screen.getch()
            if key != -1:
                self.handle(key)
            time.sleep(0.08)


class PlaylistTUI:
    """Full-screen player with an optional right-side playlist pane."""

    def __init__(self, screen: curses.window, player: Player, store: PlaylistStore, initial_query: str = "") -> None:
        self.screen, self.player, self.store = screen, player, store
        self.player.track_resolver = self.store.resolve_track
        self.history_store = HistoryStore(store.root.parent)
        self.player.history_store = self.history_store
        self.results: list[Track] = []
        self.suggestions: list[Track] = []
        self.history_results: list[Track] = []
        self.result_index = 0
        self.queue_index = 0
        self.history_index = 0
        self.tab = 0
        self.running = True
        self.showing_help = False
        self.panel_open = False
        self.focus = "main"
        self.playlist_index = 0
        self.active_playlist_id: str | None = None
        self.playlist_track_index = 0
        self.playlist_search = ""
        self.queue_search = ""
        self.visual_mode = False
        self.visual_anchor: tuple[str, int] | None = None
        self.clipboard_tracks: list[Track] = []
        self.clipboard_mode = ""
        self.clipboard_source_id: str | None = None
        self._last_escape_at = 0.0
        self._search_generation = 0
        self._history_signature: tuple[str, ...] | None = None
        self._suggestion_generation = 0
        self.searching = False
        self.search_attr = curses.A_BOLD
        if curses.has_colors():
            try:
                curses.start_color()
                curses.use_default_colors()
                curses.init_pair(2, curses.COLOR_YELLOW, -1)
                self.search_attr = curses.color_pair(2) | curses.A_BOLD
            except curses.error:
                pass
        curses.curs_set(0)
        screen.nodelay(True)
        screen.keypad(True)
        self.refresh_history_views()
        if initial_query:
            self.search(initial_query)

    @staticmethod
    def clipped(value: str, width: int) -> str:
        return value if len(value) <= width else value[: max(0, width - 1)] + "…"

    def main_width(self, total_width: int) -> int:
        return total_width if not self.panel_open else max(1, int(total_width * 0.6))

    def refresh_history_views(self) -> None:
        """Refresh History and seed Suggestions from the latest listening data."""
        history = self.history_store.tracks()
        self.history_results = history
        signature = tuple(track.url for track in history)
        if signature == self._history_signature:
            return
        self._history_signature = signature
        self._suggestion_generation += 1
        generation = self._suggestion_generation
        self.suggestions = history[:SEARCH_LIMIT]
        if not history:
            return

        seed = history[0]

        def worker() -> None:
            try:
                related = YouTube.mix_for(seed)
            except RuntimeError:
                return
            if generation != self._suggestion_generation:
                return
            seen = {track.url for track in self.suggestions}
            additions: list[Track] = []
            for track in related:
                if track.url in seen:
                    continue
                seen.add(track.url)
                additions.append(track)
            self.suggestions.extend(additions)

        threading.Thread(target=worker, daemon=True).start()

    def search(self, query: str) -> None:
        self._search_generation += 1
        generation = self._search_generation
        self.player.message = f"Searching YouTube for: {query}"
        self.searching = True
        self.draw()

        def worker() -> None:
            try:
                results = YouTube.search(query)
            except RuntimeError as error:
                if generation == self._search_generation:
                    self.searching = False
                    self.player.message = str(error)
                return
            if generation != self._search_generation:
                return
            self.results = results
            self.result_index = 0
            self.tab = 0
            self.searching = False
            self.player.message = f"{len(results)} music results for “{query}”"

        threading.Thread(target=worker, daemon=True).start()

    def prompt_line(self, label: str, suggest: bool = False) -> str | None:
        height, width = self.screen.getmaxyx()
        self.screen.nodelay(True)
        self.screen.timeout(50)
        curses.curs_set(1)
        chars: list[str] = []
        cursor = 0
        suggestions: list[Track] = []
        suggestion_index = 0
        suggestion_query = ""
        suggestion_generation = 0
        cancelled = False

        def request_suggestions(query: str) -> None:
            nonlocal suggestion_generation
            suggestion_generation += 1
            generation = suggestion_generation
            if len(query.strip()) < 2:
                suggestions.clear()
                return

            def worker() -> None:
                time.sleep(SUGGESTION_DEBOUNCE)
                if generation != suggestion_generation:
                    return
                history_matches = self.history_store.search(query) if suggest and hasattr(self, "history_store") else []
                suggestions[:] = history_matches
                try:
                    found = YouTube.suggestions(query, limit=5)
                except RuntimeError:
                    found = []
                if generation == suggestion_generation:
                    known = {track.url for track in suggestions}
                    suggestions.extend(track for track in found if track.url not in known)

            threading.Thread(target=worker, daemon=True).start()

        try:
            while True:
                query_text = "".join(chars)
                if suggest and query_text != suggestion_query:
                    suggestion_query = query_text
                    suggestion_index = 0
                    suggestions[:] = self.history_store.search(query_text) if (
                        len(query_text.strip()) >= 2 and hasattr(self, "history_store")
                    ) else []
                    request_suggestions(query_text)
                self.screen.move(height - 1, 0)
                self.screen.clrtoeol()
                prefix = f"{label}: "
                available = max(1, width - len(prefix) - 1)
                start = max(0, min(cursor - available + 1, len(chars) - available))
                visible_query = "".join(chars[start:start + available])
                text = prefix + visible_query
                self.screen.addnstr(height - 1, 0, text, width - 1)
                visible_suggestions = suggestions[: max(1, min(5, height - 2))]
                if suggest and visible_suggestions:
                    history_urls = {
                        item.url for item in self.history_store.search(query_text)
                    } if hasattr(self, "history_store") else set()
                    first_row = height - 1 - len(visible_suggestions)
                    for offset, track in enumerate(visible_suggestions):
                        row = first_row + offset
                        marker = "› " if offset == suggestion_index else "  "
                        source = "[history] " if track.url in history_urls else ""
                        self.screen.move(row, 0)
                        self.screen.clrtoeol()
                        self.screen.addnstr(row, 0, self.clipped(f"{marker}{source}{track.label}", width - 1), width - 1, curses.A_DIM)
                cursor_col = min(width - 1, len(prefix) + cursor - start)
                self.screen.move(height - 1, cursor_col)
                self.screen.refresh()
                key = self.screen.getch()
                if key < 0:
                    continue
                if key in (27, 3):
                    cancelled = True
                    break
                if key in (10, 13, curses.KEY_ENTER):
                    if suggest and visible_suggestions and suggestion_index < len(visible_suggestions):
                        chosen = visible_suggestions[suggestion_index].title
                        chars[:] = list(chosen)
                        cursor = len(chars)
                    break
                if key in (curses.KEY_BACKSPACE, 8, 127):
                    if cursor:
                        del chars[cursor - 1]
                        cursor -= 1
                elif key == getattr(curses, "KEY_DC", -999):
                    if cursor < len(chars):
                        del chars[cursor]
                elif key in (curses.KEY_LEFT, 2):  # Left / Ctrl-b
                    cursor = max(0, cursor - 1)
                elif key in (curses.KEY_RIGHT, 6):  # Right / Ctrl-f
                    cursor = min(len(chars), cursor + 1)
                elif key in (curses.KEY_HOME,):
                    cursor = 0
                elif key in (curses.KEY_END,):
                    cursor = len(chars)
                elif key in (getattr(curses, "KEY_CLEFT", -999),):
                    while cursor and chars[cursor - 1].isspace():
                        cursor -= 1
                    while cursor and not chars[cursor - 1].isspace():
                        cursor -= 1
                elif key in (getattr(curses, "KEY_CRIGHT", -999),):
                    while cursor < len(chars) and chars[cursor].isspace():
                        cursor += 1
                    while cursor < len(chars) and not chars[cursor].isspace():
                        cursor += 1
                elif suggest and key in (curses.KEY_DOWN, curses.KEY_UP):
                    if visible_suggestions:
                        step = 1 if key == curses.KEY_DOWN else -1
                        suggestion_index = max(0, min(len(visible_suggestions) - 1, suggestion_index + step))
                elif key == 9 and suggest and visible_suggestions:
                    chosen = visible_suggestions[suggestion_index].title
                    chars[:] = list(chosen)
                    cursor = len(chars)
                elif 32 <= key <= 126:
                    chars.insert(cursor, chr(key))
                    cursor += 1
                else:
                    self.handle_prompt_control(key)
        finally:
            self.screen.move(height - 1, 0)
            self.screen.clrtoeol()
            for row in range(max(0, height - min(5, height - 2) - 1), height - 1):
                self.screen.move(row, 0)
                self.screen.clrtoeol()
            self.screen.refresh()
        curses.curs_set(0)
        self.screen.timeout(0)
        self.screen.nodelay(True)
        return None if cancelled else "".join(chars).strip()

    def handle_prompt_control(self, key: int) -> None:
        """Run controls that are safe while a text prompt remains active."""
        if key == 15:  # Ctrl-o
            self.player.toggle_loop()
        elif key in (8, getattr(curses, "KEY_CLEFT", -999)):  # Ctrl-h / Ctrl-left
            self.cycle_focus(-1)
        elif key in (12, getattr(curses, "KEY_CRIGHT", -999)):  # Ctrl-l / Ctrl-right
            self.cycle_focus(1)
        elif is_backtab(key):  # Shift-Tab
            self.tab = (self.tab - 1) % 4
        elif key == 9:  # Tab
            self.tab = (self.tab + 1) % 4
        elif key in (getattr(curses, "KEY_SLEFT", -999),):
            self.player.mpv.seek(-10)
        elif key in (getattr(curses, "KEY_SRIGHT", -999),):
            self.player.mpv.seek(10)
        elif key == 4:
            if self.focus == "playlists" and self.active_playlist_id is not None:
                self.download_playlist_track()
            else:
                self.download_current()
        self.draw()

    def prompt_search(self) -> None:
        query = self.prompt_line("Search", suggest=True)
        if query is None:
            self.player.message = "Search cancelled"
        elif query:
            self.search(query)

    def prompt_playlist_number(self) -> None:
        value = self.prompt_line("Playlist number (use cN for current song)")
        if value is None:
            self.player.message = "Playlist number cancelled"
            return
        value = value.strip().lower()
        current_only = value.startswith("c")
        digits = value[1:] if current_only else value
        if not digits.isdigit():
            self.player.message = "Invalid playlist number"
            return
        index = int(digits) - 1
        playlist = self.store.get_user(index)
        if playlist is None:
            self.player.message = "Invalid playlist number"
            return
        if current_only:
            tracks = [self.player.current] if self.player.current else []
        elif self.focus == "playlists" and self.active_playlist_id is not None:
            tracks = [track for _, _, track in self.selected_playlist_tracks()]
        else:
            tracks = self.focused_main_tracks()
        if not tracks:
            self.player.message = "Select a track first (or start playback for cN)"
            return
        added = sum(self.store.add_track(playlist, track) for track in tracks)
        self.clear_visual()
        self.player.message = f"Added {added} track(s) to playlist {index + 1}: {playlist.name}"

    def prompt_confirm(self, message: str) -> bool:
        height, width = self.screen.getmaxyx()
        self.screen.nodelay(False)
        self.screen.move(height - 1, 0)
        self.screen.clrtoeol()
        self.screen.addnstr(height - 1, 0, f"{message} [y/Enter yes · n no]", width - 1)
        self.screen.refresh()
        while True:
            key = self.screen.getch()
            if key in (ord("y"), ord("Y"), 10, 13, curses.KEY_ENTER):
                answer = True
                break
            if key in (ord("n"), ord("N"), 27, 3):
                answer = False
                break
        self.screen.nodelay(True)
        self.screen.move(height - 1, 0)
        self.screen.clrtoeol()
        self.screen.refresh()
        return answer

    def focused_main_track(self) -> Track | None:
        if self.tab == 0 and self.results:
            return self.results[self.result_index]
        if self.tab == 1 and self.player.queue:
            return self.player.queue[self.queue_index]
        if self.tab == 2:
            suggestions = getattr(self, "suggestions", [])
            if suggestions:
                return suggestions[self.result_index]
        if self.tab == 3:
            history = getattr(self, "history_results", [])
            if history:
                return history[self.history_index]
        return None

    def focused_main_tracks(self) -> list[Track]:
        if self.tab == 0:
            indices = self.selected_indices_for("main")
            return [self.results[index] for index in sorted(indices) if 0 <= index < len(self.results)]
        if self.tab == 1:
            indices = self.selected_indices_for("main")
            return [self.player.queue[index] for index in sorted(indices) if 0 <= index < len(self.player.queue)]
        if self.tab == 2:
            return [self.suggestions[index] for index in sorted(self.selected_indices_for("main")) if 0 <= index < len(self.suggestions)]
        return [self.history_results[index] for index in sorted(self.selected_indices_for("main")) if 0 <= index < len(self.history_results)]

    def current_playlist(self) -> Playlist | None:
        if self.active_playlist_id is None:
            return None
        return next((item for item in self.store.all() if item.id == self.active_playlist_id), None)

    def visible_playlist_tracks(self, playlist: Playlist) -> list[tuple[int, Track]]:
        # Find mode highlights a match without filtering the playlist list.
        return list(enumerate(playlist.tracks))

    def playlist_track(self) -> tuple[Playlist, int, Track] | None:
        playlist = self.current_playlist()
        if playlist is None:
            return None
        visible = self.visible_playlist_tracks(playlist)
        if not visible or not 0 <= self.playlist_track_index < len(visible):
            return None
        index, track = visible[self.playlist_track_index]
        return playlist, index, track

    def selected_playlist_tracks(self) -> list[tuple[Playlist, int, Track]]:
        playlist = self.current_playlist()
        if playlist is None:
            return []
        visible = self.visible_playlist_tracks(playlist)
        indices = self.selected_indices_for("playlists")
        return [
            (playlist, original_index, track)
            for visible_index, (original_index, track) in enumerate(visible)
            if visible_index in indices
        ]

    def search_query_for(self, focus_name: str) -> str:
        if focus_name == "playlists":
            return getattr(self, "playlist_search", "")
        if focus_name == "main" and self.tab == 1:
            return getattr(self, "queue_search", "")
        return ""

    def draw_track_list(self, items: list[Track], selected: int, top: int, height: int, left: int, width: int, focus_name: str = "main", empty_message: str = "Nothing here yet.") -> None:
        if not items:
            self.screen.addnstr(top, left + 1, empty_message, max(1, width - 2), curses.A_DIM)
            return
        start = max(0, min(selected - height + 1, len(items) - height))
        for line, index in enumerate(range(start, min(len(items), start + height))):
            item = items[index]
            selected_indices = self.selected_indices_for(focus_name)
            marker = "*" if index in selected_indices else "›" if index == selected else " "
            downloaded = " [d]" if self.store.is_downloaded(item) else ""
            text = f"{marker} {index + 1:2}. {item.label}{downloaded}  [{format_time(item.duration)}]"
            is_focused = index == selected and self.focus == focus_name
            attr = curses.A_REVERSE if is_focused else curses.A_DIM if index in selected_indices else curses.A_NORMAL
            clipped = self.clipped(text, width - 2)
            self.screen.addnstr(top + line, left + 1, clipped, max(1, width - 2), attr)
            query = self.search_query_for(focus_name).lower().strip()
            match_start = clipped.lower().find(query) if query else -1
            while match_start >= 0:
                self.screen.addnstr(
                    top + line,
                    left + 1 + match_start,
                    clipped[match_start:match_start + len(query)],
                    len(query),
                    getattr(self, "search_attr", curses.A_BOLD) | (curses.A_REVERSE if is_focused else 0),
                )
                next_offset = match_start + max(1, len(query))
                match_start = clipped.lower().find(query, next_offset)

    def selection_context(self, focus_name: str | None = None) -> str:
        if focus_name == "playlists":
            return "playlist"
        if focus_name == "main":
            return ("results" if self.tab == 0 else "queue" if self.tab == 1 else "suggestions" if self.tab == 2 else "history")
        if self.active_playlist_id is not None:
            return "playlist"
        return "results" if self.tab == 0 else "queue" if self.tab == 1 else "suggestions" if self.tab == 2 else "history"

    def selected_indices_for(self, focus_name: str = "main") -> set[int]:
        context = self.selection_context(focus_name)
        if not self.visual_mode or not self.visual_anchor or self.visual_anchor[0] != context:
            if context == "playlist":
                return {self.playlist_track_index}
            return {self.result_index if context in ("results", "suggestions") else self.history_index if context == "history" else self.queue_index}
        start = self.visual_anchor[1]
        end = self.playlist_track_index if context == "playlist" else self.result_index if context in ("results", "suggestions") else self.history_index if context == "history" else self.queue_index
        return set(range(min(start, end), max(start, end) + 1))

    def clear_visual(self) -> None:
        self.visual_mode = False
        self.visual_anchor = None

    def toggle_visual(self, context: str) -> None:
        if self.visual_mode:
            self.clear_visual()
            self.player.message = "Selection mode off"
            return
        index = self.playlist_track_index if context == "playlist" else self.result_index if context in ("results", "suggestions") else self.history_index if context == "history" else self.queue_index
        self.visual_mode = True
        self.visual_anchor = (context, index)
        self.player.message = "Selection mode on: move with j/k, operate on selected tracks"

    def draw_main(self, width: int) -> None:
        self.refresh_history_views()
        height, _ = self.screen.getmaxyx()
        current = self.player.current
        position, paused = self.player.mpv.state() if current else (0, False)
        title = current.title if current else "Nothing playing"
        if current and self.store.is_downloaded(current):
            title += " [d]"
        mode = "ERROR" if current and self.player.playback_failed else "PAUSED" if paused else "PLAYING" if current else "IDLE"
        loop = " LOOP" if self.player.loop else " PLOOP" if self.player.playlist_loop else ""
        self.screen.addnstr(0, 1, f" OPENTUNE  ·  {mode}{loop}", max(1, width - 2), curses.A_BOLD)
        self.screen.hline(1, 0, curses.ACS_HLINE, width)
        self.screen.addnstr(2, 2, self.clipped(title, width - 4), max(1, width - 4), curses.A_BOLD)
        duration = current.duration if current else 0
        self.screen.addnstr(3, 2, f"{format_time(position)} / {format_time(duration)}", max(1, width - 4), curses.A_DIM)
        self.screen.hline(5, 0, curses.ACS_HLINE, width)
        tabs = "[ Results ]" if self.tab == 0 else "  Results  "
        tabs += "     " + ("[ Queue ]" if self.tab == 1 else "  Queue  ")
        tabs += "     " + ("[ Suggestions ]" if self.tab == 2 else "  Suggestions  ")
        tabs += "     " + ("[ History ]" if self.tab == 3 else "  History  ")
        self.screen.addnstr(6, 2, tabs, max(1, width - 4), curses.A_BOLD)
        list_height = max(1, height - 10)
        if self.showing_help:
            self.draw_help(8, width, list_height)
        elif self.tab == 0:
            self.draw_track_list(self.results, self.result_index, 8, list_height, 0, width)
        elif self.tab == 1:
            self.draw_track_list(self.player.queue, self.queue_index, 8, list_height, 0, width)
        elif self.tab == 2:
            self.result_index = min(self.result_index, max(0, len(self.suggestions) - 1))
            self.draw_track_list(
                self.suggestions,
                self.result_index,
                8,
                list_height,
                0,
                width,
                empty_message="Play songs to build history-based suggestions.",
            )
        else:
            self.history_results = self.history_store.tracks() if hasattr(self, "history_store") else getattr(self, "history_results", [])
            self.history_index = min(self.history_index, max(0, len(self.history_results) - 1))
            self.draw_track_list(
                self.history_results,
                self.history_index,
                8,
                list_height,
                0,
                width,
                empty_message="No listening history yet.",
            )
        self.screen.hline(height - 2, 0, curses.ACS_HLINE, width)
        self.screen.addnstr(height - 1, 2, self.clipped(self.player.message, width - 4), max(1, width - 4), curses.A_DIM)

    def draw_help(self, top: int, width: int, height: int) -> None:
        lines = [
            "MAIN WINDOW",
            "j/k move · g/G top/bottom · Ctrl-b/f half-page",
            "[/] previous/next search result · Enter play",
            "v select · Enter play · Space pause anywhere",
            "H/L seek · Ctrl-o loop · Tab/Shift-Tab cycle tabs · / search",
            "a append · d download · D delete queue · c clear · u undo · Ctrl-r redo",
            "f find Queue song · n/N next/previous match · s shuffle Queue",
            "Ctrl-d current download · x/y/z cut/copy/paste playlists",
            "P toggle playlists · Ctrl-h/l or Ctrl-arrows focus",
            "q quit",
            "",
            "PLAYLISTS WINDOW",
            "j/k move · g/G top/bottom · Ctrl-b/f half-page",
            "l enter · h leave · Enter play · Esc cancel visual",
            "a create (list) / append selected (open) · v select",
            "p pin/unpin playlist (list only) · D delete song or playlist",
            "D always asks for confirmation; Downloads cannot be deleted",
            "f find song · n/N next/previous match · o playlist loop",
            "Esc twice quickly clears Queue/playlist find · Ctrl-o loop",
        ]
        for index, line in enumerate(lines[:height]):
            attr = curses.A_BOLD if index in (0, 7) else curses.A_NORMAL
            self.screen.addnstr(top + index, 1, self.clipped(line, width - 2), max(1, width - 2), attr)

    def draw_playlists(self, left: int, width: int) -> None:
        height, _ = self.screen.getmaxyx()
        self.screen.vline(0, left, curses.ACS_VLINE, height)
        playlist = self.current_playlist()
        heading = "PLAYLISTS" if playlist is None else f"PLAYLIST: {playlist.name}"
        focus_attr = curses.A_BOLD if self.focus == "playlists" else curses.A_DIM
        self.screen.addnstr(0, left + 2, self.clipped(heading, width - 3), max(1, width - 3), focus_attr)
        self.screen.hline(1, left + 1, curses.ACS_HLINE, max(1, width - 1))
        if playlist is None:
            items = self.store.all()
            user_number = 0
            for line, item in enumerate(items[: max(1, height - 5)]):
                marker = "›" if line == self.playlist_index else " "
                pin = "★ " if item.pinned else "  "
                attr = curses.A_REVERSE if line == self.playlist_index and self.focus == "playlists" else curses.A_NORMAL
                if item.id == "downloads":
                    label = f"{pin}{item.name}"
                else:
                    user_number += 1
                    label = f"{user_number}. {pin}{item.name}"
                text = f"{marker} {label} ({len(item.tracks)})"
                self.screen.addnstr(3 + line, left + 2, self.clipped(text, width - 3), max(1, width - 3), attr)
            footer = "a new · p pin · D delete · l enter"
        else:
            visible = self.visible_playlist_tracks(playlist)
            tracks = [track for _, track in visible]
            self.draw_track_list(tracks, self.playlist_track_index, 3, max(1, height - 7), left + 1, width - 1, "playlists")
            footer = f"{len(visible)} songs · a append" + (f" · find: {self.playlist_search}" if self.playlist_search else "")
        self.screen.addnstr(height - 2, left + 2, self.clipped(footer, width - 3), max(1, width - 3), curses.A_DIM)

    def draw(self) -> None:
        self.screen.erase()
        height, width = self.screen.getmaxyx()
        main_width = self.main_width(width)
        self.draw_main(main_width)
        if self.panel_open:
            self.draw_playlists(main_width, width - main_width)
        self.screen.refresh()

    def toggle_panel(self) -> None:
        self.panel_open = not self.panel_open
        self.focus = "playlists" if self.panel_open else "main"

    def move_main(self, delta: int) -> None:
        if self.tab == 0:
            if self.results:
                self.result_index = (self.result_index + delta) % len(self.results)
        elif self.tab == 1:
            if self.player.queue:
                self.queue_index = (self.queue_index + delta) % len(self.player.queue)
        elif self.tab == 2 and getattr(self, "suggestions", []):
            self.result_index = (self.result_index + delta) % len(self.suggestions)
        elif self.tab == 3 and getattr(self, "history_results", []):
            self.history_index = (self.history_index + delta) % len(self.history_results)

    def move_search_result(self, delta: int) -> None:
        """Move only within the current search result list."""
        if self.tab != 0:
            self.player.message = "Switch to the Results tab first"
            return
        if not self.results:
            self.player.message = "No search results"
            return
        self.result_index = (self.result_index + delta) % len(self.results)
        self.player.message = f"Search result {self.result_index + 1}/{len(self.results)}"

    def half_page(self) -> int:
        height, _ = self.screen.getmaxyx()
        return max(1, (height - 10) // 2)

    def move_to_edge_main(self, bottom: bool = False) -> None:
        if self.tab == 0:
            self.result_index = max(0, len(self.results) - 1) if bottom else 0
        elif self.tab == 1:
            self.queue_index = max(0, len(self.player.queue) - 1) if bottom else 0
        elif self.tab == 2:
            self.result_index = max(0, len(getattr(self, "suggestions", [])) - 1) if bottom else 0
        else:
            self.history_index = max(0, len(getattr(self, "history_results", [])) - 1) if bottom else 0

    def move_to_edge_playlists(self, bottom: bool = False) -> None:
        if self.active_playlist_id is None:
            self.playlist_index = max(0, len(self.store.all()) - 1) if bottom else 0
        else:
            count = len(self.visible_playlist_tracks(self.current_playlist()))
            self.playlist_track_index = max(0, count - 1) if bottom else 0

    def cycle_focus(self, direction: int) -> None:
        """Cycle between the main and playlist panes, wrapping at each edge."""
        if not self.panel_open:
            return
        panes = ("main", "playlists")
        current = panes.index(self.focus) if self.focus in panes else 0
        self.focus = panes[(current + direction) % len(panes)]

    def move_playlists(self, delta: int) -> None:
        if self.active_playlist_id is None:
            playlists = self.store.all()
            if playlists:
                self.playlist_index = (self.playlist_index + delta) % len(playlists)
        else:
            playlist = self.current_playlist()
            count = len(self.visible_playlist_tracks(playlist)) if playlist else 0
            if count:
                self.playlist_track_index = (self.playlist_track_index + delta) % count

    def enter_playlist(self) -> None:
        if self.active_playlist_id is not None:
            return
        playlist = self.store.get(self.playlist_index)
        if playlist:
            self.active_playlist_id = playlist.id
            self.playlist_track_index = 0
            self.playlist_search = ""
            self.clear_visual()

    def leave_playlist(self) -> None:
        if self.active_playlist_id is None:
            return
        self.active_playlist_id = None
        self.playlist_search = ""
        self.clear_visual()

    def play_playlist_track(self) -> None:
        if self.active_playlist_id is None:
            return
        selected = self.playlist_track()
        if selected is None:
            return
        playlist, _, track = selected
        self.player.set_playlist_loop(playlist.tracks, self.player.playlist_loop)
        self.player.replace_queue(playlist.tracks, track)
        self.queue_index = 0
        self.player.start(track, build_mix=False)
        self.player.message = f"Playing from {playlist.name}: {track.title}"

    def create_playlist(self) -> None:
        name = self.prompt_line("New playlist name")
        if name is None:
            self.player.message = "Playlist creation cancelled"
            return
        playlist = self.store.create(name)
        self.playlist_index = len(self.store.all()) - 1
        self.player.message = f"Created playlist {playlist.name}"

    def rename_playlist(self) -> None:
        playlist = self.current_playlist() if self.active_playlist_id else self.store.get(self.playlist_index)
        if playlist is None or playlist.pinned:
            self.player.message = "Downloads cannot be renamed"
            return
        name = self.prompt_line("Rename playlist")
        if name is not None and self.store.rename(playlist, name):
            self.player.message = f"Renamed playlist to {name}"

    def toggle_pin_playlist(self) -> None:
        if self.active_playlist_id is not None:
            return
        playlist = self.store.get(self.playlist_index)
        if playlist is None:
            return
        pinned = self.store.toggle_pin(playlist)
        if pinned is None:
            self.player.message = "Downloads is always pinned"
            return
        self.playlist_index = self.store.all().index(playlist)
        self.player.message = f"{'Pinned' if pinned else 'Unpinned'} playlist: {playlist.name}"

    def delete_playlist(self) -> None:
        if self.active_playlist_id is not None:
            return
        playlist = self.store.get(self.playlist_index)
        if playlist is None:
            return
        if playlist.id == "downloads":
            self.player.message = "Downloads playlist cannot be deleted"
            return
        if not self.prompt_confirm(f"Do you want to delete playlist '{playlist.name}'?"):
            self.player.message = "Deletion cancelled"
            return
        name = playlist.name
        if self.store.delete_playlist(playlist):
            self.playlist_index = max(0, min(self.playlist_index, len(self.store.all()) - 1))
            self.player.message = f"Deleted playlist: {name}"

    def find_playlist(self) -> None:
        if self.active_playlist_id is None:
            return
        query = self.prompt_line("Find in playlist")
        if query is None:
            self.player.message = "Playlist search cancelled"
            return
        playlist = self.current_playlist()
        if playlist is None:
            return
        self.playlist_search = query
        if not query.strip():
            self.player.message = "Playlist find cleared"
            return
        needle = query.lower().strip()
        matches = [
            index for index, track in enumerate(playlist.tracks)
            if needle in track.title.lower() or needle in track.uploader.lower()
        ]
        if not matches:
            self.player.message = f"No playlist songs matching “{query}”"
            return
        current = self.playlist_track_index
        self.playlist_track_index = next(
            (index for index in matches if index >= current), matches[0]
        )
        position = matches.index(self.playlist_track_index) + 1
        self.player.message = f"Highlighted: {playlist.tracks[self.playlist_track_index].title} [{position}/{len(matches)}]"

    def find_queue(self) -> None:
        if not self.player.queue:
            self.player.message = "Queue is empty"
            return
        query = self.prompt_line("Find in queue")
        if query is None:
            self.player.message = "Queue find cancelled"
            return
        needle = query.lower().strip()
        self.queue_search = query
        if not needle:
            self.player.message = "Queue find cleared"
            return
        matches = [
            index for index, track in enumerate(self.player.queue)
            if needle in track.title.lower() or needle in track.uploader.lower()
        ]
        if not matches:
            self.player.message = f"No queue songs matching “{query}”"
            return
        self.queue_index = next(
            (index for index in matches if index >= self.queue_index), matches[0]
        )
        position = matches.index(self.queue_index) + 1
        self.player.message = f"Highlighted: {self.player.queue[self.queue_index].title} [{position}/{len(matches)}]"

    @staticmethod
    def _cycle_match(matches: list[int], current: int, direction: int) -> int:
        if direction > 0:
            return next((index for index in matches if index > current), matches[0])
        return next((index for index in reversed(matches) if index < current), matches[-1])

    def next_queue_match(self, direction: int = 1) -> None:
        query = getattr(self, "queue_search", "")
        needle = query.lower().strip()
        if not needle:
            self.player.message = "Use f to find a song in the Queue first"
            return
        matches = [
            index for index, track in enumerate(self.player.queue)
            if needle in track.title.lower() or needle in track.uploader.lower()
        ]
        if not matches:
            self.player.message = f"No queue songs matching “{query}”"
            return
        self.queue_index = self._cycle_match(matches, self.queue_index, direction)
        position = matches.index(self.queue_index) + 1
        self.player.message = f"Highlighted: {self.player.queue[self.queue_index].title} [{position}/{len(matches)}]"

    def next_playlist_match(self, direction: int = 1) -> None:
        playlist = self.current_playlist()
        query = getattr(self, "playlist_search", "")
        needle = query.lower().strip()
        if playlist is None or not needle:
            self.player.message = "Use f to find a song in the playlist first"
            return
        matches = [
            index for index, track in enumerate(playlist.tracks)
            if needle in track.title.lower() or needle in track.uploader.lower()
        ]
        if not matches:
            self.player.message = f"No playlist songs matching “{query}”"
            return
        self.playlist_track_index = self._cycle_match(matches, self.playlist_track_index, direction)
        position = matches.index(self.playlist_track_index) + 1
        self.player.message = f"Highlighted: {playlist.tracks[self.playlist_track_index].title} [{position}/{len(matches)}]"

    def delete_playlist_track(self) -> None:
        selected = self.selected_playlist_tracks()
        if not selected:
            return
        playlist = selected[0][0]
        count = len(selected)
        prompt = f"Do you want to delete {count} selected song(s)?" if count > 1 else f"Do you want to delete '{selected[0][2].title}'?"
        if not self.prompt_confirm(prompt):
            self.player.message = "Deletion cancelled"
            return
        for _, index, _ in sorted(selected, key=lambda item: item[1], reverse=True):
            self.store.remove_track(playlist, index)
        self.playlist_track_index = max(0, min(self.playlist_track_index, len(self.visible_playlist_tracks(playlist)) - 1))
        self.clear_visual()
        self.player.message = f"Permanently removed {count} song(s)"

    def copy_playlist_tracks(self, cut: bool = False) -> None:
        """Copy or cut the current visual/ highlighted playlist selection."""
        selected = self.selected_playlist_tracks()
        if not selected:
            self.player.message = "Open a playlist and select a song first"
            return
        playlist = selected[0][0]
        self.clipboard_tracks = [track for _, _, track in selected]
        self.clipboard_mode = "cut" if cut else "copy"
        self.clipboard_source_id = playlist.id
        if cut:
            for _, index, _ in sorted(selected, key=lambda item: item[1], reverse=True):
                self.store.remove_track(playlist, index)
            self.playlist_track_index = max(0, min(self.playlist_track_index, len(playlist.tracks) - 1))
            self.clear_visual()
            self.player.message = f"Cut {len(self.clipboard_tracks)} song(s); open another playlist and press z to paste"
        else:
            self.player.message = f"Copied {len(self.clipboard_tracks)} song(s); open another playlist and press z to paste"

    def paste_playlist_tracks(self) -> None:
        playlist = self.current_playlist()
        tracks = getattr(self, "clipboard_tracks", [])
        if playlist is None:
            self.player.message = "Open a destination playlist first"
            return
        if not tracks:
            self.player.message = "Clipboard is empty"
            return
        added = sum(self.store.add_track(playlist, track) for track in tracks)
        self.player.message = f"Pasted {added} song(s) into {playlist.name}"
        if self.clipboard_mode == "cut":
            self.clipboard_tracks = []
            self.clipboard_mode = ""
            self.clipboard_source_id = None

    def download_track(self, track: Track) -> None:
        downloads = self.store.get(0)
        if downloads is None:
            return
        if track.local_path and Path(track.local_path).exists():
            self.player.message = f"Already downloaded: {track.title}"
            return
        self.player.message = f"Downloading: {track.title}"

        def worker() -> None:
            try:
                local_track = Downloader.download(track, self.store.download_dir)
                if self.store.add_download(local_track):
                    self.player.message = f"Downloaded: {track.title}"
                else:
                    self.player.message = "Download finished but the local file was not registered"
            except RuntimeError as error:
                self.player.message = str(error)

        threading.Thread(target=worker, daemon=True).start()

    def download_current(self) -> None:
        track = self.player.current
        if track is None:
            self.player.message = "Nothing is currently playing"
            return
        self.download_track(track)

    def download_playlist_track(self) -> None:
        selected = self.playlist_track()
        if selected is None:
            self.player.message = "Open a playlist and select a song first"
            return
        _, _, track = selected
        self.download_track(self.store.resolve_track(track))

    def enqueue_playlist_track(self) -> None:
        selected = self.selected_playlist_tracks()
        if not selected:
            self.player.message = "Select a song in the open playlist first"
            return
        added = sum(self.player.enqueue(track) for _, _, track in selected)
        self.clear_visual()
        self.player.message = f"Added {added} song(s) to Queue"

    def toggle_playlist_loop(self) -> None:
        playlist = self.current_playlist()
        if playlist is None:
            self.player.message = "Open a playlist to toggle playlist looping"
            return
        self.player.set_playlist_loop(playlist.tracks, not self.player.playlist_loop)

    def delete_queue_selected(self) -> None:
        selected = sorted(self.selected_indices_for("main"))
        if not selected:
            return
        count = len(selected)
        prompt = f"Delete {count} selected queue song(s)?"
        if not self.prompt_confirm(prompt):
            self.player.message = "Deletion cancelled"
            return
        self.player.remove_queue_indices(selected)
        self.queue_index = max(0, min(self.queue_index, len(self.player.queue) - 1))
        self.clear_visual()

    def handle_main(self, key: int) -> None:
        if key == ord("q"):
            self.running = False
        elif key == ord("g"):
            self.move_to_edge_main()
        elif key == ord("G"):
            self.move_to_edge_main(bottom=True)
        elif key == 2:  # Ctrl-b
            self.move_main(-self.half_page())
        elif key == 6:  # Ctrl-f
            self.move_main(self.half_page())
        elif key in (ord("j"), curses.KEY_DOWN):
            self.move_main(1)
        elif key in (ord("k"), curses.KEY_UP):
            self.move_main(-1)
        elif key in (10, 13, curses.KEY_ENTER):
            if self.tab == 0 and self.results:
                self.player.start(self.results[self.result_index])
            elif self.tab == 1 and self.player.queue:
                track = self.player.take_queue_at(self.queue_index)
                if track:
                    self.queue_index = max(0, min(self.queue_index, len(self.player.queue) - 1))
                    self.player.start(track, build_mix=False)
            elif self.tab == 2 and getattr(self, "suggestions", []):
                self.player.start(self.suggestions[self.result_index])
            elif self.tab == 3 and getattr(self, "history_results", []):
                self.player.start(self.history_results[self.history_index])
        elif key == ord(" "):
            self.player.mpv.toggle_pause()
        elif key == ord("h"):
            self.player.previous()
        elif key == ord("l"):
            self.player.next()
        elif key == ord("H"):
            self.player.mpv.seek(-10)
        elif key == ord("L"):
            self.player.mpv.seek(10)
        elif key == 15:
            self.player.toggle_loop()
        elif key == 9:
            self.tab = (self.tab + 1) % 4
            self.clear_visual()
        elif key == ord("/"):
            self.prompt_search()
        elif key == ord("a"):
            tracks = self.focused_main_tracks()
            added = sum(self.player.enqueue(track) for track in tracks)
            self.clear_visual()
            self.player.message = f"Added {added} song(s) to Queue"
        elif key == ord("d"):
            track = self.focused_main_track()
            if track:
                self.download_track(track)
            else:
                self.player.message = "No highlighted song to download"
        elif key == ord("D") and self.tab == 1:
            self.delete_queue_selected()
        elif key == ord("c"):
            if self.player.queue and self.prompt_confirm("Clear the entire queue?"):
                self.player.clear_queue()
                self.queue_index = 0
            elif self.player.queue:
                self.player.message = "Deletion cancelled"
        elif key == ord("u"):
            self.player.undo_queue_action()
        elif key == 18:
            self.player.redo_queue_action()
        elif key == ord("p"):
            self.prompt_playlist_number()
        elif key == ord("v"):
            self.toggle_visual("results" if self.tab == 0 else "queue" if self.tab == 1 else "suggestions" if self.tab == 2 else "history")
        elif key == 4:
            self.download_current()

    def handle_playlists(self, key: int) -> None:
        if key in (ord("q"),):
            self.running = False
        elif key == ord("g"):
            self.move_to_edge_playlists()
        elif key == ord("G"):
            self.move_to_edge_playlists(bottom=True)
        elif key == 2:  # Ctrl-b
            self.move_playlists(-self.half_page())
        elif key == 6:  # Ctrl-f
            self.move_playlists(self.half_page())
        elif key in (ord("j"), curses.KEY_DOWN):
            self.move_playlists(1)
        elif key in (ord("k"), curses.KEY_UP):
            self.move_playlists(-1)
        elif key == curses.KEY_LEFT and self.active_playlist_id is not None:
            self.leave_playlist()
        elif key == curses.KEY_RIGHT and self.active_playlist_id is None:
            self.enter_playlist()
        elif key in (10, 13, curses.KEY_ENTER) and self.active_playlist_id is not None:
            self.play_playlist_track()
        elif key == ord("l") and self.active_playlist_id is None:
            self.enter_playlist()
        elif key == ord("h") and self.active_playlist_id is not None:
            self.leave_playlist()
        elif key == ord("a"):
            if self.active_playlist_id is None:
                self.create_playlist()
            else:
                self.enqueue_playlist_track()
        elif key == ord("v") and self.active_playlist_id is not None:
            self.toggle_visual("playlist")
        elif key == ord("x") and self.active_playlist_id is not None:
            self.copy_playlist_tracks(cut=True)
        elif key == ord("y") and self.active_playlist_id is not None:
            self.copy_playlist_tracks(cut=False)
        elif key == ord("z") and self.active_playlist_id is not None:
            self.paste_playlist_tracks()
        elif key == ord("o") and self.active_playlist_id is not None:
            self.toggle_playlist_loop()
        elif key == ord("r"):
            self.rename_playlist()
        elif key == ord("p"):
            if self.active_playlist_id is None:
                self.toggle_pin_playlist()
            else:
                self.prompt_playlist_number()
        elif key == ord("D"):
            if self.active_playlist_id is not None:
                self.delete_playlist_track()
            else:
                self.delete_playlist()
        elif key == ord("d") and self.active_playlist_id is not None:
            self.download_playlist_track()
        elif key == 4:
            if getattr(self.player, "current", None) is not None:
                self.download_current()
            else:
                self.download_playlist_track()
        elif key == ord("?"):
            self.showing_help = True

    def handle(self, key: int) -> None:
        if self.showing_help:
            if key in (27, ord("?")):
                self.showing_help = False
                return
            self.showing_help = False
        if key != 27:
            self._last_escape_at = 0.0
        if key == 27 and self.visual_mode:
            self.clear_visual()
            self.player.message = "Visual selection cancelled"
            return
        if key == 27:
            if self.active_playlist_id is not None and self.playlist_search:
                now = time.monotonic()
                if now - getattr(self, "_last_escape_at", 0.0) <= 0.8:
                    self.playlist_search = ""
                    self.playlist_track_index = 0
                    self._last_escape_at = 0.0
                    self.player.message = "Playlist find cleared"
                else:
                    self._last_escape_at = now
                    self.player.message = "Press Esc again to clear playlist find"
            elif self.active_playlist_id is None and self.tab == 1 and getattr(self, "queue_search", ""):
                now = time.monotonic()
                if now - getattr(self, "_last_escape_at", 0.0) <= 0.8:
                    self.queue_search = ""
                    self._last_escape_at = 0.0
                    self.player.message = "Queue find cleared"
                else:
                    self._last_escape_at = now
                    self.player.message = "Press Esc again to clear Queue find"
            return
        if key == ord("["):
            self.move_search_result(-1)
            return
        if key == ord("]"):
            self.move_search_result(1)
            return
        if key == ord(" "):
            self.player.mpv.toggle_pause()
            return
        if key == 15:
            self.player.toggle_loop()
            return
        if key in (ord("H"), getattr(curses, "KEY_SLEFT", -999)):
            self.player.mpv.seek(-10)
            return
        if key in (ord("L"), getattr(curses, "KEY_SRIGHT", -999)):
            self.player.mpv.seek(10)
            return
        if key == ord("/"):
            self.prompt_search()
            return
        if is_backtab(key):
            self.tab = (self.tab - 1) % 4
            self.clear_visual()
            return
        if key == 9:
            self.tab = (self.tab + 1) % 4
            self.clear_visual()
            return
        if key == ord("s") and self.tab == 1:
            self.player.shuffle_queue()
            self.queue_index = 0
            self.clear_visual()
            return
        if key == ord("f"):
            if self.focus == "playlists" and self.panel_open:
                self.find_playlist()
            elif self.tab == 1:
                self.find_queue()
            return
        if key in (ord("n"), ord("N")):
            direction = 1 if key == ord("n") else -1
            if self.focus == "playlists" and self.panel_open and self.active_playlist_id is not None:
                self.next_playlist_match(direction)
            elif self.tab == 1:
                self.next_queue_match(direction)
            return
        if key in (8, getattr(curses, "KEY_CLEFT", -999)):
            self.cycle_focus(-1)
            return
        if key in (12, getattr(curses, "KEY_CRIGHT", -999)):
            self.cycle_focus(1)
            return
        if key == ord("P"):
            self.toggle_panel()
            return
        if key == ord("?"):
            self.showing_help = not self.showing_help
            return
        if self.focus == "playlists" and self.panel_open:
            self.handle_playlists(key)
        else:
            self.handle_main(key)

    def show_update_notice_if_needed(self) -> None:
        state = NoticeState()
        if state.last_seen_version() == __version__:
            return
        height, width = self.screen.getmaxyx()
        box_height = min(height - 2, len(UPDATE_NOTICE_LINES) + 4)
        box_width = min(width - 4, max(46, max(len(line) for line in UPDATE_NOTICE_LINES) + 6))
        if box_height < 4 or box_width < 10:
            state.mark_seen()
            return
        top = max(0, (height - box_height) // 2)
        left = max(0, (width - box_width) // 2)
        try:
            modal = curses.newwin(box_height, box_width, top, left)
            modal.keypad(True)
            modal.nodelay(False)
            modal.box()
            for index, line in enumerate(UPDATE_NOTICE_LINES):
                if index + 2 >= box_height - 1:
                    break
                attr = curses.A_BOLD if index == 0 else curses.A_NORMAL
                modal.addnstr(index + 1, 2, self.clipped(line, box_width - 4), box_width - 4, attr)
            modal.refresh()
            while modal.getch() != 27:
                pass
        except curses.error:
            pass
        state.mark_seen()

    def run(self) -> None:
        self.show_update_notice_if_needed()
        while self.running:
            self.draw()
            key = self.screen.getch()
            if key != -1:
                self.handle(key)
            time.sleep(0.08)


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="opentune",
        description="A Vim-keyed terminal music player for YouTube audio streams.",
        epilog=HELP_TEXT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("query", nargs="*", help="Search query to open on launch")
    args = parser.parse_args()
    missing = require_tools()
    if missing:
        print(f"opentune: {missing}", file=sys.stderr)
        return 1
    player = Player()
    store = PlaylistStore()
    try:
        curses.wrapper(lambda screen: PlaylistTUI(screen, player, store, " ".join(args.query)).run())
    except curses.error as error:
        print(f"opentune: terminal UI error: {error}", file=sys.stderr)
        return 1
    finally:
        player.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
