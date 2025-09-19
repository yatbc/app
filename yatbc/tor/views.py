import logging
import time
from datetime import datetime, date, timedelta

from .common import shorten_torrent_name
from django.forms.models import model_to_dict
from django.http import HttpResponse
from django.http import JsonResponse
from django.template import loader
from django.http import StreamingHttpResponse
from constance import config
from django.shortcuts import redirect
from django_tasks import default_task_backend
from pathlib import Path
from django.utils import timezone
import json
import requests
from django.db import IntegrityError
from .queuemgr import get_queue_folders, get_active_queue, get_queue_count
from .common import get_name_from_magnet
from .commondao import (
    get_active_torrents_with_formatted_age,
    format_age,
    get_history_with_age,
)
from .arrmanager import get_all_arrs
from .models import (
    Torrent,
    TorrentHistory,
    TorrentTorBoxSearchResult,
    TorrentTorBoxSearch,
    TorrentType,
    ErrorLog,
    TorrentFile,
    TorrentQueue,
    ArrMovieSeries,
)
from .tasks import (
    queue_torbox_status,
    torbox_request_torrent_files,
    queue_scheduler,
    torbox_search,
    add_torbox_torrent,
    change_torrent_task,
    double_torrent_task,
    add_magnet,
    check_status,
    get_task,
    get_tasks,
    not_status_checking,
    ResultStatus,
    queue_import_from_queue_folders,
    process_arr_task,
)

from .torboxapi import validate_api, add_referral_api
from .ariaapi import validate_aria_api
from .transmissionapi import validate_transmission_api
from .stashapi import validate_stash_api


def data_updates(request):
    def wait_for_done(previous_path, timeout=10):
        logger = logging.getLogger("torbox")
        active_tasks = [
            item
            for item in get_tasks(
                exclude_tasks_type=not_status_checking,
                status=[ResultStatus.RUNNING],
            )
        ]
        if not active_tasks:
            return None, ""
        path = active_tasks[0].task_path
        for i in range(0, timeout):
            task = get_task(path, [ResultStatus.RUNNING])
            if not task:
                logger.debug(f"Task {path} is done")
                return True, ""
            time.sleep(1)
            if previous_path == path:
                logger.debug(f"Long running task: {path}")
                yield f"data: {json.dumps({'status': 'LongRunning', 'task': path})}\n\n"
                continue
            yield f"data: {json.dumps({'status': 'TaskStillWorking', 'task': path})}\n\n"
        return False, path

    def event_stream():
        logger = logging.getLogger("torbox")
        # fixme: if tasks in queue are quick to finish, there will be no notification about finished task
        try:
            path = ""
            no_active_tasks_count = 0
            worker_not_responding_threshold = 10
            previous_done_tasks_count = 0
            current_done_tasks_count = 0
            while True:
                task_done, path = yield from wait_for_done(previous_path=path)
                if task_done is None:
                    no_active_tasks_count += 1
                else:
                    no_active_tasks_count = 0
                previous_done_tasks_count = current_done_tasks_count
                current_done_tasks_count = get_tasks(
                    exclude_tasks_type=not_status_checking,
                    status=[ResultStatus.SUCCEEDED, ResultStatus.FAILED],
                ).count()

                queued_tasks = [
                    item
                    for item in get_tasks(
                        exclude_tasks_type=not_status_checking,
                        status=[ResultStatus.READY],
                    )
                ]

                if (
                    queued_tasks
                    and no_active_tasks_count > worker_not_responding_threshold
                ):
                    yield f"data: {json.dumps({'status': 'NoWorker', 'task': queued_tasks[0].task_path})}\n\n"
                    time.sleep(2)
                    continue

                if not queued_tasks and (
                    task_done or current_done_tasks_count > previous_done_tasks_count
                ):
                    if (
                        current_done_tasks_count > previous_done_tasks_count
                        and not task_done
                    ):
                        logger.debug(
                            f"Current done tasks count: {current_done_tasks_count}, previous done tasks count: {previous_done_tasks_count}"
                        )
                    yield f"data: {json.dumps({'status': 'Update'})}\n\n"
                    time.sleep(2)
                    continue

                if queued_tasks:
                    time.sleep(2)
                    continue

                yield f"data: {json.dumps({'status': 'NoTasks'})}\n\n"
                time.sleep(2)
        except GeneratorExit:
            logger.info("Event stream closed")
        except Exception as e:
            logger.error(f"Error in event stream: {e}")

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")


# API Endpoints


def search_torrent_api(request, query, season=0, episode=0):
    logger = logging.getLogger("torbox")
    logger.info(f"Search torrent: {query} {season} {episode}")
    result = torbox_search.enqueue(query)
    logger.info("Task enqueued")
    return JsonResponse({"request_id": result.id}, safe=False)


def get_config(request):
    logger = logging.getLogger("torbox")
    logger.info("Loading config")
    folders = TorrentType.objects.all()
    torrent_types = [model_to_dict(entry) for entry in folders]
    config_data = {
        "configuration": {
            "QUEUE_DIR": config.QUEUE_DIR,
            "USE_TRANSMISSION": config.USE_TRANSMISSION,
            "TRANSMISSION_HOST": config.TRANSMISSION_HOST,
            "TRANSMISSION_PORT": config.TRANSMISSION_PORT,
            "TRANSMISSION_USER": config.TRANSMISSION_USER,
            "TRANSMISSION_DIR": config.TRANSMISSION_DIR,
            "ARIA2_HOST": config.ARIA2_HOST,
            "ARIA2_PORT": config.ARIA2_PORT,
            "ARIA2_DIR": config.ARIA2_DIR,
            "ARIA2_SECRET_SET": len(config.ARIA2_PASSWORD) > 0,
            "TORBOX_HOST": config.TORBOX_HOST,
            "USE_CDN": config.USE_CDN,
            "TORBOX_API": config.TORBOX_API,
            "TORBOX_SEARCH_API": config.TORBOX_SEARCH_API,
            "TORBOX_API_KEY_SET": len(config.TORBOX_API_KEY) > 0,
            "USE_DARK": config.USE_DARK,
            "CLEAN_ACTIVE_DOWNLOADS_POLICY": config.CLEAN_ACTIVE_DOWNLOADS_POLICY,
            "ORGANIZE_MOVIE_SERIES": config.ORGANIZE_MOVIE_SERIES,
            "ORGANIZE_MOVIES": config.ORGANIZE_MOVIES,
            "RESCAN_STASH_ON_HOME_VIDEO": config.RESCAN_STASH_ON_HOME_VIDEO,
            "STASH_HOST": config.STASH_HOST,
            "STASH_PORT": config.STASH_PORT,
            "STASH_ROOT_DIR": config.STASH_ROOT_DIR,
        },
        "torrent_types": torrent_types,
    }

    return JsonResponse(config_data, safe=False)


def get_torrent_speed_history(request, id):
    logger = logging.getLogger("torbox")
    logger.info(f"Loading torrent speed history for id: {id}")
    try:
        torrent = Torrent.objects.get(id=id)
        history = TorrentHistory.objects.filter(torrent=torrent).order_by("-updated_at")
        if not history:
            logger.warning(f"No history found for torrent id: {id}")
            return JsonResponse({"error": "No history found"}, safe=False)

        data = [
            {"x": entry.updated_at.isoformat(), "y": entry.download_speed}
            for entry in history
        ]
        return JsonResponse(data, safe=False)
    except Torrent.DoesNotExist:
        logger.error(f"Torrent with id {id} does not exist")
        return JsonResponse({"error": "Torrent not found"}, safe=False)


def get_torrent_log(request, id):
    logger = logging.getLogger("torbox")
    logger.info(f"Loading torrent logs for id: {id}")
    try:
        torrent = Torrent.objects.get(id=id)
        error_logs = (
            ErrorLog.objects.filter(torrenterrorlog__torrent=torrent)
            .prefetch_related("level")
            .order_by("-created_at")
        )

        logs = [
            {
                "id": entry.id,
                "message": entry.message,
                "source": entry.source,
                "level": entry.level.name,
                "created_at": entry.created_at.isoformat(),
                "torrent_id": id,
            }
            for entry in error_logs
        ]
        return JsonResponse(logs, safe=False)
    except Torrent.DoesNotExist:
        logger.error(f"Torrent with id {id} does not exist")
        return JsonResponse({"error": "Torrent not found"}, safe=False)


def get_torrent_seeders_history(request, id):
    logger = logging.getLogger("torbox")
    logger.info(f"Loading torrent seed history for id: {id}")
    try:
        torrent = Torrent.objects.get(id=id)
        history = TorrentHistory.objects.filter(torrent=torrent).order_by("-updated_at")
        if not history:
            logger.warning(f"No history found for torrent id: {id}")
            return JsonResponse({"error": "No history found"}, safe=False)

        seeds = [
            {"x": entry.updated_at.isoformat(), "y": entry.seeds} for entry in history
        ]
        peers = [
            {"x": entry.updated_at.isoformat(), "y": entry.peers} for entry in history
        ]
        return JsonResponse({"seeds": seeds, "peers": peers}, safe=False)
    except Torrent.DoesNotExist:
        logger.error(f"Torrent with id {id} does not exist")
        return JsonResponse({"error": "Torrent not found"}, safe=False)


def get_torrent_details(request, id):
    logger = logging.getLogger("torbox")
    logger.info(f"Loading torrent details for id: {id}")
    try:
        torrent = Torrent.objects.get(id=id)
        torrent_history = (
            TorrentHistory.objects.filter(torrent=torrent)
            .order_by("-updated_at")
            .first()
        )
        if not torrent_history:
            logger.error(f"Torrent: {torrent.id} has no history!")
            return JsonResponse({"error": "Torrent has no history"}, safe=False)
        files = TorrentFile.objects.filter(torrent=torrent).prefetch_related("aria")
        files_with_aria = []
        for file in files:
            entry = model_to_dict(file)
            if file.aria:
                entry["aria"] = model_to_dict(file.aria)
            else:
                entry["aria"] = {"status": "Waiting", "error": ""}
            files_with_aria.append(entry)
        result = {
            "torrent": model_to_dict(torrent),
            "history": model_to_dict(torrent_history),
            "files": files_with_aria,
        }
        return JsonResponse(result, safe=False)
    except Torrent.DoesNotExist:
        logger.error(f"Torrent with id {id} does not exist")
        return JsonResponse({"error": "Torrent not found"}, safe=False)


def add_referral(request):
    logger = logging.getLogger("torbox")
    result, status = add_referral_api()
    if result:
        logger.info(f"Referral added: {status}")
        return JsonResponse({"status": "Referral added successfully"}, safe=False)
    else:
        logger.error(f"Failed to add referral: {status}")
        return JsonResponse({"error": status}, safe=False)


def get_history(request, current=0, limit=20):
    if current < 0:
        current = 0
    if limit < 0:
        limit = 1
    logger = logging.getLogger("torbox")
    logger.info("Loading history")
    history = Torrent.objects.filter(deleted=True).order_by("-created_at", "-name")[
        current : current + limit
    ]
    result = []
    for entry in history:
        entry = shorten_torrent_name(entry)
        entry = model_to_dict(entry)
        result.append(entry)

    return JsonResponse({"history": result}, safe=False)


def remove_arr(request, arr_id: int):
    arr = ArrMovieSeries.objects.filter(id=arr_id)
    if arr:
        arr.delete()
        return JsonResponse({"status": "Ok"}, safe=False)
    return JsonResponse({"error": f"Arr: {arr_id} didn't exist"}, safe=False)


def change_arr_activity(request, arr_id: int):
    arr = ArrMovieSeries.objects.filter(id=arr_id).first()
    if arr:
        arr.active = not arr.active
        arr.save()
        return JsonResponse({"status": "Ok"}, safe=False)
    return JsonResponse({"error": f"Arr: {arr_id} doesn't exist"}, safe=False)


def save_arr(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        logger.debug(f"Save arr request body: {body}, type: {type(body)}")
        if "imdbid" in body:
            imdbid = body["imdbid"]
            quality = body.get("quality", "")
            include_words = body.get("include_words", "")
            exclude_words = body.get("exclude_words", "")
            season = body.get("requested_season", 1)
            episode = body.get("requested_episode", 1)
            encoder = body.get("encoder", "")
            id = body.get("id", None)
            torrent_type = TorrentType.objects.get_movie_series()
            if id:
                arr = ArrMovieSeries.objects.get(pk=id)
                arr.imdbid = imdbid
                arr.quality = quality
                arr.include_words = include_words
                arr.exclude_words = exclude_words
                arr.requested_season = season
                arr.requested_episode = episode
                arr.encoder = encoder
                arr.save()
            else:
                try:
                    arr = ArrMovieSeries.objects.create(
                        imdbid=imdbid,
                        quality=quality,
                        encoder=encoder,
                        include_words=include_words,
                        exclude_words=exclude_words,
                        requested_season=season,
                        requested_episode=episode,
                        torrent_type=torrent_type,
                    )
                except IntegrityError as e:
                    return JsonResponse({"error": "Imdbid already existed"}, safe=False)
            return JsonResponse(model_to_dict(arr), safe=False)

        else:
            logger.warning(f"Wrong body in save_arr: {body}")
    return JsonResponse({"error": "Invalid request"}, safe=False)


def retry_arr(request, arr_id: int):
    process_arr_task.enqueue(arr_id)
    return JsonResponse(
        {"status": "Ok"}, safe=False
    )  # don't return task id, arr, doesn't monitor task statuses


def get_arr(request, current=0, limit=20):
    if current < 0:
        current = 0
    if limit < 0:
        limit = 1
    logger = logging.getLogger("torbox")
    logger.info("Loading arr")
    arr = get_all_arrs()
    arr = arr[current : current + limit]
    result = []
    for entry in arr:
        dict_entry = model_to_dict(entry)
        dict_entry["last_found_ago"] = (
            format_age(entry.last_found_ago.total_seconds())
            if entry.last_found_ago
            else ""
        )
        dict_entry["last_checked_ago"] = (
            format_age(entry.last_checked_ago.total_seconds())
            if entry.last_checked_ago
            else ""
        )
        result.append(dict_entry)

    return JsonResponse(
        {
            "arr": result,
            "defaultArr": model_to_dict(ArrMovieSeries.objects.get(imdbid="DEFAULT")),
        },
        safe=False,
    )


def get_logs(request, current=0, limit=20):
    logger = logging.getLogger("torbox")
    if current < 0:
        current = 0
    if limit < 0:
        limit = 1
    logger.info("Loading logs")
    logs = (
        ErrorLog.objects.all()
        .prefetch_related("torrenterrorlog_set")
        .prefetch_related("level")
        .order_by("-created_at")[current : current + limit]
    )
    logs = [
        {
            "id": entry.id,
            "message": entry.message,
            "source": entry.source,
            "level": entry.level.name,
            "created_at": entry.created_at.isoformat(),
            "torrent_id": (
                entry.torrenterrorlog_set.first().torrent.id
                if entry.torrenterrorlog_set.first()
                else None
            ),
        }
        for entry in logs
    ]
    result = {"log": logs}
    return JsonResponse(result, safe=False)


def delete_queue(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        logger.debug(f"Delete queue request body: {body}, type: {type(body)}")
        if "command" in body:
            if body["command"] == "single" and "queue_id" in body:
                id = body["queue_id"]
                TorrentQueue.objects.filter(id=id).delete()
                logger.info(f"Queue entry for: {id} removed")
                return JsonResponse(
                    {"status": f"Queue for id: {id} deleted"}, safe=False
                )
        else:
            return JsonResponse({"error": "Wrong request"}, status=400)
    return JsonResponse({"error": "Invalid request"}, status=400)


def delete_history(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        logger.debug(f"Delete history request body: {body}, type: {type(body)}")
        if "command" in body:
            if body["command"] == "single" and "torrent_id" in body:
                id = body["torrent_id"]
                Torrent.objects.filter(id=id).delete()
                logger.info(f"History for: {id} removed")
                return JsonResponse({"status": f"History for id deleted"}, safe=False)
            if body["command"] == "older":
                Torrent.objects.filter(
                    deleted=True, created_at__lte=timezone.now() - timedelta(days=30)
                ).delete()
                logger.info("History older than 14 days deleted")
                return JsonResponse(
                    {"status": "History created older than 30 days deleted"}, safe=False
                )
            elif body["command"] == "all":
                Torrent.objects.filter(deleted=True).delete()
                logger.info("All history deleted")
                return JsonResponse({"status": "All history deleted"}, safe=False)
        else:
            return JsonResponse({"error": "Wrong request"}, status=400)
    return JsonResponse({"error": "Invalid request"}, status=400)


def delete_logs(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        logger.debug(f"Delete logs request body: {body}, type: {type(body)}")
        if "command" in body:
            if body["command"] == "single" and "torrent_id" in body:
                id = body["torrent_id"]
                ErrorLog.objects.filter(torrenterrorlog__torrent_id=id).delete()
                logger.info(f"Logs related to torrent: {id} deleted")
                return JsonResponse(
                    {"status": "Logs related to selected torrent deleted"}, safe=False
                )
            if body["command"] == "older":
                ErrorLog.objects.filter(
                    created_at__lte=timezone.now() - timedelta(days=14)
                ).delete()
                logger.info("Logs older than 14 days deleted")
                return JsonResponse(
                    {"status": "Logs older than 14 days deleted"}, safe=False
                )
            elif body["command"] == "all":
                ErrorLog.objects.all().delete()
                logger.info("All logs deleted")
                return JsonResponse({"status": "All logs deleted"}, safe=False)
        else:
            return JsonResponse({"error": "Wrong request"}, status=400)
    return JsonResponse({"error": "Invalid request"}, status=400)


def save_config(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        if "USE_TRANSMISSION" in body:
            result = body
            config.USE_TRANSMISSION = result.get(
                "USE_TRANSMISSION", config.USE_TRANSMISSION
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
            config.QUEUE_DIR = result.get("QUEUE_DIR", config.QUEUE_DIR)
            config.ARIA2_DIR = result.get("ARIA2_DIR", config.ARIA2_DIR)
            config.ARIA2_HOST = result.get("ARIA2_HOST", config.ARIA2_HOST)
            config.ARIA2_PORT = result.get("ARIA2_PORT", config.ARIA2_PORT)
            config.TORBOX_HOST = result.get("TORBOX_HOST", config.TORBOX_HOST)
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

            logger.info(f"Configuration saved: {result}")
            return JsonResponse({"status": "Ok"}, safe=False)
        logger.warning(f"Wrong body in save_config: {body}")
    return JsonResponse({"error": "Invalid request"}, status=400)


def validate_stash(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        if "STASH_HOST" in body:
            result = body
            STASH_HOST = result.get("STASH_HOST", config.STASH_HOST)
            STASH_PORT = result.get("STASH_PORT", config.STASH_PORT)
            STASH_ROOT_DIR = result.get("STASH_ROOT_DIR", config.STASH_ROOT_DIR)
            ok, response = validate_stash_api(
                STASH_HOST, STASH_PORT, "", STASH_ROOT_DIR
            )

            logger.info(f"Stash validation: {ok}, {response}")
            if ok:
                return JsonResponse({"status": ok}, safe=False)
            else:
                logger.error(f"Stash validation failed: {response}")
                return JsonResponse({"error": response}, safe=False)
        logger.warning(f"Wrong body in validate_stash: {body}")
    return JsonResponse({"error": "Invalid request"}, status=400)


def validate_torbox(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        if "TORBOX_API" in body:
            result = body
            TORBOX_API = result.get("TORBOX_API", config.TORBOX_API)
            TORBOX_SEARCH_API = result.get(
                "TORBOX_SEARCH_API", config.TORBOX_SEARCH_API
            )
            TORBOX_API_KEY = result.get("TORBOX_API_KEY", config.TORBOX_API_KEY)
            TORBOX_HOST = result.get("TORBOX_HOST", config.TORBOX_HOST)
            ok, response, reason = validate_api(TORBOX_API, TORBOX_HOST, TORBOX_API_KEY)

            logger.info(f"TorBox validation: {ok}, {response}")
            if ok:
                return JsonResponse({"status": ok}, safe=False)
            else:
                logger.error(f"TorBox validation failed: {response}")
                return JsonResponse({"error": response, "reason": reason}, safe=False)
        logger.warning(f"Wrong body in validate_torbox: {body}")
    return JsonResponse({"error": "Invalid request"}, status=400)


def validate_aria(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        if "ARIA2_HOST" in body:
            result = body
            ARIA2_DIR = result.get("ARIA2_DIR", config.ARIA2_DIR)
            WRONG_ARIA2_DIR = 1
            if not Path(ARIA2_DIR).exists():
                logger.error(f"ARIA2_DIR: {ARIA2_DIR} does not exist")
                return JsonResponse(
                    {
                        "error": f"Aria validation failed: ARIA2_DIR: {ARIA2_DIR} doesn't exist or is not accessible",
                        "reason": WRONG_ARIA2_DIR,
                    },
                    safe=False,
                )
            ARIA2_HOST = result.get("ARIA2_HOST", config.ARIA2_HOST)
            ARIA2_PORT = result.get("ARIA2_PORT", config.ARIA2_PORT)
            ARIA2_PASSWORD = result.get("ARIA2_PASSWORD", config.ARIA2_PASSWORD)
            ok, response, reason = validate_aria_api(
                ARIA2_HOST, ARIA2_PORT, ARIA2_PASSWORD
            )

            logger.info(f"Aria validation: {ok}, {response}")
            if ok:
                return JsonResponse({"status": ok}, safe=False)
            else:
                logger.error(f"Aria validation failed: {response}")
                return JsonResponse({"error": response, "reason": reason}, safe=False)
        logger.warning(f"Wrong body in validate_aria: {body}")
    return JsonResponse({"error": "Invalid request"}, status=400)


def test_ip(request):
    logger = logging.getLogger("torbox")
    result = requests.get("http://ip-api.com/json/?fields=status,message,query,isp,org")
    # todo: add ip test for db_worker
    if result.ok:
        json_result = json.loads(result.content)
        if json_result["status"] == "success":
            logger.info(f"IP test success: {json_result}")
            return JsonResponse(
                {
                    "status": "success",
                    "ip": json_result["query"],
                    "isp": json_result["isp"],
                    "org": json_result["org"],
                },
                safe=False,
            )
        else:
            logger.error(f"IP test failed: {json_result['message']}")
            return JsonResponse(
                {"error": f"IP test failed: {json_result['message']}"}, safe=False
            )
    else:
        logger.error("Could not get result from ip-api.com")
        return JsonResponse({"error": f"Could not connect to ip-api.com"}, safe=False)


def validate_queue_folders(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        if "QUEUE_DIR" in body:
            result = body
            QUEUE_DIR = result.get("QUEUE_DIR", config.QUEUE_DIR)

            if not Path(QUEUE_DIR).exists():
                logger.error(f"QUEUE_DIR: {QUEUE_DIR} does not exist")
                return JsonResponse(
                    {
                        "error": f"Queue validation failed: QUEUE_DIR: {QUEUE_DIR} doesn't exist or is not accessible",
                        "reason": 1,
                    },
                    safe=False,
                )
            for path, _ in get_queue_folders():
                if not path.exists():
                    logger.error(f"What sorcery is this? {path} does not exist")

            return JsonResponse({"status": True}, safe=False)
        logger.warning(f"Wrong body in validate_queue_folders: {body}")
    return JsonResponse({"error": "Invalid request"}, status=400)


def validate_transmission(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        if "TRANSMISSION_HOST" in body:
            result = body
            TRANSMISSION_HOST = result.get(
                "TRANSMISSION_HOST", config.TRANSMISSION_HOST
            )
            TRANSMISSION_PORT = result.get(
                "TRANSMISSION_PORT", config.TRANSMISSION_PORT
            )
            TRANSMISSION_USER = result.get(
                "TRANSMISSION_USER", config.TRANSMISSION_USER
            )
            TRANSMISSION_DIR = result.get("TRANSMISSION_DIR", config.TRANSMISSION_DIR)
            TRANSMISSION_PASSWORD = result.get(
                "TRANSMISSION_PASSWORD", config.TRANSMISSION_PASSWORD
            )
            if not Path(TRANSMISSION_DIR).exists():
                logger.error(f"TRANSMISSION_DIR: {TRANSMISSION_DIR} does not exist")
                return JsonResponse(
                    {
                        "error": f"Transmission validation failed: TRANSMISSION_DIR: {TRANSMISSION_DIR} doesn't exist or is not accessible",
                        "reason": 1,
                    },
                    safe=False,
                )
            ok, response, reason = validate_transmission_api(
                TRANSMISSION_HOST,
                TRANSMISSION_PORT,
                TRANSMISSION_USER,
                TRANSMISSION_PASSWORD,
            )

            logger.info(f"Transmission validation: {ok}, {response}")
            if ok:
                return JsonResponse({"status": ok}, safe=False)
            else:
                logger.error(f"Transmission validation failed: {response}")
                return JsonResponse({"error": response, "reason": reason}, safe=False)
        logger.warning(f"Wrong body in validate_Transmission: {body}")
    return JsonResponse({"error": "Invalid request"}, status=400)


def validate_folders(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        if "TRANSMISSION_HOST" in body:
            result = body
            types = result.get("TORRENT_TYPES", {}).items()
            logger.debug(types)
            errors = []
            folders_valid = {}
            for type in types:
                type = type[1]
                logger.debug(f"Processing torrent type: {type}")
                if type["action_on_finish"] == TorrentType.ACTION_DO_NOTHING:
                    folders_valid[type["id"]] = True
                elif "target_dir" in type and type["target_dir"] is not None:
                    target_dir = Path(type["target_dir"])
                    if not target_dir.exists():
                        error = f"Target directory: {target_dir} does not exist"
                        logger.error(error)
                        folders_valid[type["id"]] = False
                        errors.append(error)
                    else:
                        folders_valid[type["id"]] = True
                else:
                    error = f"Target directory for type '{type['name']}' is not set."
                    logger.error(error)
                    folders_valid[type["id"]] = False
                    errors.append(error)

            if errors:
                return JsonResponse(
                    {"error": "; ".join(errors), "folders_valid": folders_valid},
                    safe=False,
                )
            else:
                logger.info("All folders are valid")
                return JsonResponse(
                    {"status": "Ok", "folders_valid": folders_valid}, safe=False
                )

        logger.warning(f"Wrong body in validate_Transmission: {body}")
    return JsonResponse({"error": "Invalid request"}, status=400)


def add_torrent_from_search(request, id):
    logger = logging.getLogger("torbox")
    logger.info("Adding torrent")
    result = add_torbox_torrent.enqueue(id)
    result = queue_torbox_status()
    logger.info("Task enqueued")
    return JsonResponse({"request_id": result.id}, safe=False)


def double_torrent_api(request, id):
    logger = logging.getLogger("torbox")
    logger.info("Doubling torrent")
    result = double_torrent_task.enqueue(id)
    logger.info("Task enqueued")
    return JsonResponse({"request_id": result.id}, safe=False)


def get_search_results(request, query, season=0, episode=0):
    torrent = TorrentTorBoxSearch.objects.filter_by_query_season_episode(
        query=query, season=season, episode=episode
    ).order_by("-date")
    if not torrent:
        return JsonResponse({"torrents": {}}, safe=False)
    result = TorrentTorBoxSearchResult.objects.filter(query=torrent[0]).order_by(
        "-torrent", "-cached", "raw_title"
    )
    return JsonResponse(
        {"torrents": [model_to_dict(entry) for entry in result]}, safe=False
    )


def get_torrents():
    torrent_with_latest_details = get_active_torrents_with_formatted_age()
    result = []
    summary = {"down": 0, "up": 0}
    for torrent_instance in torrent_with_latest_details:
        latest_history = None
        if torrent_instance.latest_history_id:
            latest_history = get_history_with_age(torrent_instance.latest_history_id)
            latest_history.last_updated_ago = format_age(
                latest_history.ago.total_seconds()
            )
        torrent_instance = shorten_torrent_name(torrent_instance)
        summary["down"] += latest_history.download_speed
        summary["up"] += latest_history.upload_speed
        torrent = model_to_dict(torrent_instance)
        torrent["formatted_age"] = torrent_instance.formatted_age

        history = model_to_dict(latest_history)
        history["last_updated_ago"] = latest_history.last_updated_ago
        torrent["local_status"] = model_to_dict(torrent_instance.local_status)
        torrent["local_status"]["level"] = model_to_dict(
            torrent_instance.local_status.level
        )
        result.append(
            {
                "torrent": torrent,
                "history": history,
            }
        )
    return result, summary


def update_queue_folders(request):
    logger = logging.getLogger("torbox")
    result = queue_import_from_queue_folders()
    return JsonResponse({"request_id": result.id}, safe=False)


def update_torrent_list(request):
    logger = logging.getLogger("torbox")
    result = check_status()
    queue_scheduler()
    return JsonResponse({"request_id": result.id}, safe=False)


def get_torrent_type_list(request):
    logger = logging.getLogger("torbox")
    if request.method == "GET":
        torrent_types = [model_to_dict(entry) for entry in TorrentType.objects.all()]
        logger.info(f"Returning torrent types: {torrent_types}")
        return JsonResponse({"torrent_types": torrent_types}, safe=False)
    return JsonResponse({"error": "Invalid request method"}, status=400)


def get_torrent_list(request):
    logger = logging.getLogger("torbox")
    if request.method == "GET":
        result, summary = get_torrents()
        torrent_types = [model_to_dict(entry) for entry in TorrentType.objects.all()]
        return JsonResponse(
            {
                "torrents": result,
                "summary": summary,
                "torrent_types": torrent_types,
                "queue_size": get_queue_count(),
            },
            safe=False,
        )
    return JsonResponse({"error": "Invalid request method"}, status=400)


def api_get_active_queue(request):
    logger = logging.getLogger("torbox")
    if request.method == "GET":
        result = get_active_queue()
        queue = [
            {
                "id": entry.id,
                "magnet": get_name_from_magnet(entry.magnet),
                "torrent_file": entry.torrent_file_name,
                "added_at": entry.added_at.isoformat(),
                "priority": entry.priority,
                "torrent_type_id": entry.torrent_type.id,
            }
            for entry in result
        ]
        return JsonResponse(
            {"queue": queue},
            safe=False,
        )
    return JsonResponse({"error": "Invalid request method"}, status=400)


def change_torrent_api(request, action, id):
    logger = logging.getLogger("torbox")
    actions = ["delete", "reannounce", "resume"]
    if action not in actions:
        logger.warning(f"Wrong action: {action}")
        return JsonResponse(
            {"error": f'Invalid action: {action}, known are: {",".join(actions)}'},
            status=400,
        )
    if request.method == "GET":
        if action == "delete":
            torrent = Torrent.objects.get(pk=id)
            torrent.deleted = True
            torrent.save()
            logger.debug(f"Torrent: {torrent} internally deleted")
        result = change_torrent_task.enqueue(action, id)
        return JsonResponse({"request_id": result.id}, safe=False)
    return JsonResponse({"error": "Invalid request method"}, status=400)


def add_torrent_api(request):
    logger = logging.getLogger("torbox")
    if request.method == "POST":
        body = json.loads(request.body)
        if "client" in body and "magnet" in body and "torrent_type_id" in body:
            result = add_magnet.enqueue(
                body["client"], body["magnet"], body["torrent_type_id"]
            )
            return JsonResponse({"request_id": result.id}, safe=False)
        logger.warning(f"Wrong body in add_torrent_api: {body}")
    return JsonResponse({"error": "Invalid request"}, status=400)


def download_torrent_files(request, id):
    result = torbox_request_torrent_files.enqueue(id)
    return JsonResponse({"request_id": result.id}, safe=False)


def update_torrent_type(request, torrent_id, torrent_type_id):
    logger = logging.getLogger("torbox")
    logger.info(f"Updating torrent type: {torrent_type_id} for torrent: {torrent_id}")
    torrent_type = TorrentType.objects.get(pk=torrent_type_id)
    Torrent.objects.filter(pk=torrent_id).update(
        torrent_type=torrent_type
    )  # filter has update
    return JsonResponse({"response": True}, safe=False)


def update_torrent_type_in_queue(request, queue_id, torrent_type_id):
    logger = logging.getLogger("torbox")
    logger.info(f"Updating torrent type: {torrent_type_id} for queue: {queue_id}")
    torrent_type = TorrentType.objects.get(pk=torrent_type_id)
    TorrentQueue.objects.filter(pk=queue_id).update(torrent_type=torrent_type)
    return JsonResponse({"response": True}, safe=False)


def check_task_status_api(request, task_id):
    logger = logging.getLogger("torbox")
    logger.info(f"Checking task status: {task_id}")
    result = default_task_backend.get_result(task_id)
    if result and result.is_finished:
        logger.info(f"Task {task_id} is finished")
        return JsonResponse({"status": "DONE"}, safe=False)
    elif result:
        logger.info(f"Task {task_id} status: {result.status}")
    return JsonResponse({"status": "IN_PROGRESS"}, safe=False)


# Main Views


def index(request):
    if config.SHOW_CONFIG_ON_START:
        return redirect("/config")
    template = loader.get_template("index.html")

    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def configuration(request):
    template = loader.get_template("config.html")
    context = {
        "show_on_start": config.SHOW_CONFIG_ON_START,
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
    }
    return HttpResponse(template.render(context, request))


def error_log(request):
    template = loader.get_template("error_log.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def history(request):
    template = loader.get_template("history.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def torrent_details(request, id):
    torrent = Torrent.objects.get(id=id)
    torrent_history = TorrentHistory.objects.filter(torrent=torrent)
    template = loader.get_template("torrent_details.html")
    context = {
        "torrent_id": torrent.pk,
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def add_torrent(request):
    template = loader.get_template("add_torrent.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def queue(request):
    template = loader.get_template("queue.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
    }
    return HttpResponse(template.render(context, request))


def search_torrent(request, query, season=0, episode=0):
    logger = logging.getLogger("torbox")
    logger.info(f"Searching for: {query} {season} {episode}")
    result = torbox_search.enqueue(query, season, episode)
    template = loader.get_template("torrent_search.html")
    if season != 0:
        query += "/S" + str(season)
    if episode != 0:
        query += "/E" + str(episode)
    context = {
        "query": query,
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
        "task_id": result.id,
        "use_transmission": config.USE_TRANSMISSION,
    }
    return HttpResponse(template.render(context, request))


def arr(request):
    template = loader.get_template("arr.html")
    context = {
        "use_cdn": config.USE_CDN,
        "use_dark": config.USE_DARK,
    }
    return HttpResponse(template.render(context, request))
