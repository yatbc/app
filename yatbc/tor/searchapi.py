from django.forms import model_to_dict
from .models import (
    JackettSearch,
    JackettSearchResultBase,
    JackettSearchResultHomeVideo,
    JackettSearchResultAudiobook,
    JackettQueryUrl,
    TorrentType,
    Person,
)
from .arrutils import extract_metadata
from django.utils import timezone
from .torboxapi import TorBoxApi
import requests
from lxml import etree
import logging
from time import sleep
from random import randint
from django.db.models import Q
from django.db import transaction


class JackettApi:
    def __init__(self, query_urls: list[str]):
        self.query_urls = query_urls
        self.logger = logging.getLogger("torbox")

    def search(self, query: str) -> list[etree.Element]:
        result = []
        for query_url in self.query_urls:
            if query_url.endswith("&q="):
                query_url = query_url[: query_url.index("&q=")]
            xml_result = requests.get(f"{query_url}&q={query}")
            if xml_result.status_code != 200:
                self.logger.error(
                    f"Jackett API search failed with status code {xml_result.status_code}"
                )
                continue
            result.append(etree.fromstring(xml_result.content))
        return result


def build_magnet_link(
    info_hash: str, trackers: list[str], name: str, size: int = 0
) -> str:
    unique_trackers = list(set(trackers))[
        :5
    ]  # Ppl tend to list all known trackers on page, so limit to 5 unique trackers
    not_sorted_trackers = []  # Rebuild to preserve order
    for tracker in trackers:
        if tracker in unique_trackers and tracker not in not_sorted_trackers:
            not_sorted_trackers.append(tracker)
    trackers_param = "&tr=".join(
        [requests.utils.quote(tracker) for tracker in not_sorted_trackers]
    )
    magnet_link = f"magnet:?xt=urn:btih:{info_hash}&dn={requests.utils.quote(name)}&tr={trackers_param}"
    if size:
        magnet_link += f"&xl={size}"
    return magnet_link


class NetworkApi:
    def get_html(self, url: str) -> str:
        try:
            sleep(randint(2, 4))  # Be polite to the server
            print(f"Fetching HTML from {url}")
            html = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:146.0) Gecko/20100101 Firefox/146.0"
                },
                timeout=5,
            ).text
            return html
        except Exception as e:
            logger = logging.getLogger("torbox")
            logger.error(f"Error fetching HTML from {url}: {e}")
            return ""


class AudiobookBayApi:
    def __init__(self, network_api: NetworkApi = None):
        if not network_api:
            network_api = NetworkApi()
        self.network_api = network_api
        self.logger = logging.getLogger("torbox")

    def get_audiobook_details(self, audiobookbay: str) -> dict:
        try:
            html = self.network_api.get_html(audiobookbay)
            if not html:
                return {}
            result = {}
            lxml = etree.HTML(html)

            title_query = "//title/text()"
            title = lxml.xpath(title_query)
            if title:
                result["title"] = title[0].strip()

            hash_query = (
                '//td[contains(text(), "Info Hash:")]/following-sibling::td[1]/text()'
            )
            info_hash = lxml.xpath(hash_query)
            if info_hash:
                result["hash"] = info_hash[0].strip()
            tracker_query = '//tr[td[1]="Tracker:"]/td[2]/text()'
            trackers = lxml.xpath(tracker_query)
            announce_tracker_query = '//td[contains(text(), "Announce URL:")]/following-sibling::td[1]/text()'
            announce_tracker = lxml.xpath(announce_tracker_query)
            if announce_tracker:
                result["announce_tracker"] = announce_tracker[0].strip()
            trackers_list = [tracker.strip() for tracker in trackers]
            if trackers_list:
                result["trackers"] = list(trackers_list)

            author_query = '//span[@class="author"]/text()'
            author = lxml.xpath(author_query)
            if author:
                result["author"] = author[0].strip()
            narrator_query = '//span[@class="narrator"]/text()'
            narrator = lxml.xpath(narrator_query)
            if narrator:
                result["narrator"] = narrator[0].strip()
            description_query = '//div[@class="desc"]//p[not(@style)]/text()'
            description = lxml.xpath(description_query)
            if description:
                content = " ".join([desc.strip() for desc in description])
                result["description"] = content
            all_trackers = []
            if "announce_tracker" in result:
                all_trackers.append(result["announce_tracker"])
            if "trackers" in result:
                all_trackers.extend(result["trackers"])

            if title and info_hash and trackers_list:
                result["magnet_link"] = build_magnet_link(
                    info_hash[0].strip(), all_trackers, title[0].strip()
                )

            return result
        except Exception as e:

            self.logger.error(
                f"Error parsing audiobook details from {audiobookbay}: {e}"
            )
            return {}


# todo: for recent searches it would be good to recheck cache status even if exists, because it may be already obsolete
def update_cached_status(api: TorBoxApi):
    if not api:
        api = TorBoxApi()
    logger = logging.getLogger("torbox")
    results = JackettSearchResultBase.objects.filter(
        Q(torbox_cached_updated_at__lte=timezone.now() - timezone.timedelta(days=30))
        | Q(torbox_cached_updated_at__isnull=True),
        hash__isnull=False,
    )[:30]
    hashes = [result.hash for result in results]
    if not hashes:
        return False

    cached_info = api.check_hashes_for_cached(hashes=hashes)
    logger.debug(f"Cached info: {cached_info}")
    cached = {info["hash"] for info in cached_info if "hash" in info}
    for result in results:
        result.torbox_cached = result.hash in cached
        result.torbox_cached_updated_at = timezone.now()
        logger.debug(
            f"Result {result.id} with hash {result.hash} cached status: {result.torbox_cached}"
        )
    JackettSearchResultBase.objects.bulk_update(
        results, ["torbox_cached", "torbox_cached_updated_at"]
    )
    return True


def fill_audiobook_details(
    query: JackettSearch,
    audiobook_bay_api: AudiobookBayApi,
):
    if audiobook_bay_api is None:
        audiobook_bay_api = AudiobookBayApi()
    logger = logging.getLogger("torbox")
    if query.torrent_type != TorrentType.objects.get_audiobooks():
        logger.error("fill_audiobook_details called with non-audiobook query")
        return 0
    results = JackettSearchResultAudiobook.objects.filter(
        query=query, hash__isnull=True
    )[:5]
    audiobook_details = []

    for result in results:
        if result.indexer != "AudioBook Bay":
            audiobook_details.append(result)
            continue
        query_result = audiobook_bay_api.get_audiobook_details(result.guid)
        if not query_result:
            continue
        result.hash = query_result.get("hash")
        author = query_result.get("author")
        if author:
            result.author = Person.objects.filter(name__icontains=author).first()
            if not result.author:
                result.author = Person.objects.create(name=author)
        narrator = query_result.get("narrator")
        if narrator:
            result.narrator = Person.objects.filter(name__icontains=narrator).first()
            if not result.narrator:
                result.narrator = Person.objects.create(name=narrator)
        result.description = query_result.get("description")
        result.magnet_link = query_result.get("magnet_link")
        title, author, series, part, extension, sample_rate, parsed_narrator = (
            extract_metadata(
                description=result.description,
                full_title=result.full_title,
                author=result.author.name if result.author else None,
                narrator=result.narrator.name if result.narrator else None,
                skip_author_check=True,
            )
        )
        if title:
            result.title = title
        if series:
            result.series = series
        if part:
            result.part = part
        if extension:
            result.extension = extension
        if sample_rate:
            result.sample_rate = sample_rate
        if not narrator and parsed_narrator:
            result.narrator = Person.objects.filter(
                name__icontains=parsed_narrator
            ).first()
            if not result.narrator:
                result.narrator = Person.objects.create(name=parsed_narrator)

        audiobook_details.append(result)
    with transaction.atomic():
        for details in audiobook_details:
            details.save()
    return len(audiobook_details)


def get_audiobooks(
    query: str,
    api: JackettApi = None,
) -> int:
    logger = logging.getLogger("torbox")
    if api is None:
        urls = JackettQueryUrl.objects.filter(
            torrent_type=TorrentType.objects.get_audiobooks()
        ).values_list("url", flat=True)
        api = JackettApi(query_urls=list(urls))

    query_obj, _ = JackettSearch.objects.get_or_create(
        query=query, torrent_type=TorrentType.objects.get_audiobooks()
    )
    results_xml = api.search(
        query=query
    )  # jackett adds &tt=1 to query, meaning it will search only in title and author
    results = []
    for item in results_xml:
        indexer = item.findtext(".//title")
        logger.debug(f"Processing results from indexer: {indexer}")
        for entry in item.findall(".//item"):
            public = entry.findtext(".//type")
            size = entry.findtext(".//size")
            attrs = entry.findall(
                ".//torznab:attr",
                namespaces={"torznab": "http://torznab.com/schemas/2015/feed"},
            )
            grabs = entry.findtext(".//grabs")
            guid = entry.findtext(".//guid")
            seeders = 0
            peers = 0
            cover_url = None
            genre = None
            for attr in attrs:
                if attr.get("name") == "seeders":
                    seeders = int(attr.get("value"))
                if attr.get("name") == "peers":
                    peers = int(attr.get("value"))
                if attr.get("name") == "coverurl":
                    cover_url = attr.get("value")
                if attr.get("name") == "genre":
                    genre = attr.get("value")
            link = entry.findtext(".//link")
            full_title = entry.findtext(".//title")
            published_date_text = entry.findtext(".//pubDate")
            if published_date_text:
                published_date = timezone.datetime.strptime(
                    published_date_text, "%a, %d %b %Y %H:%M:%S %z"
                )
            else:
                published_date = None

            result = JackettSearchResultAudiobook(
                query=query_obj,
                indexer=indexer,
                full_title=full_title,
                torrent_link=link,
                size=size,
                seeders=int(seeders),
                peers=int(peers),
                private=not (public == "public"),
                grabs=int(grabs) if grabs is not None else 0,
                guid=guid,
                published_date=published_date,
                cover_url=cover_url,
                tags=genre,
            )
            # todo: move to outside the loop to speed up later updates
            previous = JackettSearchResultAudiobook.objects.filter(guid=guid).first()
            if previous:
                result = previous
                result.tags = genre if genre is not None else previous.tags
                result.cover_url = (
                    cover_url if cover_url is not None else previous.cover_url
                )
                result.grabs = int(grabs) if grabs is not None else previous.grabs
                result.peers = int(peers) if peers is not None else previous.peers
                result.seeders = (
                    int(seeders) if seeders is not None else previous.seeders
                )
                result.published_date = (
                    published_date
                    if published_date is not None
                    else previous.published_date
                )
                result.torrent_link = (
                    link if link is not None else previous.torrent_link
                )

            results.append(result)

    with transaction.atomic():
        for result in results:
            result.save()
            logger.debug(f"Found audiobook result: {model_to_dict(result)}")
    return query_obj.pk
