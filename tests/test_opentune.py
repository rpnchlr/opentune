import unittest

from opentune.__main__ import Track, format_time


class OpenTuneTests(unittest.TestCase):
    def test_format_time(self):
        self.assertEqual(format_time(0), "0:00")
        self.assertEqual(format_time(65), "1:05")
        self.assertEqual(format_time(3661), "1:01:01")


    def test_track_label(self):
        self.assertEqual(Track("Song", "https://example.test", uploader="Artist").label, "Song — Artist")
        self.assertEqual(Track("Song", "https://example.test").label, "Song")
