from datetime import timezone as dt_timezone
from django.test import TestCase, override_settings
from django.utils import timezone
from ..searchapi import (
    JackettApi,
    get_audiobooks,
    AudiobookBayApi,
    NetworkApi,
    update_cached_status,
    fill_audiobook_details,
)
from .utils import get_person

import unittest
from unittest import mock

from .temp_settings import console_logging_config
import logging

from lxml import etree
from constance import config
from ..torboxapi import TorBoxApi
from ..models import (
    JackettSearch,
    JackettSearchResultAudiobook,
    JackettQueryUrl,
    TorrentType,
    JackettSearchResultBase,
)
from requests.utils import quote

audio_test = b"""
<rss xmlns:atom='http://www.w3.org/2005/Atom' xmlns:torznab='http://torznab.com/schemas/2015/feed' version='2.0'>
<channel>
<atom:link href='http://127.1.0.7:9117/' rel='self' type='application/rss+xml'/>
<title>AudioBook Bay</title>
<description>AudioBook Bay (ABB)</description>
<link>https://test.test/</link>\n    <language>en-US</language>
<category>search</category>\n    <item>
<title>My Free Book</title>
<guid>https://test.test/abss/my-free-book/</guid>
<jackettindexer id='audiobookbay'>AudioBook Bay</jackettindexer>\n      <type>public</type>
<comments>https://test.test/abss/my-free-book/</comments>
<pubDate>Mon, 1 Sep 2000 00:00:00 +0000</pubDate>\n      <size>12300</size>\n      <description/>
<link>http://127.1.0.7:9117/dl/audiobookbay/?jackett_apikey=xxx&amp;path=xxx&amp;file=My+Free+Book</link>
<category>1234</category>
<enclosure url='http://127.0.0.1:9117/dl/audiobookbay/?jackett_apikey=xxx&amp;path=xxx&amp;file=My+Free+Book' length='123400' type='application/x-bittorrent'/>
<torznab:attr name='category' value='1234'/>
<torznab:attr name='genre' value='Free Book'/>
<torznab:attr name='seeders' value='1'/>
<torznab:attr name='peers' value='1'/>
<torznab:attr name='coverurl' value='http://127.0.0.1:9117/img/audiobookbay/?jackett_apikey=xxx&amp;path=xxx&amp;file=poster'/>
<torznab:attr name='downloadvolumefactor' value='0'/>
<torznab:attr name='uploadvolumefactor' value='1'/>
</item>\n     </channel>\n</rss>\n
"""

audiobookbay_test_html = """
<!DOCTYPE html>
<html xmlns="https://www.w3.org/1999/xhtml" lang="en">
<head profile="https://gmpg.org/xfn/11">
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta http-equiv="Content-Language" content="en" />


<title>Book Title </title>
<meta name="description" content="  Book Title test s" />

    
		<div id="content">


		          
<div class="post">
    
	<div class="postTitle"><h1 itemprop="name">Book Title</h1></div>	
<div class="desc" itemprop="description">

<p style="left;">Written by <a href="/?s=Open+Source"><span class="author" >Open Source</span></a> <br />Read by <a href="/?s=Narrator+1"><span class="narrator">Narrator 1</span></a> </p>
<p>Test description</p>
<p>  Second Line</p>
</div>
<table border='1' border-color='#aaaaa' class='info'>
<tr>
<td style='width:150px;'>Announce URL:</td>
<td style='width:323px;'>http://main.localhost.test:123/announce</td>
</tr>
<tr>
<td colspan='2'>Some text</td>
</tr>
<tr>
<td>Tracker:</td>
<td>http://backup1.localhost.test:1234/announce</td>
</tr>
<tr>
<td>Tracker:</td>
<td>http://backup2.localhost.test:1235/announce</td>
</tr>
<tr>
<td>Creation Date:</td>
<td>Fri, 02 Jan 2011 01:11:11 +0100</td>
</tr>
<tr>
<td>Combined File Size:</td>
<td>234</td>
</tr>
<tr>
<td>Piece Size:</td>
<td>123</td>
</tr>
<tr>
<td>Comment:</td>
<td>Empty comment</td>
</tr>
<tr>
<td>Info Hash:</td>
<td>xxxyyyzzz</td>
</tr>
<tr>
<tr>
<td valign="top">AD:</td>
<td>
Wrong text
				</td>
</tr>
</table>
	</div>
      
                

</body>
</html>
"""


@override_settings(DEBUG=True, LOGGING=console_logging_config)
class SearchApiTests(TestCase):
    def setUp(self):
        logging.config.dictConfig(console_logging_config)

    def test_audiobay_api(self):
        network_api = mock.Mock(spec=NetworkApi)
        network_api.get_html.return_value = audiobookbay_test_html

        api = AudiobookBayApi(network_api=network_api)
        details = api.get_audiobook_details("https://test.test/abss/my-free-book/")
        print(details)
        self.assertEqual(details["author"], "Open Source")
        self.assertEqual(details["narrator"], "Narrator 1")
        self.assertEqual(details["description"], "Test description Second Line")
        self.assertEqual(details["title"], "Book Title")
        self.assertEqual(
            details["magnet_link"],
            f"magnet:?xt=urn:btih:xxxyyyzzz&dn={quote('Book Title')}&tr={quote('http://main.localhost.test:123/announce')}&tr={quote('http://backup1.localhost.test:1234/announce')}&tr={quote('http://backup2.localhost.test:1235/announce')}",
        )

    def test_update_details(self):
        audiobook_bay_api = mock.Mock(spec=AudiobookBayApi)
        audiobook_bay_api.get_audiobook_details.return_value = {
            "author": "Updated Author",
            "narrator": "Updated Narrator",
            "description": "Updated Description",
            "magnet_link": "magnet:?xt=urn:btih:updatedhash&dn=Old+Title",
            "hash": "updatedhash",
        }

        query = JackettSearch(torrent_type=TorrentType.objects.get_audiobooks())
        query.save()
        result = JackettSearchResultAudiobook(
            title="Old Title",
            hash=None,
            query=query,
            size=123,
            grabs=1,
            seeders=1,
            peers=1,
            indexer="AudioBook Bay",
        )
        result.save()

        updated_count = fill_audiobook_details(
            query=query, audiobook_bay_api=audiobook_bay_api
        )
        result.refresh_from_db()

        self.assertEqual(updated_count, 1)

        self.assertEqual(result.title, "Old Title")
        self.assertEqual(result.author, get_person("Updated Author"))
        self.assertEqual(result.narrator, get_person("Updated Narrator"))
        self.assertEqual(result.description, "Updated Description")
        self.assertEqual(result.hash, "updatedhash")
        self.assertEqual(
            result.magnet_link,
            "magnet:?xt=urn:btih:updatedhash&dn=Old+Title",
        )

    def test_check_audiobook_hashes_for_cached(self):
        torbox_api = mock.Mock(spec=TorBoxApi)
        torbox_api.check_hashes_for_cached.return_value = [
            {"hash": "hash1", "name": "Book 1"},
            {"hash": "hash3", "name": "Book 3"},
        ]

        results = []
        query = JackettSearch(torrent_type=TorrentType.objects.get_audiobooks())
        query.save()
        for i in range(1, 5):
            result = JackettSearchResultAudiobook(
                title=f"Book {i}",
                hash=f"hash{i}",
                query=query,
                size=123,
                grabs=1,
                seeders=1,
                peers=1,
            )
            results.append(result)
            result.save()

        updated = update_cached_status(api=torbox_api)

        torbox_api.check_hashes_for_cached.assert_called_once_with(
            hashes=["hash1", "hash2", "hash3", "hash4"]
        )
        self.assertTrue(updated)

        updated_results = JackettSearchResultAudiobook.objects.filter(query=query)
        for result in updated_results:
            if result.hash in ["hash1", "hash3"]:
                self.assertTrue(result.torbox_cached)
            else:
                self.assertFalse(result.torbox_cached)

    def test_search(self):
        # Arrange
        query_url = "http://127.0.0.1:9117/api/v2.0/indexers/audiobookbay/results/torznab/api?apikey=xxx&t=search&cat="
        api = unittest.mock.MagicMock()
        api.search.return_value = [etree.fromstring(audio_test)]
        query = "My Free Book"

        # Act
        query_result_id = get_audiobooks(query=query, api=api)
        result = JackettSearch.objects.get(pk=query_result_id)
        results = JackettSearchResultAudiobook.objects.filter(query=result)

        # Assert
        api.search.assert_called_once_with(query=query)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].full_title, "My Free Book")
        self.assertIsNone(results[0].hash)
        self.assertIsNone(results[0].torbox_cached)
        self.assertEqual(results[0].private, False)
        self.assertEqual(
            results[0].published_date,
            timezone.datetime(2000, 9, 1, 0, 0, tzinfo=dt_timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
