function getData() {
  return {
    ...commonCallApi(),
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
        }),
        (onError = null)
      );
    },
    deleteLogs(command = "older") {
      this.isLoading = true;
      this.callApi(
        (api = "/api/delete_logs"),
        (errorMessage = "Failed to delete error log"),
        (successMessage = "Error log deleted successfully"),
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
    },
    init() {
      this.fetchData();

    },

    sseSource: null,
  };
}
