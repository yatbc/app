function getData() {
    return {
        ...commonPagination(),

        search: [],
        torrent_types: [],
        searchTitle: Alpine.$persist("").as('searchTitle'), // this will be JackettSearch.query
        selectedTitle: Alpine.$persist("").as('selectedTitle'),
        selectedExtra: Alpine.$persist("").as('selectedExtra'),
        selectedTorrentTypeIdSearch: Alpine.$persist(0).as('selectedTorrentTypeIdSearch'),
        performSearch() {
            let query = this.selectedTorrentTypeIdSearch
            if (this.searchTitle.trim() != "") {
                query += `/${this.searchTitle.trim()}`;
            }
            this.callApi(
                "api/start_advanced_search/" + query,
                (errorMessage = "Could not start search"),
                (successMessage = "Search in progress..."),
                "GET",
                null,
                (json) => {
                    this.reloadPagination();
                },
            );
        },
        fetchData() {
            this.updateFilters();
            this.reloadPagination();
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
        filterByQuery(query) {
            this.searchTitle = query.trim();
            this.fetchData();
        },
        filterByTitle(title) {
            this.selectedTitle = title.trim();
            this.fetchData();
        },
        filterByExtra(extra) {
            this.selectedExtra = extra.trim();
            this.fetchData();
        },
        downloadFile(id) {
            this.callApi(
                "api/download_file_from_advanced_search/" + id,
                (errorMessage = "Could not download file"),
                (successMessage = "Scheduled to download"),
            );
        },
        updateFilters() {
            title = this.selectedTitle;
            if (title == "") {
                title = "None";
            }
            query = this.searchTitle.trim();
            if (query == "") {
                query = "None";
            }
            extra = this.selectedExtra;
            if (extra == "") {
                extra = "None";
            }
            console.log("Updating filters:");
            console.log(`Title: ${title}, Extra: ${this.selectedExtra}, Type ID: ${this.selectedTorrentTypeIdSearch}`);
            this.extraFilter = `/${this.selectedTorrentTypeIdSearch}/${query}/${title}/${extra}`;

        },
        filterByTorrentType(torrentTypeId) {
            this.selectedTorrentTypeIdSearch = torrentTypeId;
            this.updateFilters();
        },
        updateSearchResults() {
            this.fetchData();
        },
        init() {
            this.step = 5 // images are big, and description also takes a lot of space, so change default to lower value so it would fit better
            this.updateFilters();
            this.isLoading = true;
            this.initBootstrapHints();
            this.setupSSE(
                (update_action = () => {
                    this.lastRequestId = null;
                    this.fetchData();
                })
            );
            this.paginatedPageApi = "/api/get_advanced_search_results";
            this.paginationNewDataCallback = (data) => {
                this.search = data.results;
                this.pageCurrentItems = this.search.length;
                console.log("Updated search results:");
                console.log(this.search);
                console.log(this.pageCurrentItems);
                this.updateTooltips();
            }
            this.fetchTorrentTypes();
            this.updateSearchResults();
            setInterval(() => {
                this.updateSearchResults();
            }, 60000);
        },


        sseSource: null,
    };
}
