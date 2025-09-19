from django.db import models
from django.core.cache import cache
from django.db.models import Q


def get_or_set(key, getter, timeout=3600):
    value = cache.get(key)
    if value is None:
        value = getter()
        cache.set(key, value, timeout)
    return value


def get_value(manager: models.Manager, name):
    return get_or_set(name, lambda: manager.get(name=name))


class LevelManager(models.Manager):

    def get_info(self):
        return get_value(self, "INFO")

    def get_warning(self):
        return get_value(self, "WARNING")

    def get_error(self):
        return get_value(self, "ERROR")

    def get_debug(self):
        return get_value(self, "DEBUG")


class Level(models.Model):
    name = models.CharField(max_length=20)
    objects = LevelManager()


class ErrorLog(models.Model):
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    level = models.ForeignKey(Level, on_delete=models.CASCADE)
    source = models.CharField(max_length=100, null=True, blank=True, default=None)


class TorrentStatus(models.Model):
    name = models.CharField(max_length=100)
    level = models.ForeignKey(Level, on_delete=models.CASCADE)


class TorrentTypeManager(models.Manager):
    def get_no_type(self):
        return get_value(self, "No Type")

    def get_movie_series(self):
        return get_value(self, "Movie Series")

    def get_other(self):
        return get_value(self, "Other")

    def get_audiobooks(self):
        return get_value(self, "Audiobooks")

    def get_movies(self):
        return get_value(self, "Movies")

    def get_home_video(self):
        return get_value(self, "Home Videos")


class TorrentType(models.Model):
    ACTION_DO_NOTHING = "Nothing"
    ACTION_COPY = "Copy"
    ACTION_MOVE = "Move"
    name = models.CharField(max_length=255)
    action_on_finish = models.CharField(default="Nothing", max_length=50)
    target_dir = models.TextField(null=True, blank=True, default=None)

    objects = TorrentTypeManager()


class Torrent(models.Model):
    active = models.BooleanField(default=False)
    hash = models.CharField(max_length=255)
    name = models.TextField(default="Placeholder Torrent")
    size = models.IntegerField(default=0)
    created_at = models.DateTimeField()
    download_finished = models.BooleanField(default=False)
    download_present = models.BooleanField(default=False)
    tracker = models.TextField(default=None, null=True, blank=True)
    total_uploaded = models.IntegerField(default=0)
    total_downloaded = models.IntegerField(default=0)
    client = models.CharField(max_length=50, default="TorBox")
    internal_id = models.CharField(
        max_length=255, default=None, null=True, blank=True
    )  # remote client id
    deleted = models.BooleanField(default=False)
    magnet = models.TextField(default=None, null=True, blank=True)
    doubled = models.BooleanField(default=False)
    local_download_finished = models.BooleanField(default=False)
    local_download = models.BooleanField(default=False)
    local_download_progress = models.FloatField(default=0)
    redownload = models.BooleanField(default=False)
    torrent_type = models.ForeignKey(TorrentType, on_delete=models.CASCADE)
    local_status = models.ForeignKey(TorrentStatus, on_delete=models.CASCADE)
    finished_at = models.DateTimeField(default=None, null=True)
    cached = models.BooleanField(default=False)  # was cached on remote client?
    private = models.BooleanField(default=False)  # is from private tracker


class TorrentQueue(models.Model):
    added_at = models.DateTimeField(auto_now_add=True)
    torrent_type = models.ForeignKey(TorrentType, on_delete=models.CASCADE)
    magnet = models.TextField(default=None, null=True, blank=True)
    torrent_file = models.BinaryField(default=None, null=True)
    torrent_file_name = models.TextField(default=None, null=True, blank=True)
    torrent_private = models.BooleanField(default=False)
    priority = models.IntegerField(default=0)


class TorrentErrorLog(models.Model):
    torrent = models.ForeignKey(Torrent, on_delete=models.CASCADE)
    error_log = models.ForeignKey(ErrorLog, on_delete=models.CASCADE)


class TorrentHistory(models.Model):
    torrent = models.ForeignKey(Torrent, on_delete=models.CASCADE)
    download_speed = models.IntegerField(default=0)
    upload_speed = models.IntegerField(default=0)
    eta = models.IntegerField(default=None, null=True, blank=True)
    peers = models.IntegerField(default=0)
    ratio = models.FloatField(default=0.0)
    seeds = models.IntegerField(default=0)
    progress = models.FloatField(default=0.0)
    updated_at = models.DateTimeField()
    availability = models.FloatField(default=0.0)
    state = models.TextField(default="Unknown")


class AriaDownloadStatus(models.Model):
    internal_id = models.CharField(max_length=255, null=True, blank=True, default=None)
    path = models.CharField(max_length=255)
    progress = models.FloatField(default=0)
    done = models.BooleanField(default=False)
    error = models.TextField(default="", blank=True)
    status = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, default=None)


class TorrentFile(models.Model):
    torrent = models.ForeignKey(Torrent, on_delete=models.CASCADE)
    aria = models.ForeignKey(
        AriaDownloadStatus,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        default=None,
    )
    name = models.TextField()
    short_name = models.TextField(null=True, blank=True)
    size = models.IntegerField()
    hash = models.CharField(max_length=255, null=True, blank=True)
    mime_type = models.CharField(max_length=100, null=True, blank=True)
    internal_id = models.CharField(max_length=100, null=True, blank=True, default=None)
    action_on_finish_done = models.BooleanField(default=False)


class TorrentTorBoxSearchManager(models.Manager):
    def filter_by_query_season_episode(self, query, season=None, episode=None):
        filter = self.filter(query=query)
        if season:
            filter = filter.filter(season=season)
        if episode:
            filter = filter.filter(episode=episode)
        return filter


class TorrentTorBoxSearch(models.Model):
    query = models.TextField()
    date = models.DateTimeField()
    season = models.IntegerField(null=True, blank=True, default=None)
    episode = models.IntegerField(null=True, blank=True, default=None)
    objects = TorrentTorBoxSearchManager()


class TorrentTorBoxSearchResultManager(models.Manager):
    def filter_by_torrent(self, torrent: Torrent):
        return self.filter(Q(hash=torrent.hash) | Q(torrent=torrent))

    def delete_unassigned(self, query: TorrentTorBoxSearch):
        return self.filter(
            torrent__isnull=True, queue__isnull=True, query=query
        ).delete()


class TorrentTorBoxSearchResult(models.Model):
    query = models.ForeignKey(TorrentTorBoxSearch, on_delete=models.CASCADE)
    hash = models.CharField(max_length=255, db_index=True)
    raw_title = models.TextField()
    title = models.CharField(max_length=255, null=True, blank=True, default=None)
    resolution = models.CharField(max_length=100, null=True, blank=True, default=None)
    year = models.CharField(max_length=5, null=True, blank=True, default=None)
    codec = models.CharField(max_length=255, null=True, blank=True, default=None)
    season = models.IntegerField(null=True, blank=True, default=None)
    episode = models.CharField(
        max_length=255, null=True, blank=True, default=None
    )  # stores episodes as "1,2,3,4"
    episode_name = models.CharField(max_length=255, blank=True, default=None, null=True)
    magnet = models.TextField()
    age = models.CharField(max_length=10)
    cached = models.BooleanField()
    last_known_seeders = models.IntegerField()
    last_known_peers = models.IntegerField()
    size = models.IntegerField()
    torrent = models.ForeignKey(
        Torrent, null=True, blank=True, default=None, on_delete=models.SET_NULL
    )
    queue = models.ForeignKey(  # needed to know if I can clear the search
        TorrentQueue, null=True, blank=True, default=None, on_delete=models.SET_NULL
    )

    objects = TorrentTorBoxSearchResultManager()


class ArrBase(models.Model):
    added_at = models.DateTimeField(auto_now_add=True)
    last_checked = models.DateTimeField(null=True, blank=True, default=None)
    last_found = models.DateTimeField(null=True, blank=True, default=None)
    active = models.BooleanField(default=True)

    last_added_torrent = models.OneToOneField(
        Torrent,
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET_NULL,
        related_name="arr_last_added",
    )
    torrent_type = models.ForeignKey(TorrentType, on_delete=models.CASCADE)
    include_words = models.TextField(null=True, blank=True, default=None)
    exclude_words = models.TextField(null=True, blank=True, default=None)


class ArrMovieSeries(ArrBase):
    imdbid = models.CharField(max_length=20, unique=True)
    title = models.CharField(max_length=255, null=True, blank=True, default=None)
    quality = models.CharField(max_length=50, null=True, blank=True, default=None)
    encoder = models.CharField(max_length=100, null=True, blank=True, default=None)
    requested_season = models.IntegerField()
    requested_episode = models.IntegerField()


class ArrErrorLog(models.Model):
    arr = models.ForeignKey(ArrBase, on_delete=models.CASCADE)
    error_log = models.ForeignKey(ErrorLog, on_delete=models.CASCADE)
