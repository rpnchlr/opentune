from __future__ import annotations

import argparse
import curses
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SEARCH_LIMIT = 12
MIX_LIMIT = 10


@dataclass(frozen=True)
class Track:
    title: str
    url: str
    duration: int = 0
    uploader: str = ""

    @property
    def label(self) -> str:
        return f"{self.title} — {self.uploader}" if self.uploader else self.title


def format_time(seconds: float | int | None) -> str:
    total = max(0, int(seconds or 0))
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def require_tools() -> str | None:
    absent = [name for name in ("mpv", "yt-dlp") if not shutil.which(name)]
    return f"Missing required command(s): {', '.join(absent)}" if absent else None


class YouTube:
    """Small, deliberately dependency-free yt-dlp adapter."""

    @staticmethod
    def search(query: str, limit: int = SEARCH_LIMIT) -> list[Track]:
        if not query.strip():
            return []
        command = ["yt-dlp", "--flat-playlist", "--dump-single-json", f"ytsearch{limit}:{query}"]
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=25, check=True)
            payload = json.loads(completed.stdout)
        except (subprocess.SubprocessError, json.JSONDecodeError) as error:
            raise RuntimeError(f"Search failed: {error}") from error
        tracks: list[Track] = []
        for entry in payload.get("entries") or []:
            video_id = entry.get("id")
            if not video_id:
                continue
            tracks.append(Track(
                title=entry.get("title") or "Untitled",
                url=entry.get("webpage_url") or f"https://www.youtube.com/watch?v={video_id}",
                duration=int(entry.get("duration") or 0),
                uploader=entry.get("uploader") or entry.get("channel") or "",
            ))
        return tracks

    @classmethod
    def mix_for(cls, track: Track) -> list[Track]:
        # This intentionally stays a search-derived mix: predictable, quick, and works
        # without scraping private YouTube recommendation endpoints.
        seed = f"{track.uploader} {track.title}".strip()
        candidates = cls.search(seed, MIX_LIMIT + 4)
        return [candidate for candidate in candidates if candidate.url != track.url][:MIX_LIMIT]


class MPV:
    """Controls one headless mpv instance over its JSON IPC socket."""

    def __init__(self, on_finished: callable) -> None:
        self._on_finished = on_finished
        self._directory = tempfile.TemporaryDirectory(prefix="opentune-")
        self.socket_path = str(Path(self._directory.name) / "mpv.sock")
        self.process: subprocess.Popen[str] | None = None
        self._intentional_stop = False
        self._lock = threading.Lock()

    def play(self, track: Track, loop: bool = False) -> None:
        self.stop()
        self._intentional_stop = False
        command = [
            "mpv", "--no-video", "--force-window=no", "--really-quiet",
            f"--input-ipc-server={self.socket_path}", "--ytdl-format=bestaudio/best", track.url,
        ]
        if loop:
            command.insert(-1, "--loop-file=inf")
        self.process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        threading.Thread(target=self._watch, args=(self.process,), daemon=True).start()

    def _watch(self, process: subprocess.Popen[str]) -> None:
        process.wait()
        if not self._intentional_stop and process is self.process:
            self._on_finished()

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

    def close(self) -> None:
        self.stop()
        self._directory.cleanup()


class Player:
    def __init__(self) -> None:
        self.current: Track | None = None
        self.queue: list[Track] = []
        self.history: list[Track] = []
        self.loop = False
        self.message = "Ready. Press / to search."
        self._lock = threading.Lock()
        self.mpv = MPV(self._finished)

    def start(self, track: Track, *, build_mix: bool = True, remember_current: bool = True) -> None:
        with self._lock:
            if remember_current and self.current and self.current.url != track.url:
                self.history.append(self.current)
            self.current = track
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
                    self.queue.extend(item for item in mix if item.url not in existing)
                    self.message = f"Mix ready: {len(self.queue)} tracks queued"
        except RuntimeError:
            pass

    def next(self) -> None:
        with self._lock:
            if not self.queue:
                self.message = "Queue is empty"
                return
            next_track = self.queue.pop(0)
        self.start(next_track, build_mix=False)

    def previous(self) -> None:
        with self._lock:
            if not self.history:
                self.message = "No previous track"
                return
            previous_track = self.history.pop()
            if self.current:
                self.queue.insert(0, self.current)
        self.start(previous_track, build_mix=False, remember_current=False)

    def _finished(self) -> None:
        if not self.loop:
            self.next()

    def toggle_loop(self) -> None:
        self.loop = not self.loop
        self.mpv.set_loop(self.loop)
        self.message = f"Loop {'on' if self.loop else 'off'}"

    def close(self) -> None:
        self.mpv.close()


class TUI:
    def __init__(self, screen: curses.window, player: Player, initial_query: str = "") -> None:
        self.screen, self.player = screen, player
        self.results: list[Track] = []
        self.result_index = 0
        self.queue_index = 0
        self.tab = 0  # 0 results, 1 queue
        self.running = True
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
        self.screen.move(height - 1, 0)
        self.screen.clrtoeol()
        self.screen.addstr(height - 1, 0, "Search: ")
        try:
            query = self.screen.getstr(height - 1, 8).decode().strip()
        except KeyboardInterrupt:
            query = ""
        curses.curs_set(0)
        self.screen.nodelay(True)
        if query:
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
        mode = "PAUSED" if paused else "PLAYING" if current else "IDLE"
        loop = " LOOP" if self.player.loop else ""
        self.screen.addnstr(0, 1, f" OPENTUNE  ·  {mode}{loop}", width - 2, curses.A_BOLD)
        self.screen.hline(1, 0, curses.ACS_HLINE, width)
        self.screen.addnstr(2, 2, self.clipped(title, width - 4), width - 4, curses.A_BOLD)
        self.screen.addnstr(3, 2, f"{format_time(position)} / {format_time(duration)}", width - 4, curses.A_DIM)
        self.screen.hline(5, 0, curses.ACS_HLINE, width)
        tabs = "[ Results ]" if self.tab == 0 else "  Results  "
        tabs += "     " + ("[ Queue ]" if self.tab == 1 else "  Queue  ")
        self.screen.addnstr(6, 2, tabs, width - 4, curses.A_BOLD)
        list_height = max(1, height - 10)
        if self.tab == 0:
            self.draw_track_list(self.results, self.result_index, 8, list_height, width)
        else:
            self.draw_track_list(self.player.queue, self.queue_index, 8, list_height, width)
        self.screen.hline(height - 2, 0, curses.ACS_HLINE, width)
        status = self.clipped(self.player.message, width - 4)
        self.screen.addnstr(height - 1, 2, status, width - 4, curses.A_DIM)
        self.screen.refresh()

    def move(self, delta: int) -> None:
        if self.tab == 0:
            self.result_index = max(0, min(len(self.results) - 1, self.result_index + delta))
        else:
            self.queue_index = max(0, min(len(self.player.queue) - 1, self.queue_index + delta))

    def select(self) -> None:
        if self.tab == 0 and self.results:
            self.player.start(self.results[self.result_index])
        elif self.tab == 1 and self.player.queue:
            with self.player._lock:
                track = self.player.queue.pop(self.queue_index)
            self.queue_index = max(0, min(self.queue_index, len(self.player.queue) - 1))
            self.player.start(track, build_mix=False)

    def handle(self, key: int) -> None:
        if key in (ord("q"), 27):
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
        elif key == 12:  # Ctrl-l
            self.player.toggle_loop()
        elif key == ord("/"):
            self.prompt_search()

    def run(self) -> None:
        while self.running:
            self.draw()
            key = self.screen.getch()
            if key != -1:
                self.handle(key)
            time.sleep(0.08)


def main() -> int:
    parser = argparse.ArgumentParser(description="A terminal YouTube music player")
    parser.add_argument("query", nargs="*", help="Search query to open on launch")
    args = parser.parse_args()
    missing = require_tools()
    if missing:
        print(f"opentune: {missing}", file=sys.stderr)
        return 1
    player = Player()
    try:
        curses.wrapper(lambda screen: TUI(screen, player, " ".join(args.query)).run())
    except curses.error as error:
        print(f"opentune: terminal UI error: {error}", file=sys.stderr)
        return 1
    finally:
        player.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
