function getData() {
    return {
        ...commonCallApi(),
        queue: [],
        torrent_types: [],
        fetchTorrentTypes() {
            fetch(`/api/get_torrent_type_list`)
                .then((res) => res.json())
                .then((data) => {
                    this.torrent_types = data.torrent_types;
                    console.log("Torrent types fetched:", this.torrent_types);
                    this.fetchData();
                    this.callApi("/api/update_queue_folders");
                });
        },
        deleteQueue(command = "single", queue_id = null) {

            body = { command: command }
            if (queue_id) {
                body["queue_id"] = queue_id;
            }
            this.dialogConfirmBody = "Are you sure you want to delete queue item(s)?";
            this.dialogConfirmHeader = "Confirm delete";
            this.dialogConfirmCallback = () => {
                this.isLoading = true;
                this.callApi(
                    (api = "/api/delete_queue"),
                    (errorMessage = "Failed to delete queue"),
                    (successMessage = "Queue deleted successfully"),
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
            };
            this.showModal = true;

        },
        fetchData() {
            this.isLoading = true;
            this.callApi(
                (api = "/api/get_active_queue"),
                (errorMessage = "Failed to read queue"),
                (successMessage = null),
                (method = "GET"),
                (body = null),
                (onSuccess = (json) => {
                    console.log("Fetched:", json);
                    this.queue = json.queue;
                }),
                (onError = null)
            );
        },
        handleSelection(queueId, newTorrentTypeId) {
            console.log(
                `Queue ID: ${queueId}, newTorrentTypeId: ${newTorrentTypeId}`
            );
            this.callApi(
                `/api/update_torrent_type_in_queue/${queueId}/${newTorrentTypeId}`,
                "",
                "Torrent type updated successfully"
            );
        },
        init() {
            this.setupSSE(
                (update_action = () => {
                    if (this.taskId) {
                        this.checkTaskStatus(this.taskId, this.fetchData.bind(this));
                    } else {
                        this.fetchData();
                    }
                })
            );
            this.fetchTorrentTypes();


        },

        sseSource: null,
    };
}
