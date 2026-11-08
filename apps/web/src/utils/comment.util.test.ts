import { aVersion } from '@/test/fake-api';
import { defaultCommentVersion, draftKey } from '@/utils/comment.util';

describe('comment.util', () => {
  it('opens comments on the newest ready version', () => {
    const versions = [
      aVersion({ id: 'a', number: 1, status: 'ready' }),
      aVersion({ id: 'b', number: 2, status: 'ready' }),
      aVersion({ id: 'c', number: 3, status: 'failed' }),
    ];

    expect(defaultCommentVersion(versions)?.id).toBe('b');
  });

  it('falls back to the newest version when none is ready, and to nothing without versions', () => {
    expect(defaultCommentVersion([aVersion({ id: 'p', status: 'processing' })])?.id).toBe('p');
    expect(defaultCommentVersion([])).toBeUndefined();
  });

  it('keeps a key for the same content and makes a new one for new content', () => {
    const first = draftKey(null, 'a');

    expect(draftKey(first, 'a')).toBe(first);
    expect(draftKey(first, 'b').key).not.toBe(first.key);
    expect(first.key).toMatch(/^[0-9a-f-]{36}$/);
  });
});
