import { UPLOAD_MAX_BYTES } from '@/constants/upload.constant';
import { UploadRejection } from '@/enums/upload-rejection.enum';
import { declareUpload } from '@/utils/upload-file.util';

/** A File whose size is faked, so 500 MiB cases need no memory. */
const fileOf = (name: string, type: string, size: number): File => {
  const file = new File(['x'], name, { type });
  Object.defineProperty(file, 'size', { value: size });
  return file;
};

describe('declareUpload', () => {
  it('declares a PNG with its type, size and a name without the extension', () => {
    expect(declareUpload(fileOf('rock_albedo.png', 'image/png', 1_500))).toEqual({
      declaration: {
        file_name: 'rock_albedo.png',
        content_type: 'image/png',
        size_bytes: 1_500,
        name: 'rock_albedo',
      },
    });
  });

  it.each([
    ['crate.glb', ''],
    ['crate.GLB', 'application/octet-stream'],
  ])('takes the glTF type from the extension of %s (browsers report %j)', (name, type) => {
    expect(declareUpload(fileOf(name, type, 10)).declaration?.content_type).toBe(
      'model/gltf-binary',
    );
  });

  it.each([
    ['photo.jpeg', 'image/jpeg'],
    ['photo.JPG', ''],
    ['tile.webp', 'image/webp'],
  ])('accepts %s', (name, type) => {
    expect(declareUpload(fileOf(name, type, 10)).rejection).toBeUndefined();
  });

  it.each([
    ['notes.txt', 'text/plain'],
    ['scene.gltf', 'model/gltf+json'],
    ['anim.gif', 'image/gif'],
    ['noextension', ''],
  ])('refuses %s as unsupported', (name, type) => {
    expect(declareUpload(fileOf(name, type, 10))).toEqual({
      rejection: UploadRejection.Unsupported,
    });
  });

  it('refuses an empty file', () => {
    expect(declareUpload(fileOf('rock.png', 'image/png', 0))).toEqual({
      rejection: UploadRejection.Empty,
    });
  });

  it('accepts exactly the size limit and refuses one byte more', () => {
    expect(
      declareUpload(fileOf('big.png', 'image/png', UPLOAD_MAX_BYTES)).rejection,
    ).toBeUndefined();
    expect(declareUpload(fileOf('big.png', 'image/png', UPLOAD_MAX_BYTES + 1))).toEqual({
      rejection: UploadRejection.TooLarge,
    });
  });

  it('cuts a long name to the API limit and keeps a name for a dot file', () => {
    const long = `${'a'.repeat(200)}.png`;
    expect(declareUpload(fileOf(long, 'image/png', 1)).declaration?.name).toHaveLength(120);
    expect(declareUpload(fileOf('.png', 'image/png', 1)).declaration?.name).toBe('.png');
  });

  it('cuts the name by characters, never inside an emoji', () => {
    const name = declareUpload(fileOf(`${'a'.repeat(119)}😀b.png`, 'image/png', 1)).declaration
      ?.name;

    expect(name).toBe(`${'a'.repeat(119)}😀`);
    expect(Array.from(name ?? '')).toHaveLength(120);
  });

  it('accepts a 255-character file name and refuses a longer one', () => {
    const named = (length: number) => fileOf(`${'é'.repeat(length - 4)}.png`, 'image/png', 1);

    expect(declareUpload(named(255)).rejection).toBeUndefined();
    expect(declareUpload(named(256))).toEqual({ rejection: UploadRejection.NameTooLong });
  });

  it('trusts the extension over a misleading browser type', () => {
    expect(declareUpload(fileOf('fake.txt', 'image/png', 1))).toEqual({
      rejection: UploadRejection.Unsupported,
    });
  });
});
