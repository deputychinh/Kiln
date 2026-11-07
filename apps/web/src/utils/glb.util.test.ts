import { readFileSync } from 'node:fs';

import {
  GLB_MAX_JSON_BYTES,
  MODEL_MAX_ACCESSOR_ELEMENTS,
  MODEL_MAX_TRIANGLES,
  MODEL_MAX_VERTICES,
} from '@/constants/viewer.constant';
import { ViewerError } from '@/enums/viewer-error.enum';
import { buildGlb, cubeJson, cubeGlb } from '@/test/glb';
import { inspectGlb, isEmbeddedUrl } from '@/utils/glb.util';

const withJson = (extra: Record<string, unknown>): ArrayBuffer =>
  buildGlb({ ...cubeJson, ...extra });

describe('inspectGlb', () => {
  it('accepts a self-contained glTF 2.0 binary', () => {
    expect(inspectGlb(cubeGlb())).toBeNull();
  });

  it('accepts a JSON-only file and an image embedded as a data URI', () => {
    expect(inspectGlb(buildGlb({ asset: { version: '2.0' } }, null))).toBeNull();
    expect(
      inspectGlb(withJson({ images: [{ uri: 'data:image/png;base64,iVBORw0K' }] })),
    ).toBeNull();
    expect(inspectGlb(withJson({ images: [{ bufferView: 0, mimeType: 'image/png' }] }))).toBeNull();
  });

  it.each([
    ['too short for a header', new ArrayBuffer(19)],
    ['another magic', new TextEncoder().encode('PK\x03\x04'.padEnd(24, '\0')).buffer],
    ['glTF 1', buildGlb(cubeJson, null, { version: 1 })],
    ['a truncated file', cubeGlb().slice(0, 100)],
    ['invalid JSON', buildGlb('{"asset":', null)],
    ['JSON that is not an object', buildGlb([1, 2], null)],
    ['buffers that are not a list', withJson({ buffers: { uri: 'x' } })],
  ])('refuses %s as unreadable', (_case, buffer) => {
    expect(inspectGlb(buffer)).toBe(ViewerError.Unreadable);
  });

  it('refuses a header whose length disagrees with the file', () => {
    const buffer = cubeGlb();
    new DataView(buffer).setUint32(8, buffer.byteLength + 4, true);
    expect(inspectGlb(buffer)).toBe(ViewerError.Unreadable);
  });

  it('refuses a file whose first chunk is not JSON', () => {
    const buffer = cubeGlb();
    new DataView(buffer).setUint32(16, 0x004e4942, true);
    expect(inspectGlb(buffer)).toBe(ViewerError.Unreadable);
  });

  it('refuses a JSON chunk longer than the file', () => {
    const buffer = buildGlb(cubeJson, null);
    new DataView(buffer).setUint32(12, buffer.byteLength, true);
    expect(inspectGlb(buffer)).toBe(ViewerError.Unreadable);
  });

  it('refuses a JSON chunk above the worker limit as too complex, before reading it', () => {
    const buffer = buildGlb(cubeJson, null);
    new DataView(buffer).setUint32(12, GLB_MAX_JSON_BYTES + 4, true);
    expect(inspectGlb(buffer)).toBe(ViewerError.TooComplex);
  });

  it.each([
    ['a buffer with a URI', { buffers: [{ byteLength: 240, uri: 'cube.bin' }] }],
    ['a buffer with a data URI', { buffers: [{ byteLength: 4, uri: 'data:,abcd' }] }],
    ['an image on another site', { images: [{ uri: 'https://evil.test/a.png' }] }],
    ['an image next to the file', { images: [{ uri: 'textures/a.png' }] }],
    ['an image on this host by protocol-relative URL', { images: [{ uri: '//evil.test/a.png' }] }],
    ['an image with a URI that is not text', { images: [{ uri: 42 }] }],
  ])('refuses %s: nothing outside the file is fetched', (_case, extra) => {
    expect(inspectGlb(withJson(extra))).toBe(ViewerError.ExternalReference);
  });

  it.each([
    'KHR_draco_mesh_compression',
    'EXT_meshopt_compression',
    'KHR_texture_basisu',
    'VENDOR_unknown',
  ])('refuses the required extension %s as unsupported', (name) => {
    expect(inspectGlb(withJson({ extensionsRequired: [name] }))).toBe(ViewerError.Unsupported);
  });

  it('accepts required extensions three reads without a decoder', () => {
    const extensionsRequired = [
      'KHR_materials_unlit',
      'KHR_materials_transmission',
      'KHR_texture_transform',
      'KHR_mesh_quantization',
      'KHR_lights_punctual',
      'EXT_texture_webp',
      'EXT_texture_avif',
    ];
    expect(inspectGlb(withJson({ extensionsRequired }))).toBeNull();
  });

  it('only checks extensions that are required, not merely used', () => {
    expect(inspectGlb(withJson({ extensionsUsed: ['KHR_draco_mesh_compression'] }))).toBeNull();
  });
});

describe('isEmbeddedUrl', () => {
  it.each(['blob:http://127.0.0.1:4173/0d1f', 'data:image/png;base64,AAAA', 'DATA:,x'])(
    'lets %s through: it is inside the file',
    (url) => {
      expect(isEmbeddedUrl(url)).toBe(true);
    },
  );

  it.each([
    'https://evil.test/a.png',
    'http://127.0.0.1:8333/kiln-assets/x',
    '//evil.test/a.png',
    'textures/a.png',
    '',
    'javascript:alert(1)',
    ' data:,x',
  ])('blocks %s', (url) => {
    expect(isEmbeddedUrl(url)).toBe(false);
  });
});

// KILN-9 review: three.js allocates every accessor a file names, whatever the scene draws.
describe('inspectGlb and accessors', () => {
  /** The review's 768-byte proof of concept: COLOR_0 of 200,000,000 VEC4 with no bufferView. */
  const colourBomb = (): ArrayBuffer => {
    // Vitest runs from apps/web (under jsdom `import.meta.url` is not a file URL).
    const crate = readFileSync(`${process.cwd()}/e2e/fixtures/crate.glb`);
    const length = crate.readUInt32LE(12);
    const json = JSON.parse(crate.subarray(20, 20 + length).toString()) as typeof cubeJson & {
      meshes: { primitives: { attributes: Record<string, number> }[] }[];
    };
    json.accessors.push({ componentType: 5126, count: 200_000_000, type: 'VEC4' } as never);
    const [primitive] = json.meshes[0]?.primitives ?? [];
    if (primitive) primitive.attributes.COLOR_0 = 2;
    return buildGlb(json, new Uint8Array(crate.subarray(20 + length + 8)));
  };

  const withAccessor = (accessor: object): ArrayBuffer =>
    withJson({ accessors: [...cubeJson.accessors, accessor] });

  it('refuses the 768-byte colour accessor bomb before three.js sees it', () => {
    const bomb = colourBomb();
    expect(bomb.byteLength).toBe(768);
    expect(inspectGlb(bomb)).toBe(ViewerError.Unreadable);
  });

  it.each([
    ['without a bufferView', { componentType: 5126, count: 8, type: 'VEC3' }],
    ['one element past its view', { bufferView: 0, componentType: 5126, count: 9, type: 'VEC3' }],
    [
      'pushed past its view by its offset',
      { bufferView: 0, byteOffset: 4, componentType: 5126, count: 8, type: 'VEC3' },
    ],
    [
      'a matrix larger than its view',
      { bufferView: 0, componentType: 5126, count: 2, type: 'MAT4' },
    ],
    [
      'sparse',
      { bufferView: 0, componentType: 5126, count: 2, type: 'VEC3', sparse: { count: 1 } },
    ],
    ['misaligned', { bufferView: 0, byteOffset: 2, componentType: 5126, count: 1, type: 'SCALAR' }],
    [
      'of an unknown component type',
      { bufferView: 0, componentType: 5124, count: 1, type: 'SCALAR' },
    ],
    ['of an unknown type', { bufferView: 0, componentType: 5126, count: 1, type: 'VEC5' }],
    [
      'with a count that is not a whole number',
      { bufferView: 0, componentType: 5126, count: 1.5, type: 'SCALAR' },
    ],
    [
      'in a view that is not there',
      { bufferView: 7, componentType: 5126, count: 1, type: 'SCALAR' },
    ],
  ])('refuses an accessor %s, even one nothing draws', (_case, accessor) => {
    expect(inspectGlb(withAccessor(accessor))).toBe(ViewerError.Unreadable);
  });

  it('accepts an accessor inside its view that nothing draws', () => {
    expect(
      inspectGlb(withAccessor({ bufferView: 0, componentType: 5126, count: 24, type: 'SCALAR' })),
    ).toBeNull();
  });

  it('bounds an accessor by the stride of its view', () => {
    const views = [{ ...cubeJson.bufferViews[0], byteStride: 24 }, cubeJson.bufferViews[1]];
    const accessors = [
      ...cubeJson.accessors,
      { bufferView: 0, componentType: 5126, count: 5, type: 'VEC3' },
    ];
    expect(inspectGlb(withJson({ bufferViews: views, accessors }))).toBe(ViewerError.Unreadable);
  });

  it.each([
    ['a view past its buffer', { bufferViews: [{ buffer: 0, byteOffset: 200, byteLength: 96 }] }],
    ['a buffer longer than the binary chunk', { buffers: [{ byteLength: 4096 }] }],
    ['a second buffer', { buffers: [{ byteLength: 240 }, { byteLength: 4 }] }],
    ['a view of another buffer', { bufferViews: [{ buffer: 1, byteLength: 96 }] }],
    [
      'a stride above the glTF maximum',
      { bufferViews: [{ buffer: 0, byteLength: 96, byteStride: 256 }] },
    ],
  ])('refuses %s', (_case, extra) => {
    expect(inspectGlb(withJson(extra))).toBe(ViewerError.Unreadable);
  });

  it.each(['attributes', 'targets'])('refuses %s of a primitive with different counts', (where) => {
    const accessors = [
      ...cubeJson.accessors,
      { bufferView: 0, componentType: 5126, count: 4, type: 'VEC3' },
    ];
    const primitive =
      where === 'attributes'
        ? { attributes: { POSITION: 0, NORMAL: 2 }, indices: 1 }
        : { attributes: { POSITION: 0 }, indices: 1, targets: [{ POSITION: 2 }] };
    expect(inspectGlb(withJson({ accessors, meshes: [{ primitives: [primitive] }] }))).toBe(
      ViewerError.Unreadable,
    );
  });

  it('counts the vertices of every mesh, drawn or not, against the worker budget', () => {
    const accessors = [
      ...cubeJson.accessors,
      { bufferView: 0, componentType: 5126, count: MODEL_MAX_VERTICES, type: 'VEC3' },
    ];
    const meshes = [...cubeJson.meshes, { primitives: [{ attributes: { POSITION: 2 } }] }];
    expect(inspectGlb(withJson({ accessors, meshes }))).toBe(ViewerError.TooComplex);
  });

  it('counts the indices of every mesh against the worker triangle budget', () => {
    const accessors = [
      ...cubeJson.accessors,
      { bufferView: 1, componentType: 5125, count: 3 * MODEL_MAX_TRIANGLES + 3, type: 'SCALAR' },
    ];
    const meshes = [
      ...cubeJson.meshes,
      { primitives: [{ attributes: { POSITION: 0 }, indices: 2 }] },
    ];
    expect(inspectGlb(withJson({ accessors, meshes }))).toBe(ViewerError.TooComplex);
  });

  it('caps all accessor elements together', () => {
    const accessor = {
      bufferView: 0,
      componentType: 5126,
      count: MODEL_MAX_ACCESSOR_ELEMENTS + 1,
      type: 'SCALAR',
    };
    expect(inspectGlb(withAccessor(accessor))).toBe(ViewerError.TooComplex);
  });
});
