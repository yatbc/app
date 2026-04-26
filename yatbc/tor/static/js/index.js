function getData() {
  return {
    ...commonPagination(),
    ...getAddTorrent(),

    torrents: [],
    summary: [],
    trackers: [],
    torrent_types: [],
    queue_size: 0,
    selectedTorrentStatusId: Alpine.$persist(0).as('selectedTorrentStatusId'),
    selectedTorrentTypeId: Alpine.$persist(0).as('selectedTorrentTypeId'),
    selectedClient: Alpine.$persist("ALL").as('selectedClient'),
    selectedPrivateStatus: Alpine.$persist("ALL").as('selectedPrivateStatus'),
    selectedName: Alpine.$persist("").as('selectedName'),
    selectedTracker: Alpine.$persist("ALL").as('selectedTracker'),
    torrent_statuses: [],
    torrent_types_filter: [],

    fetchData() {
      this.updateFilters();
      this.reloadPagination();
    },
    fetchTorrentTypes() {
      fetch(`api/get_torrent_type_list`)
        .then((res) => res.json())
        .then((data) => {
          this.torrent_types = data.torrent_types;
          this.torrent_types_filter = data.torrent_types;
          this.torrent_types_filter.unshift({ id: 0, name: "ALL" });

          console.log(this.torrent_types);
          this.fetchData();
        });
    },
    fetchTorrentStatuses() {
      fetch(`api/get_torrent_status_list`)
        .then((res) => res.json())
        .then((data) => {
          this.torrent_statuses = data.torrent_status;
          console.log(this.torrent_statuses);
        });
    },
    filterByName(name) {
      this.selectedName = name.trim();
      this.fetchData();
    },
    updateFilters() {
      if (this.selectedName == "") {
        this.extraFilter = `/${this.selectedTorrentStatusId}/${this.selectedTorrentTypeId}/${this.selectedClient}/${this.selectedPrivateStatus}/${this.selectedTracker}`;
      } else {
        this.extraFilter = `/${this.selectedTorrentStatusId}/${this.selectedTorrentTypeId}/${this.selectedClient}/${this.selectedPrivateStatus}/${this.selectedTracker}/${this.selectedName}`;
      }
    },
    filterByTracker(tracker) {
      this.selectedTracker = tracker;
      this.fetchData();
    },
    filterByPrivateStatus(private) {
      this.selectedPrivateStatus = private;
      this.fetchData();
    },
    filterByClient(client) {
      this.selectedClient = client;
      this.fetchData();
    },
    filterByStatus(statusId) {
      this.selectedTorrentStatusId = statusId;
      this.fetchData();
    },
    filterByTorrentType(torrentTypeId) {
      this.selectedTorrentTypeId = torrentTypeId;
      this.fetchData();
    },
    init() {
      this.updateFilters(0, 0, "");
      this.isLoading = true;
      this.initAddTorrent();
      this.initBootstrapHints();
      this.setupSSE(
        (update_action = () => {
          this.lastRequestId = null;
          this.fetchData();
        })
      );
      this.paginatedPageApi = "/api/get_torrents_list";
      this.paginationNewDataCallback = (data) => {
        if (this.torrent_types.length == 0) {
          console.log("Got torrent types from data");
          this.torrent_types = data.torrent_types;
        }
        this.torrents = data.torrents;
        this.summary = data.summary;
        if (data.trackers.length > this.trackers.length) {//fixme: move trackers to separate tables
          this.trackers = data.trackers;
        }
        this.queue_size = data.queue_size
        this.pageCurrentItems = this.torrents.length;
        console.log(this.torrents);
        console.log(this.torrent_types);
        console.log(this.summary);
        this.updateTooltips();
      }
      this.updateTorrentList();
      this.fetchTorrentTypes();
      this.fetchTorrentStatuses();
      setInterval(() => {
        this.updateTorrentList();
      }, 60000);
    },
    changeTorrent(action, id, delete_files = 0) {
      this.callApi("/api/change_torrent/" + action + "/" + id + "/" + delete_files);
    },
    handleSelection(torrentId, newTorrentTypeId) {
      console.log(
        `Torrent ID: ${torrentId}, newTorrentTypeId: ${newTorrentTypeId}`
      );
      this.callApi(
        `/api/update_torrent_type/${torrentId}/${newTorrentTypeId}`,
        "",
        "Torrent type updated successfully"
      );
    },
    updateTorrentList() {
      this.callApi("/api/update_torrent_list");
    },

    deleteTorrent(id, index) {
      this.dialogConfirmBody = "Are you sure you want to delete:<br/>'" + this.torrents[index].torrent.name + "'?";
      this.dialogConfirmHeader = "Confirm delete";
      if (this.torrents[index].torrent.client == "Transmission") {
        this.dialogConfirmShowCheckBox = true;
        this.dialogConfirmCheckBoxValue = false;
        this.dialogConfirmCheckBoxText = "Also delete downloaded data on remote client";
      }

      this.dialogConfirmCallback = () => {
        this.showAlert("Torrent scheduled for deletion");
        this.changeTorrent("delete", id, this.dialogConfirmCheckBoxValue ? 1 : 0);
        this.torrents.splice(index, 1);
      };
      this.showModal = true;
    },
    finishTorrent(id) {
      this.callApi(
        (api = "/api/force_finish_torrent/" + id),
        (errorMessage = "Failed to mark torrent as done"),
        (successMessage = null),
        (method = "GET"),
        (body = null),
        (onSuccess = (data) => {
          this.fetchData();
        }),
        (onError = null)
      );
    },
    redownloadLocalFiles(id) {
      this.callApi(
        (api = "/api/redownload_torrent_files/" + id),
        (errorMessage = null),
        (successMessage = "Torrent scheduled to redownload local files"),
        (method = "GET"),
        (body = null),
        (onSuccess = (data) => {
          this.fetchData();
        }),
        (onError = null)
      );
    },
    doubleTorrent(id) {
      this.callApi(
        "/api/double_torrent/" + id,
        "",
        "Torrent scheduled to double"
      );
    },
    downloadFile(id) {
      this.callApi(
        "api/request_torrent_files/" + id,
        "Could not add file to local download. Are you connected?",
        "Torrent files scheduled to download"
      );
    },
    sseSource: null,
  };
}
