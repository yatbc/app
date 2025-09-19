from .models import ArrMovieSeries, TorrentTorBoxSearchResult, Torrent, Level
from django.db.models import Q, F, ExpressionWrapper, fields
from django.utils import timezone
from datetime import timedelta
from .torboxapi import search_torrent, add_torrent_by_magnet
from .torboxapi import TorBoxApi
from .commondao import add_log
import logging
import re

SOURCE = "arrmanager"
ANY = "any"  # special value for any quality or encoder


def get_next_arrs():
    return (
        ArrMovieSeries.objects.annotate(
            ago=ExpressionWrapper(
                timezone.now() - F("last_checked"), output_field=fields.DurationField()
            )
        )
        .filter(
            Q(last_checked__isnull=True) | Q(ago__gt=timedelta(days=1)), active=True
        )
        .order_by("last_checked")
    )


def get_all_arrs():
    return (
        ArrMovieSeries.objects.annotate(
            last_checked_ago=ExpressionWrapper(
                timezone.now() - F("last_checked"), output_field=fields.DurationField()
            )
        )
        .annotate(
            last_found_ago=ExpressionWrapper(
                timezone.now() - F("last_found"), output_field=fields.DurationField()
            )
        )
        .order_by("imdbid")
    )


def get_api():
    return TorBoxApi()


def arrs_to_str(arrs: list[ArrMovieSeries]):
    return ",".join([entry.raw_title for entry in arrs])


def build_list(query: str, remove_any=True):
    if not query:
        return []
    queries = [q.strip().lower() for q in query.split(",")]
    if remove_any and ANY in queries:
        queries.remove(ANY)
    return queries


def get_episodes(result: TorrentTorBoxSearchResult):
    return [int(e) for e in build_list(result.episode)]


def build_search_pattern(query: str, remove_any=True):
    queries = build_list(query, remove_any=remove_any)
    if not queries:
        return None
    return re.compile(r"\b(" + "|".join(queries) + r")\b")


# sort by quality, encoder, include_words, cache, seeders
def get_best_match(matches: list[TorrentTorBoxSearchResult], arr: ArrMovieSeries):
    def sort_key(result: TorrentTorBoxSearchResult):
        logger = logging.getLogger("torbox")
        quality_score = 0  # ANY will be 0
        if arr.quality:
            qualities = build_list(arr.quality)
            qualities = [
                re.compile(r"\b" + q.strip().lower() + r"\b") for q in qualities
            ]
            for idx, q in enumerate(qualities):
                if q.search(result.raw_title.lower()):
                    quality_score = len(qualities) - idx
                    break
        encoder_score = 0  # ANY will be 0
        if arr.encoder:
            encoders = build_list(arr.encoder)
            encoders = [re.compile(r"\b" + e.strip().lower() + r"\b") for e in encoders]
            for idx, e in enumerate(encoders):
                if e.search(result.raw_title.lower()):
                    encoder_score = len(encoders) - idx
                    break
        include_score = 0  # ANY will be 0
        if arr.include_words:
            include_words = build_list(arr.include_words)
            include_words = [
                re.compile(r"\b" + e.strip().lower() + r"\b") for e in include_words
            ]
            for idx, e in enumerate(include_words):
                if e.search(result.raw_title.lower()):
                    include_score += len(include_words) - idx

        cache_score = 1 if result.cached else 0
        episode_score = len(get_episodes(result))
        logger.debug(
            f"Sort score for: {result.raw_title} quality_score: {quality_score}, encoder_score: {encoder_score}, include_score: {include_score}, cache_score: {cache_score}, episode_score: {episode_score}, seeders: {result.last_known_seeders}"
        )
        return (
            quality_score,
            encoder_score,
            include_score,
            cache_score,
            episode_score,
            result.last_known_seeders,
        )

    logger = logging.getLogger("torbox")
    if not matches:
        return None
    matches.sort(key=sort_key, reverse=True)
    logger.debug(f"Sorted matches: {arrs_to_str(matches)}")
    return matches[0]


def process_arr(arr_id: int):
    logger = logging.getLogger("torbox")
    arr = ArrMovieSeries.objects.filter(id=arr_id).first()
    if arr is None:
        logger.info(
            f"User removed arr: {arr_id} before, app had a chance to process it"
        )
        return None, False

    age_of_last_found = (
        timezone.now() - arr.last_found
        if arr.last_found
        else timezone.now() - arr.added_at
    )
    logger.info(
        f"Processing arr: {arr.imdbid} - {arr.title}, age_of_last_found: {age_of_last_found}"
    )
    api = get_api()
    arr.last_checked = timezone.now()
    torrent_search = search_torrent(
        query=arr.imdbid,
        season=arr.requested_season,
        episode=arr.requested_episode,
        api=api,
    )
    search_results = TorrentTorBoxSearchResult.objects.filter(query=torrent_search)
    found_matches = []

    encoder_pattern = build_search_pattern(arr.encoder)
    quality_pattern = build_search_pattern(arr.quality)
    include_pattern = build_search_pattern(arr.include_words)
    exclude_pattern = build_search_pattern(arr.exclude_words)
    any_pattern = build_search_pattern(ANY, remove_any=False)
    for result in search_results:
        episodes = get_episodes(result)
        logger.debug(episodes)
        if (
            episodes and arr.requested_episode not in episodes
        ):  # assume empty episodes mean full season
            logger.debug(
                f"Skipping {result.raw_title} due to episode mismatch: {arr.requested_episode} not in {result.episode}"
            )
            continue
        if not result.season or arr.requested_season != result.season:
            logger.debug(
                f"Skipping {result.raw_title} due to season mismatch: {arr.requested_season} != {result.season}"
            )
            continue

        if quality_pattern:
            if not quality_pattern.search(
                result.raw_title.lower()
            ) and not any_pattern.search(arr.quality.lower()):
                logger.debug(
                    f"Skipping {result.raw_title} due to quality: {arr.quality}"
                )
                continue
        if encoder_pattern:
            if not encoder_pattern.search(
                result.raw_title.lower()
            ) and not any_pattern.search(arr.encoder.lower()):
                logger.debug(
                    f"Skipping {result.raw_title} due to encoder: {arr.encoder}"
                )
                continue
        if exclude_pattern and exclude_pattern.search(result.raw_title.lower()):
            logger.debug(
                f"Skipping {result.raw_title} due to exclude words: {exclude_pattern.search(result.raw_title.lower()).group()}"
            )
            continue
        if (
            include_pattern
            and not include_pattern.search(result.raw_title.lower())
            and not any_pattern.search(arr.include_words.lower())
        ):
            logger.debug(
                f"Skipping {result.raw_title} due to missing any of include words: {arr.include_words}"
            )
            continue
        if result.torrent:  # user already added this torrent
            continue
        found_matches.append(result)

        if not arr.title:
            arr.title = result.title

    if not found_matches:
        if age_of_last_found > timedelta(days=9):
            arr.active = False
            arr.save()
            add_log(
                message=f"Could not find torrent for arr {arr.imdbid} {arr.title} S{arr.requested_season}E{arr.requested_episode} in over 9 days. Disabling arr.",
                level=Level.objects.get_warning(),
                source=SOURCE,
                arr=arr,
            )
            return arr, False

        if age_of_last_found > timedelta(days=7) and age_of_last_found < timedelta(
            days=9
        ):
            arr.requested_season += 1
            arr.requested_episode = 1
            arr.save()
            add_log(
                message=f"Could not find torrent for arr {arr.imdbid} {arr.title} S{arr.requested_season-1}E{arr.requested_episode} in over 7 days. Moving to season {arr.requested_season}.",
                level=Level.objects.get_info(),
                source=SOURCE,
                arr=arr,
            )
            return arr, False

        arr.save()
        add_log(
            message=f"Could not find torrent for arr {arr.imdbid} {arr.title} S{arr.requested_season}E{arr.requested_episode} at this time. Will try tomorrow.",
            level=Level.objects.get_info(),
            source=SOURCE,
            arr=arr,
        )
        return arr, False

    best_match = get_best_match(found_matches, arr)
    torrent, queue = add_torrent_by_magnet(
        magnet=best_match.magnet, torrent_type_id=arr.torrent_type.id, api=api
    )
    request_text = f"S{arr.requested_season}/E{arr.requested_episode}"
    arr.last_found = timezone.now()
    if best_match.episode:
        next_episode = max(get_episodes(best_match)) + 1
        logger.debug(f"Found match for: {request_text}, updating with: {next_episode}")
        arr.requested_episode = next_episode
    else:
        arr.requested_episode = 1
        arr.requested_season += 1
        add_log(
            message=f"From arr {arr.imdbid} found full season: {best_match.raw_title}, switching to next one: S{arr.requested_season}/E{arr.requested_episode}",
            level=Level.objects.get_info(),
            source=SOURCE,
            torrent=torrent,
            arr=arr,
        )
    arr.active = True
    arr.save()
    if torrent:
        arr.last_added_torrent = torrent
        arr.save()
        best_match.torrent = torrent
        best_match.save()
        add_log(
            message=f"Added torrent {best_match.raw_title} from arr {arr.imdbid}, to fulfill request for: {request_text}",
            level=Level.objects.get_info(),
            source=SOURCE,
            torrent=torrent,
            arr=arr,
        )
        return arr, True
    best_match.queue = queue
    best_match.save()
    add_log(
        message=f"Added torrent  {best_match.raw_title} from arr {arr.imdbid} to queue {queue.id}, to fulfill request for: {request_text}",
        level=Level.objects.get_info(),
        source=SOURCE,
        arr=arr,
    )
    return arr, True
