// Serve pinned OCR resources ourselves: documents never leave for an OCR service.
import { mkdir, copyFile, readdir } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
const root = fileURLToPath(new URL('../', import.meta.url));
const destination = path.join(root, 'public/ocr');
await mkdir(destination, { recursive: true });
await copyFile(path.join(root, 'node_modules/tesseract.js/dist/worker.min.js'), path.join(destination, 'worker.min.js'));
const core = path.join(root, 'node_modules/tesseract.js-core');
for (const name of (await readdir(core)).filter(name => /\.(js|wasm)$/.test(name))) {
  await copyFile(path.join(core, name), path.join(destination, name));
}
for (const language of ['fra', 'eng']) {
  await copyFile(path.join(root, `node_modules/@tesseract.js-data/${language}/4.0.0/${language}.traineddata.gz`), path.join(destination, `${language}.traineddata.gz`));
}
