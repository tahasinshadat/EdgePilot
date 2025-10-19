const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('edgepilot', {
  backendUrl: process.env.BACKEND_URL || 'http://127.0.0.1:8000'
});
