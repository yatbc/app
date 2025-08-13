function getDetails() {
    return {
        ...commonCallApi(),
        torrent: {},
        history: {},
        log: [],
        files: [],
        torrent_types: [],
        torrent_type: { name: "" },
        fetchTorrentTypes() {
            fetch(`/api/get_torrent_type_list`)
                .then((res) => res.json())
                .then((data) => {
                    this.torrent_types = data.torrent_types;
                    console.log("Torrent types fetched:", this.torrent_types);
                    this.fetchData();
                });
        },
        drawSeedersHistory(seedHistory) {
            seeds = seedHistory.seeds;
            peers = seedHistory.peers;
            const ctx = document.getElementById('torrentSeedersHistory').getContext('2d');

            new Chart(ctx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'Seeders History',
                        data: seeds,
                        backgroundColor: 'rgba(75, 192, 192, 0.6)',
                        borderColor: 'rgba(75, 192, 192, 1)',
                        borderWidth: 1,
                        pointRadius: 5
                    }, {
                        label: 'Peers History',
                        data: peers,
                        backgroundColor: 'rgba(153, 102, 255, 0.6)',
                        borderColor: 'rgba(153, 102, 255, 1)',
                        borderWidth: 1,
                        pointRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            type: 'time',
                            unit: 'second',
                            position: 'bottom',
                            title: {
                                display: true,
                                text: 'Date/Time'
                            },
                            tooltipFormat: 'yyyy-MM-dd HH:mm:ss', // Format for the tooltip
                            displayFormats: {
                                millisecond: 'HH:mm:ss.SSS',
                                second: 'HH:mm:ss',
                                minute: 'HH:mm',
                                hour: 'HH:mm'
                            },
                            grid: {
                                display: true // Show grid lines
                            }
                        },
                        y: {
                            type: 'linear',
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Seeders/Peers'
                            },
                            grid: {
                                display: true // Show grid lines
                            }
                        },
                    },
                    plugins: {
                        legend: {
                            display: true // Hide legend if not needed
                        }
                    }
                }
            });
        },
        drawSpeedHistory(speedHistory) {
            const ctx = document.getElementById('torrentSpeedHistory').getContext('2d');

            new Chart(ctx, {
                type: 'line',
                data: {
                    datasets: [{
                        label: 'Speed History',
                        data: speedHistory,
                        backgroundColor: 'rgba(75, 192, 192, 0.6)',
                        borderColor: 'rgba(75, 192, 192, 1)',
                        borderWidth: 1,
                        pointRadius: 5
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    scales: {
                        x: {
                            type: 'time',
                            unit: 'second',
                            position: 'bottom',
                            title: {
                                display: true,
                                text: 'Date/Time'
                            },
                            tooltipFormat: 'yyyy-MM-dd HH:mm:ss', // Format for the tooltip
                            displayFormats: {
                                millisecond: 'HH:mm:ss.SSS',
                                second: 'HH:mm:ss',
                                minute: 'HH:mm',
                                hour: 'HH:mm'
                            },
                            grid: {
                                display: true // Show grid lines
                            }
                        },
                        y: {
                            type: 'linear',
                            position: 'left',
                            title: {
                                display: true,
                                text: 'Speed (b/s)'
                            },
                            grid: {
                                display: true // Show grid lines
                            }
                        }
                    },
                    plugins: {
                        legend: {
                            display: false // Hide legend if not needed
                        }
                    }
                }
            });
        },

        fetchData() {
            this.callApi(
                '/api/get_torrent_details/' + globalTorrentId,
                errorMessage = "Could not fetch torrent details",
                successMessage = "",
                method = "GET",
                body = null,
                onSuccess = (data) => {
                    this.torrent = data.torrent;
                    this.history = data.history;
                    this.files = data.files;
                    console.log("Torrent details fetched:", this.torrent);
                    console.log("Torrent files fetched:", this.files);
                    this.torrent_type = this.torrent_types.find(item => item.id === this.torrent.torrent_type);

                },

            )
        },
        deleteLogs(command = "single") {
            this.isLoading = true;
            this.callApi(
                (api = "/api/delete_logs"),
                (errorMessage = "Failed to delete error log"),
                (successMessage = "Error log deleted successfully"),
                (method = "POST"),
                (body = { command: command, torrent_id: globalTorrentId }),
                (onSuccess = () => {
                    this.isLoading = false;
                    this.getTorrentLogs();
                }),
                (onError = () => {
                    this.isLoading = false;
                })
            );
        },
        getTorrentSpeedHistory() {
            this.callApi(
                '/api/get_torrent_speed_history/' + globalTorrentId,
                errorMessage = "Could not fetch torrent speed history",
                successMessage = "",
                method = "GET",
                body = null,
                onSuccess = (data) => {
                    console.log("Torrent speed history fetched:", data);
                    this.drawSpeedHistory(data);
                },
            )
        },
        getTorrentSeedersHistory() {
            this.callApi(
                '/api/get_torrent_seeders_history/' + globalTorrentId,
                errorMessage = "Could not fetch torrent seeders history",
                successMessage = "",
                method = "GET",
                body = null,
                onSuccess = (data) => {
                    console.log("Torrent seeders history fetched:", data);
                    this.drawSeedersHistory(data);
                },
            )
        },
        getTorrentLogs() {
            this.callApi(
                '/api/get_torrent_log/' + globalTorrentId,
                errorMessage = "Could not fetch torrent logs",
                successMessage = "",
                method = "GET",
                body = null,
                onSuccess = (data) => {
                    console.log("Torrent logs fetched:", data);
                    this.log = data;
                },
            )
        },

        init() {
            this.fetchTorrentTypes();
            this.getTorrentSpeedHistory();
            this.getTorrentSeedersHistory();

            this.getTorrentLogs();
        },
        sseSource: null,
    };
}
