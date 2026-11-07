import {
  GLTF_COMPONENT_BYTES,
  GLTF_MAX_STRIDE,
  GLTF_TYPE_WIDTHS,
  MODEL_MAX_ACCESSOR_ELEMENTS,
  MODEL_MAX_OBJECTS,
  MODEL_MAX_TRIANGLES,
  MODEL_MAX_VERTICES,
} from '@/constants/viewer.constant';
import { ViewerError } from '@/enums/viewer-error.enum';

type Json = Record<string, unknown>;

const isRecord = (value: unknown): value is Json =>
  typeof value === 'object' && value !== null && !Array.isArray(value);

const isCount = (value: unknown): value is number =>
  typeof value === 'number' && Number.isSafeInteger(value) && value >= 0;

/** Stops the check at the first problem; `checkGeometry` turns it into its error. */
const refuse = (error: ViewerError): never => {
  throw Object.assign(new Error(error), { refusal: error });
};

const unreadable = (): never => refuse(ViewerError.Unreadable);

const countOf = (value: unknown): number => (isCount(value) ? value : unreadable());

const listOf = (json: Json, key: string): unknown[] => {
  const value = json[key] ?? [];
  if (!Array.isArray(value)) return unreadable();
  if (value.length > MODEL_MAX_OBJECTS) return refuse(ViewerError.TooComplex);
  return value;
};

const entryOf = (list: unknown[], index: unknown): Json => {
  const entry = isCount(index) ? list[index] : undefined;
  return isRecord(entry) ? entry : unreadable();
};

/** Counts first: every attribute of a primitive shares one count; totals over all meshes. */
const checkBudgets = (meshes: unknown[], accessors: unknown[]): void => {
  const positions = new Set<number>();
  const indices = new Set<number>();
  const count = (index: number): number => countOf(entryOf(accessors, index).count);
  for (const mesh of meshes) {
    const primitives = isRecord(mesh) ? (mesh.primitives ?? []) : unreadable();
    if (!Array.isArray(primitives)) unreadable();
    for (const primitive of primitives as unknown[]) {
      if (!isRecord(primitive)) unreadable();
      const { attributes = {}, targets = [], indices: indexAccessor } = primitive as Json;
      if (!Array.isArray(targets)) unreadable();
      const sets = [attributes, ...(targets as unknown[])];
      if (!sets.every(isRecord)) unreadable();
      const named = (sets as Json[]).flatMap((set) => Object.values(set));
      if (!named.every(isCount)) unreadable();
      if (new Set((named as number[]).map(count)).size > 1) unreadable();
      const position = (attributes as Json).POSITION;
      if (isCount(position)) positions.add(position);
      if (indexAccessor !== undefined)
        indices.add(isCount(indexAccessor) ? indexAccessor : unreadable());
    }
  }
  const sum = (set: Iterable<number>): number => [...set].reduce((total, i) => total + count(i), 0);
  const elements = sum(accessors.keys());
  if (
    sum(positions) > MODEL_MAX_VERTICES ||
    sum(indices) > 3 * MODEL_MAX_TRIANGLES ||
    elements > MODEL_MAX_ACCESSOR_ELEMENTS
  ) {
    refuse(ViewerError.TooComplex);
  }
};

/** Every accessor lies inside its bufferView, every view inside the one buffer, the BIN chunk. */
const checkLayouts = (json: Json, accessors: unknown[], binLength: number): void => {
  const buffers = listOf(json, 'buffers');
  const views = listOf(json, 'bufferViews');
  if (buffers.length > 1) unreadable();
  const bufferLength = buffers.length ? countOf(entryOf(buffers, 0).byteLength) : 0;
  if (bufferLength > binLength) unreadable();
  for (const accessor of accessors) {
    if (!isRecord(accessor) || 'sparse' in accessor || accessor.bufferView === undefined) {
      unreadable();
    }
    const { componentType, type, bufferView, byteOffset = 0, count } = accessor as Json;
    const size =
      typeof componentType === 'number' ? GLTF_COMPONENT_BYTES[componentType] : undefined;
    const width = typeof type === 'string' ? GLTF_TYPE_WIDTHS[type] : undefined;
    if (size === undefined || width === undefined) return unreadable();
    const view = entryOf(views, bufferView);
    if (view.buffer !== 0) unreadable();
    const viewOffset = countOf(view.byteOffset ?? 0);
    const viewLength = countOf(view.byteLength);
    if (viewOffset + viewLength > bufferLength) unreadable();
    const element = size * width;
    const stride = countOf(view.byteStride ?? element);
    if (stride < element || stride > GLTF_MAX_STRIDE || stride % size !== 0) unreadable();
    const offset = countOf(byteOffset);
    const elements = countOf(count);
    if (offset % size !== 0) unreadable();
    if (elements > 0 && offset + stride * (elements - 1) + element > viewLength) unreadable();
  }
};

/**
 * Bounds what three.js would allocate, the same way the worker's reader does (KILN-9 review):
 * counts within the worker's budgets over every mesh and accessor, then every accessor paid for
 * in bytes of its view. Returns why the file cannot be shown, or null.
 */
export const checkGeometry = (json: Json, binLength: number): ViewerError | null => {
  try {
    const accessors = listOf(json, 'accessors');
    checkBudgets(listOf(json, 'meshes'), accessors);
    checkLayouts(json, accessors, binLength);
    return null;
  } catch (error) {
    if (error instanceof Error && 'refusal' in error) return error.refusal as ViewerError;
    throw error;
  }
};
