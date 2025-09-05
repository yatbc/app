from .models import Torrent, TorrentFile, TorrentType, TorrentTorBoxSearchResult
from .statusmgr import StatusMgr
import logging
import abc
import shutil
from .commondao import torrent_file_to_log, format_log_value, add_log, torrent_to_log
from pathlib import Path
from django.db.models import Q
from constance import config


class ActionHandler:
    def __init__(self):
        self.handler = None
        self.logger = logging.getLogger("torbox")

    def set_next(self, handler):
        self.handler = handler
        return self

    @abc.abstractmethod
    def handle(self, action):
        if self.handler:
            self.handler.handle(action)


class NothingActionHandler(ActionHandler):
    def handle(self, action):
        return super().handle(action)


class Action:
    def __init__(
        self,
        file: TorrentFile,
        torrent_dir: str,
        exit_handler: ActionHandler,
        enter_handler: ActionHandler,
    ):
        self.file = file
        self.torrent_type = file.torrent.torrent_type
        self.torrent_dir = torrent_dir
        self.status_mgr = StatusMgr.get_instance()
        self.logger = logging.getLogger("torbox")
        self.exit_handler = exit_handler
        self.enter_handler = enter_handler

    @abc.abstractmethod
    def exec(self):
        pass

    def __enter__(self):
        self.enter_handler.handle(self)
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            self.status_mgr.action_error(
                self.file.torrent,
                message=f"Error in execution action on done on file {format_log_value(self.source_path)},<br/> to {format_log_value(self.target_path)}: {format_log_value(exc_value)}",
            )
            return False
        self.exit_handler.handle(self)


class ExitHandler(ActionHandler):
    def __init__(self):
        super().__init__()

    def handle(self, action: Action):
        action.file.action_on_finish_done = True
        action.file.save()


def get_stash_api():
    from .stashapi import StashApi

    return StashApi()


class StashRescanExitHandler(ActionHandler):
    def __init__(self):
        super().__init__()

        self.stash = get_stash_api()

    def handle(self, action: Action):

        if (
            config.RESCAN_STASH_ON_HOME_VIDEO
            and action.torrent_type == TorrentType.objects.get_home_video()
        ):

            folder = action.target_dir.name
            if self.stash.rescan_stash(folder):
                add_log(
                    message=f"Stash rescan for folder: {format_log_value(folder)} started",
                    level=action.status_mgr.INFO,
                    source="action",
                    torrent=action.file.torrent,
                )
            else:
                add_log(
                    message=f"Could not start Stash rescan for folder: {format_log_value(folder)}",
                    level=action.status_mgr.ERROR,
                    source="action",
                    torrent=action.file.torrent,
                )
        else:
            self.logger.info(
                "Skipping Stash rescan, because Stash settings are not set"
            )
        if self.handler:
            self.handler.handle(action)


class ActionNothing(Action):

    def exec(self):
        message = (
            f"File: {torrent_file_to_log(self.file)} has type: <i>'{self.torrent_type.name}'</i> which is marked with action: <i>'{self.torrent_type.action_on_finish}'</i>, skipping",
        )
        self.status_mgr.action_progress(self.file.torrent, message)
        return True


class CopyEnterHandler(ActionHandler):
    def __init__(self):
        self.next_handler = None

    def assure_target_dir_exists(self, action):
        if not action.target_dir.exists():
            action.logger.info(f"Creating target directory: {action.target_dir}")
            action.target_dir.mkdir(parents=True, exist_ok=True)

    def handle(self, action: Action):
        self.assure_target_dir_exists(action)
        return True


class ActionCopy(Action):
    def __init__(
        self,
        file: TorrentFile,
        torrent_dir,
        enter_handler: ActionHandler,
        exit_handler: ActionHandler,
    ):
        super().__init__(
            file, torrent_dir, exit_handler=exit_handler, enter_handler=enter_handler
        )
        torrent_type = file.torrent.torrent_type
        self.source_path = Path(file.aria.path)
        file_name = self.source_path.name
        self.target_dir = Path(torrent_type.target_dir) / torrent_dir
        self.target_path = self.target_dir / file_name
        self.enter_handler = enter_handler
        self.exit_handler = exit_handler

    def exec_target_exists(self):
        add_log(
            message=f"Target file already exists: <i>'{self.target_path}'</i>, skipping action execution for torrent: {torrent_to_log(self.file.torrent)}, and marking action on finish as done",
            level=self.status_mgr.WARNING,
            source="action",
            torrent=self.file.torrent,
        )

    def exec(self):
        if self.target_path.exists():
            self.exec_target_exists()
            return True

        message_start = f"Copy action for file: {torrent_file_to_log(self.file)} started: source: {format_log_value(self.source_path)},<br/> target: {format_log_value(self.target_path)}"
        message_stop = f"Copy action for file done: {torrent_file_to_log(self.file)}, source: {format_log_value(self.source_path)},<br/> target: {format_log_value(self.target_path)}"
        self.status_mgr.action_progress(self.file.torrent, message=message_start)

        shutil.copy(self.source_path, self.target_path)

        self.status_mgr.action_progress(self.file.torrent, message=message_stop)


class ActionMove(ActionCopy):
    def __init__(self, file, torrent_dir, enter_handler, exit_handler):
        super().__init__(file, torrent_dir, enter_handler, exit_handler)

    def exec_target_exists(self):
        super().exec_target_exists()
        self.source_path.unlink(missing_ok=True)
        add_log(
            message=f"Source file <i>'{self.source_path}'</i> removed after move action, because target file already exists: <i>'{self.target_path}'</i> for torrent: {torrent_to_log(self.file.torrent)}",
            level=self.status_mgr.WARNING,
            source="action",
            torrent=self.file.torrent,
        )

    def exec(self):
        if self.target_path.exists():
            self.exec_target_exists()
            return True

        message_start = f"Move action for file: {torrent_file_to_log(self.file)} started: source: {format_log_value(self.source_path)},<br/> target: {format_log_value(self.target_path)}"
        message_stop = f"Move action for file done: {torrent_file_to_log(self.file)}, source: {format_log_value(self.source_path)},<br/> target: {format_log_value(self.target_path)}"
        self.status_mgr.action_progress(self.file.torrent, message=message_start)

        shutil.move(self.source_path, self.target_path)

        self.status_mgr.action_progress(self.file.torrent, message=message_stop)


def clean_title(title: str):
    return (
        title.replace("/", "")
        .replace("\\", "")
        .replace("_", " ")
        .replace(".", " ")
        .replace("  ", " ")
        .strip()
    )


def get_metadata_by_file(file_name: str, title=None, season=None, episode=None):
    import re

    result = re.search(r"[s](eason)*(\d+)", file_name.lower())
    if result and title is None:
        title = file_name[0 : result.start()]
        title = title.strip()
    if result and season is None:
        season = int(result.group(2))
        # only care about episode if there is a season
        result = re.search(r"e(\d+)", file_name.lower())
        if result and episode is None:
            episode = int(result.group(1))
    if title is None:
        title = Path(file_name).stem
    return title, season, episode


def get_metadata_by_search(
    torbox_search: TorrentTorBoxSearchResult, title=None, season=None, episode=None
):
    if not torbox_search:
        return title, season, episode, None

    query = torbox_search.query
    result = query.query.split("/")
    episode = None
    imdbid = result[0]
    season = None
    if len(result) > 1 and season is None:
        season = int(result[1].lower().replace("s", ""))
        if len(result) > 2 and episode is None:
            episode = int(result[2].lower().replace("e", ""))

    if torbox_search.season and season is None:
        season = int(torbox_search.season)

    if torbox_search.episode and episode is None:
        episode = int(torbox_search.episode)

    return torbox_search.title, season, episode, imdbid


def pad_number(number):
    number = int(number)
    return f"{number:02}"


def build_season_dir_name(season):
    return f"season {pad_number(season)}"


def find_season_dir(media_dir: Path, season=None):
    if season is None:
        return None
    for entry in media_dir.iterdir():
        if build_season_dir_name(season) in entry.name.lower() and entry.is_dir():
            return entry
    return None


def build_target_dir(target_dir: Path, season=None):
    season_dir = find_season_dir(target_dir, season)
    if season_dir:
        return season_dir
    if season:
        season_dir = target_dir / build_season_dir_name(season)
        return season_dir
    return target_dir  # just a movie?


def find_existing_dir(
    target_dir: Path, title: str, file_name: str, season=None, episode=None, imdbid=None
):
    title_words = title.split(" ")
    for entry in target_dir.iterdir():
        if not entry.is_dir():
            continue
        if imdbid and imdbid in entry.name:
            return build_target_dir(entry, season)

        title_folder = clean_title(entry.name).lower()
        present = True
        for word in title_words:
            if word.lower().strip() not in title_folder:
                present = False
                break
        if present:
            return build_target_dir(entry, season)
    return None


def normalize_movie_series_file_name(file_name, title=None, season=None, episode=None):
    if not title:
        return file_name
    normalized = title.title()
    if season:
        normalized += f" S{pad_number(season)}"
    if episode:
        normalized += f"E{pad_number(episode)}"
    normalized = normalized + Path(file_name).suffix
    return normalized


def normalize_moves_file_name(file_name, title=None):
    return normalize_movie_series_file_name(file_name=file_name, title=title)


def is_known_movie_type(file: TorrentFile):
    logger = logging.getLogger("torbox")
    logger.debug(f"Checking file: {file.name} with type: {file.mime_type}")
    if "video" in file.mime_type.lower():
        return True
    if "text/" in file.mime_type.lower():
        return False
    extension = Path(file.name).suffix.lower()
    wrong_types = [".txt", ".nfo"]
    if extension in wrong_types:
        return False
    ok_types = [".mp4", ".avi", ".mkv"]
    if extension in ok_types:
        return True
    return False


class MoviesEnterHandler(ActionHandler):
    def __init__(self):
        super().__init__()
        self.movies_type = TorrentType.objects.get_movies()

    def _prepare_folders(self, action: Action):
        import re

        file_name = action.file.name
        torbox_search = TorrentTorBoxSearchResult.objects.filter_by_torrent(
            action.file.torrent
        ).first()
        if not torbox_search:
            self.logger.debug(
                f"Torrent: {action.file.torrent} is not connected to search"
            )
        title, _, _ = get_metadata_by_file(file_name=file_name)
        title, _, _, imdbid = get_metadata_by_search(torbox_search, title, None, None)

        title = clean_title(title=title)

        existing_dir = find_existing_dir(
            Path(action.torrent_type.target_dir),
            title,
            file_name,
            None,
            None,
            imdbid,
        )
        normalized_file_name = normalize_moves_file_name(file_name, title)
        if existing_dir:
            add_log(
                f"Folder with movie from torrent: {torrent_to_log(action.file.torrent)} already existed, skipping",
                level=action.status_mgr.INFO,
                source="actionmgr",
                torrent=action.file.torrent,
            )
            return
        if title:
            target_dir = Path(action.torrent_type.target_dir)
            if imdbid:
                title = title.title() + f" [imdbid-{imdbid}]"
            target_dir = target_dir / title
            target_path = target_dir / normalized_file_name
            add_log(
                f"Updating target path for movie. From: {format_log_value(action.target_path)}<br/> to new dir: {format_log_value(target_path)}",
                level=action.status_mgr.INFO,
                source="actionmgr",
                torrent=action.file.torrent,
            )
            action.target_dir = target_dir
            action.target_path = target_path
            return
        add_log(
            message=f"Could not find/build target folder for movie: title: {format_log_value(title)}, file_name: {format_log_value(file_name)}, imdbid: {format_log_value(imdbid)}",
            level=action.status_mgr.WARNING,
            source="actionmgr",
            torrent=action.file.torrent,
        )

    def handle(self, action: Action):
        if action.torrent_type == self.movies_type:
            if config.ORGANIZE_MOVIES == True:
                self.logger.info("Handling action for movies")
                if is_known_movie_type(action.file):
                    self._prepare_folders(action)
                else:
                    add_log(
                        message=f"File: {torrent_file_to_log(action.file)} is not known as movie type, skipping organization",
                        level=action.status_mgr.WARNING,
                        source="actionmgr",
                        torrent=action.file.torrent,
                    )

            else:
                self.logger.info(
                    "Skipping movies organization action, it is disabled in settings"
                )

        if self.handler:
            self.handler.handle(action)


class MoveSeriesEnterHandler(ActionHandler):
    def __init__(self):
        super().__init__()
        self.movie_series_type = TorrentType.objects.get_movie_series()

    def _prepare_folders(self, action: Action):
        import re

        file_name = action.file.name
        torbox_search = TorrentTorBoxSearchResult.objects.filter_by_torrent(
            action.file.torrent
        ).first()
        if not torbox_search:
            self.logger.debug(
                f"Torrent: {action.file.torrent} is not connected to search"
            )
        title, season, episode = get_metadata_by_file(file_name=file_name)
        title, season, episode, imdbid = get_metadata_by_search(
            torbox_search, title, season, episode
        )

        title = clean_title(title=title)

        existing_dir = find_existing_dir(
            Path(action.torrent_type.target_dir),
            title,
            file_name,
            season,
            episode,
            imdbid,
        )
        normalized_file_name = normalize_movie_series_file_name(
            file_name, title, season, episode
        )
        if existing_dir:
            target_path = existing_dir / normalized_file_name
            add_log(
                f"Updating target path for movie series. From: {format_log_value(action.target_path)}<br/> to existing dir: {format_log_value(target_path)}",
                level=action.status_mgr.INFO,
                source="actionmgr",
                torrent=action.file.torrent,
            )
            action.target_dir = existing_dir
            action.target_path = existing_dir / normalized_file_name
            return
        if title and season:
            target_dir = Path(action.torrent_type.target_dir)
            if imdbid:
                title = title + f" [imdbid-{imdbid}]"
            target_dir = target_dir / title / f"season {season:02}"
            target_path = target_dir / normalized_file_name
            add_log(
                f"Updating target path for movie series. From: {format_log_value(action.target_path)}<br/> to new dir: {format_log_value(target_path)}",
                level=action.status_mgr.INFO,
                source="actionmgr",
                torrent=action.file.torrent,
            )
            action.target_dir = target_dir
            action.target_path = target_path
            return
        add_log(
            message=f"Could not find/build target folder for movie series: title: {format_log_value(title)}, file_name: {format_log_value(file_name)}, season: {format_log_value(season)}, episode: {format_log_value(episode)}, imdbid: {format_log_value(imdbid)}",
            level=action.status_mgr.WARNING,
            source="actionmgr",
            torrent=action.file.torrent,
        )

    def handle(self, action: Action):
        if action.torrent_type == self.movie_series_type:
            if config.ORGANIZE_MOVIE_SERIES == True:
                self.logger.info("Handling action for movie series")
                if is_known_movie_type(action.file):
                    self._prepare_folders(action)
                else:
                    add_log(
                        message=f"File: {torrent_file_to_log(action.file)} is not known as movie type, skipping organization",
                        level=action.status_mgr.WARNING,
                        source="actionmgr",
                        torrent=action.file.torrent,
                    )
            else:
                self.logger.info(
                    "Skipping movie series organization action, it is disabled in settings"
                )

        if self.handler:
            self.handler.handle(action)


class ActionFactory:
    def __init__(self):
        self.logger = logging.getLogger("torbox")

    def create_action(self, file: TorrentFile, torrent_dir: str) -> Action:
        enter_handler = CopyEnterHandler()
        enter_handler = MoviesEnterHandler().set_next(
            MoveSeriesEnterHandler().set_next(enter_handler)
        )
        exit_handler = StashRescanExitHandler().set_next(ExitHandler())
        torrent_type = file.torrent.torrent_type
        if torrent_type.action_on_finish == TorrentType.ACTION_DO_NOTHING:
            self.logger.debug("Creating action for nothing")
            enter_handler = NothingActionHandler()
            return ActionNothing(
                file=file,
                torrent_dir=torrent_dir,
                enter_handler=enter_handler,
                exit_handler=exit_handler,
            )
        if torrent_type.action_on_finish == TorrentType.ACTION_COPY:
            self.logger.debug("Creating action for copy")
            return ActionCopy(
                file=file,
                torrent_dir=torrent_dir,
                enter_handler=enter_handler,
                exit_handler=exit_handler,
            )
        if torrent_type.action_on_finish == TorrentType.ACTION_MOVE:
            self.logger.debug("Creating action for move")
            return ActionMove(
                file=file,
                torrent_dir=torrent_dir,
                enter_handler=enter_handler,
                exit_handler=exit_handler,
            )


class ActionMgr:
    def __init__(
        self,
    ):

        self.status_mgr = StatusMgr.get_instance()
        self.logger = logging.getLogger("torbox")
        self.action_factory = ActionFactory()

    def _is_valid(
        self,
        file: TorrentFile,
        source_path: Path,
    ):
        if (
            not file.aria
            or not file.aria.done
            or file.action_on_finish_done
            or not file.torrent
            or not file.torrent.torrent_type
        ):
            self.logger.warning(
                f"File: {file} is not done or action on finish already executed, skipping action execution"
            )
            return False

        if not source_path.exists():
            self.status_mgr.action_error(
                file.torrent,
                message=f"Source file does not exist: {format_log_value(source_path)}",
            )
            return False
        return True

    def run(self, file: TorrentFile, torrent_dir: str):
        # torrent_dir is part of target path: target dir from torrent_type/torrent_dir
        source_path = Path(file.aria.path)
        if not self._is_valid(file, source_path):
            return
        with self.action_factory.create_action(
            file=file, torrent_dir=torrent_dir
        ) as action:
            action.exec()
