from .models import TorrentStatus, Torrent, Level, TorrentFile, TorrentType
from .commondao import add_log, format_log_value, torrent_to_log
from django.utils import timezone
from pathlib import Path
import logging


# todo: refactor Aria2 progress state, to explicitly handle one file done, now it is handled in aria_progress. Same goes for actions?
# refactor, change to free functions, and extract class VARS as singletone
class StatusMgr:
    SOURCE = "statusmgr"

    DEBUG = None
    INFO = None
    WARNING = None
    ERROR = None

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

    def remote_client_done(self, torrent: Torrent, request_torrent_files=None):
        if request_torrent_files is None:  # todo: next one for transmission
            from .tasks import torbox_request_torrent_files

            request_torrent_files = torbox_request_torrent_files

        add_log(
            f"Torrent: {torrent_to_log(torrent)} finished on Remote Client, adding to Aria2c",
            level=StatusMgr.get_instance().INFO,
            source=self.SOURCE,
            local_status=self.client_done,
            torrent=torrent,
        )
        request_torrent_files.enqueue(torrent.id)

    def remote_client_added_torrent(self, torrent: Torrent):
        torrent.local_status = self.client_added
        torrent.save()
        add_log(
            message=f"Torrent: {torrent_to_log(torrent)} added to client: {format_log_value(torrent.client)}",
            level=self.INFO,
            source=self.SOURCE,
            torrent=torrent,
        )

    def remote_client_progress(self, torrent: Torrent):
        add_log(
            message=f"Remote client is working on {torrent_to_log(torrent)}",
            level=StatusMgr.get_instance().INFO,
            source=self.SOURCE,
            torrent=torrent,
            local_status=self.client_progress,
        )

    def aria_new(self, torrent):
        torrent.local_download = True
        torrent.save()
        add_log(
            message=f"Torrent: {torrent_to_log(torrent)} send to Aria2c",
            level=self.INFO,
            source=self.SOURCE,
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
            level=self.INFO,
            source=self.SOURCE,
            torrent=torrent,
        )
        return torrent

    def action_error(self, torrent, message):
        add_log(
            message=message,
            level=self.ERROR,
            source=self.SOURCE,
            torrent=torrent,
            local_status=self.finish_error,
        )

    def action_start(self, torrent, message):
        add_log(
            message=message,
            level=self.INFO,
            source=self.SOURCE,
            torrent=torrent,
            local_status=self.finish_started,
        )

    def action_progress(self, torrent, message):
        add_log(
            message=message,
            level=self.INFO,
            source=self.SOURCE,
            torrent=torrent,
            local_status=self.finish_progress,
        )

    def torrent_done(self, torrent: Torrent):
        add_log(
            message=f"Torrent: {torrent_to_log(torrent)} finished actions, and is marked as done.",
            level=self.INFO,
            source=self.SOURCE,
            torrent=torrent,
        )
        torrent.local_status = self.finish_done
        torrent.finished_at = timezone.now()
        torrent.save()
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
                    source=self.SOURCE,
                    torrent=torrent,
                    level=self.INFO,
                )
            except Exception as e:
                message = f"Couldn't remove dir: {format_log_value(source_dir)},<br/> error: {format_log_value(e)},<br/> remove it manually"
                add_log(
                    message=message,
                    source=self.SOURCE,
                    level=self.WARNING,
                    torrent=torrent,
                )

    def aria_error(self, torrent, message):
        add_log(
            message=message,
            level=self.ERROR,
            source=self.SOURCE,
            torrent=torrent,
            local_status=self.local_error,
        )

    def aria_progress(self, torrent, message):
        add_log(
            torrent=torrent,
            local_status=self.local_progress,
            message=message,
            level=self.INFO,
            source=self.SOURCE,
        )

    def aria_done(self, torrent):
        torrent.local_download_progress = 1
        torrent.local_download_finished = True
        torrent.save()
        add_log(
            message=f"Torrent: {torrent_to_log(torrent)} has finished local download, adding task for action on finish",
            level=self.INFO,
            source=self.SOURCE,
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
        if StatusMgr.DEBUG is None:
            StatusMgr.DEBUG = Level.objects.get(name="DEBUG")
            StatusMgr.INFO = Level.objects.get(name="INFO")
            StatusMgr.WARNING = Level.objects.get(name="WARNING")
            StatusMgr.ERROR = Level.objects.get(name="ERROR")

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
