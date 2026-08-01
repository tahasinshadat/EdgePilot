const { downloadArtifact } = require('@electron/get');
const extract = require('extract-zip');
const fs = require('fs');
const path = require('path');
const version = '30.5.1';

downloadArtifact({
  version,
  artifactName: 'electron',
  platform: 'darwin',
  arch: 'arm64'
}).then(zipPath => {
  console.log("Downloaded to", zipPath);
  return extract(zipPath, { dir: path.join(__dirname, 'node_modules/electron/dist') });
}).then(() => {
  console.log("Extracted!");
  fs.writeFileSync(path.join(__dirname, 'node_modules/electron/path.txt'), 'Electron.app/Contents/MacOS/Electron');
  console.log("Wrote path.txt");
}).catch(console.error);
