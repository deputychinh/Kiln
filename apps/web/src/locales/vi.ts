import type { Copy } from '@/interfaces/copy.interface';

export const vi: Copy = {
  locale: 'vi',
  app: {
    name: 'Kiln',
    skipToContent: 'Bỏ qua tới nội dung',
  },
  errors: {
    unreachable: 'Kiln không kết nối được máy chủ. Hãy kiểm tra mạng rồi thử lại.',
    unexpected: 'Đã có lỗi xảy ra.',
  },
  assets: {
    title: 'Asset',
    loading: 'Đang tải asset…',
    shown: (count) => `Đang hiển thị ${String(count)} asset`,
    emptyTitle: 'Chưa có asset nào',
    emptyBody:
      'Hãy đăng ảnh hoặc model glTF đầu tiên qua Kiln API. Asset sẽ hiện ở đây kèm ảnh xem trước sau khi xử lý xong.',
    loadFailed: 'Không tải được danh sách asset',
    loadMore: 'Tải thêm',
    loadingMore: 'Đang tải thêm…',
    loadMoreFailed: 'Không tải thêm được asset',
    retry: 'Thử lại',
    kind: { image: 'Ảnh', model: 'Model' },
    status: {
      pending_upload: 'Chờ tải lên',
      processing: 'Đang xử lý',
      ready: 'Sẵn sàng',
      failed: 'Lỗi',
    },
    failure: {
      UPLOAD_CHANGED: 'Tệp đã thay đổi sau khi tải lên. Hãy tải lại.',
      UNREADABLE_IMAGE: 'Đây không phải ảnh PNG, JPEG hoặc WebP đọc được.',
      IMAGE_TOO_LARGE: 'Ảnh có quá nhiều điểm ảnh để tạo bản xem trước.',
      PROCESSING_GAVE_UP: 'Xử lý thất bại nhiều lần. Hãy tải tệp lên lại sau.',
    },
    detailLabel: 'Chi tiết asset',
    selectPrompt: 'Chọn một asset để xem các phiên bản.',
    back: 'Tất cả asset',
    previewAlt: (name) => `Ảnh xem trước của ${name}`,
    kindLabel: 'Loại',
    created: 'Tạo lúc',
    updated: 'Cập nhật',
    versionsTitle: 'Phiên bản',
    versionLabel: (number) => `Phiên bản ${String(number)}`,
    stale: 'Không làm mới được, nên thông tin có thể đã cũ.',
    fileSummary: (name, size) => `${name} · ${size}`,
    loadingAsset: 'Đang tải asset…',
    loadAssetFailed: 'Không tải được asset này',
    notFoundTitle: 'Không tìm thấy asset',
    notFoundBody: 'Asset có thể đã bị xoá, hoặc đường dẫn bị sai.',
  },
};
