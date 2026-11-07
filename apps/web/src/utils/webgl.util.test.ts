import { canUseWebGl } from '@/utils/webgl.util';

const documentWith = (getContext: () => unknown): Document =>
  ({ createElement: () => ({ getContext }) }) as unknown as Document;

describe('canUseWebGl', () => {
  it('is true when a WebGL 2 or a WebGL 1 context can be made', () => {
    expect(canUseWebGl(documentWith(() => ({})))).toBe(true);
    const onlyWebGl1 = vi.fn((kind: string) => (kind === 'webgl' ? {} : null));
    expect(canUseWebGl(documentWith(onlyWebGl1 as unknown as () => unknown))).toBe(true);
  });

  it('is false when neither can be made, or asking throws', () => {
    expect(canUseWebGl(documentWith(() => null))).toBe(false);
    expect(
      canUseWebGl(
        documentWith(() => {
          throw new Error('blocked');
        }),
      ),
    ).toBe(false);
  });
});
