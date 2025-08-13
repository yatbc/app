function getData() {
  return {
    ...commonCallApi(),
    torrents: [],
    taskId: globalTaskId,
    fetchData() {
      this.isLoading = true;
      const searchQuery = Alpine.store("appState").query;
      console.log("searchQuery", searchQuery);
      fetch(`/search_torrent/api/get_search_results/` + searchQuery)
        .then((res) => res.json())
        .then((data) => {
          this.isLoading = false;
          this.torrents = data.torrents;
          console.log("Fetched torrents:", this.torrents);
        });
    },
    init() {
      this.isLoading = true; // Search is always loading initially
      this.setupSSE(
        (update_action = () => {
          this.checkTaskStatus(this.taskId, this.fetchData.bind(this));
        })
      );

    },
    downloadFile(id) {
      this.callApi(
        "/search_torrent/api/add_torrent_from_search/" + id,
        (errorMessage = "Failed to add torrent"),
        (successMessage = "Torrent scheduled to add")
      );
    },
    sseSource: null,
  };
}
