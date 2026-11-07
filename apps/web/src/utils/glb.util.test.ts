import { GLB_MAX_JSON_BYTES } from '@/constants/viewer.constant';
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

  it('refuses a JSON chunk above the worker limit as too large, before reading it', () => {
    const buffer = buildGlb(cubeJson, null);
    new DataView(buffer).setUint32(12, GLB_MAX_JSON_BYTES + 4, true);
    expect(inspectGlb(buffer)).toBe(ViewerError.TooLarge);
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
