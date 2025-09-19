function getData() {
  return {
    ...commonCallApi(),
    ...getAddTorrent(),

    torrents: [],
    summary: [],
    torrent_types: [],
    queue_size: 0,

    fetchData() {
      fetch(`api/get_torrents_list`)
        .then((res) => res.json())
        .then((data) => {
          if (this.torrent_types.length == 0) {
            console.log("Got torrent types from data");
            this.torrent_types = data.torrent_types;
          }
          this.torrents = data.torrents;
          this.summary = data.summary;
          this.queue_size = data.queue_size
          console.log(this.torrents);
          console.log(this.torrent_types);
          this.updateTooltips();
        });
    },
    fetchTorrentTypes() {
      fetch(`api/get_torrent_type_list`)
        .then((res) => res.json())
        .then((data) => {
          this.torrent_types = data.torrent_types;
          console.log(this.torrent_types);
          this.fetchData();
        });
    },
    init() {
      this.isLoading = true;
      this.initAddTorrent();
      this.initBootstrapHints();
      this.setupSSE(
        (update_action = () => {
          this.lastRequestId = null;
          this.fetchData();
        })
      );
      this.updateTorrentList();
      this.fetchTorrentTypes();
      setInterval(() => {
        this.updateTorrentList();
      }, 60000);
    },
    changeTorrent(action, id) {
      this.callApi("/api/change_torrent/" + action + "/" + id);
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
      this.dialogConfirmCallback = () => {
        this.showAlert("Torrent scheduled for deletion");
        this.changeTorrent("delete", id);
        this.torrents.splice(index, 1);
      };
      this.showModal = true;
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
