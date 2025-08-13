from django.db import models


class ErrorLog(models.Model):
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    level = models.CharField(max_length=50, default="ERROR")
    source = models.CharField(max_length=100, null=True, blank=True, default=None)


class TorrentType(models.Model):
    ACTION_DO_NOTHING = "Nothing"
    ACTION_COPY = "Copy"
    ACTION_MOVE = "Move"
    name = models.CharField(max_length=255)
    action_on_finish = models.CharField(default="Nothing", max_length=50)
    target_dir = models.TextField(null=True, blank=True, default=None)


class Torrent(models.Model):
    active = models.BooleanField(default=False)
    hash = models.CharField(max_length=255)
    name = models.TextField(default="Empty Torrent")
    size = models.IntegerField(default=0)
    created_at = models.DateTimeField()
    download_finished = models.BooleanField(default=False)
    download_present = models.BooleanField(default=False)
    tracker = models.TextField(default=None, null=True, blank=True)
    total_uploaded = models.IntegerField(default=0)
    total_downloaded = models.IntegerField(default=0)
    client = models.CharField(max_length=50, default="TorBox")
    internal_id = models.CharField(max_length=255, default=None, null=True, blank=True)
    deleted = models.BooleanField(default=False)
    magnet = models.TextField(default=None, null=True, blank=True)
    doubled = models.BooleanField(default=False)
    local_download_finished = models.BooleanField(default=False)
    local_download = models.BooleanField(default=False)
    local_download_progress = models.FloatField(default=0)
    redownload = models.BooleanField(default=False)
    torrent_type = models.ForeignKey(TorrentType, on_delete=models.CASCADE)
    local_status = models.CharField(max_length=150, null=True, blank=True, default=None)
    local_status_level = models.CharField(
        max_length=20, null=True, blank=True, default=None
    )


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


class TorrentTorBoxSearch(models.Model):
    query = models.TextField()
    date = models.DateTimeField()


class TorrentTorBoxSearchResult(models.Model):
    query = models.ForeignKey(TorrentTorBoxSearch, on_delete=models.CASCADE)
    hash = models.CharField(max_length=255)
    raw_title = models.TextField()
    title = models.CharField(max_length=255, null=True, blank=True, default=None)
    resolution = models.CharField(max_length=100, null=True, blank=True, default=None)
    year = models.CharField(max_length=5, null=True, blank=True, default=None)
    codec = models.CharField(max_length=255, null=True, blank=True, default=None)
    season = models.IntegerField(null=True, blank=True, default=None)
    episode = models.IntegerField(null=True, blank=True, default=None)
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
