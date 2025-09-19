function getData() {
    return {
        ...commonPagination(),
        arr: [],
        arrObject: {
            id: null,
            imdbid: "",
            quality: "",
            encoder: "",
            current_season: 1,
            current_episode: 1,
            include_words: "",
            exclude_words: "",
            active: true
        },
        showHelp: false,
        defaultArr: null,
        imdbidValid: false,
        dialogEditHeader: "Add new movie series monitoring",
        showArr: false,
        canAdd: false,
        seasonEpisode: "",
        seasonEpisodeValid: false,

        saveButtonText: "Add",
        addArr: true,
        validateImdbid() {
            const imdbidPattern = /^(tt\d{6,8})|(DEFAULT)$/;
            this.imdbidValid = imdbidPattern.test(this.arrObject.imdbid.trim());
            this.canAdd = this.imdbidValid && this.seasonEpisodeValid;
            console.log(this.canAdd);
            console.log(this.isLoading);
        },

        validateSeasonEpisode() {
            const seasonEpisodePattern = /^(S\d{1,2})\/(E\d{1,2})$/;
            this.seasonEpisodeValid = seasonEpisodePattern.test(this.seasonEpisode.trim());
            if (this.seasonEpisodeValid) {
                const matches = this.seasonEpisode.trim().match(seasonEpisodePattern);
                this.arrObject.requested_season = parseInt(matches[1].substring(1));
                this.arrObject.requested_episode = parseInt(matches[2].substring(1));
            }
            this.canAdd = this.imdbidValid && this.seasonEpisodeValid;
            console.log(this.canAdd);
            console.log(this.isLoading);
        },

        addNewArr() {
            this.isLoading = false;
            this.arrObject = { ...this.defaultArr };
            this.arrObject.id = null;
            this.arrObject.imdbid = "tt000000";
            this.arrObject.active = true;
            this.imdbidValid = false;
            this.dialogEditHeader = "Add new movie series monitoring";
            this.showArr = true;

            this.seasonEpisode = `S${this.arrObject.requested_season}/E${this.arrObject.requested_episode}`;
            this.seasonEpisodeValid = false;
            this.canAdd = false;
            this.saveButtonText = "Add";
            this.addArr = true;
            this.validateSeasonEpisode();
        },
        removeArr(item) {
            this.dialogConfirmBody = "Are you sure you want to delete Arr:<br/>'" + item.imdbid + "'?";
            this.dialogConfirmHeader = "Confirm delete";
            this.dialogConfirmCallback = () => {
                this.callApi(
                    "api/remove_arr/" + item.id,
                    (errorMessage = "Could not remove Arr"),
                    (successMessage = "Arr removed"),
                    "GET",
                    null,
                    (json) => {
                        this.reloadPagination();
                    },
                );
            };
            this.showModal = true;

        },
        changeActivityStatus(item) {
            this.callApi(
                "api/change_arr_activity/" + item.id,
                (errorMessage = "Could not change Arr"),
                (successMessage = "Arr status changed"),
                "GET",
                null,
                (json) => {
                    this.arrObject.active = !this.arrObject.active;
                    this.reloadPagination();
                },
            );
        },
        editArr(item) {
            this.isLoading = false;
            this.arrObject = { ...item };
            this.imdbidValid = true;
            this.dialogEditHeader = "Edit movie series monitoring";
            this.showArr = true;
            this.quality = item.quality;
            this.encoder = item.encoder;
            this.seasonEpisode = `S${item.requested_season}/E${item.requested_episode}`;
            this.seasonEpisodeValid = true;
            this.includeWords = item.include_words;
            this.excludeWords = item.exclude_words;
            this.canAdd = true;
            this.saveButtonText = "Save";
            this.addArr = false;
        },
        retryArr(item) {
            this.callApi(
                "api/retry_arr/" + item.id,
                (errorMessage = "Could not retry Arr"),
                (successMessage = "Arr scheduled to retry")
            );
        },
        save_arr() {
            if (!this.canAdd) {
                return;
            }
            if (this.arrObject.imdbid != "DEFAULT") {
                this.arrObject.active = true
            }
            this.callApi(
                "api/save_arr",
                (errorMessage = "Could not save Arr entry"),
                (successMessage = "Arr entry saved successfully"),
                (method = "POST"),
                (body = this.arrObject),
                (onSuccess = (json) => {
                    this.isLoading = false;
                    this.editArr(json);
                    this.reloadPagination();
                }),
                (onError = (json) => {
                    this.isLoading = false;
                    this.showAlert(json.error, false);
                })
            );
        },
        init() {
            this.paginatedPageApi = "/api/get_arr";
            this.paginationNewDataCallback = (json) => {
                this.arr = json.arr;
                this.defaultArr = json.defaultArr;
                this.pageCurrentItems = this.arr.length;
                this.updateTooltips();
            }
            this.reloadPagination();
            this.initBootstrapHints();

        },

        sseSource: null,
    };
}
