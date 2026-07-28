import unittest
from unittest.mock import patch

from opentune.__main__ import Track, YouTube, format_time


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
