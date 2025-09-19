from django.test import TestCase, override_settings
from ..models import (
    Torrent,
    TorrentTorBoxSearchResult,
    TorrentTorBoxSearch,
    ArrBase,
    ArrMovieSeries,
    Level,
    TorrentType,
)
from ..arrmanager import get_next_arrs, process_arr, get_all_arrs, get_best_match
from constance import config
from unittest.mock import patch, Mock

from pathlib import Path
from django.utils import timezone
import logging
from .temp_settings import console_logging_config
from .utils import create_search, create_torrent
import shutil


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class ArrManagerTests(TestCase):
    def setUp(self):
        logging.config.dictConfig(console_logging_config)
        self.no_type = TorrentType.objects.get_no_type()

    def _create_arr(
        self,
        imdbid="tt1234567",
        title="Test Show",
        quality="1080p",
        encoder="TestEnc",
        season=1,
        episode=1,
        last_found=None,
        last_checked=None,
        exclude_words=None,
        include_words=None,
    ):
        arr = ArrMovieSeries.objects.create(
            imdbid=imdbid,
            title=title,
            quality=quality,
            encoder=encoder,
            requested_season=season,
            requested_episode=episode,
            torrent_type=TorrentType.objects.get_movie_series(),
            last_found=last_found,
            last_checked=last_checked,
            exclude_words=exclude_words,
            include_words=include_words,
        )
        return arr

    def test_removed_arr(self):
        result, status = process_arr(-1)
        self.assertIsNone(result)
        self.assertFalse(status)

    def test_get_any(self):
        arr1 = self._create_arr(
            imdbid="tt0000001", quality="1080p,720p,ANY", encoder=""
        )
        search = create_search(
            raw_title=f"Test.1720p.TestEnc.S01.E02",
            query="test",
            season=1,
            episode="",
            title="test",
        )
        search2 = create_search(
            query_object=search.query,
            raw_title=f"Test.Quality.TestEnc.S01.E02",
            query="test",
            season=1,
            episode="",
            title="test",
        )

        result = get_best_match([search, search2], arr1)
        self.assertEqual(result, search)

    def test_get_any_but_prefer_include(self):
        arr1 = self._create_arr(
            imdbid="tt0000001",
            include_words="1080p,720p,TestEnc,ANY",
            quality="",
            encoder="",
        )
        search = create_search(
            raw_title=f"Test.720p.TestEnc.S01.E02",
            query="test",
            season=1,
            episode="",
            title="test",
        )
        search2 = create_search(
            query_object=search.query,
            raw_title=f"Test.Quality.TestEnc.S01.E02",
            query="test",
            season=1,
            episode="",
            title="test",
        )
        search3 = create_search(
            query_object=search.query,
            raw_title=f"Test.1080p.TestEnc.S01.E02",
            query="test",
            season=1,
            episode="",
            title="test",
        )

        result = get_best_match([search, search2, search3], arr1)
        self.assertEqual(result, search3)

    def test_get_next_arrs(self):
        ArrMovieSeries.objects.all().delete()
        arr1 = self._create_arr(
            imdbid="tt0000001", last_checked=timezone.now() - timezone.timedelta(days=2)
        )
        arr2 = self._create_arr(
            imdbid="tt0000002",
            last_checked=timezone.now() - timezone.timedelta(hours=12),
        )
        arr3 = self._create_arr(imdbid="tt0000003")  # never checked
        arrs = get_next_arrs()
        self.assertEqual(len(arrs), 2)  # arr1 and arr3
        self.assertIsNone(arrs[0].ago)  # never checked comes first
        self.assertGreater(arrs[1].ago, timezone.timedelta(days=1))  # arr1 is next

    def test_get_all_arrs(self):
        ArrMovieSeries.objects.all().delete()
        arr1 = self._create_arr(
            imdbid="tt0000001", last_checked=timezone.now() - timezone.timedelta(days=2)
        )
        arr2 = self._create_arr(
            imdbid="tt0000002",
            last_checked=timezone.now() - timezone.timedelta(hours=12),
        )
        arr3 = self._create_arr(imdbid="tt0000003")  # never checked
        arrs = get_all_arrs()
        self.assertEqual(len(arrs), 3)
        self.assertGreater(arrs[0].last_checked_ago, timezone.timedelta(days=2))

    @patch(target="tor.arrmanager.get_api")
    @patch(target="tor.arrmanager.search_torrent")
    @patch(target="tor.arrmanager.add_torrent_by_magnet")
    def test_deactivate(
        self, add_torrent_by_magnet: Mock, search_torrent: Mock, get_api: Mock
    ):
        api = Mock()
        get_api.return_value = api

        expected_imdbid = "tt0000001"
        expected_quality = "1080p"
        expected_encoder = "TestEncoder"
        expected_title = "Test.Movie.Series"
        expected_season = 1
        expected_episode = 2
        search_episode = 1

        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=search_episode,
            raw_title=f"{expected_title}.{expected_quality}.{expected_encoder}.S{expected_season}.E{search_episode}",
            title=expected_title,
        )
        arr = self._create_arr(
            imdbid=expected_imdbid,
            title=None,
            quality=expected_quality,
            encoder=expected_encoder,
            season=expected_season,
            episode=expected_episode,
            last_found=timezone.now() - timezone.timedelta(days=14),
        )

        search_torrent.return_value = search.query

        result, status = process_arr(arr.id)

        self.assertFalse(status)

        add_torrent_by_magnet.assert_not_called()

        search_torrent.assert_called_once_with(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            api=api,
        )
        self.assertFalse(result.active)

    @patch(target="tor.arrmanager.get_api")
    @patch(target="tor.arrmanager.search_torrent")
    @patch(target="tor.arrmanager.add_torrent_by_magnet")
    def test_move_to_next_season(
        self, add_torrent_by_magnet: Mock, search_torrent: Mock, get_api: Mock
    ):
        api = Mock()
        get_api.return_value = api

        expected_imdbid = "tt0000001"
        expected_quality = "1080p"
        expected_encoder = "TestEncoder"
        expected_title = "Test.Movie.Series"
        expected_season = 1
        expected_episode = 2
        search_episode = 1

        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=search_episode,
            raw_title=f"{expected_title}.{expected_quality}.{expected_encoder}.S{expected_season}.E{search_episode}",
            title=expected_title,
        )
        arr = self._create_arr(
            imdbid=expected_imdbid,
            title=None,
            quality=expected_quality,
            encoder=expected_encoder,
            season=expected_season,
            episode=expected_episode,
            last_found=timezone.now() - timezone.timedelta(days=8),
        )

        search_torrent.return_value = search.query

        result, status = process_arr(arr.id)
        self.assertFalse(status)

        add_torrent_by_magnet.assert_not_called()

        search_torrent.assert_called_once_with(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            api=api,
        )
        self.assertEqual(result.requested_episode, 1)
        self.assertEqual(result.requested_season, expected_season + 1)

    @patch(target="tor.arrmanager.get_api")
    @patch(target="tor.arrmanager.search_torrent")
    @patch(target="tor.arrmanager.add_torrent_by_magnet")
    def test_try_tomorrow(
        self, add_torrent_by_magnet: Mock, search_torrent: Mock, get_api: Mock
    ):
        api = Mock()
        get_api.return_value = api

        expected_imdbid = "tt0000001"
        expected_quality = "1080p"
        expected_encoder = "TestEncoder"
        expected_title = "Test.Movie.Series"
        expected_season = 1
        expected_episode = 2
        search_episode = 1

        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=search_episode,
            raw_title=f"{expected_title}.{expected_quality}.{expected_encoder}.S{expected_season}.E{search_episode}",
            title=expected_title,
        )
        arr = self._create_arr(
            imdbid=expected_imdbid,
            title=None,
            quality=expected_quality,
            encoder=expected_encoder,
            season=expected_season,
            episode=expected_episode,
            last_found=timezone.now() - timezone.timedelta(days=1),
        )

        search_torrent.return_value = search.query

        result, status = process_arr(arr.id)
        self.assertFalse(status)

        add_torrent_by_magnet.assert_not_called()

        search_torrent.assert_called_once_with(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            api=api,
        )
        self.assertEqual(result.requested_episode, expected_episode)
        self.assertEqual(result.requested_season, expected_season)

    @patch(target="tor.arrmanager.get_api")
    @patch(target="tor.arrmanager.search_torrent")
    @patch(target="tor.arrmanager.add_torrent_by_magnet")
    def test_simple_ok(
        self, add_torrent_by_magnet: Mock, search_torrent: Mock, get_api: Mock
    ):
        api = Mock()
        get_api.return_value = api

        expected_imdbid = "tt0000001"
        expected_quality = "1080p"
        expected_encoder = "TestEncoder"
        expected_title = "Test.Movie.Series"
        expected_season = 1
        expected_episode = 1

        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            raw_title=f"{expected_title}.{expected_quality}.{expected_encoder}.S{expected_season}.E{expected_episode}",
            title=expected_title,
        )
        arr = self._create_arr(
            imdbid=expected_imdbid,
            title=None,
            quality=expected_quality,
            encoder=expected_encoder,
            season=expected_season,
            episode=expected_episode,
        )
        torrent = create_torrent(arr.torrent_type)
        add_torrent_by_magnet.return_value = (torrent, None)
        search_torrent.return_value = search.query

        result, status = process_arr(arr.id)
        self.assertTrue(status)

        add_torrent_by_magnet.assert_called_once_with(
            magnet=search.magnet, torrent_type_id=arr.torrent_type.id, api=api
        )

        search_torrent.assert_called_once_with(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            api=api,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.requested_episode, expected_episode + 1)

    @patch(target="tor.arrmanager.get_api")
    @patch(target="tor.arrmanager.search_torrent")
    @patch(target="tor.arrmanager.add_torrent_by_magnet")
    def test_full_season(
        self, add_torrent_by_magnet: Mock, search_torrent: Mock, get_api: Mock
    ):
        api = Mock()
        get_api.return_value = api

        expected_imdbid = "tt0000001"
        expected_quality = "1080p"
        expected_encoder = "TestEncoder"
        expected_title = "Test.Movie.Series"
        expected_season = 1
        expected_episode = 2

        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=None,
            raw_title=f"{expected_title}.{expected_quality}.{expected_encoder}.S{expected_season}",
            title=expected_title,
        )
        arr = self._create_arr(
            imdbid=expected_imdbid,
            title=None,
            quality=expected_quality,
            encoder=expected_encoder,
            season=expected_season,
            episode=expected_episode,
        )
        torrent = create_torrent(arr.torrent_type)
        add_torrent_by_magnet.return_value = (torrent, None)
        search_torrent.return_value = search.query

        result, status = process_arr(arr.id)
        self.assertTrue(status)

        add_torrent_by_magnet.assert_called_once_with(
            magnet=search.magnet, torrent_type_id=arr.torrent_type.id, api=api
        )

        search_torrent.assert_called_once_with(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            api=api,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.requested_episode, 1)
        self.assertEqual(result.requested_season, expected_season + 1)

    @patch(target="tor.arrmanager.get_api")
    @patch(target="tor.arrmanager.search_torrent")
    @patch(target="tor.arrmanager.add_torrent_by_magnet")
    def test_matching_multiple_episodes(
        self, add_torrent_by_magnet: Mock, search_torrent: Mock, get_api: Mock
    ):
        api = Mock()
        get_api.return_value = api

        expected_imdbid = "tt0000001"
        expected_quality = "1080p"
        expected_encoder = "TestEncoder"
        expected_title = "Test.Movie.Series"
        expected_season = 1
        expected_episode = 1
        search_result_episode = "1,2,3,4"

        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=search_result_episode,
            raw_title=f"{expected_title}.{expected_quality}.{expected_encoder}.S{expected_season}.E1-E4",
            title=expected_title,
        )
        arr = self._create_arr(
            imdbid=expected_imdbid,
            title=None,
            quality=expected_quality,
            encoder=expected_encoder,
            season=expected_season,
            episode=1,
        )
        torrent = create_torrent(arr.torrent_type)
        add_torrent_by_magnet.return_value = (torrent, None)
        search_torrent.return_value = search.query

        result, status = process_arr(arr.id)
        self.assertTrue(status)

        add_torrent_by_magnet.assert_called_once_with(
            magnet=search.magnet, torrent_type_id=arr.torrent_type.id, api=api
        )

        search_torrent.assert_called_once_with(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            api=api,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.requested_episode, 5)

    @patch(target="tor.arrmanager.get_api")
    @patch(target="tor.arrmanager.search_torrent")
    @patch(target="tor.arrmanager.add_torrent_by_magnet")
    def test_add_with_matching_quality(
        self, add_torrent_by_magnet: Mock, search_torrent: Mock, get_api: Mock
    ):
        api = Mock()
        get_api.return_value = api

        expected_imdbid = "tt0000001"
        expected_quality = "1080p"
        expected_encoder = "TestEncoder"
        expected_title = "Test.Movie.Series"
        expected_season = 1
        expected_episode = 1

        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            raw_title=f"{expected_title}.{expected_quality}.{expected_encoder}.S{expected_season}.E{expected_episode}",
            title=expected_title,
        )
        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            raw_title=f"{expected_title}.1080pWrongQuality.{expected_encoder}.S{expected_season}.E{expected_episode}",
            title=expected_title,
            query_object=search.query,
        )
        arr = self._create_arr(
            imdbid=expected_imdbid,
            title=None,
            quality=expected_quality,
            encoder=expected_encoder,
            season=expected_season,
            episode=expected_episode,
        )
        torrent = create_torrent(arr.torrent_type)
        add_torrent_by_magnet.return_value = (torrent, None)
        search_torrent.return_value = search.query

        result, status = process_arr(arr.id)
        self.assertTrue(status)

        add_torrent_by_magnet.assert_called_once_with(
            magnet=search.magnet, torrent_type_id=arr.torrent_type.id, api=api
        )

        search_torrent.assert_called_once_with(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            api=api,
        )
        self.assertEqual(result.requested_episode, expected_episode + 1)
        self.assertIsNotNone(result)

    @patch(target="tor.arrmanager.get_api")
    @patch(target="tor.arrmanager.search_torrent")
    @patch(target="tor.arrmanager.add_torrent_by_magnet")
    def test_add_with_matching_any_quality(
        self, add_torrent_by_magnet: Mock, search_torrent: Mock, get_api: Mock
    ):
        api = Mock()
        get_api.return_value = api

        expected_imdbid = "tt0000001"
        expected_quality = "1080p"
        expected_encoder = ""
        expected_title = "Test.Movie.Series"
        expected_season = 1
        expected_episode = 1

        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            raw_title=f"{expected_title}.{expected_quality}.{expected_encoder}.S{expected_season}.E{expected_episode}",
            title=expected_title,
        )
        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            raw_title=f"{expected_title}.Quality.{expected_encoder}.S{expected_season}.E{expected_episode}",
            title=expected_title,
            query_object=search.query,
        )
        arr = self._create_arr(
            imdbid=expected_imdbid,
            title=None,
            quality="720p,ANY",
            encoder=expected_encoder,
            season=expected_season,
            episode=expected_episode,
        )
        torrent = create_torrent(arr.torrent_type)
        add_torrent_by_magnet.return_value = (torrent, None)
        search_torrent.return_value = search.query

        result, status = process_arr(arr.id)
        self.assertTrue(status)

        add_torrent_by_magnet.assert_called_once_with(
            magnet=search.magnet, torrent_type_id=arr.torrent_type.id, api=api
        )

        search_torrent.assert_called_once_with(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            api=api,
        )
        self.assertEqual(result.requested_episode, expected_episode + 1)
        self.assertIsNotNone(result)

    @patch(target="tor.arrmanager.get_api")
    @patch(target="tor.arrmanager.search_torrent")
    @patch(target="tor.arrmanager.add_torrent_by_magnet")
    def test_add_with_skipping_excluded(
        self, add_torrent_by_magnet: Mock, search_torrent: Mock, get_api: Mock
    ):
        api = Mock()
        get_api.return_value = api

        expected_imdbid = "tt0000001"
        expected_quality = "1080p"
        expected_encoder = ""
        expected_title = "Test.Movie.Series"
        expected_season = 1
        expected_episode = 1

        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            raw_title=f"{expected_title}.MeToo.{expected_encoder}.S{expected_season}.E{expected_episode}",
            title=expected_title,
        )
        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            raw_title=f"{expected_title}.SkipMe.{expected_encoder}.S{expected_season}.E{expected_episode}",
            title=expected_title,
            query_object=search.query,
        )
        arr = self._create_arr(
            imdbid=expected_imdbid,
            title=None,
            quality=None,
            encoder=None,
            season=expected_season,
            episode=expected_episode,
            exclude_words="SkipMe,MeToo",
        )
        torrent = create_torrent(arr.torrent_type)
        add_torrent_by_magnet.return_value = (torrent, None)
        search_torrent.return_value = search.query

        result, status = process_arr(arr.id)
        self.assertFalse(status)

        add_torrent_by_magnet.assert_not_called()

        search_torrent.assert_called_once_with(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            api=api,
        )

    @patch(target="tor.arrmanager.get_api")
    @patch(target="tor.arrmanager.search_torrent")
    @patch(target="tor.arrmanager.add_torrent_by_magnet")
    def test_add_with_matching_encoder(
        self, add_torrent_by_magnet: Mock, search_torrent: Mock, get_api: Mock
    ):
        api = Mock()
        get_api.return_value = api

        expected_imdbid = "tt0000001"
        expected_quality = "1080p"
        expected_encoder = "TestEncoder"
        expected_title = "Test.Movie.Series"
        expected_season = 1
        expected_episode = 1

        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            raw_title=f"{expected_title}.{expected_quality}.{expected_encoder}.S{expected_season}.E{expected_episode}",
            title=expected_title,
        )
        search = create_search(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            raw_title=f"{expected_title}.{expected_quality}.WrongEncoder.S{expected_season}.E{expected_episode}",
            title=expected_title,
            query_object=search.query,
        )
        arr = self._create_arr(
            imdbid=expected_imdbid,
            title=None,
            quality=expected_quality,
            encoder=expected_encoder,
            season=expected_season,
            episode=expected_episode,
        )
        torrent = create_torrent(arr.torrent_type)
        add_torrent_by_magnet.return_value = (torrent, None)
        search_torrent.return_value = search.query

        result, status = process_arr(arr.id)
        self.assertTrue(status)

        add_torrent_by_magnet.assert_called_once_with(
            magnet=search.magnet, torrent_type_id=arr.torrent_type.id, api=api
        )

        search_torrent.assert_called_once_with(
            query=expected_imdbid,
            season=expected_season,
            episode=expected_episode,
            api=api,
        )
        self.assertEqual(result.requested_episode, expected_episode + 1)
        self.assertIsNotNone(result)
