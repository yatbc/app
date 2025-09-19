from .models import Torrent, TorrentFile, TorrentType, TorrentTorBoxSearchResult, Level
from .statusmgr import StatusMgr
import logging
import abc
import shutil
import re
from .commondao import (
    torrent_file_to_log,
    format_log_value,
    add_log,
    torrent_to_log,
    prepare_torrent_dir_name,
)
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

    def _handle_type(
        self,
        torrent_type: TorrentType,
        handler,
        action,
    ):
        if action.torrent_type == torrent_type:
            return handler(action)
        return True


class NothingActionHandler(ActionHandler):
    def handle(self, action):
        return super().handle(action)


class Action:
    def __init__(
        self,
        torrent: Torrent,
        files: list[TorrentFile],
        torrent_dir: str,
        exit_handler: ActionHandler,
        enter_handler: ActionHandler,
    ):
        self.files = files
        self.torrent = torrent
        self.torrent_type = torrent.torrent_type
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
                self.torrent,
                message=f"Error in execution action,<br/> {format_log_value(exc_value)}",
            )
            return False
        self.exit_handler.handle(self)


class ExitHandler(ActionHandler):
    def __init__(self):
        super().__init__()

    def handle(self, action: Action):
        for file in action.files:
            file.action_on_finish_done = True
            file.save()


def get_stash_api():
    from .stashapi import StashApi

    return StashApi()


class StashRescanExitHandler(ActionHandler):
    def __init__(self):
        super().__init__()

        self.stash = get_stash_api()

    def _rescan_if_needed(self, action: Action):
        if config.RESCAN_STASH_ON_HOME_VIDEO:
            folder = action.target_dir.name
            if self.stash.rescan_stash(folder):
                add_log(
                    message=f"Stash rescan for folder: {format_log_value(folder)} started",
                    level=Level.objects.get_info(),
                    source="action",
                    torrent=action.torrent,
                )
            else:
                add_log(
                    message=f"Could not start Stash rescan for folder: {format_log_value(folder)}",
                    level=Level.objects.get_error(),
                    source="action",
                    torrent=action.torrent,
                )
            return True
        return False

    def handle(self, action: Action):
        if not self._handle_type(
            TorrentType.objects.get_home_video(),
            self._rescan_if_needed,
            action,
        ):
            self.logger.info(
                "Skipping Stash rescan, because Stash settings are not set or torrent type is not Home Video"
            )
        if self.handler:
            self.handler.handle(action)


class ActionNothing(Action):

    def exec(self):
        message = (
            f"Torrent: {torrent_to_log(self.torrent)} has type: <i>'{self.torrent_type.name}'</i> which is marked with action: <i>'{self.torrent_type.action_on_finish}'</i>, skipping",
        )

        self.status_mgr.action_progress(self.torrent, message)
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
        torrent: Torrent,
        files: list[TorrentFile],
        torrent_dir: str,
        enter_handler: ActionHandler,
        exit_handler: ActionHandler,
    ):
        super().__init__(
            torrent,
            files,
            torrent_dir,
            exit_handler=exit_handler,
            enter_handler=enter_handler,
        )
        torrent_type = torrent.torrent_type
        self.target_dir = Path(torrent_type.target_dir) / torrent_dir
        self.paths = []
        for file in files:
            source_path, target_path = self.build_paths(file)
            self.paths.append((source_path, target_path, file))

        self.enter_handler = enter_handler
        self.exit_handler = exit_handler

    def build_paths(self, file: TorrentFile):
        source_path = Path(file.aria.path)
        target_path = self.target_dir / source_path.name
        return source_path, target_path

    def exec_target_exists(self, source_path: Path, target_path: Path):
        add_log(
            message=f"Target file already exists: <i>'{target_path}'</i>, skipping action execution for this file",
            level=Level.objects.get_warning(),
            source="action",
            torrent=self.torrent,
        )

    def exec(self):
        for source, target, file in self.paths:
            if target.exists():
                self.exec_target_exists(source, target)
                continue

            message_start = f"Copy action for file: {torrent_file_to_log(file)} started: source: {format_log_value(source)},<br/> target: {format_log_value(target)}"
            message_stop = f"Copy action for file done: {torrent_file_to_log(file)}, source: {format_log_value(source)},<br/> target: {format_log_value(target)}"
            self.status_mgr.action_progress(self.torrent, message=message_start)

            shutil.copy(source, target)
            self.status_mgr.action_progress(self.torrent, message=message_stop)


class ActionMove(ActionCopy):
    def __init__(
        self,
        torrent: Torrent,
        files: list[TorrentFile],
        torrent_dir,
        enter_handler,
        exit_handler,
    ):
        super().__init__(torrent, files, torrent_dir, enter_handler, exit_handler)

    def exec_target_exists(self, source: Path, target: Path):
        super().exec_target_exists(source, target)
        source.unlink(missing_ok=True)
        add_log(
            message=f"Source file {format_log_value(source)} removed after move action, because target file already exists: {format_log_value(target)} for torrent: {torrent_to_log(self.torrent)}",
            level=Level.objects.get_warning(),
            source="action",
            torrent=self.torrent,
        )

    def exec(self):
        for source, target, file in self.paths:
            if target.exists():
                self.exec_target_exists(source, target)
                continue

            message_start = f"Move action for file: {torrent_file_to_log(file)} started: source: {format_log_value(source)},<br/> target: {format_log_value(target)}"
            message_stop = f"Move action for file done: {torrent_file_to_log(file)}, source: {format_log_value(source)},<br/> target: {format_log_value(target)}"
            self.status_mgr.action_progress(self.torrent, message=message_start)

            shutil.move(source, target)
            self.status_mgr.action_progress(self.torrent, message=message_stop)


def clean_title(title: str):
    return (
        title.replace("/", "")
        .replace("\\", "")
        .replace("_", " ")
        .replace(".", " ")
        .replace(":", " ")
        .replace("  ", " ")
        .replace("  ", " ")
        .strip()
    )


def get_metadata_by_file(file_name: str, title=None, season=None, episode=None):
    import re

    name = Path(file_name).stem
    result = re.search(r"s(eason){0,1}\s*(\d+)\s*e(pisode)*\s*(\d+)", name.lower())
    if result and title is None:
        print(result.group())
        title = name[0 : result.start()]
        title = clean_title(title.strip())
    if result and season is None:
        season = int(result.group(2))
    if result and episode is None:
        episode = int(result.group(4))

    if title is None:
        title = clean_title(Path(file_name).stem)
    logger = logging.getLogger("torbox")
    logger.debug(
        f"Extracted metadata from file: {file_name}, title: {title}, season: {season}, episode: {episode}"
    )
    return title, season, episode


def get_metadata_by_search(
    torbox_search: TorrentTorBoxSearchResult, title=None, season=None, episode=None
):
    if not torbox_search:
        return title, season, episode, None

    query = torbox_search.query
    result = query.query.split("/")
    imdbid = result[0]
    if len(result) > 1 and season is None:
        season = int(result[1].lower().replace("s", ""))
        if len(result) > 2 and episode is None:
            episode = int(result[2].lower().replace("e", ""))

    if torbox_search.season and season is None:
        season = int(torbox_search.season)

    if (
        torbox_search.episode
        and episode is None
        and len(torbox_search.episode.split(",")) == 1  # it can contain "1,2,3,4"
    ):
        episode = int(torbox_search.episode)
    logger = logging.getLogger("torbox")
    title = torbox_search.title
    logger.debug(
        f"Extracted metadata from search, title: {title}, season: {season}, episode: {episode}"
    )
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
    title = re.compile(r"\b" + title.lower() + r"\b")
    IMDBID = "imdbid-"
    if imdbid:
        imdbid = re.compile(r"\b" + imdbid + r"\b")
    for entry in target_dir.iterdir():
        if not entry.is_dir():
            continue

        if imdbid and imdbid.search(entry.name):
            return build_target_dir(entry, season)

        if IMDBID in entry.name and imdbid:  # has id, but it's different then given
            continue

        title_folder = clean_title(entry.name).lower()
        if title.search(title_folder):
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


def find_movie(files: list[TorrentFile]):
    for file in files:
        if is_known_movie_type(file):
            return file
    return None


class MoviesEnterHandler(ActionHandler):
    def __init__(self):
        super().__init__()
        self.movies_type = TorrentType.objects.get_movies()

    def _prepare_folders(self, file: TorrentFile, action: Action):
        import re

        file_name = file.name
        torbox_search = TorrentTorBoxSearchResult.objects.filter_by_torrent(
            action.torrent
        ).first()
        if not torbox_search:
            self.logger.debug(f"Torrent: {action.torrent} is not connected to search")
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
                f"Folder with movie from torrent: {torrent_to_log(action.torrent)} already existed, skipping organization. Existing dir: {format_log_value(existing_dir)}",
                level=Level.objects.get_info(),
                source="actionmgr",
                torrent=action.torrent,
            )
            action.target_dir = existing_dir
            return normalized_file_name
        if title:
            source, old_target = action.build_paths(file)
            target_dir = Path(action.torrent_type.target_dir)
            if imdbid:
                title = title.title() + f" [imdbid-{imdbid}]"
            target_dir = target_dir / title
            target_path = target_dir / normalized_file_name
            add_log(
                f"Updating target path for movie. From: {format_log_value(old_target)}<br/> to new dir: {format_log_value(target_path)}",
                level=Level.objects.get_info(),
                source="actionmgr",
                torrent=action.torrent,
            )
            action.target_dir = target_dir
            return normalized_file_name
        add_log(
            message=f"Could not find/build target folder for movie: title: {format_log_value(title)}, file_name: {format_log_value(file_name)}, imdbid: {format_log_value(imdbid)}",
            level=Level.objects.get_warning(),
            source="actionmgr",
            torrent=action.file.torrent,
        )
        return None

    def _organize(self, action: Action):
        if config.ORGANIZE_MOVIES == True:
            self.logger.info("Handling action for movies")
            movie = find_movie(action.files)
            if not movie:
                add_log(
                    message=f"Could not find movie file in torrent: {torrent_to_log(action.torrent)}, skipping organization",
                    level=Level.objects.get_warning(),
                    source="actionmgr",
                    torrent=action.torrent,
                )
                return True

            action.paths = []  # reset paths, because target_dir could have changed

            file_name = self._prepare_folders(
                movie, action
            )  # generate target_dir from movie file
            for (
                file
            ) in (
                action.files
            ):  # fill paths again, because target_dir could have changed
                source_path, target_path = action.build_paths(file)
                if file == movie:
                    action.paths.append(
                        (source_path, action.target_dir / file_name, file)
                    )
                    continue
                if is_known_movie_type(file):
                    new_name = self._prepare_folders(file, action)
                    action.paths.append(
                        (source_path, action.target_dir / new_name, file)
                    )
                    continue
                action.paths.append((source_path, target_path, file))

            return True
        return False

    def handle(self, action: Action):
        if not self._handle_type(self.movies_type, self._organize, action):
            self.logger.info(
                "Skipping movies organization action, it is disabled in settings"
            )

        if self.handler:
            self.handler.handle(action)


class MoveSeriesEnterHandler(ActionHandler):
    def __init__(self):
        super().__init__()
        self.movie_series_type = TorrentType.objects.get_movie_series()

    def _prepare_folders(self, file: TorrentFile, action: Action):
        import re

        file_name = file.name
        torbox_search = TorrentTorBoxSearchResult.objects.filter_by_torrent(
            action.torrent
        ).first()
        if not torbox_search:
            self.logger.debug(f"Torrent: {action.torrent} is not connected to search")
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
                f"Updating target path for movie series to existing dir:<br/> {format_log_value(target_path)}",
                level=Level.objects.get_info(),
                source="actionmgr",
                torrent=action.torrent,
            )
            action.target_dir = existing_dir

            return normalized_file_name
        if title and season:
            target_dir = Path(action.torrent_type.target_dir)
            if imdbid:
                title = title + f" [imdbid-{imdbid}]"
            target_dir = target_dir / title / f"season {season:02}"
            target_path = target_dir / normalized_file_name
            add_log(
                f"Updating target path for movie series to new dir:<br/> {format_log_value(target_path)}",
                level=Level.objects.get_info(),
                source="actionmgr",
                torrent=action.torrent,
            )
            action.target_dir = target_dir
            return normalized_file_name
        add_log(
            message=f"Could not find/build target folder for movie series: title: {format_log_value(title)}, file_name: {format_log_value(file_name)}, season: {format_log_value(season)}, episode: {format_log_value(episode)}, imdbid: {format_log_value(imdbid)}",
            level=Level.objects.warning(),
            source="actionmgr",
            torrent=action.torrent,
        )
        return None

    def _organize(self, action: Action):
        if config.ORGANIZE_MOVIE_SERIES == True:
            self.logger.info("Handling action for movie series")
            movie = find_movie(action.files)
            if not movie:
                add_log(
                    message=f"Could not find movie file in torrent: {torrent_to_log(action.torrent)}, skipping organization",
                    level=Level.objects.get_warning(),
                    source="actionmgr",
                    torrent=action.torrent,
                )
                return True
            action.paths = []  # reset paths, because target_dir could have changed
            file_name = self._prepare_folders(
                movie, action
            )  # generate target_dir from movie file
            for (
                file
            ) in (
                action.files
            ):  # fill paths again, because target_dir could have changed
                source_path, target_path = action.build_paths(file)
                if file == movie:
                    action.paths.append(
                        (source_path, action.target_dir / file_name, file)
                    )
                    continue
                if is_known_movie_type(file):
                    new_name = self._prepare_folders(file, action)
                    action.paths.append(
                        (source_path, action.target_dir / new_name, file)
                    )
                    continue
                action.paths.append((source_path, target_path, file))

            return True
        return False

    def handle(self, action: Action):
        if not self._handle_type(self.movie_series_type, self._organize, action):
            self.logger.info(
                "Skipping movie series organization action, it is disabled in settings"
            )

        if self.handler:
            self.handler.handle(action)


class ActionFactory:
    def __init__(self):
        self.logger = logging.getLogger("torbox")

    def create_action(
        self, torrent: Torrent, torrent_dir: str, files: list[TorrentFile]
    ) -> Action:
        enter_handler = CopyEnterHandler()
        enter_handler = MoviesEnterHandler().set_next(
            MoveSeriesEnterHandler().set_next(enter_handler)
        )
        exit_handler = StashRescanExitHandler().set_next(ExitHandler())
        torrent_type = torrent.torrent_type
        if torrent_type.action_on_finish == TorrentType.ACTION_DO_NOTHING:
            self.logger.debug("Creating action for nothing")
            enter_handler = NothingActionHandler()
            return ActionNothing(
                torrent=torrent,
                files=files,
                torrent_dir=torrent_dir,
                enter_handler=enter_handler,
                exit_handler=exit_handler,
            )
        if torrent_type.action_on_finish == TorrentType.ACTION_COPY:
            self.logger.debug("Creating action for copy")
            return ActionCopy(
                torrent=torrent,
                files=files,
                torrent_dir=torrent_dir,
                enter_handler=enter_handler,
                exit_handler=exit_handler,
            )
        if torrent_type.action_on_finish == TorrentType.ACTION_MOVE:
            self.logger.debug("Creating action for move")
            return ActionMove(
                torrent=torrent,
                files=files,
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
            add_log(
                message=f"File: {torrent_file_to_log(file)} is not done, skipping action execution for torrent: {torrent_to_log(file.torrent)}",
                level=Level.objects.get_warning(),
                source="actionmgr",
                torrent=file.torrent,
            )

            return False

        if not source_path.exists():
            self.status_mgr.action_error(
                file.torrent,
                message=f"Source file does not exist: {format_log_value(source_path)}",
            )
            add_log(
                message=f"File: {torrent_file_to_log(file)} does not exist at path: {format_log_value(source_path)}, skipping action execution for torrent: {torrent_to_log(file.torrent)}",
                level=Level.objects.get_error(),
                source="actionmgr",
                torrent=file.torrent,
            )
            return False
        return True

    def run(self, torrent: Torrent):
        actions = TorrentFile.objects.filter(
            torrent=torrent, action_on_finish_done=False, aria__done=True
        )
        self.status_mgr.action_start(
            torrent=torrent,
            message=f"Executing actions on finish for torrent: {torrent_to_log(torrent)}, actions to finish: {len(actions)}",
        )
        torrent_dir_name = prepare_torrent_dir_name(
            torrent.name
        )  # dir, where all torrent files will be stored in target dir(target dir is based on torrent_type)
        all_done = True
        files = []
        for file in actions:
            source_path = Path(file.aria.path)
            if not self._is_valid(file, source_path):
                all_done = False
                continue
            files.append(file)
        if files:
            with self.action_factory.create_action(
                torrent=torrent, torrent_dir=torrent_dir_name, files=files
            ) as action:
                action.exec()

        if all_done:
            self.status_mgr.torrent_done(torrent=torrent)
