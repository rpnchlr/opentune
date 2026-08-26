import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opentune.__main__ import Downloader, MPV, PlaylistStore, PlaylistTUI, Track, YouTube, format_time


class OpenTuneTests(unittest.TestCase):
    def test_format_time(self):
        self.assertEqual(format_time(0), "0:00")
        self.assertEqual(format_time(65), "1:05")
        self.assertEqual(format_time(3661), "1:01:01")


    def test_track_label(self):
        self.assertEqual(Track("Song", "https://example.test", uploader="Artist").label, "Song — Artist")
        self.assertEqual(Track("Song", "https://example.test").label, "Song")

    def test_mix_uses_youtube_radio_and_removes_duplicate_song_uploads(self):
        seed = Track("Artist - Seed Song (Official Video)", "https://www.youtube.com/watch?v=seed", uploader="Artist")
        payload = [
            seed,
            Track("Artist - Seed Song (Official Audio)", "https://www.youtube.com/watch?v=duplicate", uploader="Artist"),
            Track("Different Song", "https://www.youtube.com/watch?v=one", uploader="Another Artist"),
            Track("Different Song (Official Video)", "https://www.youtube.com/watch?v=two", uploader="Another Artist"),
            Track("Third Song", "https://www.youtube.com/watch?v=three", uploader="Third Artist"),
        ]
        with patch.object(YouTube, "_fetch", return_value=payload) as fetch:
            mix = YouTube.mix_for(seed)
        self.assertEqual([track.title for track in mix], ["Different Song", "Third Song"])
        self.assertEqual(fetch.call_args.args[0], "https://www.youtube.com/watch?v=seed&list=RDseed")

    def test_music_filter_rejects_non_music_results(self):
        self.assertTrue(YouTube._looks_like_music({"title": "Artist - Song (Official Audio)", "duration": 210}))
        self.assertFalse(YouTube._looks_like_music({"title": "Artist interview", "duration": 210}))
        self.assertFalse(YouTube._looks_like_music({"title": "Artist song", "duration": 12}))
        self.assertFalse(YouTube._looks_like_music({"title": "Artist song", "categories": ["Gaming"]}))

    def test_queue_operations(self):
        from opentune.__main__ import Player

        player = Player()
        player.mpv.play = lambda track, loop=False: None
        first = Track("First Song", "https://www.youtube.com/watch?v=first")
        second = Track("Second Song", "https://www.youtube.com/watch?v=second")
        self.assertTrue(player.enqueue(first))
        self.assertFalse(player.enqueue(first))
        self.assertTrue(player.enqueue(second))
        self.assertEqual(player.remove_queue_at(0), first)
        self.assertEqual(player.clear_queue(), 1)
        self.assertEqual(player.queue, [])
        player.close()

    def test_queue_delete_and_clear_undo_redo(self):
        from opentune.__main__ import Player

        player = Player()
        player.mpv.play = lambda track, loop=False: None
        first = Track("First Song", "https://www.youtube.com/watch?v=first")
        second = Track("Second Song", "https://www.youtube.com/watch?v=second")
        third = Track("Third Song", "https://www.youtube.com/watch?v=third")
        for track in (first, second, third):
            player.enqueue(track)

        player.remove_queue_at(1)
        self.assertEqual(player.queue, [first, third])
        self.assertTrue(player.undo_queue_action())
        self.assertEqual(player.queue, [first, second, third])
        self.assertTrue(player.redo_queue_action())
        self.assertEqual(player.queue, [first, third])

        player.clear_queue()
        self.assertEqual(player.queue, [])
        self.assertTrue(player.undo_queue_action())
        self.assertEqual(player.queue, [first, third])
        self.assertTrue(player.redo_queue_action())
        self.assertEqual(player.queue, [])
        player.close()

    def test_bulk_queue_delete_has_one_undo_action(self):
        from opentune.__main__ import Player

        player = Player()
        player.mpv.play = lambda track, loop=False: None
        tracks = [Track(f"Song {index}", f"https://www.youtube.com/watch?v={index}") for index in range(4)]
        for track in tracks:
            player.enqueue(track)
        self.assertEqual(player.remove_queue_indices([1, 3]), 2)
        self.assertEqual(player.queue, [tracks[0], tracks[2]])
        self.assertTrue(player.undo_queue_action())
        self.assertEqual(player.queue, tracks)
        self.assertTrue(player.redo_queue_action())
        self.assertEqual(player.queue, [tracks[0], tracks[2]])
        player.close()

    def test_playlist_loop_repopulates_queue_after_last_track(self):
        from opentune.__main__ import Player

        player = Player()
        played = []
        player.mpv.play = lambda track, loop=False: played.append(track)
        first = Track("First", "https://www.youtube.com/watch?v=first")
        second = Track("Second", "https://www.youtube.com/watch?v=second")
        player.set_playlist_loop([first, second], True)
        player.current = first
        player.queue = [second]
        player._finished()
        self.assertEqual(player.current, second)
        player._finished()
        self.assertEqual(player.current, first)
        self.assertEqual(played, [second, first])
        player.close()

    def test_finished_track_starts_next_queue_item_immediately(self):
        from opentune.__main__ import Player

        player = Player()
        played = []
        player.mpv.play = lambda track, loop=False: played.append(track)
        first = Track("First", "https://www.youtube.com/watch?v=first")
        second = Track("Second", "https://www.youtube.com/watch?v=second")
        player.current = first
        player.queue = [second]
        player._finished()
        self.assertIs(player.current, second)
        self.assertEqual(played, [second])
        self.assertFalse(player.playback_failed)
        player.close()

    def test_failed_mpv_does_not_advance_queue(self):
        class FakeProcess:
            returncode = 1
            stderr = io.StringIO("network error")

            def wait(self):
                return self.returncode

        mpv = MPV.__new__(MPV)
        errors = []
        finished = []
        mpv._intentional_stop = False
        mpv.process = process = FakeProcess()
        mpv._on_finished = lambda: finished.append(True)
        mpv._on_error = lambda message: errors.append(message)
        mpv._watch(process)
        self.assertEqual(finished, [])
        self.assertEqual(errors, ["network error"])

    def test_normal_mpv_exit_dispatches_finished_callback(self):
        class FakeProcess:
            returncode = 0
            stderr = io.StringIO("")

            def wait(self):
                return self.returncode

        mpv = MPV.__new__(MPV)
        finished = []
        mpv._intentional_stop = False
        mpv.process = process = FakeProcess()
        mpv._on_finished = lambda: finished.append(True)
        mpv._on_error = lambda message: None
        mpv._watch(process)
        self.assertEqual(finished, [True])
        self.assertIsNone(mpv.process)

    def test_playlists_persist_and_default_names_are_numbered(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Playlists"
            store = PlaylistStore(root)
            self.assertEqual(store.get(0).name, "Downloads")
            first = store.create()
            second = store.create()
            track = Track("Saved Song", "https://www.youtube.com/watch?v=saved", uploader="Artist")
            self.assertTrue(store.add_track(second, track))
            reloaded = PlaylistStore(root)
            self.assertEqual([item.name for item in reloaded.all()], ["Downloads", "My Playlist #1", "My Playlist #2"])
            self.assertEqual(reloaded.get(2).tracks[0], track)

    def test_download_playlist_removal_deletes_local_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Playlists"
            store = PlaylistStore(root)
            local_file = Path(directory) / "song.mp3"
            local_file.write_bytes(b"audio")
            track = Track("Downloaded", "https://www.youtube.com/watch?v=downloaded", local_path=str(local_file))
            downloads = store.get(0)
            self.assertTrue(store.add_download(track))
            store.remove_track(downloads, 0)
            self.assertFalse(local_file.exists())

    def test_downloads_reject_metadata_only_tracks_and_user_indexes_skip_downloads(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Playlists"
            store = PlaylistStore(root)
            first = store.create("First")
            second = store.create("Second")
            metadata_only = Track("Not downloaded", "https://www.youtube.com/watch?v=not-local")
            self.assertFalse(store.add_track(store.get(0), metadata_only))
            self.assertIsNone(store.get_user(-1))
            self.assertIs(store.get_user(0), first)
            self.assertIs(store.get_user(1), second)
            self.assertIsNone(store.get_user(2))

    def test_downloaded_track_resolves_to_local_path_for_offline_playback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Playlists"
            local_file = Path(directory) / "saved.mp3"
            local_file.write_bytes(b"audio")
            store = PlaylistStore(root)
            downloaded = Track("Saved", "https://www.youtube.com/watch?v=saved", local_path=str(local_file))
            self.assertTrue(store.add_download(downloaded))
            metadata = Track("Saved", downloaded.url)
            resolved = store.resolve_track(metadata)
            self.assertEqual(resolved.local_path, str(local_file))
            self.assertTrue(store.is_downloaded(metadata))

    def test_playlist_pinning_and_deletion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "Playlists"
            store = PlaylistStore(root)
            first = store.create("First")
            second = store.create("Second")
            self.assertEqual([item.name for item in store.all()], ["Downloads", "First", "Second"])

            self.assertTrue(store.toggle_pin(second))
            self.assertEqual([item.name for item in store.all()], ["Downloads", "Second", "First"])
            reloaded = PlaylistStore(root)
            self.assertEqual([item.name for item in reloaded.all()], ["Downloads", "Second", "First"])
            self.assertTrue(reloaded.get(1).pinned)

            removable = reloaded.get(1)
            playlist_file = root / f"{removable.id}.json"
            self.assertTrue(playlist_file.exists())
            self.assertTrue(reloaded.delete_playlist(removable))
            self.assertFalse(playlist_file.exists())
            self.assertEqual([item.name for item in reloaded.all()], ["Downloads", "First"])

    def test_contextual_keybinds_do_not_conflict(self):
        class StubPlayer:
            def __init__(self):
                self.loop_toggles = 0
                self.pause_toggles = 0

                class MPVStub:
                    def __init__(self, owner):
                        self.owner = owner

                    def toggle_pause(self):
                        self.owner.pause_toggles += 1

                self.mpv = MPVStub(self)

            def toggle_loop(self):
                self.loop_toggles += 1

        with tempfile.TemporaryDirectory() as directory:
            tui = PlaylistTUI.__new__(PlaylistTUI)
            tui.running = True
            tui.panel_open = False
            tui.tab = 0
            tui.store = PlaylistStore(Path(directory) / "Playlists")
            tui.playlist_index = 0
            tui.active_playlist_id = None
            tui.playlist_track_index = 0
            tui.playlist_search = ""
            tui.player = StubPlayer()
            tui.showing_help = False
            tui.focus = "main"

            tui.handle_main(27)  # Esc is not a quit key outside a prompt.
            self.assertTrue(tui.running)
            tui.handle_main(ord("q"))
            self.assertFalse(tui.running)

            tui.running = True
            tui.handle_main(15)  # Ctrl-o toggles track looping.
            self.assertEqual(tui.player.loop_toggles, 1)
            tui.panel_open = True
            tui.handle_main(15)
            self.assertEqual(tui.player.loop_toggles, 2)
            tui.handle_playlists(ord("l"))
            self.assertEqual(tui.active_playlist_id, "downloads")
            tui.handle_playlists(ord("h"))
            self.assertIsNone(tui.active_playlist_id)

            tui.focus = "playlists"
            tui.handle(15)
            self.assertEqual(tui.player.loop_toggles, 3)
            tui.handle(ord(" "))
            self.assertEqual(tui.player.pause_toggles, 1)

    def test_ctrl_d_downloads_focused_open_playlist_song(self):
        class StubPlayer:
            message = ""

        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target

            def start(self):
                self.target()

        with tempfile.TemporaryDirectory() as directory:
            store = PlaylistStore(Path(directory) / "Playlists")
            playlist = store.create("Saved songs")
            track = Track("Saved Song", "https://www.youtube.com/watch?v=saved")
            store.add_track(playlist, track)
            downloaded = Track(
                track.title,
                track.url,
                local_path=str(Path(directory) / "saved.mp3"),
            )
            Path(downloaded.local_path).write_bytes(b"audio")
            tui = PlaylistTUI.__new__(PlaylistTUI)
            tui.store = store
            tui.player = StubPlayer()
            tui.active_playlist_id = playlist.id
            tui.playlist_track_index = 0
            tui.playlist_search = ""

            with patch.object(Downloader, "download", return_value=downloaded), \
                    patch("opentune.__main__.threading.Thread", ImmediateThread):
                tui.handle_playlists(4)  # Ctrl-d

            self.assertEqual(store.get(0).tracks, [downloaded])

    def test_a_appends_focused_open_playlist_song_to_queue(self):
        class StubPlayer:
            def __init__(self):
                self.queue = []
                self.message = ""

            def enqueue(self, track):
                self.queue.append(track)
                return True

        with tempfile.TemporaryDirectory() as directory:
            store = PlaylistStore(Path(directory) / "Playlists")
            playlist = store.create("Saved songs")
            track = Track("Saved Song", "https://www.youtube.com/watch?v=saved")
            store.add_track(playlist, track)
            tui = PlaylistTUI.__new__(PlaylistTUI)
            tui.store = store
            tui.player = StubPlayer()
            tui.active_playlist_id = playlist.id
            tui.playlist_track_index = 0
            tui.playlist_search = ""
            tui.visual_mode = False
            tui.visual_anchor = None

            tui.handle_playlists(ord("a"))

            self.assertEqual(tui.player.queue, [track])

    def test_visual_selection_collects_contiguous_tracks(self):
        class StubPlayer:
            def __init__(self):
                self.queue = []
                self.message = ""

            def enqueue(self, track):
                self.queue.append(track)
                return True

        tui = PlaylistTUI.__new__(PlaylistTUI)
        tui.player = StubPlayer()
        tui.results = [Track(f"Song {index}", f"https://example.test/{index}") for index in range(4)]
        tui.result_index = 1
        tui.queue_index = 0
        tui.tab = 0
        tui.visual_mode = False
        tui.visual_anchor = None
        tui.toggle_visual("results")
        tui.result_index = 3
        self.assertEqual(tui.focused_main_tracks(), tui.results[1:4])

    def test_escape_cancels_visual_selection(self):
        class StubPlayer:
            message = ""

            class MPVStub:
                def toggle_pause(self):
                    pass

            mpv = MPVStub()

        tui = PlaylistTUI.__new__(PlaylistTUI)
        tui.player = StubPlayer()
        tui.running = True
        tui.panel_open = False
        tui.showing_help = False
        tui.focus = "main"
        tui.visual_mode = True
        tui.visual_anchor = ("results", 1)
        tui.handle(27)
        self.assertFalse(tui.visual_mode)
        self.assertIsNone(tui.visual_anchor)
        self.assertEqual(tui.player.message, "Visual selection cancelled")

    def test_queue_shuffle_changes_queue_only(self):
        from opentune.__main__ import Player

        with tempfile.TemporaryDirectory() as directory:
            store = PlaylistStore(Path(directory) / "Playlists")
            playlist = store.create("Mix")
            tracks = [Track(f"Song {index}", f"https://www.youtube.com/watch?v={index}") for index in range(3)]
            for track in tracks:
                store.add_track(playlist, track)
            player = Player()
            player.mpv.play = lambda track, loop=False: None
            player.queue = list(tracks)
            tui = PlaylistTUI.__new__(PlaylistTUI)
            tui.store = store
            tui.player = player
            tui.active_playlist_id = None
            tui.visual_mode = False
            tui.visual_anchor = None
            tui.queue_index = 0
            with patch("opentune.__main__.random.shuffle", side_effect=lambda values: values.reverse()):
                player.shuffle_queue()
            self.assertEqual([track.url for track in playlist.tracks], [track.url for track in tracks])
            self.assertEqual([track.url for track in player.queue], [track.url for track in reversed(tracks)])
            player.close()

    def test_list_edge_and_half_page_navigation(self):
        class ScreenStub:
            def getmaxyx(self):
                return (30, 100)

        class PlayerStub:
            queue = [Track(str(index), str(index)) for index in range(20)]

        tui = PlaylistTUI.__new__(PlaylistTUI)
        tui.screen = ScreenStub()
        tui.player = PlayerStub()
        tui.tab = 1
        tui.queue_index = 0
        tui.results = []
        tui.move_to_edge_main(bottom=True)
        self.assertEqual(tui.queue_index, 19)
        tui.move_main(-1)
        self.assertEqual(tui.queue_index, 18)
        tui.move_main(-18)
        self.assertEqual(tui.queue_index, 0)
        tui.move_main(-tui.half_page())
        self.assertEqual(tui.queue_index, 10)

    def test_search_worker_updates_results_without_blocking_ui(self):
        class ImmediateThread:
            def __init__(self, target, daemon=False):
                self.target = target

            def start(self):
                self.target()

        class StubPlayer:
            message = ""

        tui = PlaylistTUI.__new__(PlaylistTUI)
        tui.player = StubPlayer()
        tui.results = []
        tui.result_index = 0
        tui.tab = 1
        tui.searching = False
        tui._search_generation = 0
        tui.draw = lambda: None
        with patch.object(YouTube, "search", return_value=[Track("Found", "url")]), \
                patch("opentune.__main__.threading.Thread", ImmediateThread):
            tui.search("found")
        self.assertFalse(tui.searching)
        self.assertEqual(tui.results[0].title, "Found")
        self.assertEqual(tui.tab, 0)

    def test_playlist_p_adds_selected_song_to_another_playlist(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlaylistStore(Path(directory) / "Playlists")
            source = store.create("Source")
            target = store.create("Target")
            track = Track("Saved", "https://example.test/saved")
            store.add_track(source, track)
            tui = PlaylistTUI.__new__(PlaylistTUI)
            tui.store = store
            tui.player = type("PlayerStub", (), {"message": ""})()
            tui.active_playlist_id = source.id
            tui.playlist_track_index = 0
            tui.playlist_search = ""
            tui.visual_mode = False
            tui.visual_anchor = None
            tui.focus = "playlists"
            tui.prompt_line = lambda label: "2"
            tui.prompt_playlist_number()
            self.assertEqual(target.tracks, [track])

            current = Track("Currently playing", "https://example.test/current")
            tui.player.current = current
            tui.prompt_line = lambda label: "c2"
            tui.prompt_playlist_number()
            self.assertEqual(target.tracks, [track, current])

    def test_global_controls_work_while_playlist_pane_is_focused(self):
        class MPVStub:
            def __init__(self):
                self.seeks = []
                self.pauses = 0

            def seek(self, seconds):
                self.seeks.append(seconds)

            def toggle_pause(self):
                self.pauses += 1

        class PlayerStub:
            def __init__(self):
                self.mpv = MPVStub()
                self.loop_toggles = 0

            def toggle_loop(self):
                self.loop_toggles += 1

        tui = PlaylistTUI.__new__(PlaylistTUI)
        tui.player = PlayerStub()
        tui.panel_open = True
        tui.focus = "playlists"
        tui.tab = 0
        tui.showing_help = False
        tui.visual_mode = False
        tui.visual_anchor = None
        tui.handle(ord("H"))
        tui.handle(ord("L"))
        tui.handle(ord(" "))
        tui.handle(15)
        tui.handle(9)
        tui.handle(8)
        self.assertEqual(tui.focus, "main")
        tui.handle(12)
        self.assertEqual(tui.player.mpv.seeks, [-10, 10])
        self.assertEqual(tui.player.mpv.pauses, 1)
        self.assertEqual(tui.player.loop_toggles, 1)
        self.assertEqual(tui.tab, 1)
        self.assertEqual(tui.focus, "playlists")

    def test_help_closes_and_executes_the_pressed_command(self):
        class MPVStub:
            def toggle_pause(self):
                pass

        class PlayerStub:
            def __init__(self):
                self.mpv = MPVStub()
                self.queue = [Track("one", "one"), Track("two", "two")]
                self.message = ""

            def shuffle_queue(self):
                self.queue.reverse()

        tui = PlaylistTUI.__new__(PlaylistTUI)
        tui.player = PlayerStub()
        tui.panel_open = False
        tui.focus = "main"
        tui.tab = 1
        tui.queue_index = 0
        tui.visual_mode = False
        tui.visual_anchor = None
        tui.showing_help = True
        tui.handle(ord("s"))
        self.assertFalse(tui.showing_help)
        self.assertEqual([track.title for track in tui.player.queue], ["two", "one"])

    def test_find_highlights_queue_and_playlist_without_filtering(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PlaylistStore(Path(directory) / "Playlists")
            playlist = store.create("Favorites")
            tracks = [
                Track("Alpha", "alpha", uploader="Artist"),
                Track("Beta", "beta", uploader="Band"),
            ]
            for track in tracks:
                store.add_track(playlist, track)
            player = type("PlayerStub", (), {"message": "", "queue": list(tracks)})()
            tui = PlaylistTUI.__new__(PlaylistTUI)
            tui.store = store
            tui.player = player
            tui.active_playlist_id = playlist.id
            tui.playlist_track_index = 0
            tui.playlist_search = ""
            tui.prompt_line = lambda label: "beta"
            tui.find_playlist()
            self.assertEqual(tui.playlist_track_index, 1)
            self.assertEqual(len(tui.visible_playlist_tracks(playlist)), 2)

            tui.tab = 1
            tui.queue_index = 0
            tui.active_playlist_id = None
            tui.prompt_line = lambda label: "alpha"
            tui.find_queue()
            self.assertEqual(tui.queue_index, 0)

    def test_double_escape_clears_playlist_find_query(self):
        class PlayerStub:
            message = ""

        tui = PlaylistTUI.__new__(PlaylistTUI)
        tui.player = PlayerStub()
        tui.active_playlist_id = "playlist"
        tui.playlist_search = "beta"
        tui.playlist_track_index = 1
        tui.visual_mode = False
        tui.showing_help = False
        tui._last_escape_at = 0.0
        with patch("opentune.__main__.time.monotonic", side_effect=[10.0, 10.4]):
            tui.handle(27)
            self.assertEqual(tui.playlist_search, "beta")
            tui.handle(27)
        self.assertEqual(tui.playlist_search, "")
        self.assertEqual(tui.playlist_track_index, 0)
