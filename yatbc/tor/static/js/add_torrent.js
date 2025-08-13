function get_add_torrent() {
  return {
    ...commonCallApi(),
    torrent_types: [],
    selectedTypeId: null,
    magnetValid: false,
    magnetValue: "",
    canAdd: false,
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

    add_torrent(client, magnet, torrent_type_id) {
      this.isLoading = true;
      const body = {
        "torrent_type_id": torrent_type_id,
        "magnet": magnet,
        "client": client,

      };
      this.callApi("api/add_torrent", "Failed to add torrent", "Torrent sheduled to add", "POST", body);
    },
    init() {
      this.setupSSE(update_action = () => {
        this.isLoading = false;
        this.showAlert("Torrent added");
      });
      fetch(`api/get_torrent_type_list`)
        .then((res) => res.json())
        .then((data) => {
          this.torrent_types = data.torrent_types;
          const noTypeItem = this.torrent_types.find(item => item.name === 'No Type');
          if (noTypeItem) {
            this.selectedTypeId = noTypeItem.id;
          }
          console.log(this.torrent_types);
        });
    },


    sseSource: null,
  };
}
