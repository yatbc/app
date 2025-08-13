// common.js
function formatBytes(bytes, decimals = 2) {
  if (!+bytes) return "0 Bytes";

  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = [
    "Bytes",
    "KiB",
    "MiB",
    "GiB",
    "TiB",
    "PiB",
    "EiB",
    "ZiB",
    "YiB",
  ];

  const i = Math.floor(Math.log(bytes) / Math.log(k));

  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

document.addEventListener("alpine:init", () => {
  Alpine.store("appState", {
    query: "", // The shared search query

  });
});

function commonSearchValidator() {
  return {
    isValid: false,
    validationRegex: /^tt\d+(\/S\d+)*(\/E\d+)*$/,

    validateInput() {

      console.log("Validating input:", this.$store.appState.query);
      this.isValid = this.validationRegex.test(this.$store.appState.query);
    },
  };
}

function commonAlert() {
  return {
    alertVisible: false,
    alertText: "",
    alertSuccess: true,
    showAlert(text, success = true) {
      this.alertSuccess = success;
      this.alertText = text;
      this.alertVisible = true;
      if (success) {
        setTimeout(() => {
          this.alertVisible = false;
        }, 5000);
      }
    },
  };
}

function commonTooltips() {
  return {
    initBootstrapHints() {

      //const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
      //console.log([...tooltipTriggerList].map(tooltipTriggerEl => this.toolTips.push(new bootstrap.Tooltip(tooltipTriggerEl))));
    },
    updateTooltips() {
      Alpine.nextTick(() => {

        // const tooltipTriggerList = document.querySelectorAll('[data-bs-toggle="tooltip"]');
        // tooltipTriggerList.forEach((el) => {
        //   this.toolTips.push(new bootstrap.Tooltip(el));
        // });
      });
    }
  }
}

function commonCallApi() {
  return {
    isLoading: false,
    lastRequestId: null,
    wait_class: "text-primary",
    wait_text: "Please wait...",
    ...commonAlert(),
    ...commonTooltips(),
    checkTaskStatus(taskId, action) {
      this.isLoading = true;
      fetch(`/api/check_task_status/${taskId}`)
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
          json = response.json();

          return json;
        })
        .then((json) => {
          console.log("Task status response:", json);
          if (json.hasOwnProperty("error")) {
            throw new Error(json.error);
          }
          if (json.status === "DONE") {
            this.lastRequestId = null;
            this.isLoading = false;
            action();
          } else {
            console.log(
              "Task: " + taskId + " is still running, status:",
              json.status
            );
          }
        })
        .catch((error) => {
          console.error("Error checking task status:", error);
          this.showAlert("Error checking task status: " + error.message, false);
        });
    },
    callApi(
      api,
      errorMessage = "",
      successMessage = "",
      method = "GET",
      body = null,
      onSuccess = null,
      onError = null
    ) {
      this.isLoading = true;
      this.wait_text = "Action in progress. Please wait...";
      this.wait_class = "text-primary";
      options = {
        method: method,
      };
      if (method === "GET" && body) {
        method = "POST";
      }
      if (body) {
        csrftoken = document.querySelector("[name=csrfmiddlewaretoken]").value;
        options.body = JSON.stringify(body);
        options.headers = {
          "Content-Type": "application/json",
          "X-CSRFToken": csrftoken,
        };
      }
      fetch(api, options)
        .then((response) => {
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
          json = response.json();
          return json;
        })
        .then((json) => {
          console.log("API response:", json);
          console.log("Error?:", json.hasOwnProperty("error"));
          if (json.hasOwnProperty("error")) {
            if (onError) {
              onError(json);
            } else {
              this.showAlert(errorMessage + " " + json.error, false);
            }
            return json;
          }
          if (json.hasOwnProperty("request_id")) {
            this.lastRequestId = json.request_id;
            console.log("Last task ID:", this.lastRequestId);
          } else {
            this.lastRequestId = null;
            console.log("No request ID returned from API call: " + api);
          }
          if (successMessage) {
            this.showAlert(successMessage, true);
          }
          if (onSuccess) {
            console.log("Calling onSuccess callback with JSON:", json);
            onSuccess(json);
          }
          return json;
        })
        .catch((error) => {
          this.showAlert(
            errorMessage + " Failed to process request: " + error,
            false
          );
        })
        .finally(() => {
          this.isLoading = false; // will this cause issues if called from search?
        });
    },
    setupSSE(
      update_action = null,
      long_running_action = null,
      task_still_working_action = null,
      no_worker_action = null,
      no_tasks_action = null
    ) {
      this.sseSource = new EventSource("/api/data-updates/");
      this.sseSource.onmessage = (event) => {
        const data = JSON.parse(event.data);
        if (data.status === "Update") {
          if (update_action) {
            this.wait_text = "Data updated, refreshing...";
            this.wait_class = "text-success";
            update_action();
          }
        }
        if (data.status === "TaskStillWorking") {
          console.log("Task is still running.");
          this.isLoading = true;
          this.wait_text = "Task: <i>'" + data.task + "</i>' is running, please wait...";
          this.wait_class = "text-info";
          if (task_still_working_action) {
            task_still_working_action();
          }
        }
        if (data.status === "LongRunning") {
          this.isLoading = true;
          this.wait_class = "text-warning";
          this.wait_text =
            "Task: <i>'" + data.task + "'</i> is still running. Please wait...";
          console.log("Long running task detected.");
          if (long_running_action) {
            long_running_action();
          }
        }
        if (data.status === "NoWorker") {
          this.isLoading = true;
          this.wait_class = "text-danger";
          this.wait_text =
            "No active worker. Is db_worker running? Task: <i>'" + data.task + "'</i> is waiting.";
          console.log("No active worker.");
          if (no_worker_action) {
            no_worker_action();
          }
        }
        if (data.status === "NoTasks") {
          this.isLoading = false;
          this.lastRequestId = null;
          this.wait_text = "Waiting for tasks...";
          this.wait_class = "text-info";
          if (no_tasks_action) {
            console.log("Calling task for no tasks running")
            no_tasks_action();
          }

        }
      };
      this.sseSource.onerror = (error) => {
        this.wait_class = "text-danger";
        this.wait_text =
          "Could not connect to server. Attepmting to reconnect... (Is server running?)";
        console.error("SSE error:", error);
        this.sseSource.close();
        setTimeout(() => this.setupSSE(), 5000); // Attempt to reconnect after a delay
      };
    },
  };
}
