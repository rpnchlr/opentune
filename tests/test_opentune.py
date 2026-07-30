import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from opentune.__main__ import MPV, PlaylistStore, Track, YouTube, format_time


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
            store.add_track(downloads, track)
            store.remove_track(downloads, 0)
            self.assertFalse(local_file.exists())
