import type { Copy } from '@/interfaces/copy.interface';

export const vi: Copy = {
  app: {
    name: 'Kiln',
    tagline: 'Review và phát hành asset sáng tạo cùng studio.',
    skipToContent: 'Bỏ qua tới nội dung',
  },
  health: {
    checking: 'Đang kiểm tra API…',
    ok: (version) => `API hoạt động · v${version}`,
    down: 'Không kết nối được API.',
    retry: 'Thử lại',
  },
};
