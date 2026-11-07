import {
  ASSET_NAME_MAX_LENGTH,
  KIND_BY_CONTENT_TYPE,
  FILE_NAME_MAX_LENGTH,
  UPLOAD_CONTENT_TYPES,
  UPLOAD_MAX_BYTES,
} from '@/constants/upload.constant';
import { UploadRejection } from '@/enums/upload-rejection.enum';
import type { AssetKind } from '@/interfaces/asset.interface';
import type { UploadDeclarationResult } from '@/interfaces/upload.interface';

const extensionOf = (fileName: string): string => {
  const dot = fileName.lastIndexOf('.');
  return dot === -1 ? '' : fileName.slice(dot + 1).toLowerCase();
};

/** Characters as the API counts them (code points), so a cut never splits an emoji in half. */
const charactersOf = (text: string): string[] => Array.from(text);

const WRONG_KIND: Readonly<Record<AssetKind, UploadRejection>> = {
  image: UploadRejection.NotAnImage,
  model: UploadRejection.NotAModel,
};

const assetNameOf = (fileName: string): string => {
  const dot = fileName.lastIndexOf('.');
  const stem = dot > 0 ? fileName.slice(0, dot) : fileName;
  return charactersOf(stem).slice(0, ASSET_NAME_MAX_LENGTH).join('');
};

/**
 * What to tell the API about a file, or why it would refuse it. The type comes from the
 * extension: browsers report `.glb` as empty and anyone can rename a file, so the API and the
 * worker (magic bytes) stay the real gate. With `kind`, the file is a new version of an asset of
 * that kind and must be the same kind of file.
 */
export const declareUpload = (file: File, kind?: AssetKind): UploadDeclarationResult => {
  const contentType = UPLOAD_CONTENT_TYPES[extensionOf(file.name)];
  if (!contentType) return { rejection: UploadRejection.Unsupported };
  if (kind && KIND_BY_CONTENT_TYPE[contentType] !== kind) return { rejection: WRONG_KIND[kind] };
  if (file.size === 0) return { rejection: UploadRejection.Empty };
  if (file.size > UPLOAD_MAX_BYTES) return { rejection: UploadRejection.TooLarge };
  if (charactersOf(file.name).length > FILE_NAME_MAX_LENGTH)
    return { rejection: UploadRejection.NameTooLong };
  return {
    declaration: {
      file_name: file.name,
      content_type: contentType,
      size_bytes: file.size,
      name: assetNameOf(file.name),
    },
  };
};
