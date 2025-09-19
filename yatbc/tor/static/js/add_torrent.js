function getAddTorrent() {
  return {
    torrent_types_add_torrent: [],
    selectedTypeId: null,
    magnetValid: false,
    magnetValue: "",
    canAdd: false,
    showAddTorrentModal: false,
    canCallAdd() {
      this.canAdd = this.magnetValid;
      return this.canAdd;
    },
    validateMagnet() {
      const text = String(this.magnetValue || '').trim();
      this.magnetValid = text.startsWith('magnet:?');
      this.canCallAdd();
      return this.magnetValid;
    },
    showAddTorrent() {
      console.log("Showing add torrent modal");
      this.showAddTorrentModal = true;
    },

    add_torrent(client, magnet, torrent_type_id) {
      console.log(`Adding torrent: ${magnet}, type id: ${torrent_type_id}, client: ${client}`);
      this.isLoading = true;
      const body = {
        "torrent_type_id": torrent_type_id,
        "magnet": magnet,
        "client": client,

      };
      this.callApi("api/add_torrent", "Failed to add torrent", "Torrent scheduled to add", "POST", body);
      this.magnetValue = "";
      this.validateMagnet();

    },
    initAddTorrent() {
      fetch(`api/get_torrent_type_list`)
        .then((res) => res.json())
        .then((data) => {
          this.torrent_types_add_torrent = data.torrent_types;
          const noTypeItem = this.torrent_types_add_torrent.find(item => item.name === 'No Type');
          if (noTypeItem) {
            this.selectedTypeId = noTypeItem.id;
          }

        });
    },

  };
}
