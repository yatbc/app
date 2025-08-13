function getData() {
  return {
    ...commonCallApi(),
    history: [],
    torrent_types: [],
    fetchTorrentTypes() {
      fetch(`/api/get_torrent_type_list`)
        .then((res) => res.json())
        .then((data) => {
          this.torrent_types = data.torrent_types;
          console.log("Torrent types fetched:", this.torrent_types);
          this.fetchData();
        });
    },
    fetchData() {
      this.isLoading = true;
      this.callApi(
        (api = "/api/get_history"),
        (errorMessage = "Failed to read error history"),
        (successMessage = null),
        (method = "GET"),
        (body = null),
        (onSuccess = (json) => {
          console.log("Fetched:", json);
          this.history = json.history;
          this.updateTooltips();
        }),
        (onError = null)
      );
    },
    deleteHistory(command = "older", torrent_id = null) {
      this.isLoading = true;
      body = { command: command }
      if (torrent_id) {
        body["torrent_id"] = torrent_id;
      }
      this.callApi(
        (api = "/api/delete_history"),
        (errorMessage = "Failed to delete history"),
        (successMessage = "History deleted successfully"),
        (method = "POST"),
        (body = body),
        (onSuccess = () => {
          this.isLoading = false;
          this.fetchData();
        }),
        (onError = () => {
          this.isLoading = false;
        })
      );
    },
    init() {
      this.initBootstrapHints();
      this.fetchTorrentTypes();

    },

    sseSource: null,
  };
}
