window.app = Vue.createApp({
  el: '#vue',
  mixins: [windowMixin],
  data() {
    return {
      protocol: window.location.protocol,
      location: window.location.hostname,
      wslocation: window.location.hostname,
      filter: '',
      currency: 'USD',
      lnurlValue: '',
      websocketMessage: '',
      devices: [],
      deviceTable: {
        columns: [
          {
            name: 'websocket',
            align: 'left',
            label: 'Status',
            field: 'websocket'
          },
          {
            name: 'title',
            align: 'left',
            label: 'title',
            field: 'title'
          },
          {
            name: 'theId',
            align: 'left',
            label: 'id',
            field: 'id'
          },
          {
            name: 'wallet',
            align: 'left',
            label: 'wallet',
            field: 'wallet'
          },
          {
            name: 'currency',
            align: 'left',
            label: 'currency',
            field: 'currency'
          }
        ],
        pagination: {
          rowsPerPage: 10
        }
      },
      settingsDialog: {
        show: false,
        data: {}
      },
      formDialog: {
        show: false,
        data: {
          switches: [],
          title: '',
          branding: 'BITCOINTAPS',
          currency: 'sat',
          wallet: ''
        }
      },
      qrCodeDialog: {
        show: false,
        data: null
      }
    }
  },
  computed: {
    wsMessage() {
      return this.websocketMessage
    }
  },
  methods: {
    openQrCodeDialog(deviceId) {
      const device = _.findWhere(this.devices, {
        id: deviceId
      })
      this.qrCodeDialog.data = _.clone(device)
      this.qrCodeDialog.data.url =
        window.location.protocol + '//' + window.location.host
      this.lnurlValue = this.qrCodeDialog.data.switches[0].lnurl
      this.websocketConnector(
        'wss://' + window.location.host + '/api/v1/ws/' + deviceId
      )
      this.qrCodeDialog.show = true
    },
    addSwitch() {
      this.formDialog.data.switches.push({
        amount: 10,
        duration: 1000,
      })
    },
    removeSwitch() {
      this.formDialog.data.switches.pop()
    },
    cancelFormDialog() {
      this.formDialog.show = false
      this.clearFormDialog()
    },
    closeFormDialog() {
      this.clearFormDialog()
      this.formDialog.data = {
        is_unique: false
      }
    },
    sendFormData() {
      if (this.formDialog.data.id) {
        this.updateDevice(
          this.g.user.wallets[0].adminkey,
          this.formDialog.data
        )
      } else {
        this.createDevice(
          this.g.user.wallets[0].adminkey,
          this.formDialog.data
        )
      }
    },

    createDevice(wallet, data) {
      const updatedData = {}
      for (const property in data) {
        if (data[property]) {
          updatedData[property] = data[property]
        }
      }
      LNbits.api
        .request(
          'POST',
          '/partytap/api/v1/partytap',
          wallet,
          updatedData
        )
        .then(response => {
          this.devices.push(response.data)
          this.formDialog.show = false
          this.clearFormDialog()
        })
        .catch(function (error) {
          LNbits.utils.notifyApiError(error)
        })
    },
    updateDevice(wallet, data) {
      const updatedData = {}
      for (const property in data) {
        if (data[property]) {
          updatedData[property] = data[property]
        }
      }
      LNbits.api
        .request(
          'PUT',
          '/partytap/api/v1/partytap/' + updatedData.id,
          wallet,
          updatedData
        )
        .then(response => {
          this.devices = _.reject(this.devices, function (obj) {
            return obj.id === updatedData.id
          })
          this.devices.push(response.data)
          this.formDialog.show = false
          this.clearFormDialog()
        })
        .catch(function (error) {
          LNbits.utils.notifyApiError(error)
        })
    },
    getDevices() {
      LNbits.api
        .request(
          'GET',
          '/partytap/api/v1/partytap',
          this.g.user.wallets[0].adminkey
        )
        .then(response => {
          if (response.data.length > 0) {
            this.devices = response.data
          }
        })
        .catch(function (error) {
          LNbits.utils.notifyApiError(error)
        })
    },
    deleteDevice(deviceId) {
      LNbits.utils
        .confirmDialog('Are you sure you want to delete this pay link?')
        .onOk(() => {
          LNbits.api
            .request(
              'DELETE',
              '/partytap/api/v1/partytap/' + deviceId,
              this.g.user.wallets[0].adminkey
            )
            .then(() => {
              this.devices = _.reject(
                this.devices,
                function (obj) {
                  return obj.id === deviceId
                }
              )
            })
            .catch(function (error) {
              LNbits.utils.notifyApiError(error)
            })
        })
    },
    openUpdateDevice(deviceId) {
      const device = _.findWhere(this.devices, {
        id: deviceId
      })
      this.formDialog.data = _.clone(device)
      this.formDialog.show = true
    },
    openDeviceSettings(deviceId) {
      const device = _.findWhere(this.devices, {
        id: deviceId
      })
      this.wslocation =
        'wss://' + window.location.host + '/api/v1/ws/' + deviceId
      this.settingsDialog.data = _.clone(device)
      this.settingsDialog.show = true
    },
    websocketConnector(websocketUrl) {
      if ('WebSocket' in window) {
        const ws = new WebSocket(websocketUrl)
        this.updateWsMessage('Websocket connected')
        ws.onmessage = evt => {
          this.updateWsMessage('Message received: ' + evt.data)
        }
        ws.onclose = () => {
          this.updateWsMessage('Connection closed')
        }
      } else {
        this.updateWsMessage('WebSocket NOT supported by your Browser!')
      }
    },
    updateWsMessage(message) {
      this.websocketMessage = message
    },
    clearFormDialog() {
      this.formDialog.data = {
        lnurl_toggle: false,
        show_message: false,
        show_ack: false,
        show_price: 'None',
        title: ''
      }
    },
    exportCSV() {
      LNbits.utils.exportCSV(
        this.deviceTable.columns,
        this.devices
      )
    }
  },
  created() {
    this.getDevices()
    this.location = [window.location.protocol, '//', window.location.host].join(
      ''
    )
    this.wslocation = ['wss://', window.location.host].join('')
    LNbits.api
      .request('GET', '/api/v1/currencies')
      .then(response => {
        this.currency = ['sat', 'USD', ...response.data]
      })
      .catch(LNbits.utils.notifyApiError)
  }
})
