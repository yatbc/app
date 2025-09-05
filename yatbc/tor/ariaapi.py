import requests
import logging
import json
import shutil
from pathlib import Path
from django.utils import timezone
from django.db.models import Q
from .models import (
    AriaDownloadStatus,
    TorrentFile,
    Torrent,
    TorrentType,
)
from .statusmgr import StatusMgr

from constance import config
import random
from .commondao import (
    prepare_torrent_dir_name,
    torrent_file_to_log,
    torrent_to_log,
    clean_html,
    add_log,
    format_log_value,
)


class AriaApi:
    def __init__(self, host=None, port=None, secret=None):
        self.logger = logging.getLogger("torbox")
        if not host:
            host = config.ARIA2_HOST
        if not port:
            port = config.ARIA2_PORT
        if not secret:
            secret = config.ARIA2_PASSWORD
        self.host = host
        self.port = port
        self.secret = secret
        self.aria = f"http://{self.host}:{self.port}/jsonrpc"

    def _build_request_id(self):
        return str(random.randint(0, 10000000))

    def get_version(self):
        try:
            self.logger.debug(f"Check version of aria2c rpc server: {self.aria}")
            query = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": self._build_request_id(),
                    "method": "aria2.getVersion",
                    "params": [
                        f"token:{self.secret}",
                    ],
                }
            )
            self._log_query(query)
            result = requests.post(self.aria, data=query)

            if result.ok:
                json_result = json.loads(result.content)
                self.logger.debug(f"Aria2c version result: {json_result}")
                return True, json_result["result"]
            else:
                self.logger.error(
                    f"Could not get getVersion from aria: {result.reason}"
                )
                return False, result.reason
        except Exception as e:
            self.logger.error("Couldn't getVersion of Aria2c: " + str(e))
            return None

    def download_file(self, link, target_name, target_folder, torrent=None):
        try:
            self.logger.debug(
                f"Downloading file: {link} to {target_folder}/{target_name}, with aria2c rpc server: {self.aria}"
            )
            query = json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": self._build_request_id(),
                    "method": "aria2.addUri",
                    "params": [
                        f"token:{self.secret}",
                        [link],
                        {"dir": target_folder, "out": target_name},
                    ],
                }
            )
            self._log_query(query)
            result = requests.post(self.aria, data=query)

            if result.ok:
                json_result = json.loads(result.content)
                self.logger.debug(f"Aria2c download_file result: {json_result}")
                return True, json_result["result"]
            else:
                self.logger.error(
                    f"Could not get download_file from aria: {result.reason}"
                )
                return False, result.reason
        except Exception as e:
            add_log(
                message=f"Could not download file: <i>'{link}'</i> to <i>'{target_folder}/{target_name}'</i>: <i>'{clean_html(e)}'</i>",
                level=StatusMgr.get_instance().ERROR,
                source="ariaapi",
                torrent=torrent,
            )
            return False, str(e)

    def _log_query(self, query):
        censored = query
        if self.secret:
            censored = query.replace(self.secret, "***")
        self.logger.debug(f"Aria query: {censored}")

    def tellStatus(self, internal_id):

        self.logger.debug(
            f"Updating status for aria internal id: {internal_id} from aria2 api {self.aria}"
        )
        query = json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "aria2.tellStatus",
                "id": self._build_request_id(),
                "params": [
                    f"token:{self.secret}",
                    internal_id,
                ],  # if no secret is used, Aria2c ignores it
            }
        )
        self._log_query(query)
        result = requests.post(self.aria, data=query)

        if result.ok:
            json_result = json.loads(result.content)
            self.logger.debug(f"Aria2c tellStatus result: {json_result}")
            return True, json_result["result"]
        else:
            self.logger.error(f"Could not get tellStatus from aria: {result.reason}")
            return False, result.reason


def validate_aria_api(host, port, password, api=None):
    if not api:
        api = AriaApi(host=host, port=port, secret=password)

    logger = logging.getLogger("torbox")
    logger.debug(
        f"Validating aria api with host: {host}, port: {port} and password (hidden)"
    )

    status, result = api.get_version()
    logger.debug(f"Aria2 version: {result}")
    if status:
        return True, "Ok", None
    else:
        return False, "Aria validation failed: Could not connect to aria2 api", 2


def _update_aria_status(json_result, aria_internal_id):
    logger = logging.getLogger("torbox")
    gid = json_result["gid"]
    path = json_result["files"][0]["path"]  # in TorBox there will be always just one
    completed_length = int(json_result["completedLength"])
    total_length = int(json_result["totalLength"])
    error_message = ""
    if "errorCode" in json_result and json_result["errorCode"] != "0":
        error_code = json_result["errorCode"]
        if "errorMessage" in json_result:
            error_message = json_result["errorMessage"]
            # if there is an error Aria2 will try to repeat and if it will fail, user will have to redownload
        else:
            logger.error(
                f"Aria download errorCode: {error_code} for {gid}, but no error message found"
            )

    status = json_result["status"]
    logger.debug(
        f"{gid}, {path}, {completed_length}, {total_length}, {error_message}, {status}"
    )
    aria_download_status = AriaDownloadStatus.objects.get(internal_id=aria_internal_id)
    aria_download_status.path = path
    aria_download_status.error = error_message
    aria_download_status.status = status
    aria_download_status.done = status == "complete"
    logger.debug(
        f"Updating aria progress: {aria_download_status} with: {completed_length}, {total_length}"
    )
    if aria_download_status.done:
        aria_download_status.progress = 1
        aria_download_status.finished_at = timezone.now()
    elif total_length > 0:
        aria_download_status.progress = float(completed_length) / float(total_length)
    else:
        aria_download_status.progress = 0
        aria_download_status.done = False
    aria_download_status.save()
    return aria_download_status


def update_status(aria_internal_id, api=None):
    status_mgr = StatusMgr.get_instance()
    if not api:
        api = AriaApi()
    ok, result = api.tellStatus(aria_internal_id)
    torrent = None
    file = TorrentFile.objects.filter(
        aria__internal_id=aria_internal_id
    ).first()  # first or none
    if file:
        torrent = file.torrent

    if not ok:
        status_mgr.aria_error(
            torrent,
            message=f"Could not get result from aria api for aria internal id <i>'{aria_internal_id}'</i>: {format_log_value(result)}",
        )
        return

    status = _update_aria_status(result, aria_internal_id)

    if status.error:
        status_mgr.aria_error(
            torrent,
            message=f"Aria download failed with error: {format_log_value(status.error)}, aria_id: {format_log_value(aria_internal_id)}, file: {torrent_file_to_log(file)}",
        )
        return

    status_mgr.aria_progress(
        torrent,
        message=f"Aria download updated. Progress: {format_log_value(status.progress)}, aria_id: {format_log_value(aria_internal_id)}, file: {torrent_file_to_log(file)}, status: {format_log_value(status.status)}",
    )


def calculate_progress(files: TorrentFile):
    logger = logging.getLogger("torbox")
    status_mgr = StatusMgr.get_instance()
    if len(files) == 0:
        logger.warning("No files found for torrent, returning 0 progress")
        return 0, 0, False

    total = 0.0
    progress = 0.0
    done = []
    for file in files:
        logger.debug(f"Processing torrent: {file.torrent}")
        if not file.aria:
            add_log(
                message=f"File: {torrent_file_to_log(file)} has no Aria id, but torrent has local download set to true: {torrent_to_log(file.torrent)}",
                level=status_mgr.WARNING,
                source="ariaapi",
                torrent=file.torrent,
            )
            break
        total += 1.0
        progress += file.aria.progress
        if file.aria.done:
            done.append(file.aria.done)
            add_log(
                message=f"File: {torrent_file_to_log(file)} has finished downloading in Aria",
                level=status_mgr.INFO,
                source="ariaapi",
                torrent=file.torrent,
            )

    if total == 0:
        logger.warning(f"Torrent has no total value")
        add_log(
            message=f"Torrent has no total value: {torrent_to_log(files[0].torrent)}, is Aria working? Remove {torrent_file_to_log(file)} and try again. If this happens often, check your Aria settings.",
            level=status_mgr.WARNING,
            source="ariaapi",
            torrent=files[0].torrent,
        )
        return 0, 0, False
    return total, progress, done


def exec_action_on_file(file: TorrentFile, torrent_type: TorrentType, torrent_dir: str):
    from .actiononfinishmgr import ActionMgr

    mgr = ActionMgr()

    mgr.run(file, torrent_dir)


def exec_action_on_finish(torrent: Torrent):
    logger = logging.getLogger("torbox")
    status_mgr = StatusMgr.get_instance()
    actions = TorrentFile.objects.filter(
        torrent=torrent, action_on_finish_done=False, aria__done=True
    )
    status_mgr.action_start(
        torrent=torrent,
        message=f"Executing action on finish for torrent: {torrent_to_log(torrent)}, actions to finish: {len(actions)}",
    )
    torrent_dir_name = prepare_torrent_dir_name(
        torrent.name
    )  # dir, where all torrent files will be stored in target dir(target dir is based on torrent_type)
    all_done = True
    for file in actions:
        if file.aria and file.aria.done:
            logger.debug(f"Executing action on file: {file} for torrent: {torrent}")
            exec_action_on_file(file, torrent.torrent_type, torrent_dir_name)
        else:
            all_done = False
            add_log(
                message=f"File: {torrent_file_to_log(file)} is not done, skipping action execution for torrent: {torrent_to_log(torrent)}",
                level=status_mgr.WARNING,
                source="ariaapi",
                torrent=torrent,
            )

    if all_done:
        status_mgr.torrent_done(torrent=torrent)


def check_local_download_status(api=None):
    if not api:
        api = AriaApi()
    status_mgr = StatusMgr()
    logger = logging.getLogger("torbox")
    files = AriaDownloadStatus.objects.filter(
        done=False, error="", internal_id__isnull=False
    )
    for aria in files:
        logger.debug(
            f"Checking status of: {aria.id} with internal id: {aria.internal_id}"
        )
        update_status(aria.internal_id, api=api)

    torrents = Torrent.objects.exclude(
        Q(local_download_finished=True) | Q(deleted=True)
    ).filter(local_download=True)

    # update torrent progress for downloading files from torbox to local storage
    for torrent in torrents:
        files = TorrentFile.objects.filter(torrent=torrent)
        total, progress, done = calculate_progress(files)
        if total == 0:
            logger.warning(
                f"Torrent: {torrent} has no total value, skipping progress update"
            )
            continue
        torrent.local_download_progress = progress / total
        logger.debug(f"Updating progress: {torrent} {torrent.local_download_progress}")
        if len(done) == len(files):
            status_mgr.aria_done(torrent=torrent)
