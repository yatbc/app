function getData() {
  return {
    ...commonPagination(),
    log: [],
    log_sources: [],
    log_source_filter_id: 0,
    full: false,
    fetchData() {
      this.isLoading = true;
      this.callApi(
        (api = "/api/get_logs"),
        (errorMessage = "Failed to read error log"),
        (successMessage = null),
        (method = "GET"),
        (body = null),
        (onSuccess = (json) => {
          console.log("Fetched logs:", json);
          this.log = json.log;
          this.pageCurrentItems = this.log.length;
        }),
        (onError = null)
      );
    },
    fetchLogSourcesData() {
      this.isLoading = true;
      this.callApi(
        (api = "/api/get_log_sources_list"),
        (errorMessage = "Failed to read log sources"),
        (successMessage = null),
        (method = "GET"),
        (body = null),
        (onSuccess = (json) => {
          this.log_sources = json.log_sources;
          console.log("Fetched log sources:", this.log_sources);

        }),
        (onError = null)
      );
    },
    deleteLogs(command = "older") {

      this.dialogConfirmBody = "Are you sure you want to delete logs?";
      this.dialogConfirmHeader = "Confirm delete";
      this.dialogConfirmCallback = () => {
        this.isLoading = true;
        this.callApi(
          (api = "/api/delete_logs"),
          (errorMessage = "Failed to delete log"),
          (successMessage = "Log deleted successfully"),
          (method = "POST"),
          (body = { command: command }),
          (onSuccess = () => {
            this.isLoading = false;
            this.fetchData();
          }),
          (onError = () => {
            this.isLoading = false;
          })
        );
      };
      this.showModal = true;

    },
    filter(logSourceId) {
      console.log("Filtering logs: " + logSourceId);
      this.extraFilter = "/" + logSourceId;
      this.reloadPagination();
    },
    init() {
      this.fetchLogSourcesData()
      this.paginatedPageApi = "/api/get_logs";
      this.extraFilter = "/0" // load all logs 
      this.paginationNewDataCallback = (json) => {
        this.log = json.log;
        this.pageCurrentItems = this.log.length;
        console.log(this.pageCurrentItems);
        this.updateTooltips();
      }
      this.reloadPagination();

    },

    sseSource: null,
  };
}
