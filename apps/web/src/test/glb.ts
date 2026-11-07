const MAGIC = 0x46546c67; // "glTF"
const JSON_CHUNK = 0x4e4f534a;
const BIN_CHUNK = 0x004e4942;

const padded = (bytes: Uint8Array, fill: number): Uint8Array => {
  const length = Math.ceil(bytes.length / 4) * 4;
  const out = new Uint8Array(length).fill(fill);
  out.set(bytes);
  return out;
};

/** A cube: 8 corners, 12 triangles; the same shape as `e2e/fixtures/crate.glb`. */
export const cubeJson = {
  asset: { version: '2.0' },
  buffers: [{ byteLength: 240 }],
  bufferViews: [
    { buffer: 0, byteOffset: 0, byteLength: 96 },
    { buffer: 0, byteOffset: 96, byteLength: 144 },
  ],
  accessors: [
    {
      bufferView: 0,
      componentType: 5126,
      count: 8,
      type: 'VEC3',
      min: [-1, -1, -1],
      max: [1, 1, 1],
    },
    { bufferView: 1, componentType: 5125, count: 36, type: 'SCALAR' },
  ],
  meshes: [{ primitives: [{ attributes: { POSITION: 0 }, indices: 1 }] }],
  nodes: [{ mesh: 0 }],
  scenes: [{ nodes: [0] }],
  scene: 0,
};

const CUBE_FACES = [
  [0, 1, 2, 0, 2, 3],
  [4, 6, 5, 4, 7, 6],
  [0, 4, 5, 0, 5, 1],
  [1, 5, 6, 1, 6, 2],
  [2, 6, 7, 2, 7, 3],
  [3, 7, 4, 3, 4, 0],
].flat();

export const cubeBin = (): Uint8Array => {
  const positions = new Float32Array(
    [
      [-1, -1, -1],
      [1, -1, -1],
      [1, 1, -1],
      [-1, 1, -1],
      [-1, -1, 1],
      [1, -1, 1],
      [1, 1, 1],
      [-1, 1, 1],
    ].flat(),
  );
  const out = new Uint8Array(240);
  out.set(new Uint8Array(positions.buffer), 0);
  out.set(new Uint8Array(new Uint32Array(CUBE_FACES).buffer), 96);
  return out;
};

/** A GLB file (glTF 2.0 §4.4) from a JSON object and an optional BIN chunk. */
export const buildGlb = (
  json: unknown,
  bin: Uint8Array | null = cubeBin(),
  { version = 2 }: { version?: number } = {},
): ArrayBuffer => {
  const jsonBytes = padded(new TextEncoder().encode(JSON.stringify(json)), 0x20);
  const binBytes = bin ? padded(bin, 0) : null;
  const length = 12 + 8 + jsonBytes.length + (binBytes ? 8 + binBytes.length : 0);
  const buffer = new ArrayBuffer(length);
  const view = new DataView(buffer);
  view.setUint32(0, MAGIC, true);
  view.setUint32(4, version, true);
  view.setUint32(8, length, true);
  view.setUint32(12, jsonBytes.length, true);
  view.setUint32(16, JSON_CHUNK, true);
  new Uint8Array(buffer, 20, jsonBytes.length).set(jsonBytes);
  if (binBytes) {
    const at = 20 + jsonBytes.length;
    view.setUint32(at, binBytes.length, true);
    view.setUint32(at + 4, BIN_CHUNK, true);
    new Uint8Array(buffer, at + 8, binBytes.length).set(binBytes);
  }
  return buffer;
};

export const cubeGlb = (): ArrayBuffer => buildGlb(cubeJson);
