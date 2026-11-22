# Known issues and platform notes

## Termux MPV linker error — deferred

Some Termux installations report an MPV startup error similar to:

```text
CANNOT LINK EXECUTABLE "mpv": cannot locate symbol "_ZNSt6__ndk127__from_chars_floating_point..."
```

This is an Android/MPV native-library compatibility problem. It is explicitly
deferred for v1.1.0: OpenTune does not replace MPV binaries, patch Android
libraries, or change the playback dependency to hide it. The existing playback
error is reported and the rest of the application remains usable.

## Touchscreen input

Termux can expose taps through terminal mouse reporting when the terminal
emulator forwards them. OpenTune handles those events on a best-effort basis.
The terminal protocol cannot guarantee that every Android gesture reaches the
application, so keyboard input remains supported and documented.

## Windows playback dependencies

Windows requires `mpv`, `yt-dlp`, and `ffmpeg` on `PATH`. `install.ps1` uses
`winget` where available and installs the `windows-curses` Python extra. If an
organisation manages binaries centrally, use `-SkipDependencies` after the
commands are available.
