function get_config() {
  return {
    ...commonCallApi(),
    configuration: {},
    aria_password_value: "",
    transmission_password_value: "",
    torbox_api_key_value: "",
    torrent_types: {},
    torbox_api_valid: null,
    torbox_host_valid: null,
    aria2_dir_valid: null,
    aria2_host_valid: null,
    aria2_port_valid: null,
    aria2_user_valid: null,
    aria2_password_valid: null,
    transmission_dir_valid: null,
    transmission_host_valid: null,
    transmission_port_valid: null,
    transmission_user_valid: null,
    transmission_password_valid: null,
    queue_root_folder_valid: null,
    folders_valid: {},
    test_ip: "",
    test_isp: "",
    get_config() {
      this.isLoading = true;
      this.callApi(
        "get_config",
        (errorMessage = "Could not get configuration"),
        (successMessage = null),
        (method = "POST"),
        (body = {}),
        (onSuccess = (data) => {
          this.isLoading = false;
          for (const key in data.torrent_types) {
            this.folders_valid[data.torrent_types[key].id] = null;
          }
          this.configuration = data.configuration;
          this.torrent_types = data.torrent_types;
          this.folders_valid = [];
          if (globalFirstRun && !this.configuration.TORBOX_API_KEY_SET) {
            this.torbox_api_valid = false;
          }

          console.log(this.configuration);
          console.log(this.torrent_types);
        })
      );

    },
    init() {
      this.initBootstrapHints();
      this.get_config();
    },
    buildConfig() {
      value = {
        ...this.configuration,
        TORRENT_TYPES: {
          ...this.torrent_types,
        },
      };
      if (this.torbox_api_key_value) {
        value.TORBOX_API_KEY = this.torbox_api_key_value;
      }
      if (this.aria_password_value) {
        value.ARIA2_PASSWORD = this.aria_password_value;
      }
      if (this.transmission_password_value) {
        value.TRANSMISSION_PASSWORD = this.transmission_password_value;
      }
      return value;
    },
    saveConfig() {
      this.isLoading = true;
      const configData = this.buildConfig();
      this.callApi(
        "api/save_config",
        (errorMessage = "Could not save configuration"),
        (successMessage = "Configuration saved"),
        (method = "POST"),
        (body = configData),
        (onSuccess = () => {
          window.location.reload(true);
        })
      );
    },
    validateQueueFolders() {
      this.isLoading = true;
      const configData = this.buildConfig();
      this.callApi(
        "api/validate_queue_folders",
        (errorMessage = "Could not validate Queue folders"),
        (successMessage = "Queue folders validated successfully"),
        (method = "POST"),
        (body = configData),
        (onSuccess = (json) => {
          this.isLoading = false;
          this.queue_root_folder_valid = true;
        }),
        (onError = (json) => {
          this.isLoading = false;
          this.showAlert(json.error, false);
          this.queue_root_folder_valid = false;
        })
      );
    },
    validateTorBox() {
      this.isLoading = true;
      const configData = this.buildConfig();
      this.callApi(
        "api/validate_torbox",
        (errorMessage = "Could not validate TorBox"),
        (successMessage = "TorBox validated successfully"),
        (method = "POST"),
        (body = configData),
        (onSuccess = (json) => {
          this.isLoading = false;
          this.torbox_api_valid = true;
          this.torbox_host_valid = true;
        }),
        (onError = (json) => {
          this.isLoading = false;
          this.showAlert(json.error, false);
          WRONG_KEY = 2;
          if (json["reason"] == WRONG_KEY) {
            this.torbox_api_valid = false;
            this.torbox_host_valid = true;
          } else {
            this.torbox_api_valid = false;
            this.torbox_host_valid = false;
          }
        })
      );
    },
    addReferral() {
      this.isLoading = true;
      this.isLoading = true;
      this.callApi(
        "api/add_referral",
        (errorMessage = "Could not add referral"),
        (successMessage = "Referral added successfully. Thank you!"),
        (method = "GET"),
        (body = null),
      );
    },
    validateAria() {
      this.isLoading = true;
      const configData = this.buildConfig();
      this.callApi(
        "api/validate_aria",
        (errorMessage = "Could not validate Aria"),
        (successMessage = "Aria validated successfully"),
        (method = "POST"),
        (body = configData),
        (onSuccess = (json) => {
          console.log("Aria validation success:", json);
          this.isLoading = false;
          this.aria2_dir_valid = true;
          this.aria2_host_valid = true;
          this.aria2_port_valid = true;
          this.aria2_user_valid = true;
          this.aria2_password_valid = true;
        }),
        (onError = (json) => {
          this.isLoading = false;
          this.showAlert(json.error, false);
          WRONG_ARIA_DIR = 1;
          console.log("Aria validation failed:", json);
          if (json["reason"] == WRONG_ARIA_DIR) {
            this.aria2_dir_valid = false;
            this.aria2_host_valid = null;
            this.aria2_port_valid = null;
            this.aria2_user_valid = null;
            this.aria2_password_valid = null;
          } else {
            this.aria2_dir_valid = true;
            this.aria2_host_valid = false;
            this.aria2_port_valid = false;
            this.aria2_user_valid = false;
            this.aria2_password_valid = false;
          }
        })
      );
    },
    testIp() {
      this.isLoading = true;
      this.callApi(
        "api/test_ip",
        (errorMessage = "Could not test IP"),
        (successMessage = "IP tested successfully"),
        (method = "GET"),
        null,
        (onSuccess = (json) => {
          this.isLoading = false;
          this.test_ip = json.ip;
          this.test_isp = json.isp;
          if (json.org !== "") this.test_isp += " (" + json.org + ")";
          console.log("IP test success:", json);
        }),
        (onError = (json) => {
          this.isLoading = false;
          this.showAlert(json["error"], false);
          console.log("IP test failed:", json);
        })
      );
    },
    validateTransmission() {
      this.isLoading = true;
      const configData = this.buildConfig();
      this.callApi(
        "api/validate_transmission",
        (errorMessage = "Could not validate Transmission"),
        (successMessage = "Transmission validated successfully"),
        (method = "POST"),
        (body = configData),
        (onSuccess = (json) => {
          console.log("Transmission validation success:", json);
          this.isLoading = false;
          this.transmission_dir_valid = true;
          this.transmission_host_valid = true;
          this.transmission_port_valid = true;
          this.transmission_user_valid = true;
          this.transmission_password_valid = true;
        }),
        (onError = (json) => {
          this.isLoading = false;
          this.showAlert(json.error, false);
          WRONG_TRANSMISSION_DIR = 1;
          console.log("Transmission validation failed:", json);
          if (json["reason"] == WRONG_TRANSMISSION_DIR) {
            this.transmission_dir_valid = false;
            this.transmission_host_valid = null;
            this.transmission_port_valid = null;
            this.transmission_user_valid = null;
            this.transmission_password_valid = null;
          } else {
            this.transmission_dir_valid = true;
            this.transmission_host_valid = false;
            this.transmission_port_valid = false;
            this.transmission_user_valid = false;
            this.transmission_password_valid = false;
          }
        })
      );
    },
    validateFolders() {
      this.isLoading = true;
      const configData = this.buildConfig();
      this.callApi(
        "api/validate_folders",
        (errorMessage = "Could not validate folders"),
        (successMessage = "Folders validated successfully"),
        (method = "POST"),
        (body = configData),
        (onSuccess = (json) => {
          this.isLoading = false;
          console.log("Folders validation succeeded:", json);

          this.folders_valid = json.folders_valid;
        }),
        (onError = (json) => {
          this.isLoading = false;
          this.showAlert(json.error, false);
          console.log("Folders validation failed:", json);
          this.folders_valid = json.folders_valid;
          console.log("Folders validation error:", this.folders_valid);
        })
      );
    },

    sseSource: null,
  };
}
