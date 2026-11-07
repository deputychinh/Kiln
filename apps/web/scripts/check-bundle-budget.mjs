// Bundle budget (KILN-9), run after every `vite build`: the JS the first page loads must stay
// small, and three.js must arrive only with the 3D viewer. Sizes are gzip bytes.
import { readdirSync, readFileSync } from 'node:fs';
import { gzipSync } from 'node:zlib';

const DIST = new URL('../dist/', import.meta.url);
const BUDGET = {
  // Everything index.html loads (entry + its static imports): 116.2 kB at KILN-9.
  initial: 120_000,
  // The viewer route's own chunk (page, file download, checks): 3.9 kB at KILN-9.
  viewerRoute: 8_000,
  // The lazily loaded scene with three.js and react-three-fiber: 257.4 kB at KILN-9.
  scene: 280_000,
};
// three.js logs with this prefix; finding it in a chunk means three.js is in that chunk.
const THREE_MARKER = 'THREE.';

const html = readFileSync(new URL('index.html', DIST), 'utf8');
const initialFiles = [...html.matchAll(/(?:src|href)="\/(assets\/[^"]+\.js)"/g)].map((m) => m[1]);
const read = (file) => readFileSync(new URL(file, DIST));
const gzipOf = (file) => gzipSync(read(file)).length;
const assets = readdirSync(new URL('assets/', DIST)).map((name) => `assets/${name}`);
const only = (pattern) => {
  const found = assets.filter((file) => pattern.test(file));
  if (found.length !== 1)
    throw new Error(`expected one chunk for ${pattern}, found ${found.length}`);
  return found[0];
};

const measured = {
  initial: initialFiles.reduce((sum, file) => sum + gzipOf(file), 0),
  viewerRoute: gzipOf(only(/^assets\/assets_\._assetId\.view-[\w-]+\.js$/)),
  scene: gzipOf(only(/^assets\/ModelScene-[\w-]+\.js$/)),
};
const problems = Object.entries(BUDGET)
  .filter(([name, limit]) => measured[name] > limit)
  .map(([name, limit]) => `${name}: ${measured[name]} B gzip > budget ${limit} B`);
const leaked = initialFiles.filter((file) => read(file).includes(THREE_MARKER));
if (leaked.length > 0) problems.push(`three.js is in the first load: ${leaked.join(', ')}`);

for (const [name, size] of Object.entries(measured)) {
  console.log(
    `bundle ${name}: ${(size / 1000).toFixed(1)} kB gzip (budget ${BUDGET[name] / 1000} kB)`,
  );
}
if (problems.length > 0) {
  console.error(`Bundle budget exceeded:\n- ${problems.join('\n- ')}`);
  process.exit(1);
}
