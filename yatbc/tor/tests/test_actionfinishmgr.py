from django.test import TestCase, override_settings
from ..models import (
    Torrent,
    TorrentFile,
    TorrentType,
    AriaDownloadStatus,
    TorrentTorBoxSearchResult,
    TorrentTorBoxSearch,
)
from ..actiononfinishmgr import (
    ActionMgr,
    ActionFactory,
    ActionNothing,
    ActionCopy,
    ActionMove,
    normalize_movie_series_file_name,
    get_metadata_by_file,
    get_metadata_by_search,
    clean_title,
    find_existing_dir,
    find_season_dir,
)
from ..statusmgr import StatusMgr
from unittest.mock import patch, Mock
import shutil
from pathlib import Path
import logging
from .temp_settings import console_logging_config
from .utils import (
    create_torrent,
    create_torrent_file,
    create_work_dir,
    create_file,
    create_search,
)
from django.utils import timezone
from constance import config


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class ActionMgrTests(TestCase):
    def setUp(self):
        logging.config.dictConfig(console_logging_config)
        config.ORGANIZE_MOVIE_SERIES = True
        config.ORGANIZE_MOVIES = True
        self.status_mgr = StatusMgr.get_instance()
        self.no_type = TorrentType.objects.get_no_type()
        self.other = TorrentType.objects.get_other()
        self.other.action_on_finish = TorrentType.ACTION_COPY
        self.other.save()
        self.audio = TorrentType.objects.get_audiobooks()
        self.audio.action_on_finish = TorrentType.ACTION_MOVE
        self.audio.save()
        self.movie_series = TorrentType.objects.get_movie_series()
        self.movie_series.action_on_finish = TorrentType.ACTION_MOVE
        self.movie_series.target_dir = "target"
        self.movie_series.save()

        self.movies = TorrentType.objects.get_movies()
        self.movies.action_on_finish = TorrentType.ACTION_MOVE
        self.movies.target_dir = "target"
        self.movies.save()
        self.home = TorrentType.objects.get_home_video()
        self.home.action_on_finish = TorrentType.ACTION_MOVE
        self.home.target_dir = "target"
        self.home.save()

    @patch(target="tor.actiononfinishmgr.get_stash_api")
    def test_rescan_stash_on_home_video_setting(self, mock_get_stash: Mock):
        stash_api = Mock()
        mock_get_stash.return_value = stash_api
        stash_api.rescan_stash.return_value = True
        config.RESCAN_STASH_ON_HOME_VIDEO = True
        file, temp_file, work_dir = self._prepare_test(self.home)
        expected_name = file.torrent.name
        target = create_work_dir(self.home.target_dir)

        mgr = ActionMgr()
        mgr.run(file.torrent)

        stash_api.rescan_stash.assert_called_once_with(expected_name)

        # shutil.rmtree(work_dir)
        shutil.rmtree(target)

    def _prepare_test(
        self,
        torrent_type: TorrentType,
        file_name="test.txt",
        old_torrent=None,
        work_dir=None,
    ):
        temp_file, work_dir = create_file(file_name, work_dir=work_dir)
        aria_id = "aaaa"
        aria = AriaDownloadStatus.objects.create(
            path=temp_file.as_posix(),
            progress=1,
            done=True,
            error="",
            status="complete",
            internal_id=aria_id,
        )
        if old_torrent is None:
            torrent = create_torrent(torrent_type)
        else:
            torrent = old_torrent
        file = create_torrent_file(torrent, aria=aria, name=temp_file.name)
        return file, temp_file, work_dir

    def test_find_season_dir(self):
        work = create_work_dir()
        season_dir = create_work_dir(work / "Season 01")
        self.assertEqual(find_season_dir(work, 1), season_dir)
        self.assertIsNone(find_season_dir(work, 2))
        shutil.rmtree(work)

    def test_find_existing(self):
        target_dir = create_work_dir("media")
        work = create_work_dir(target_dir / "test movie series [imdbid-tt000]")
        work2 = create_work_dir(target_dir / "some other [imdbid-tt001]")
        same_name_different_id = create_work_dir(
            target_dir / "same name [imdbid-tt003]"
        )
        same_name_different_id_2 = create_work_dir(
            target_dir / "same name 2 [imdbid-tt004]"
        )
        season_dir = create_work_dir(work / "Season 01")
        season_dir_second = Path(work2 / "season 02")
        self.assertEqual(
            find_existing_dir(
                target_dir, "Wrong title", "Test", 1, None, imdbid="tt000"
            ),
            season_dir,
        )
        self.assertEqual(
            find_existing_dir(
                target_dir, "Wrong title", "Test", 2, None, imdbid="tt001"
            ),
            season_dir_second,
        )

        self.assertEqual(
            find_existing_dir(target_dir, "same name", "Test", imdbid="tt003"),
            same_name_different_id,
        )
        self.assertEqual(
            find_existing_dir(target_dir, "same name 2", "Test", imdbid="tt004"),
            same_name_different_id_2,
        )
        self.assertEqual(
            find_existing_dir(target_dir, "Test Movie Series", "Test", 1), season_dir
        )
        self.assertIsNone(find_existing_dir(target_dir, "Unknown", "Test", 1))
        self.assertIsNone(find_existing_dir(target_dir, "Test Movie Ser", "Test"))
        self.assertIsNone(find_existing_dir(target_dir, "other some", "Test"))
        shutil.rmtree(target_dir)

    def test_clean_title(self):
        title_with_junk = "Magic. Series/ "
        expected = "Magic Series"
        result = clean_title(title_with_junk)
        self.assertEqual(expected, result)

    def test_normalize_movie_series_file_name(self):
        expected = "Magic Series S01E02.mp4"
        result = normalize_movie_series_file_name(
            "Magic. Series/ S01E2.mp4", "Magic Series", 1, 2
        )
        self.assertEqual(expected, result)

    def test_get_metadata_by_file(self):
        title, season, episode = get_metadata_by_file(
            file_name="Magic. Series S1E2.mp4"
        )
        self.assertEqual("Magic Series", title)
        self.assertEqual(1, season)
        self.assertEqual(2, episode)

        title, season, episode = get_metadata_by_file(file_name="Magic. Series.mp4")
        self.assertEqual("Magic Series", title)
        self.assertIsNone(season)
        self.assertIsNone(episode)

        title, season, episode = get_metadata_by_file(file_name="Magic Series s04.mp4")
        self.assertEqual("Magic Series s04", title)
        self.assertIsNone(season)  # no episode, so probably something other then s/e
        self.assertIsNone(episode)

        title, season, episode = get_metadata_by_file(
            file_name="TestMovie.S01.Ble.720p/TestMovie.S01E02.Local.720p.mkv"
        )
        self.assertEqual("TestMovie", title)
        self.assertEqual(1, season)
        self.assertEqual(2, episode)

        title, season, episode = get_metadata_by_file(
            file_name="Test Series Season 2 [2160p x265 10bit S123 Extra]/Test Series S02E03 [2160p x2].mp4"
        )
        self.assertEqual("Test Series", title)
        self.assertEqual(2, season)
        self.assertEqual(3, episode)

        title, season, episode = get_metadata_by_file(
            file_name="Wrong Folder Season.3 Completed Extra Text/Ok Movie Series Season 03 Episode 04.mp4"
        )
        self.assertEqual("Ok Movie Series", title)
        self.assertEqual(3, season)
        self.assertEqual(4, episode)

        title, season, episode = get_metadata_by_file(  # this is not a movie/series
            file_name="Wrong Folder Season.1 Completed Extra Text/Ok Movie Series Season 01 Episode 01 Some More Extra Text/Some extra.txt"
        )
        self.assertEqual("Some extra", title)
        self.assertIsNone(season)
        self.assertIsNone(episode)

    def test_get_metadata_by_search(self):
        title, season, episode, imdbid = get_metadata_by_search(None)
        self.assertIsNone(title)
        self.assertIsNone(season)
        self.assertIsNone(episode)
        self.assertIsNone(imdbid)

        search = create_search(
            query="tt0000/s1/E2", title="Magic test", season=None, episode=None
        )
        title, season, episode, imdbid = get_metadata_by_search(search)
        self.assertEqual(title, "Magic test")
        self.assertEqual(season, 1)
        self.assertEqual(episode, 2)
        self.assertEqual(imdbid, "tt0000")

        search = create_search(query="tt1", title="Magic test", season=2, episode="3")
        title, season, episode, imdbid = get_metadata_by_search(search)
        self.assertEqual(title, "Magic test")
        self.assertEqual(season, 2)
        self.assertEqual(episode, 3)
        self.assertEqual(imdbid, "tt1")

    def test_action_factory_nothing(self):
        file, temp_file, work_dir = self._prepare_test(self.no_type)
        factory = ActionFactory()
        action = factory.create_action(
            torrent=file.torrent, torrent_dir="", files=[file]
        )
        self.assertTrue(isinstance(action, ActionNothing))
        shutil.rmtree(work_dir)

    def test_action_factory_copy(self):
        file, temp_file, work_dir = self._prepare_test(self.other)
        factory = ActionFactory()
        action = factory.create_action(
            torrent=file.torrent, torrent_dir="", files=[file]
        )
        self.assertTrue(isinstance(action, ActionCopy))
        shutil.rmtree(work_dir)

    def test_action_factory_move(self):
        file, temp_file, work_dir = self._prepare_test(self.audio)
        factory = ActionFactory()
        action = factory.create_action(
            torrent=file.torrent, torrent_dir="", files=[file]
        )
        self.assertTrue(isinstance(action, ActionMove))
        shutil.rmtree(work_dir)

    def test_move_series_new_dir(self):
        file, temp_file, work_dir = self._prepare_test(
            self.movie_series, file_name="test.mp4"
        )
        search = create_search("tt001", "Test Movie Series", 1, 1, file.torrent)
        mgr = ActionMgr()
        target = create_work_dir(self.movie_series.target_dir)
        self.assertTrue(temp_file.exists())
        self.assertFalse(file.action_on_finish_done)

        mgr.run(file.torrent)

        expected_file = Path(
            target
            / "Test Movie Series [imdbid-tt001]"
            / "season 01"
            / "Test Movie Series S01E01.mp4"
        )
        self.assertTrue(expected_file.exists())
        self.assertFalse(temp_file.exists())
        shutil.rmtree(target)

    def test_move_series_new_dir_multiple_files(self):
        file, temp_file, work_dir = self._prepare_test(
            self.movie_series, file_name="test S01E01.mp4"
        )
        file2, temp_file2, _ = self._prepare_test(
            self.movie_series,
            file_name="test S01E02.mp4",
            old_torrent=file.torrent,
            work_dir=work_dir,
        )
        file3, temp_file3, _ = self._prepare_test(
            self.movie_series,
            file_name="Extra.txt",
            old_torrent=file.torrent,
            work_dir=work_dir,
        )

        search = create_search("tt001", "Test Movie Series", None, None, file.torrent)
        mgr = ActionMgr()
        target = create_work_dir(self.movie_series.target_dir)
        self.assertTrue(temp_file.exists())
        self.assertFalse(file.action_on_finish_done)

        mgr.run(file.torrent)

        expected_file = Path(
            target
            / "Test Movie Series [imdbid-tt001]"
            / "season 01"
            / "Test Movie Series S01E01.mp4"
        )
        expected_file2 = Path(
            target
            / "Test Movie Series [imdbid-tt001]"
            / "season 01"
            / "Test Movie Series S01E02.mp4"
        )
        expected_file3 = Path(
            target / "Test Movie Series [imdbid-tt001]" / "season 01" / "Extra.txt"
        )
        self.assertTrue(expected_file.exists())
        self.assertTrue(expected_file2.exists())
        self.assertTrue(expected_file3.exists())
        self.assertFalse(temp_file.exists())
        self.assertFalse(temp_file2.exists())
        self.assertFalse(temp_file3.exists())
        shutil.rmtree(target)

    def test_move_series_old_dir(self):
        file, temp_file, work_dir = self._prepare_test(
            self.movie_series, file_name="test.mp4"
        )
        search = create_search("tt001", "Test Movie Series", 2, 1, file.torrent)
        mgr = ActionMgr()
        target = create_work_dir(self.movie_series.target_dir)
        movie_series_dir = create_work_dir(target / "Test Movie Series [imdbid-tt001]")
        season = create_work_dir(movie_series_dir / "season 02")
        self.assertTrue(temp_file.exists())
        self.assertFalse(file.action_on_finish_done)

        mgr.run(file.torrent)

        expected_file = Path(season / "Test Movie Series S02E01.mp4")
        self.assertFalse(temp_file.exists())
        self.assertTrue(expected_file.exists())
        shutil.rmtree(target)

    def test_move_series_old_dir_no_search(self):
        file, temp_file, work_dir = self._prepare_test(
            self.movie_series, file_name="Test Movie Series S03E02 Some Junk.mp4"
        )
        mgr = ActionMgr()
        target = create_work_dir(self.movie_series.target_dir)
        movie_series_dir = create_work_dir(target / "Test Movie Series [imdbid-tt002]")
        season = create_work_dir(movie_series_dir / "season 03")
        self.assertTrue(temp_file.exists())
        self.assertFalse(file.action_on_finish_done)

        mgr.run(file.torrent)

        expected_file = Path(season / "Test Movie Series S03E02.mp4")
        self.assertFalse(temp_file.exists())
        self.assertTrue(expected_file.exists())
        shutil.rmtree(target)

    def test_ok_nothing(self):
        file, temp_file, work_dir = self._prepare_test(self.no_type)
        mgr = ActionMgr()
        target = create_work_dir("./target/")
        self.assertTrue(temp_file.exists())
        self.assertFalse(file.action_on_finish_done)

        mgr.run(file.torrent)
        file.refresh_from_db()

        # action nothing does nothing, so nothing should change, except for file action state
        self.assertTrue(file.action_on_finish_done)
        self.assertTrue(temp_file.exists())
        items = [entry for entry in target.iterdir()]
        self.assertTrue(len(items) == 0)

        shutil.rmtree(target)
        shutil.rmtree(work_dir)

    def test_moves_new_dir(self):
        file, temp_file, work_dir = self._prepare_test(
            self.movies, file_name="test.mp4"
        )
        search = create_search("tt001", "Test Movie", None, None, file.torrent)
        mgr = ActionMgr()
        target = create_work_dir(self.movies.target_dir)
        self.assertTrue(temp_file.exists())
        self.assertFalse(file.action_on_finish_done)

        mgr.run(file.torrent)

        expected_file = Path(target / "Test Movie [imdbid-tt001]" / "Test Movie.mp4")
        self.assertTrue(expected_file.exists())
        self.assertFalse(temp_file.exists())
        shutil.rmtree(target)
