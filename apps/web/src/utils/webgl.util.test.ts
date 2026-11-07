import { canUseWebGl } from '@/utils/webgl.util';

const documentWith = (getContext: () => unknown): Document =>
  ({ createElement: () => ({ getContext }) }) as unknown as Document;

describe('canUseWebGl', () => {
  it('is true when a WebGL 2 or a WebGL 1 context can be made', () => {
    const context = { getExtension: () => null };
    expect(canUseWebGl(documentWith(() => context))).toBe(true);
    const onlyWebGl1 = vi.fn((kind: string) => (kind === 'webgl' ? context : null));
    expect(canUseWebGl(documentWith(onlyWebGl1 as unknown as () => unknown))).toBe(true);
  });

  it('releases the context it made to ask', () => {
    const loseContext = vi.fn();
    const context = {
      getExtension: (name: string) => (name === 'WEBGL_lose_context' ? { loseContext } : null),
    };
    expect(canUseWebGl(documentWith(() => context))).toBe(true);
    expect(loseContext).toHaveBeenCalledTimes(1);
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
