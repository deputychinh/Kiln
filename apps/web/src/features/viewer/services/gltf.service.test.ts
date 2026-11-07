import { Mesh, type Object3D } from 'three';

import { ViewerError } from '@/enums/viewer-error.enum';
import { createSafeLoadingManager, parseModel } from '@/features/viewer/services/gltf.service';
import { urlOf } from '@/test/fake-api';
import { buildGlb, cubeGlb, cubeJson } from '@/test/glb';
import { viewerErrorOf } from '@/utils/viewer.util';

const meshesOf = (object: Object3D): Mesh[] => {
  const found: Mesh[] = [];
  object.traverse((child) => {
    if (child instanceof Mesh) found.push(child as Mesh);
  });
  return found;
};

const failureOf = async (promise: Promise<unknown>): Promise<ViewerError> => {
  try {
    await promise;
  } catch (error) {
    return viewerErrorOf(error);
  }
  throw new Error('expected a failure');
};

describe('parseModel', () => {
  afterEach(() => vi.restoreAllMocks());

  it('reads a self-contained .glb from memory', async () => {
    const scene = await parseModel(cubeGlb());

    const [mesh] = meshesOf(scene);
    expect(mesh?.geometry.getAttribute('position').count).toBe(8);
    expect(mesh?.geometry.getIndex()?.count).toBe(36);
  });

  it('refuses to fetch an image the file names outside itself', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    const json = {
      ...cubeJson,
      images: [{ uri: 'https://evil.test/a.png' }],
      textures: [{ source: 0 }],
      materials: [{ pbrMetallicRoughness: { baseColorTexture: { index: 0 } } }],
      meshes: [{ primitives: [{ attributes: { POSITION: 0 }, indices: 1, material: 0 }] }],
    };

    expect(await failureOf(parseModel(buildGlb(json)))).toBe(ViewerError.ExternalReference);
    expect(fetchMock.mock.calls.map(([input]) => urlOf(input))).not.toContain(
      'https://evil.test/a.png',
    );
  });

  it('refuses to fetch a buffer the file names outside itself', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch');
    const json = { ...cubeJson, buffers: [{ byteLength: 240, uri: 'https://evil.test/a.bin' }] };

    expect(await failureOf(parseModel(buildGlb(json, null)))).toBe(ViewerError.ExternalReference);
    expect(fetchMock.mock.calls.map(([input]) => urlOf(input))).not.toContain(
      'https://evil.test/a.bin',
    );
  });

  it('reports a file three cannot parse as unreadable', async () => {
    const json = {
      ...cubeJson,
      accessors: [{ bufferView: 9, componentType: 5126, count: 8, type: 'VEC3' }],
    };
    expect(await failureOf(parseModel(buildGlb(json)))).toBe(ViewerError.Unreadable);
  });
});

describe('createSafeLoadingManager', () => {
  it('lets URLs inside the file through and turns every other one into nothing', () => {
    const onBlocked = vi.fn();
    const manager = createSafeLoadingManager(onBlocked);

    expect(manager.resolveURL('blob:http://app.test/1')).toBe('blob:http://app.test/1');
    expect(manager.resolveURL('data:image/png;base64,AA')).toBe('data:image/png;base64,AA');
    expect(onBlocked).not.toHaveBeenCalled();

    expect(manager.resolveURL('https://evil.test/a.png')).toBe('data:,');
    expect(manager.resolveURL('textures/a.png')).toBe('data:,');
    expect(onBlocked).toHaveBeenCalledTimes(2);
  });
});
