const { execFileSync } = require('node:child_process');
const path = require('node:path');

// macOS Finder can abort a copy from a DMG with "Error code -36" when the
// bundle carries stale extended attributes or AppleDouble (._) metadata.
// Strip both from the packaged .app before electron-builder creates the image.
function run(command, args) {
  try {
    execFileSync(command, args, { stdio: 'ignore' });
  } catch (error) {
    console.warn(`[after-pack-mac] ${command} skipped: ${error.message}`);
  }
}

module.exports = async function afterPack(context) {
  if (context.electronPlatformName !== 'darwin') return;

  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  console.log(`[after-pack-mac] Cleaning metadata in ${appPath}`);

  run('xattr', ['-cr', appPath]);
  run('find', [appPath, '-name', '._*', '-type', 'f', '-delete']);
  run('find', [appPath, '-name', '.DS_Store', '-type', 'f', '-delete']);
  run('dot_clean', [appPath]);
};
