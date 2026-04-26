from django.http import JsonResponse
import json
from constance import config
from tor.models import JackettQueryUrl, TorrentType
import logging
from django.forms.models import model_to_dict


def save_config(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        if "USE_TRANSMISSION" in body:
            result = body
            config.USE_TRANSMISSION = result.get(
                "USE_TRANSMISSION", config.USE_TRANSMISSION
            )
            config.TRANSMISSION_SFTP_USER = result.get(
                "TRANSMISSION_SFTP_USER", config.TRANSMISSION_SFTP_USER
            )
            config.TRANSMISSION_SFTP_PORT = result.get(
                "TRANSMISSION_SFTP_PORT", config.TRANSMISSION_SFTP_PORT
            )
            config.TRANSMISSION_SFTP_HOST = result.get(
                "TRANSMISSION_SFTP_HOST", config.TRANSMISSION_SFTP_HOST
            )
            config.TRANSMISSION_HOST = result.get(
                "TRANSMISSION_HOST", config.TRANSMISSION_HOST
            )
            config.TRANSMISSION_PORT = result.get(
                "TRANSMISSION_PORT", config.TRANSMISSION_PORT
            )
            config.TRANSMISSION_USER = result.get(
                "TRANSMISSION_USER", config.TRANSMISSION_USER
            )
            config.TRANSMISSION_DIR = result.get(
                "TRANSMISSION_DIR", config.TRANSMISSION_DIR
            )
            config.CLEAN_ACTIVE_DOWNLOADS_POLICY = result.get(
                "CLEAN_ACTIVE_DOWNLOADS_POLICY", config.CLEAN_ACTIVE_DOWNLOADS_POLICY
            )
            config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TRANSMISSION = result.get(
                "SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TRANSMISSION",
                config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TRANSMISSION,
            )
            config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX = result.get(
                "SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX",
                config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX,
            )
            config.DOWNLOAD_PRIVATE_ON_TRANSMISSION_ONLY = result.get(
                "DOWNLOAD_PRIVATE_ON_TRANSMISSION_ONLY",
                config.DOWNLOAD_PRIVATE_ON_TRANSMISSION_ONLY,
            )
            config.DOWNLOAD_HOME_VIDEOS_TYPE_ON_TRANSMISSION = result.get(
                "DOWNLOAD_HOME_VIDEOS_TYPE_ON_TRANSMISSION",
                config.DOWNLOAD_HOME_VIDEOS_TYPE_ON_TRANSMISSION,
            )
            config.DOWNLOAD_NO_TYPE_ON_TRANSMISSION = result.get(
                "DOWNLOAD_NO_TYPE_ON_TRANSMISSION",
                config.DOWNLOAD_NO_TYPE_ON_TRANSMISSION,
            )
            config.DOWNLOAD_MOVIE_TYPE_ON_TRANSMISSION = result.get(
                "DOWNLOAD_MOVIE_TYPE_ON_TRANSMISSION",
                config.DOWNLOAD_MOVIE_TYPE_ON_TRANSMISSION,
            )
            config.DOWNLOAD_MOVIE_SERIES_TYPE_ON_TRANSMISSION = result.get(
                "DOWNLOAD_MOVIE_SERIES_TYPE_ON_TRANSMISSION",
                config.DOWNLOAD_MOVIE_SERIES_TYPE_ON_TRANSMISSION,
            )
            config.DOWNLOAD_AUDIOBOOKS_TYPE_ON_TRANSMISSION = result.get(
                "DOWNLOAD_AUDIOBOOKS_TYPE_ON_TRANSMISSION",
                config.DOWNLOAD_AUDIOBOOKS_TYPE_ON_TRANSMISSION,
            )
            config.DOWNLOAD_EBOOKS_TYPE_ON_TRANSMISSION = result.get(
                "DOWNLOAD_EBOOKS_TYPE_ON_TRANSMISSION",
                config.DOWNLOAD_EBOOKS_TYPE_ON_TRANSMISSION,
            )
            config.DOWNLOAD_OTHER_TYPE_ON_TRANSMISSION = result.get(
                "DOWNLOAD_OTHER_TYPE_ON_TRANSMISSION",
                config.DOWNLOAD_OTHER_TYPE_ON_TRANSMISSION,
            )
            config.QUEUE_DIR = result.get("QUEUE_DIR", config.QUEUE_DIR)
            config.ARIA2_DIR = result.get("ARIA2_DIR", config.ARIA2_DIR)
            config.ARIA2_HOST = result.get("ARIA2_HOST", config.ARIA2_HOST)
            config.ARIA2_PORT = result.get("ARIA2_PORT", config.ARIA2_PORT)
            config.TORBOX_HOST = result.get("TORBOX_HOST", config.TORBOX_HOST)
            config.COLLECT_PEER_INFO = result.get(
                "COLLECT_PEER_INFO", config.COLLECT_PEER_INFO
            )
            config.USE_CDN = result.get("USE_CDN", config.USE_CDN)
            config.TORBOX_API = result.get("TORBOX_API", config.TORBOX_API)
            config.TORBOX_SEARCH_API = result.get(
                "TORBOX_SEARCH_API", config.TORBOX_SEARCH_API
            )
            config.USE_DARK = result.get("USE_DARK", config.USE_DARK)
            config.SHOW_CONFIG_ON_START = False
            config.ORGANIZE_MOVIE_SERIES = result.get(
                "ORGANIZE_MOVIE_SERIES", config.ORGANIZE_MOVIE_SERIES
            )
            config.ORGANIZE_AUDIOBOOKS_ONLY_CONNECTED_TO_SEARCH = result.get(
                "ORGANIZE_AUDIOBOOKS_ONLY_CONNECTED_TO_SEARCH",
                config.ORGANIZE_AUDIOBOOKS_ONLY_CONNECTED_TO_SEARCH,
            )
            config.ORGANIZE_AUDIOBOOKS = result.get(
                "ORGANIZE_AUDIOBOOKS", config.ORGANIZE_AUDIOBOOKS
            )
            config.ORGANIZE_MOVIES = result.get(
                "ORGANIZE_MOVIES", config.ORGANIZE_MOVIES
            )
            config.STASH_HOST = result.get("STASH_HOST", config.STASH_HOST)
            config.STASH_PORT = result.get("STASH_PORT", config.STASH_PORT)
            config.STASH_ROOT_DIR = result.get("STASH_ROOT_DIR", config.STASH_ROOT_DIR)
            config.RESCAN_STASH_ON_HOME_VIDEO = result.get(
                "RESCAN_STASH_ON_HOME_VIDEO", config.RESCAN_STASH_ON_HOME_VIDEO
            )
            if result.get("TORBOX_API_KEY", None):
                config.TORBOX_API_KEY = result.get("TORBOX_API_KEY", None)
                result["TORBOX_API_KEY"] = "UPDATED"
            if result.get("TRANSMISSION_PASSWORD", None):
                config.TRANSMISSION_PASSWORD = result.get("TRANSMISSION_PASSWORD", None)
                result["TRANSMISSION_PASSWORD"] = "UPDATED"
            if result.get("TRANSMISSION_SFTP_PASSWORD", None):
                config.TRANSMISSION_SFTP_PASSWORD = result.get(
                    "TRANSMISSION_SFTP_PASSWORD", None
                )
                result["TRANSMISSION_SFTP_PASSWORD"] = "UPDATED"
            if result.get("ARIA2_PASSWORD", None):
                config.ARIA2_PASSWORD = result.get("ARIA2_PASSWORD", None)
                result["ARIA2_PASSWORD"] = "UPDATED"
            actions = [
                TorrentType.ACTION_COPY,
                TorrentType.ACTION_MOVE,
                TorrentType.ACTION_DO_NOTHING,
            ]
            for type in result.get("TORRENT_TYPES", {}).items():
                type = type[1]
                logger.debug(f"Processing torrent type: {type}")
                if "id" in type and type["id"] is not None:
                    if type["action_on_finish"] not in actions:
                        logger.warning(
                            f"Invalid action_on_finish: {type['action_on_finish']}, skipping"
                        )
                        continue
                    torrent_type = TorrentType.objects.get(pk=type["id"])
                    torrent_type.action_on_finish = type["action_on_finish"]
                    torrent_type.target_dir = type["target_dir"]
                    torrent_type.save()
            for entry in result.get("JACKETT_QUERY_URLS", {}).items():
                entry = entry[1]  # 0 is torrent_type id, 1 is the dict
                logger.debug(f"Processing Jackett Query Url: {entry}")
                if "id" in entry and entry["id"] is not None:
                    query = JackettQueryUrl.objects.get(pk=entry["id"])
                    query.url = entry["url"]
                    query.save()

            logger.info(f"Configuration saved: {result}")
            return JsonResponse({"status": "Ok"}, safe=False)
        logger.warning(f"Wrong body in save_config: {body}")
    return JsonResponse({"error": "Invalid request"}, status=400)


def get_config(request):
    logger = logging.getLogger("torbox")
    logger.info("Loading config")
    folders = TorrentType.objects.all()
    torrent_types = [model_to_dict(entry) for entry in folders]
    jackett_query_urls = {}
    for entry in JackettQueryUrl.objects.all():
        jackett_query_urls[entry.torrent_type.id] = model_to_dict(
            entry
        )  # at the moment only one url per type is supported

    config_data = {
        "configuration": {
            "SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX": config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX,
            "SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TRANSMISSION": config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TRANSMISSION,
            "QUEUE_DIR": config.QUEUE_DIR,
            "USE_TRANSMISSION": config.USE_TRANSMISSION,
            "TRANSMISSION_HOST": config.TRANSMISSION_HOST,
            "TRANSMISSION_PORT": config.TRANSMISSION_PORT,
            "TRANSMISSION_USER": config.TRANSMISSION_USER,
            "TRANSMISSION_DIR": config.TRANSMISSION_DIR,
            "TRANSMISSION_PASSWORD_SET": len(config.TRANSMISSION_PASSWORD) > 0,
            "TRANSMISSION_SFTP_USER": config.TRANSMISSION_SFTP_USER,
            "TRANSMISSION_SFTP_PORT": config.TRANSMISSION_SFTP_PORT,
            "TRANSMISSION_SFTP_HOST": config.TRANSMISSION_SFTP_HOST,
            "TRANSMISSION_SFTP_PASSWORD_SET": len(config.TRANSMISSION_SFTP_PASSWORD)
            > 0,
            "ARIA2_HOST": config.ARIA2_HOST,
            "ARIA2_PORT": config.ARIA2_PORT,
            "ARIA2_DIR": config.ARIA2_DIR,
            "ARIA2_SECRET_SET": len(config.ARIA2_PASSWORD) > 0,
            "TORBOX_HOST": config.TORBOX_HOST,
            "COLLECT_PEER_INFO": config.COLLECT_PEER_INFO,
            "USE_CDN": config.USE_CDN,
            "TORBOX_API": config.TORBOX_API,
            "TORBOX_SEARCH_API": config.TORBOX_SEARCH_API,
            "TORBOX_API_KEY_SET": len(config.TORBOX_API_KEY) > 0,
            "USE_DARK": config.USE_DARK,
            "CLEAN_ACTIVE_DOWNLOADS_POLICY": config.CLEAN_ACTIVE_DOWNLOADS_POLICY,
            "ORGANIZE_MOVIE_SERIES": config.ORGANIZE_MOVIE_SERIES,
            "ORGANIZE_MOVIES": config.ORGANIZE_MOVIES,
            "ORGANIZE_AUDIOBOOKS_ONLY_CONNECTED_TO_SEARCH": config.ORGANIZE_AUDIOBOOKS_ONLY_CONNECTED_TO_SEARCH,
            "ORGANIZE_AUDIOBOOKS": config.ORGANIZE_AUDIOBOOKS,
            "RESCAN_STASH_ON_HOME_VIDEO": config.RESCAN_STASH_ON_HOME_VIDEO,
            "STASH_HOST": config.STASH_HOST,
            "STASH_PORT": config.STASH_PORT,
            "STASH_ROOT_DIR": config.STASH_ROOT_DIR,
            "DOWNLOAD_PRIVATE_ON_TRANSMISSION_ONLY": config.DOWNLOAD_PRIVATE_ON_TRANSMISSION_ONLY,
            "DOWNLOAD_HOME_VIDEOS_TYPE_ON_TRANSMISSION": config.DOWNLOAD_HOME_VIDEOS_TYPE_ON_TRANSMISSION,
            "DOWNLOAD_NO_TYPE_ON_TRANSMISSION": config.DOWNLOAD_NO_TYPE_ON_TRANSMISSION,
            "DOWNLOAD_MOVIE_TYPE_ON_TRANSMISSION": config.DOWNLOAD_MOVIE_TYPE_ON_TRANSMISSION,
            "DOWNLOAD_MOVIE_SERIES_TYPE_ON_TRANSMISSION": config.DOWNLOAD_MOVIE_SERIES_TYPE_ON_TRANSMISSION,
            "DOWNLOAD_AUDIOBOOKS_TYPE_ON_TRANSMISSION": config.DOWNLOAD_AUDIOBOOKS_TYPE_ON_TRANSMISSION,
            "DOWNLOAD_EBOOKS_TYPE_ON_TRANSMISSION": config.DOWNLOAD_EBOOKS_TYPE_ON_TRANSMISSION,
            "DOWNLOAD_OTHER_TYPE_ON_TRANSMISSION": config.DOWNLOAD_OTHER_TYPE_ON_TRANSMISSION,
        },
        "torrent_types": torrent_types,
        "jackett_query_urls": jackett_query_urls,
    }

    return JsonResponse(config_data, safe=False)
