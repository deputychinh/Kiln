/** Whether this browser can create a WebGL context at all (it may be off, blocked or missing). */
export const canUseWebGl = (doc: Document = document): boolean => {
  try {
    const canvas = doc.createElement('canvas');
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'));
  } catch {
    return false;
  }
};
