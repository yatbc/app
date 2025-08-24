function getData() {
  return {
    ...commonPagination(),
    log: [],
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
    init() {
      this.fetchData();
      this.paginatedPageApi = "/api/get_logs";
      this.paginationNewDataCallback = (json) => {
        this.log = json.log;
        this.pageCurrentItems = this.log.length;
        console.log(this.pageCurrentItems);
        this.updateTooltips();
      }

    },

    sseSource: null,
  };
}
