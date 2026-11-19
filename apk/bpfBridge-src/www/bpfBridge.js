'use strict';
var exec = require('cordova/exec');

/** Bridge native BPF Agenda: notifikasi lokal + widget home screen. */
var BpfBridge = {
  notify: function (title, message, success, failure) {
    exec(success, failure, 'bpfBridge', 'notify',
      [String(title || 'BPF Agenda'), String(message || 'Ada agenda baru dari admin.')]);
  },
  askNotifyPermission: function (success, failure) {
    exec(success, failure, 'bpfBridge', 'notify-permission', []);
  },
  addWidget: function (success, failure) {
    exec(success, failure, 'bpfBridge', 'addWidget', []);
  },
  refreshWidget: function (success, failure) {
    exec(success, failure, 'bpfBridge', 'refreshWidget', []);
  },
  // teks agenda hari ini untuk widget home screen
  setWidgetAgenda: function (date, text, success, failure) {
    exec(success, failure, 'bpfBridge', 'widgetAgenda',
      [String(date || ''), String(text || '')]);
  },
  // unduh media ke folder Download (DownloadManager)
  download: function (url, name, success, failure) {
    exec(success, failure, 'bpfBridge', 'download', [String(url), String(name || '')]);
  },
  // bagikan media lewat share sheet (file diunduh ke cache dulu)
  share: function (url, name, mime, success, failure) {
    exec(success, failure, 'bpfBridge', 'share',
      [String(url), String(name || ''), String(mime || '')]);
  }
};

module.exports = BpfBridge;
