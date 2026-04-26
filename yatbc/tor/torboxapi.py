from django.utils import timezone
import json
from .models import *
from .statusmgr import StatusMgr
import logging
from .commondao import (
    format_log_value,
    update_torrent,
    mark_deleted_torrents,
    TORBOX_CLIENT,
    TRANSMISSION_CLIENT,
    add_log,
    torrent_file_to_log,
    torrent_to_log,
    clean_html,
    map_torbox_entry_to_torrent as map_entry_to_torrent,
    map_torbox_entry_to_torrent_history,
    get_active_torbox_downloads,
    add_to_queue_by_magnet,
    get_previous_torrents,
    get_torrents_with_no_history,
    get_torrent_ides,
)
from torbox_api import TorboxApi
from datetime import date, timedelta
import requests
from constance import config


class TorBoxApi:
    def __init__(
        self,
        access_token=None,
        timeout=20000,
        host=None,
        api=None,
        search_api=None,
        version="v1",
    ):
        if not access_token:
            access_token = config.TORBOX_API_KEY
        if not host:
            host = config.TORBOX_HOST
        if not api:
            api = config.TORBOX_API
        if not search_api:
            search_api = config.TORBOX_SEARCH_API
        self.access_token = access_token
        self.timeout = timeout
        self.host = host
        self.api = api
        self.search_api = search_api
        self.version = version
        self.logger = logging.getLogger("torbox")
        self.status_mgr = StatusMgr.get_instance()

        self.sdk = TorboxApi(
            access_token=self.access_token,
            timeout=self.timeout,
            base_url=f"https://{self.api}.{self.host}",
        )

    def get_max_download_slots(self):
        # just ask for plan to know how many slots user have
        try:
            response = self.sdk.user.get_user_data(api_version=self.version)
            if response.success:
                additional_slots = response.data._kwargs["additional_concurrent_slots"]
                plan = response.data.plan
                if plan == 3:  # standard
                    result = 5
                elif plan == 2:  # pro
                    result = 10
                elif plan == 1:  # basic
                    result = 3
                else:
                    result = 0
                self.logger.debug(
                    f"User allowed slots: {result}, user additional slots: {additional_slots}"
                )
                return result + additional_slots
        except Exception as e:
            add_log(
                message=f"Could not get user data to read download slots: {format_log_value(e)}, assuming 3",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_torbox_api(),
            )
        return 3

    def add_torrent(self, magnet=None, blob=None):
        try:
            from torbox_api.models.create_torrent_request import CreateTorrentRequest

            request = CreateTorrentRequest(magnet=magnet, file=blob)
            result = self.sdk.torrents.create_torrent(
                api_version=self.version, request_body=request
            )
            if result.success:
                return result.data
        except Exception as e:
            add_log(
                message=f"Could not add torrent: {format_log_value(e)}",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_torbox_api(),
            )
        return None

    def add_referral(self, referral_code):
        try:
            result = self.sdk.user.add_referral_to_account(
                api_version=self.version, referral=referral_code
            )
            if result.success:
                self.logger.info("Referral added successfully")
                return True, "Referral added successfully"
            self.logger.error(f"Failed to add referral: {result.error}")
            return False, f"Failed to add referral: {result.error}"
        except Exception as e:
            self.logger.error(f"Could not add referral: {e}")
            return False, f"Could not add referral: {e}"

    def change_torrent(self, torrent, action):
        body = {"operation": action, "torrent_id": int(torrent.internal_id)}

        try:
            self.logger.debug(body)
            result = requests.post(
                f"https://{self.api}.{self.host}/{self.version}/api/torrents/controltorrent",
                headers={"Authorization": f"Bearer {self.access_token}"},
                json=body,
            )
            if result.ok:
                return True
            return False
        except Exception as e:
            self.logger.error(body)
            self.logger.error(e)

            add_log(
                message=f"Could not change torrent: {torrent_to_log(torrent)}, {action}: {e}",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_torbox_api(),
                torrent=torrent,
            )
            return False

    def search_torrent(self, query, season=0, episode=0, by_id=True):
        additional_params = ""
        if season != 0:
            additional_params += f"&season={season}"
        if episode != 0:
            additional_params += f"&episode={episode}"
        if by_id:
            search_query = f"imdb:{query}"
        else:
            search_query = f"search/{query}"
        url = f"https://{self.search_api}.{self.host}/torrents/{search_query}?metadata=true&check_cache=true&check_owned=true&search_user_engines=true{additional_params}"
        self.logger.debug(f"Requesting search API: {url}")
        result = requests.get(
            url, headers={"Authorization": f"Bearer {self.access_token}"}
        )
        if result.ok:
            json_result = json.loads(result.text)
            self.logger.debug(json.dumps(json_result, indent=4))
            return json_result
        self.logger.error(f"Failed to search torrent: {query}, {result.reason}")
        add_log(
            message=f"Could not get result from torbox search api for query: {clean_html(query)}: reason: {clean_html(result.reason)}",
            level=Level.objects.get_error(),
            source=LogSource.objects.get_torbox_api(),
        )
        return None

    def search_usenet(self, query, season=0, episode=0, by_id=True):
        additional_params = ""
        if season != 0:
            additional_params += f"&season={season}"
        if episode != 0:
            additional_params += f"&episode={episode}"
        if by_id:
            search_query = f"imdb:{query}"
        else:
            search_query = f"search/{query}"
        url = f"https://{self.search_api}.{self.host}/usenet/{search_query}?metadata=true&check_cache=true&check_owned=true&search_user_engines=true{additional_params}"
        self.logger.debug(f"Requesting search API: {url}")
        result = requests.get(
            url, headers={"Authorization": f"Bearer {self.access_token}"}
        )
        if result.ok:
            json_result = json.loads(result.text)
            self.logger.debug(json.dumps(json_result, indent=4))
            return json_result
        self.logger.error(f"Failed to search torrent: {query}, {result.reason}")
        add_log(
            message=f"Could not get result from torbox search api for query: {clean_html(query)}: reason: {clean_html(result.reason)}",
            level=Level.objects.get_error(),
            source=LogSource.objects.get_torbox_api(),
        )
        return None

    def get_torrent_list(self):
        try:
            result = self.sdk.torrents.get_torrent_list(
                api_version=self.version,
                bypass_cache="True",  # if it will start failing with to many results, set it to False
                # id_="integer",
                # offset="integer",
                # limit="integer"
            )

            if result.error:
                add_log(
                    message=f"Failed to access tor api: {clean_html(result.error)}",
                    level=Level.objects.get_error(),
                    source=LogSource.objects.get_torbox_api(),
                )
                return None
            if result.success:
                return result.data
            self.logger.error(
                f"Wrong api structure, if there is no error, there should be a success in get_torrent_list"
            )
        except Exception as e:
            add_log(
                message=f"Could not get torrents: {clean_html(e)}",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_torbox_api(),
            )
            return None
        return None

    def check_hashes_for_cached(self, hashes: list[str]) -> dict[str, bool]:
        try:
            self.logger.debug(f"Checking cached for hashes: {hashes}")
            result = self.sdk.torrents.get_torrent_cached_availability(
                hash=",".join(hashes),
                api_version=self.version,
                format="list",
                list_files="true",
            )

            if result.error:
                add_log(
                    message=f"Failed to access tor api: {clean_html(result.error)}",
                    level=Level.objects.get_error(),
                    source=LogSource.objects.get_torbox_api(),
                )
                return None
            if result.success:
                return result.data
            self.logger.error(
                f"Wrong api structure, if there is no error, there should be a success in get_torrent_cached_availability"
            )
        except Exception as e:
            add_log(
                message=f"Could not check get_torrent_cached_availability: {clean_html(e)}",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_torbox_api(),
            )
            return None
        return None

    def request_download_link(self, file: TorrentFile) -> str:
        try:
            result = self.sdk.torrents.request_download_link(
                api_version=self.version,
                token=self.access_token,
                torrent_id=file.torrent.internal_id,
                file_id=file.internal_id,
            )
            if not result.success:
                add_log(
                    message=f"Could not request download link for torrent {torrent_to_log(file.torrent)} using file link: {clean_html(result.error)}",
                    level=Level.objects.get_error(),
                    source=LogSource.objects.get_torbox_api(),
                    torrent=file.torrent,
                )
                return None
            return result.data
        except Exception as e:
            add_log(
                message=f"Could not request download link for torrent {torrent_to_log(file.torrent)} file {torrent_file_to_log(file)}: {clean_html(e)}",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_torbox_api(),
                torrent=file.torrent,
            )
            return None

    def request_download_link_as_zip(self, torrent) -> str:
        try:
            result = self.sdk.torrents.request_download_link(
                api_version=self.version,
                token=self.access_token,
                torrent_id=torrent.internal_id,
                zip_link="True",
            )
            if not result.success:
                add_log(
                    message=f"Could not request download link for torrent {torrent_to_log(torrent)} using zip link: {clean_html(result.error)}",
                    level=Level.objects.get_error(),
                    source=LogSource.objects.get_torbox_api(),
                    torrent=torrent,
                )
                return None
            return result.data
        except Exception as e:
            add_log(
                message=f"Could not request download link for torrent {torrent_to_log(torrent)} as zip file: {clean_html(e)}",
                level=Level.objects.get_error(),
                source=LogSource.objects.get_torbox_api(),
                torrent=torrent,
            )
            return None

    def request_download_links(
        self, torrent, remove_single_files_for_zip=True
    ) -> list[(str, TorrentFile)]:
        files = TorrentFile.objects.filter(torrent=torrent)
        download_links = []
        if files.count() > 10:
            link = self.request_download_link_as_zip(torrent)
            if not link:
                return None
            if remove_single_files_for_zip:
                files.delete()  # remove single files and replace them with zip
                add_log(
                    message=f"Torrent has more then 10 files, will request zip file instead {torrent_to_log(torrent)}",
                    level=Level.objects.get_info(),
                    source=LogSource.objects.get_torbox_api(),
                    torrent=torrent,
                )
            file = TorrentFile.objects.create(
                torrent=torrent,
                name=f"{torrent.name}.zip",
                short_name=f"{torrent.name}.zip",
                size=torrent.size,
                internal_id=None,
            )
            return [(link, file)]
        for file in files:
            link = self.request_download_link(file)
            if link:
                download_links.append((link, file))
            else:
                self.logger.warning(
                    f"Could not get download link for file: {file.name} in torrent: {torrent.name}, retrying"
                )
                link = self.request_download_link(file)
                if link:
                    download_links.append((link, file))
                else:
                    return None
        return download_links


def update_available_slots(api=None, force=False):
    logger = logging.getLogger("torbox")
    if not api:
        api = TorBoxApi()
    if (
        config.NEXT_MAX_DOWNLOAD_TORBOX_SLOTS_CHECK is None
        or config.NEXT_MAX_DOWNLOAD_TORBOX_SLOTS_CHECK <= date.today()
        or force
    ):
        config.MAX_DOWNLOAD_TORBOX_SLOTS = api.get_max_download_slots()
        config.NEXT_MAX_DOWNLOAD_TORBOX_SLOTS_CHECK = date.today() + timedelta(days=1)


def create_torrent_search_entry(
    result, torrent_search: TorrentTorBoxSearch, previous=None
) -> TorrentTorBoxSearch:
    logger = logging.getLogger("torbox")
    new_search_results = []
    hashes_seen = set()
    for torrent in result["data"]["torrents"]:
        hash = torrent["hash"]
        if hash in previous:
            logger.debug(f"Skipping saving of: {hash}, because it was already assigned")
            continue
        torrent_search_result = TorrentTorBoxSearchResult()

        torrent_search_result.raw_title = torrent["raw_title"]
        torrent_search_result.query = torrent_search
        torrent_search_result.hash = hash
        torrent_search_result.age = torrent["age"]
        try:
            if "title" in torrent:
                torrent_search_result.title = torrent["title"]
            if "title_parsed_data" in torrent:
                parsed = torrent["title_parsed_data"]
                if "year" in parsed:
                    torrent_search_result.year = parsed["year"]
                if "resolution" in parsed:
                    torrent_search_result.resolution = parsed["resolution"]
                if "codec" in parsed:
                    torrent_search_result.codec = parsed["codec"]
                if "season" in parsed and not isinstance(parsed["season"], list):
                    torrent_search_result.season = int(parsed["season"])
                else:
                    torrent_search_result.season = None
                if "episode" in parsed and not isinstance(parsed["episode"], list):
                    torrent_search_result.episode = parsed["episode"]
                elif "episode" in parsed and isinstance(parsed["episode"], list):
                    torrent_search_result.episode = ",".join(
                        [str(episode) for episode in parsed["episode"]]
                    )
                else:
                    torrent_search_result.episode = None
                if "episodeName" in parsed:
                    torrent_search_result.episode_name = parsed["episodeName"]

        except Exception as e:
            logger.error(f"Could not parse: {e}, {torrent}")
        torrent_search_result.magnet = torrent["magnet"]
        torrent_search_result.last_known_peers = torrent["last_known_peers"]
        torrent_search_result.last_known_seeders = torrent["last_known_seeders"]
        torrent_search_result.size = torrent["size"]
        torrent_search_result.cached = torrent["cached"]
        hashes_seen.add(hash)
        new_search_results.append(torrent_search_result)

    torrents_for_hash = Torrent.objects.filter(hash__in=hashes_seen)
    hash_torrent_map = {t.hash: t for t in torrents_for_hash}
    for search_result in new_search_results:
        if not hash_torrent_map:
            break
        if search_result.hash in hash_torrent_map:
            search_result.torrent = hash_torrent_map[search_result.hash]
            del hash_torrent_map[search_result.hash]
    TorrentTorBoxSearchResult.objects.bulk_create(new_search_results)
    return torrent_search


def search_torrent(query, season, episode, api=None) -> TorrentTorBoxSearch | None:
    logger = logging.getLogger("torbox")
    logger.info(f"Searching for: {query} {season} {episode}")
    query_filter = TorrentTorBoxSearch.objects.filter_by_query_season_episode(
        query=query, season=season, episode=episode
    )
    latest = query_filter.order_by("-date").first()

    if latest:
        latest_age = timezone.now() - latest.date
        if latest_age < timezone.timedelta(hours=1):
            logger.info(f"Search for: {query} is only {latest_age}, skipping")
            return latest
    if not api:
        api = TorBoxApi()
    result = api.search_torrent(query, season=season, episode=episode)
    if not result:
        return None

    torrent_search = TorrentTorBoxSearch()
    previous = []
    if latest:
        logger.info(f"Got new data, removing unassigned results from previous {query}")
        TorrentTorBoxSearchResult.objects.delete_unassigned(query=latest)
        torrent_search = latest
        previous = TorrentTorBoxSearchResult.objects.filter(query=latest).values_list(
            "hash", flat=True
        )

    torrent_search.date = timezone.now()
    torrent_search.query = query
    torrent_search.episode = episode
    torrent_search.season = season
    torrent_search.save()
    return create_torrent_search_entry(
        result, previous=previous, torrent_search=torrent_search
    )


def get_free_torbox_download_slots(api=None):
    update_available_slots(api=api, force=False)
    return config.MAX_DOWNLOAD_TORBOX_SLOTS - get_active_torbox_downloads()


def have_free_download_slot(api=None):
    if not api:
        api = TorBoxApi()
    return get_free_torbox_download_slots(api) > 0


def add_torrent_by_data(torrent_type, magnet=None, blob=None, private=False, api=None):
    status_mgr = StatusMgr.get_instance()
    if not api:
        api = TorBoxApi()
    result = api.add_torrent(magnet, blob)
    if not result:
        return None
    new_torrent = status_mgr.new_torrent(
        hash=result.hash,
        client=TORBOX_CLIENT,
        internal_id=result.torrent_id,
        magnet=magnet,
        torrent_type=torrent_type,
        private=private,
    )
    TorrentHistory.objects.create(
        torrent=new_torrent, updated_at=timezone.now().isoformat(), state="New"
    )
    # todo: move to the task?
    search_result = JackettSearchResultBase.objects.filter(hash=new_torrent.hash)

    for item in search_result:
        item.torrent = new_torrent
        item.save()

    return new_torrent


def add_torrent_by_magnet(magnet, torrent_type_id, api=None, skip_queue_add=False):
    logger = logging.getLogger("torbox")

    torrent_type = TorrentType.objects.get(pk=torrent_type_id)
    logger.debug(
        f"Adding torrent from magnet: {magnet}, with type: {torrent_type.name}"
    )
    if not api:
        api = TorBoxApi()

    if not have_free_download_slot(api):
        if not skip_queue_add:
            return None, add_to_queue_by_magnet(
                magnet=magnet, torrent_type=torrent_type
            )
        return None, None
    return add_torrent_by_data(magnet=magnet, torrent_type=torrent_type, api=api), None


# todo: refactor to use eider torbox or transmission
def add_torrent_from_queue(queue: TorrentQueue, api=None):

    if not api:
        api = TorBoxApi()

    torrent = add_torrent_by_data(
        magnet=queue.magnet,
        blob=queue.torrent_file,
        api=api,
        torrent_type=queue.torrent_type,
        private=queue.torrent_private,
    )
    search = TorrentTorBoxSearchResult.objects.filter(queue=queue).first()
    if search:
        search.torrent = torrent
        search.save()
    return torrent


def add_torrent(query_search_id):
    logger = logging.getLogger("torbox")
    result = TorrentTorBoxSearchResult.objects.get(pk=query_search_id)
    if result.season:
        torrent_type = TorrentType.objects.get(name="Movie Series")
    else:
        torrent_type = TorrentType.objects.get(name="Movies")
    torrent, queue = add_torrent_by_magnet(
        result.magnet, torrent_type_id=torrent_type.id
    )

    logger.debug(
        f"Updating search result: {result} with matching torrent {torrent} or queue {queue}"
    )
    result.torrent = torrent
    result.queue = queue
    result.save()
    if torrent:
        add_log(
            message=f"Torrent {torrent_to_log(torrent)} with hash: {format_log_value(torrent.hash)} was added from search result: {format_log_value(result.query)}",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_torbox_api(),
            torrent=torrent,
        )
    if queue:
        add_log(
            message=f"Torrent was added to internal queue {queue.id} from search result: {format_log_value(result.query)}",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_torbox_api(),
        )


def delete_torrent(torrent_id, api=None):

    if not api:
        api = TorBoxApi()
    return change_torrent(torrent_id=torrent_id, action="delete", api=api)


def change_torrent(torrent_id, action, api=None):
    logger = logging.getLogger("torbox")
    torrent = Torrent.objects.get(pk=torrent_id)
    if not api:
        api = TorBoxApi()
    if not api.change_torrent(torrent, action):
        if action == "delete":
            torrent.deleted = False
            torrent.save()
        return False
    if action == "delete":
        torrent.deleted = True
        torrent.save()
    logger.info(f"Torrent: {torrent_id} changed: {action}")
    add_log(
        message=f"Torrent: {torrent_to_log(torrent)} changed: {action}",
        level=Level.objects.get_info(),
        source=LogSource.objects.get_torbox_api(),
        torrent=torrent,
    )
    return True


def add_referral_api(api=None):
    logger = logging.getLogger("torbox")
    if not config.TORBOX_API_KEY:
        logger.error("You need to set your TorBox API key in the settings!")
        return (
            False,
            "Please set your TorBox API key in the settings and save the configuration.",
        )
    if not api:
        api = TorBoxApi()

    logger.info("Adding referral to account, thank you!")
    from .referral import referral_code

    return api.add_referral(referral_code)


def validate_api(api, host, key):
    logger = logging.getLogger("torbox")
    WRONG_HOST = 1
    WRONG_KEY = 2
    API_VERSION = "v1"
    try:
        result = requests.get(
            f"https://{api}.{host}/{API_VERSION}/api/user/referraldata",
            headers={"Authorization": f"Bearer {key}"},
        )
    except Exception as e:
        logger.error(e)
        return (
            False,
            "Could not connect to TorBox API, check your host settings",
            WRONG_HOST,
        )
    logger.debug(result)
    if result.ok:
        logger.info(f"Access to TorBox API validated: {api}.{host} with key")
        return True, "Access to TorBox API validated", None
    logger.error(f"Failed to validate TorBox API: {api}.{host} with key")
    return False, "Failed to validate TorBox API. Check your API key.", WRONG_KEY


def update_torrent_list(api=None, request_files_task=None):
    if not api:
        api = TorBoxApi()
    no_type = TorrentType.objects.get(name="No Type")
    status_mgr = StatusMgr.get_instance()

    logger = logging.getLogger("torbox")
    data = api.get_torrent_list()
    if data is None:
        return None
    logger.debug(f"Updating entries: {len(data)} in torboxapi")
    torrents = {}
    for entry in data:
        new_torrent = map_entry_to_torrent(entry, no_type)
        torrents[new_torrent.hash] = {"new": new_torrent, "old": None, "double": None}
    torrents = get_previous_torrents(torrent_map=torrents, client=TORBOX_CLIENT)
    torrent_ids = get_torrent_ides(torrents)
    torrents_with_no_history = get_torrents_with_no_history(torrent_ids)

    not_deleted = []
    for entry in data:
        logger.debug(f"Processing entry: {entry.name} {entry.hash}")
        new_torrent, old_torrent, double = (
            torrents[entry.hash]["new"],
            torrents[entry.hash]["old"],
            torrents[entry.hash]["double"],
        )
        # fixme: download_finished can be false, but it can still be processing, check download_present?
        torrent = update_torrent(
            new_torrent=new_torrent, old_torrent=old_torrent, double=double
        )
        has_history = torrent.id not in torrents_with_no_history
        status_mgr.transition_in_client_progress_if_needed(
            torrent, has_history=has_history
        )
        previous_activity = False
        if has_history:
            previous_activity = TorrentHistory.objects.filter(
                torrent=torrent, updated_at=entry.updated_at
            ).exists()
        if not previous_activity:
            torrent_history = map_torbox_entry_to_torrent_history(entry, torrent)
            if new_torrent.download_finished:
                torrent_history.progress = 1
            torrent_history.save()
        else:
            logger.debug("Torrent wasn't active from last check")
        files = TorrentFile.objects.filter(torrent=torrent)
        if entry.files and not files:
            logger.debug(
                f"Filling files for: {torrent.name} with files: {len(entry.files)}"
            )
            new_files = []
            for file in entry.files:
                new_file = TorrentFile(
                    torrent=torrent,
                    name=file.name,
                    short_name=file.short_name,
                    size=file.size,
                    hash=(file._kwargs["hash"] if "hash" in file._kwargs else None),
                    mime_type=file.mimetype,
                    internal_id=file.id_,
                )
                new_files.append(new_file)
            TorrentFile.objects.bulk_create(new_files)

        status_mgr.transition_in_client_done_if_needed(
            torrent,
            files,
            request_torrent_files=request_files_task,
        )

        not_deleted.append(torrent)
    mark_deleted_torrents(not_deleted, clients=[TRANSMISSION_CLIENT])
    config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX = False
