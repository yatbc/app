from django.urls import path
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("start_api", views.start_api, name="start_api"),
    path("config", views.configuration, name="config"),
    path("log", views.error_log, name="error_log"),
    path("get_config", views.get_config, name="get_config"),
    path("api/save_config", views.save_config, name="save_config"),
    path("api/get_logs", views.get_logs, name="get_logs"),
    path(
        "api/check_task_status/<task_id>",
        views.check_task_status_api,
        name="check_task_status_api",
    ),
    path(
        "search_torrent/api/get_search_results/<query>",
        views.get_search_results,
        name="get_search_results",
    ),
    path(
        "search_torrent/api/get_search_results/<query>/S<int:season>",
        views.get_search_results,
        name="get_search_results",
    ),
    path(
        "search_torrent/api/get_search_results/<query>/S<int:season>/E<int:episode>",
        views.get_search_results,
        name="get_search_results",
    ),
    path(
        "search_torrent/api/add_torrent_from_search/<int:id>",
        views.add_torrent_from_search,
        name="add_torrent_from_search",
    ),
    path(
        "api/search_torrent/<query>",
        views.search_torrent_api,
        name="search_torrent_api",
    ),
    path(
        "api/search_torrent/<query>/S<int:season>",
        views.search_torrent_api,
        name="search_torrent_api",
    ),
    path(
        "api/search_torrent/<query>/S<int:season>/E<int:episode>",
        views.search_torrent_api,
        name="search_torrent_api",
    ),
    path("search_torrent/<query>", views.search_torrent, name="search_torrent"),
    path(
        "search_torrent/<query>/S<int:season>",
        views.search_torrent,
        name="search_torrent",
    ),
    path(
        "search_torrent/<query>/S<int:season>/E<int:episode>",
        views.search_torrent,
        name="search_torrent",
    ),
    path(
        "api/get_torrent_type_list",
        views.get_torrent_type_list,
        name="get_torrent_types",
    ),
    path(
        "api/update_torrent_type/<int:torrent_id>/<int:torrent_type_id>",
        views.update_torrent_type,
        name="update_torrent_type",
    ),
    path("api/data-updates/", views.data_updates, name="data_updates"),
    path(
        "api/update_torrent_list", views.update_torrent_list, name="update_torrent_list"
    ),
    path("api/get_torrents_list", views.get_torrent_list, name="get_torrents_list"),
    path(
        "api/change_torrent/<action>/<int:id>",
        views.change_torrent_api,
        name="change_torrent_api",
    ),
    path(
        "api/double_torrent/<int:id>",
        views.double_torrent_api,
        name="double_torrent_api",
    ),
    path(
        "api/request_torrent_files/<int:id>",
        views.download_torrent_files,
        name="download_torrent_files",
    ),
    path("torrent_details/<int:id>", views.torrent_details, name="torrent_details"),
    path("add_torrent", views.add_torrent, name="add_torrent"),
    path("api/add_torrent", views.add_torrent_api, name="add_torrent_api"),
    path("api/validate_torbox", views.validate_torbox, name="validate_torbox"),
    path("api/validate_aria", views.validate_aria, name="validate_aria"),
    path(
        "api/validate_transmission",
        views.validate_transmission,
        name="validate_transmission",
    ),
    path("api/validate_folders", views.validate_folders, name="validate_folders"),
    path("api/test_ip", views.test_ip, name="test_ip"),
    path("history", views.history, name="history"),
    path("api/delete_logs", views.delete_logs, name="delete_logs"),
    path("api/delete_history", views.delete_history, name="delete_history"),
    path("api/get_history", views.get_history, name="get_history"),
    path("api/add_referral", views.add_referral, name="add_referral"),
    path(
        "api/get_torrent_details/<int:id>",
        views.get_torrent_details,
        name="get_torrent_details",
    ),
    path(
        "api/get_torrent_speed_history/<int:id>",
        views.get_torrent_speed_history,
        name="get_torrent_speed_history",
    ),
    path(
        "api/get_torrent_seeders_history/<int:id>",
        views.get_torrent_seeders_history,
        name="get_torrent_seeders",
    ),
    path("api/get_torrent_log/<int:id>", views.get_torrent_log, name="get_torrent_log"),
]
