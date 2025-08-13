from django.utils import timezone
import json
from .models import *
from time import sleep
from datetime import timedelta
import logging
from .commondao import (
    update_torrent,
    mark_deleted_torrents,
    TORBOX_CLIENT,
    TRANSMISSION_CLIENT,
    prepare_torrent_dir_name,
    add_log,
    torrent_file_to_log,
    torrent_to_log,
    clean_html,
    map_torbox_entry_to_torrent,
    map_torbox_entry_to_torrent_history,
)
from .ariaapi import AriaApi
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
        from torbox_api import TorboxApi

        self.sdk = TorboxApi(
            access_token=self.access_token,
            timeout=self.timeout,
            base_url=f"https://{self.api}.{self.host}",
        )

    def add_torrent(self, magnet):
        try:
            from torbox_api.models.create_torrent_request import CreateTorrentRequest

            request = CreateTorrentRequest(magnet=magnet)
            result = self.sdk.torrents.create_torrent(
                api_version=self.version, request_body=request
            )
            if result.success:
                return result.data
        except Exception as e:
            self.logger.error(f"Could not add torrent: {e}")
            add_log(
                message=f"Could not add torrent: <i>'{e}'</i>",
                level="ERROR",
                source="torboxapi",
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
        body = body = json.dumps(
            {"operation": action, "torrent_id": int(torrent.internal_id)}
        )
        try:
            self.logger.debug(body)
            result = requests.post(
                f"https://{self.api}.{self.host}/{self.version}/api/torrents/controltorrent",
                headers={"Authorization": f"Bearer {self.access_token}"},
                data=body,
            )
            if result.ok:
                return True
            return False
        except Exception as e:
            self.logger.error(body)
            self.logger.error(e)
            add_log(
                message=f"Could not change torrent: {torrent_to_log(torrent)}, {action}: {e}",
                level="ERROR",
                source="torboxapi",
                torrent=torrent,
            )
            return False

    def search_torrent(self, query, season=0, episode=0):
        additional_params = ""
        if season != 0:
            additional_params += f"&season={season}"
        if episode != 0:
            additional_params += f"&episode={episode}"
        url = f"https://{self.search_api}.{self.host}/torrents/imdb:{query}?metadata=true&check_cache=true&check_owned=true&search_user_engines=true{additional_params}"
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
            message=f"Could not get result from torbox search api for query: <i>'{clean_html(query)}'</i>: reason: <i>'{clean_html(result.reason)}'</i>",
            level="ERROR",
            source="torboxapi",
        )
        return None

    def get_torrent_list(self):
        try:
            result = self.sdk.torrents.get_torrent_list(
                api_version=self.version,
                bypass_cache="True",  # ,
                # id_="integer",
                # offset="integer",
                # limit="integer"
            )
            if result.error:
                self.logger.debug("Failed to access tor api")
                add_log(
                    message=f"Failed to access tor api: {clean_html(result.error)}",
                    level="ERROR",
                    source="torboxapi",
                )
                return None
            if result.success:
                return result.data
        except Exception as e:
            self.logger.error(f"Could not get torrents: {e}")
            add_log(
                message=f"Could not get torrents: {clean_html(e)}",
                level="ERROR",
                source="torboxapi",
            )
            return None
        return None

    def request_download_link(self, torrent, file):
        try:
            result = self.sdk.torrents.request_download_link(
                api_version=self.version,
                token=self.access_token,
                torrent_id=torrent.internal_id,
                file_id=file.internal_id,
            )
            if not result.success:
                self.logger.error(result)
                add_log(
                    message=f"Could not request download link for torrent {torrent_to_log(torrent)} file {torrent_file_to_log(file)}: <i>'{clean_html(result.error)}'</i>",
                    level="ERROR",
                    source="torboxapi",
                    torrent=torrent,
                )
                return None
            return result.data
        except Exception as e:
            self.logger.error(f"Could not request a download link from TorBox: {e}")
            add_log(
                message=f"Could not request download link for torrent {torrent_to_log(torrent)} file {torrent_file_to_log(file)}: {clean_html(e)}",
                level="ERROR",
                source="torboxapi",
                torrent=torrent,
            )
            return None


def search_torrent(query, season, episode, api=None):
    logger = logging.getLogger("torbox")
    logger.info(f"Searching for: {query} {season} {episode}")
    if not api:
        api = TorBoxApi()
    result = api.search_torrent(query, season=season, episode=episode)
    if not result:
        return None
    logger.info(f"Got new data, removing previous query {query}")
    TorrentTorBoxSearch.objects.filter(query=query).delete()
    torrent_search = TorrentTorBoxSearch()
    torrent_search.date = timezone.now()
    torrent_search.query = query
    torrent_search.save()
    for torrent in result["data"]["torrents"]:
        torrent_search_result = TorrentTorBoxSearchResult()
        torrent_search_result.raw_title = torrent["raw_title"]
        torrent_search_result.query = torrent_search
        torrent_search_result.hash = torrent["hash"]
        torrent_search_result.age = torrent["age"]
        try:
            if "title_parsed_data" in torrent:
                parsed = torrent["title_parsed_data"]
                if "year" in parsed:
                    torrent_search_result.year = parsed["year"]
                if "resolution" in parsed:
                    torrent_search_result.resolution = parsed["resolution"]
                if "codec" in parsed:
                    torrent_search_result.codec = parsed["codec"]
                if "season" in parsed:
                    try:
                        torrent_search_result.season = int(parsed["season"])
                    except ValueError:
                        logger.error(
                            f"Could not parse season: {parsed['season']} for torrent: {torrent_search_result.hash}"
                        )
                        torrent_search_result.season = None
                if "episode" in parsed:
                    torrent_search_result.episode = int(parsed["episode"])
                if "episodeName" in parsed:
                    torrent_search_result.episode_name = parsed["episodeName"]
            if "title" in torrent:
                torrent_search_result.title = torrent["title"]
        except Exception as e:
            logger.error(f"Could not parse: {e}")
        torrent_search_result.magnet = torrent["magnet"]
        torrent_search_result.last_known_peers = torrent["last_known_peers"]
        torrent_search_result.last_known_seeders = torrent["last_known_seeders"]
        torrent_search_result.size = torrent["size"]
        torrent_search_result.cached = torrent["cached"]
        previous = Torrent.objects.filter(hash=torrent_search_result.hash)
        if previous:
            torrent_search_result.torrent = previous[0]
            add_log(
                message=f"Torrent: {torrent_to_log(torrent_search_result.torrent)} already exists in search for: <i>'{clean_html(query)}'</i>",
                level="INFO",
                source="torboxapi",
                torrent=torrent_search_result.torrent,
            )
        torrent_search_result.save()


def add_torrent_by_magnet(magnet, torrent_type_id, api=None):
    logger = logging.getLogger("torbox")
    torrent_type = TorrentType.objects.get(pk=torrent_type_id)
    if not torrent_type:
        logger.error(f"Torrent type with id {torrent_type_id} not found")
        return None
    logger.debug(
        f"Adding torrent from magnet: {magnet}, with type: {torrent_type.name}"
    )
    if not api:
        api = TorBoxApi()
    result = api.add_torrent(magnet)
    if not result:
        return None
    new_torrent = Torrent.objects.create(
        hash=result.hash,
        created_at=timezone.now().isoformat(),
        client=TORBOX_CLIENT,
        internal_id=result.torrent_id,
        magnet=magnet,
        torrent_type=torrent_type,
    )
    TorrentHistory.objects.create(
        torrent=new_torrent, updated_at=timezone.now().isoformat(), state="New"
    )
    logger.info(
        f"Added new torrent from user: {new_torrent.id} with type: {new_torrent.torrent_type.name}"
    )
    add_log(
        message=f"Torrent with hash <i>'{clean_html(new_torrent.hash)}'</i> was created from magnet: <i>'{clean_html(magnet)}'</i> with type: <i>'{torrent_type.name}'</i>",
        level="INFO",
        source="torboxapi",
        torrent=new_torrent,
        local_status="TorBox: Init",
    )
    return new_torrent


def add_torrent(query_search_id):
    logger = logging.getLogger("torbox")
    result = TorrentTorBoxSearchResult.objects.get(pk=query_search_id)
    if result.season:
        torrent_type = TorrentType.objects.get(name="Movie Series")
    else:
        torrent_type = TorrentType.objects.get(name="Movies")
    torrent = add_torrent_by_magnet(result.magnet, torrent_type_id=torrent_type.id)
    if not torrent:
        return

    logger.debug(f"Updating search result: {result} with matching torrent {torrent}")
    torrent.torrent = torrent
    torrent.save()
    add_log(
        message=f"Torrent {torrent_to_log(torrent)} with hash: <i>'{torrent.hash}'</i> was added from search result: <i>'{result.query}'</i>",
        level="INFO",
        source="torboxapi",
        torrent=torrent,
    )


def request_dl(torrent_id, api=None, aria_api=None):
    logger = logging.getLogger("torbox")

    def validate_torrent(torrent_id):
        try:
            torrent = Torrent.objects.get(
                pk=torrent_id, client=TORBOX_CLIENT, download_finished=True
            )
            if not torrent.internal_id:
                logger.error(f"Torrent have no internal id: {torrent}")
                add_log(
                    message=f"Torrent have no internal id: {torrent_to_log(torrent)}",
                    level="ERROR",
                    source="torboxapi",
                    torrent=torrent,
                )
                return None
            return torrent
        except Exception as e:
            logger.warning(
                f"Can not find torrent to download: {torrent_id} for {TORBOX_CLIENT} and finished download"
            )
            add_log(
                message=f"Can not find torrent to download: {torrent_id} for {TORBOX_CLIENT} and finished download",
                level="WARNING",
                source="torboxapi",
            )
            return None

    def validate_files(torrent_files):
        result = []
        for file in torrent_files:
            logger.debug(file)
            if not file.internal_id:
                logger.error(f"Torrent file: {file} has no internal id, stoping")
                add_log(
                    message=f"Torrent file: {torrent_file_to_log(file)} has no internal id",
                    level="ERROR",
                    source="torboxapi",
                    torrent=torrent,
                )
                return []
            if file.aria:
                logger.info(f"Torrent file: {file} already has aria id")
                add_log(
                    message=f"Torrent file: {torrent_file_to_log(file)} already has aria id",
                    level="INFO",
                    source="torboxapi",
                    torrent=torrent,
                )
                continue
            logger.info(
                f"torrent_id: {torrent.internal_id}, file_id: {file.internal_id}"
            )
            result.append(file)
        return result

    torrent = validate_torrent(torrent_id=torrent_id)
    if not torrent:
        return
    logger.info(f"Torrent to local download: {torrent}")
    torrent_files = TorrentFile.objects.filter(torrent=torrent)
    files = validate_files(torrent_files=torrent_files)
    if not files:
        return
    if not api:
        api = TorBoxApi()
    if not aria_api:
        aria_api = AriaApi()
    request_data = []
    for file in files:
        result = api.request_download_link(torrent=torrent, file=file)
        logger.debug(result)
        if not result:
            logger.error("Stoping requests for download links")
            return
        request_data.append(
            {
                "url": result,
                "path": f"{config.ARIA2_DIR}/{prepare_torrent_dir_name(torrent.name)}",
                "file": file,
            }
        )

    # fixme: in case of an error, do we want to do something about files that already were requested? Aria is probably down, so not here.
    for request in request_data:
        url = request["url"]
        path = request["path"]
        file = request["file"]
        ok, aria_id = aria_api.download_file(
            link=url, target_name=file.short_name, target_folder=path, torrent=torrent
        )
        if not ok:
            logger.error(f"Could not request Aria to download file: {url}, stopping")
            return
        aria_download_status = AriaDownloadStatus.objects.create(
            internal_id=aria_id, path=path
        )
        file.aria = aria_download_status
        file.save()
        add_log(
            message=f"Torrent file: {torrent_file_to_log(file)} for torrent: {torrent_to_log(torrent)} send to Aria for download with id: <i>'{aria_id}'</i> and path: <i>'{path}'</i>",
            level="INFO",
            source="torboxapi",
            torrent=torrent,
            local_status="Aria: New",
        )
    torrent.local_download = True
    torrent.save()


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
        level="INFO",
        source="torboxapi",
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
    from .referral import refferal_code

    return api.add_referral(refferal_code)


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


def update_torrent_list(api=None):
    if not api:
        api = TorBoxApi()
    no_type = TorrentType.objects.get(name="No Type")
    from .tasks import torbox_request_torrent_files

    logger = logging.getLogger("torbox")
    data = api.get_torrent_list()
    if not data:
        return None

    not_deleted = []
    for entry in data:
        new_torrent = map_torbox_entry_to_torrent(entry, no_type=no_type)
        torrent = update_torrent(new_torrent)
        if not TorrentHistory.objects.filter(torrent=torrent).exists():
            add_log(
                message=f"TorBox is working",
                level="INFO",
                source="torboxapi",
                torrent=torrent,
                local_status="TorBox: In progress",
            )
        previous_activity = TorrentHistory.objects.filter(
            torrent=torrent, updated_at=entry.updated_at
        )
        if not previous_activity.exists():
            torrent_history = map_torbox_entry_to_torrent_history(entry, torrent)
            if new_torrent.download_finished:
                torrent_history.progress = 1
            torrent_history.save()
        else:
            logger.debug("Torrent wasn't active from last check")

        if entry.files and not TorrentFile.objects.filter(torrent=torrent):
            logger.debug(f"Updating files for: {torrent.name}")
            for file in entry.files:
                logger.debug(file)
                TorrentFile.objects.create(
                    torrent=torrent,
                    name=file.name,
                    short_name=file.short_name,
                    size=file.size,
                    hash=file._kwargs["hash"],
                    mime_type=file.mimetype,
                    internal_id=file.id_,
                )

            if torrent.download_finished:
                add_log(
                    f"Torrent: {torrent_to_log(torrent)} finished on TorBox, adding to Aria2c",
                    level="INFO",
                    source="torboxapi",
                    local_status="TorBox: done",
                    torrent=torrent,
                )
                torbox_request_torrent_files.enqueue(torrent.id)

        not_deleted.append(torrent)
    mark_deleted_torrents(not_deleted, clients=[TRANSMISSION_CLIENT])
