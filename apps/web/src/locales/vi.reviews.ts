import type { ReviewsCopy } from '@/interfaces/reviews-copy.interface';

/** Vietnamese copy of review states, decisions and history (KILN-11). */
export const viReviews: ReviewsCopy = {
  tab: 'Duyệt',
  state: { in_review: 'Đang duyệt', approved: 'Đã duyệt', changes_requested: 'Cần sửa' },
  versionLabel: 'Duyệt phiên bản',
  versionOption: (number, isNewest) =>
    isNewest ? `Phiên bản ${String(number)} (mới nhất)` : `Phiên bản ${String(number)}`,
  currentLabel: (number) => `Phiên bản ${String(number)}:`,
  formLabel: (number) => `Quyết định cho phiên bản ${String(number)}`,
  noteLabel: 'Ghi chú (không bắt buộc)',
  notePlaceholder: 'Vì sao? Hoạ sĩ sẽ thấy ghi chú này trong lịch sử.',
  action: { approve: 'Duyệt', request_changes: 'Yêu cầu sửa', reopen: 'Mở lại' },
  saving: 'Đang lưu…',
  notReadyHint: 'Có thể duyệt hoặc yêu cầu sửa phiên bản này khi nó đã xử lý xong.',
  decidedHint: 'Mở lại để đưa phiên bản về trạng thái đang duyệt và quyết định lại.',
  announce: {
    approve: (number) => `Đã duyệt phiên bản ${String(number)}`,
    request_changes: (number) => `Đã yêu cầu sửa phiên bản ${String(number)}`,
    reopen: (number) => `Phiên bản ${String(number)} đã quay lại trạng thái đang duyệt`,
  },
  conflict: (state) =>
    `Người khác đã quyết định trước: phiên bản này giờ là “${state}”. Hãy xem lại rồi quyết định. Ghi chú của bạn vẫn được giữ.`,
  errors: {
    invalidNote: 'Ghi chú quá dài hoặc có ký tự ẩn. Hãy viết tối đa 1.000 ký tự văn bản thường.',
    notReady: 'Phiên bản này chưa sẵn sàng để duyệt (đang xử lý hoặc bị lỗi).',
    readOnly: 'Quyền của bạn chỉ là đọc, nên không thể duyệt.',
    transition:
      'Quyết định đó không còn áp dụng cho phiên bản này. Hãy xem trạng thái rồi thử lại.',
    gone: 'Phiên bản này không còn tồn tại.',
    retry: 'Không khớp được quyết định này với lần thử trước. Hãy xem trạng thái rồi thử lại.',
  },
  historyTitle: 'Lịch sử',
  historyLabel: (number) => `Lịch sử duyệt của phiên bản ${String(number)}`,
  loading: 'Đang tải lịch sử duyệt…',
  loadFailed: 'Không tải được lịch sử duyệt',
  retry: 'Thử lại',
  emptyTitle: 'Chưa có quyết định nào',
  emptyBody: 'Duyệt phiên bản này hoặc yêu cầu sửa, mỗi quyết định sẽ được liệt kê ở đây.',
  showOlder: 'Xem cũ hơn',
  loadingOlder: 'Đang tải…',
  event: {
    approve: (name) => `${name} đã duyệt`,
    request_changes: (name) => `${name} đã yêu cầu sửa`,
    reopen: (name) => `${name} đã mở lại`,
  },
  fromTo: (from, to) => `từ ${from} sang ${to}`,
  filterLabel: 'Trạng thái duyệt',
  filterAll: 'Mọi trạng thái',
  filteredEmptyTitle: (state) => `Không có tài sản nào đã tải ở trạng thái “${state}”`,
  filteredEmptyBody: 'Chưa có tài sản nào đã tải ở trạng thái này. Hãy tải thêm hoặc hiện tất cả.',
  showAllStates: 'Hiện mọi trạng thái',
};
