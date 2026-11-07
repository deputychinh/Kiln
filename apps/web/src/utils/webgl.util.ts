/**
 * Whether this browser can create a WebGL context at all (it may be off, blocked or missing). The
 * probe's context is released at once: browsers allow only a few live contexts per page.
 */
export const canUseWebGl = (doc: Document = document): boolean => {
  try {
    const canvas = doc.createElement('canvas');
    const context = canvas.getContext('webgl2') ?? canvas.getContext('webgl');
    if (!context) return false;
    context.getExtension('WEBGL_lose_context')?.loseContext();
    return true;
  } catch {
    return false;
  }
};
