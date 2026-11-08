import type { Copy } from '@/interfaces/copy.interface';

/** Vietnamese copy of why a version failed processing (moved out of vi.ts to keep it short). */
export const viFailure: Copy['assets']['failure'] = {
  UPLOAD_CHANGED: 'Tệp đã thay đổi sau khi tải lên. Hãy tải lại.',
  UNREADABLE_IMAGE: 'Đây không phải ảnh PNG, JPEG hoặc WebP đọc được.',
  IMAGE_TOO_LARGE: 'Ảnh có quá nhiều điểm ảnh để tạo bản xem trước.',
  PROCESSING_GAVE_UP: 'Xử lý thất bại nhiều lần. Hãy tải tệp lên lại sau.',
  UPLOAD_EXPIRED: 'Tệp chưa bao giờ được tải lên xong. Hãy tải lại tệp.',
  UNREADABLE_MODEL:
    'Đây không phải tệp glTF nhị phân (.glb) mà Kiln đọc được. Chưa hỗ trợ mesh nén (Draco, meshopt) và tệp tham chiếu bên ngoài.',
  MODEL_TOO_LARGE:
    'Model quá lớn hoặc quá phức tạp để tạo bản xem trước (giới hạn gồm 256 MB, 2 triệu tam giác và 60 giây render).',
};
