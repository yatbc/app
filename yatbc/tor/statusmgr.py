from .models import (
    TorrentStatus,
    Torrent,
    Level,
    TorrentFile,
    TorrentType,
    LogSource,
    TorrentHistory,
)
from .commondao import add_log, format_log_value, torrent_to_log, torrent_file_to_log
from .common import TORBOX_CLIENT, TRANSMISSION_CLIENT
from constance import config
from django.utils import timezone
from pathlib import Path
import logging


# todo: refactor Aria2 progress state, to explicitly handle one file done, now it is handled in aria_progress. Same goes for actions?
# refactor, change to free functions, and extract class VARS as singletone
class StatusMgr:

    unknown = None

    client_init = None
    client_added = None
    client_progress = None
    client_done = None
    client_error = None

    local_error = None
    local_new = None
    local_progress = None
    local_done = None

    finish_started = None
    finish_progress = None
    finish_done = None
    finish_error = None
    INSTANCE = None

    def remote_client_done(self, torrent: Torrent, request_torrent_files):
        if request_torrent_files is None:
            raise ValueError("request_torrent_files cannot be None")
        torrent.local_download_finished = False
        torrent.local_download_progress = 0
        torrent.local_download = False
        torrent.download_finished = True
        torrent.save()
        TorrentFile.objects.filter(torrent=torrent).update(aria=None)

        torrent.local_status = self.client_done

        add_log(
            f"Torrent: {torrent_to_log(torrent)} finished on Remote Client, adding to Aria2c",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            local_status=self.client_done,
            torrent=torrent,
        )
        request_torrent_files.enqueue(torrent.id)

    def remote_client_added_torrent(self, torrent: Torrent):
        torrent.local_status = self.client_added
        torrent.save()
        add_log(
            message=f"Torrent: {torrent_to_log(torrent)} added to client: {format_log_value(torrent.client)}",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
        )

    def remote_client_progress(self, torrent: Torrent):
        add_log(
            message=f"Remote client is working on {torrent_to_log(torrent)}",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
            local_status=self.client_progress,
        )

    def remote_client_error(self, torrent: Torrent):
        add_log(
            message=f"Remote client failed for {torrent_to_log(torrent)}. Try re-downloading again. If problem will persist check service provider site.",
            level=Level.objects.get_error(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
            local_status=self.client_error,
        )

    def aria_new(self, torrent):
        torrent.local_download = True
        torrent.save()
        add_log(
            message=f"Torrent: {torrent_to_log(torrent)} send to Aria2c",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
            local_status=self.local_new,
        )

    def new_torrent(
        self, hash, magnet, torrent_type, internal_id, client, private=False
    ):
        torrent = Torrent.objects.create(
            hash=hash,
            created_at=timezone.now().isoformat(),
            client=client,
            internal_id=internal_id,
            magnet=magnet,
            torrent_type=torrent_type,
            local_status=self.client_init,
            private=private,
        )
        add_log(
            message=f"New torrent created: {torrent_to_log(torrent)} with hash: {format_log_value(torrent.hash)}, and client internal id: {format_log_value(torrent.internal_id)}",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
        )
        return torrent

    def action_error(self, torrent, message):
        add_log(
            message=message,
            level=Level.objects.get_error(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
            local_status=self.finish_error,
        )

    def action_start(self, torrent, message):
        add_log(
            message=message,
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
            local_status=self.finish_started,
        )

    def action_progress(self, torrent, message):
        add_log(
            message=message,
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
            local_status=self.finish_progress,
        )

    def torrent_done(self, torrent: Torrent, skipped_download=False):
        add_log(
            message=f"Torrent: {torrent_to_log(torrent)} finished actions, and is marked as done.",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
        )
        torrent.local_status = self.finish_done
        torrent.finished_at = timezone.now()
        torrent.save()
        if skipped_download:
            self.logger.debug(
                f"Torrent {torrent.id} was marked as done with skipped download."
            )
            return
        # remove empty source dir
        source_dir = Path(torrent.torrentfile_set.first().aria.path).parent
        if (
            source_dir.exists()
            and torrent.torrent_type.action_on_finish == TorrentType.ACTION_MOVE
        ):
            try:
                source_dir.rmdir()
                add_log(
                    message=f"Source dir: {format_log_value(source_dir.as_posix())} for torrent: {torrent_to_log(torrent)}, was not needed anymore and was deleted",
                    source=LogSource.objects.get_status_mgr(),
                    torrent=torrent,
                    level=Level.objects.get_info(),
                )
            except Exception as e:
                message = f"Couldn't remove dir: {format_log_value(source_dir)},<br/> error: {format_log_value(e)},<br/> remove it manually"
                add_log(
                    message=message,
                    source=LogSource.objects.get_status_mgr(),
                    level=Level.objects.get_warning(),
                    torrent=torrent,
                )

    def aria_error(self, torrent, message):
        add_log(
            message=message,
            level=Level.objects.get_error(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
            local_status=self.local_error,
        )

    def aria_progress(self, torrent, message, done_downloading=False, file=None):
        add_log(
            torrent=torrent,
            local_status=self.local_progress,
            message=message,
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
        )
        if done_downloading:
            add_log(
                message=f"File: {torrent_file_to_log(file)} has finished downloading in Aria",
                level=Level.objects.get_info(),
                source=LogSource.objects.get_status_mgr(),
                torrent=torrent,
            )

    def force_transition_in_client_done(self, torrent: Torrent, request_torrent_files):
        allowed_statuses = [self.local_done, self.local_error, self.finish_done]
        if torrent.local_status not in allowed_statuses:
            self.logger.debug(
                f"Torrent {torrent.id} in status {torrent.local_status.name} cannot be transited to redownload."
            )
            return False
        add_log(
            f"Forcing transition of torrent {torrent.id} to client done status",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
        )
        torrent.finished_at = None
        torrent.save()
        self.remote_client_done(torrent, request_torrent_files=request_torrent_files)
        return True

    def force_transition_in_done(self, torrent: Torrent):
        add_log(
            f"Forcing transition of torrent {torrent.id} to finished status",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
        )
        torrent.local_download = True
        torrent.local_download_finished = True
        torrent.local_download_progress = 1
        torrent.save()
        self.torrent_done(torrent, skipped_download=True)

    def transition_in_client_progress_if_needed(self, torrent: Torrent):
        if (
            not TorrentHistory.objects.filter(torrent=torrent).exists()
            or torrent.local_status == self.client_added
        ):
            self.remote_client_progress(torrent)

    def transition_in_client_done_if_needed(
        self,
        torrent: Torrent,
        files: list[TorrentFile],
        request_torrent_files=None,
    ):
        if not files:
            return  # nothing to download
        allowed_statuses = [self.client_added, self.client_progress, self.client_init]
        if torrent.local_status not in allowed_statuses:
            self.logger.debug(
                f"Torrent {torrent.id} in status {torrent.local_status.name} cannot be transited to client done status."
            )
            return

        if (
            torrent.client == TORBOX_CLIENT
            and config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TORBOX
        ) or (
            torrent.client == TRANSMISSION_CLIENT
            and config.SKIP_DOWNLOAD_FOR_NEXT_STATUS_CHECK_IN_TRANSMISSION
        ):
            add_log(
                message=f"Skipping download for next status check in torbox for torrent {torrent.id}",
                level=Level.objects.get_info(),
                source=LogSource.objects.get_status_mgr(),
                torrent=torrent,
            )
            self.torrent_done(torrent, skipped_download=True)
            return
        if (  # refactor to use same code as request_dl
            torrent.download_finished and not any([file.aria for file in files])
        ):
            self.logger.debug(
                f"Torrent {torrent.id} will be transited to client done status."
            )
            self.remote_client_done(torrent, request_torrent_files)

    def aria_done(self, torrent):
        torrent.local_download_progress = 1
        torrent.local_download_finished = True
        torrent.save()
        add_log(
            message=f"Torrent: {torrent_to_log(torrent)} has finished local download, adding task for action on finish",
            level=Level.objects.get_info(),
            source=LogSource.objects.get_status_mgr(),
            torrent=torrent,
            local_status=self.local_done,
        )
        from .tasks import exec_action_on_file_task

        exec_action_on_file_task.enqueue(torrent.id)

    @classmethod
    def get_instance(cls, override=None):
        if override:
            cls.INSTANCE = override
        if cls.INSTANCE is None:
            cls.INSTANCE = StatusMgr()
        return cls.INSTANCE

    def __init__(self):
        self.logger = logging.getLogger("torbox")
        if StatusMgr.unknown is None:

            StatusMgr.unknown = TorrentStatus.objects.get(name="Unknown")

            StatusMgr.client_init = TorrentStatus.objects.get(name="Client: Init")
            StatusMgr.client_added = TorrentStatus.objects.get(name="Client: Added")
            StatusMgr.client_progress = TorrentStatus.objects.get(
                name="Client: In Progress"
            )
            StatusMgr.client_done = TorrentStatus.objects.get(name="Client: Done")
            StatusMgr.client_error = TorrentStatus.objects.get(name="Client: Error")

            StatusMgr.local_error = TorrentStatus.objects.get(
                name="Local download: Error"
            )
            StatusMgr.local_new = TorrentStatus.objects.get(name="Local download: New")
            StatusMgr.local_progress = TorrentStatus.objects.get(
                name="Local download: Progress"
            )
            StatusMgr.local_done = TorrentStatus.objects.get(
                name="Local download: Done"
            )

            StatusMgr.finish_started = TorrentStatus.objects.get(name="Finish: Started")
            StatusMgr.finish_progress = TorrentStatus.objects.get(
                name="Finish: Progress"
            )
            StatusMgr.finish_done = TorrentStatus.objects.get(name="Finish: Done")
            StatusMgr.finish_error = TorrentStatus.objects.get(name="Finish: Error")
