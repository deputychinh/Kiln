# Design system

Nguồn duy nhất: `packages/ui` (`@kiln/ui`). Web chỉ dùng token và component từ đây. Theo `references/frontend-and-ux.md`.

## Định hướng

Công cụ cho artist: **asset là nhân vật chính**, giao diện lùi lại. Mặc định nền tối trung tính (không ám màu để không làm lệch cảm nhận màu của texture), có chế độ sáng. Mật độ cao trên desktop, thoáng hơn trên điện thoại.

## Token (`--kiln-*`)

| Nhóm        | Ví dụ                                                                                                                                                             |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Màu         | `--kiln-color-surface`, `-surface-raised`, `-on-surface`, `-on-surface-muted`, `-primary`, `-on-primary`, `-outline`, `-success`, `-warning`, `-danger`, `-focus` |
| Khoảng cách | thang 4 px: `--kiln-space-1` (4) … `--kiln-space-8` (48)                                                                                                          |
| Chữ         | `--kiln-font-sans`, `--kiln-font-mono`; cỡ `--kiln-text-xs` … `--kiln-text-2xl`                                                                                   |
| Bo góc      | `--kiln-radius-sm/md/lg/full`                                                                                                                                     |
| Bóng        | `--kiln-shadow-1/2`                                                                                                                                               |
| Chuyển động | `--kiln-duration-fast/base`, `--kiln-ease-standard`; tôn trọng `prefers-reduced-motion`                                                                           |
| Lớp         | `--kiln-z-header/drawer/dialog/toast`                                                                                                                             |

Độ tương phản: chữ thường ≥ 4.5:1, chữ lớn và viền điều khiển ≥ 3:1, ở cả hai theme.

## Bố cục theo cỡ cửa sổ (Material 3)

| Cỡ       | Rộng       | Điều hướng      | Gallery                        |
| -------- | ---------- | --------------- | ------------------------------ |
| compact  | < 600 px   | thanh dưới      | 2 cột                          |
| medium   | 600–839 px | navigation rail | 3–4 cột                        |
| expanded | ≥ 840 px   | rail mở rộng    | lưới + panel chi tiết bên phải |

## Component (thứ tự xây)

v0.1: `Button`, `IconButton`, `TextField`, `Badge`, `Card`, `AssetThumb`, `EmptyState`, `ErrorState`, `Skeleton`, `Dropzone`, `ProgressBar`, `AppShell`.
v0.2: `Tabs`, `Dialog`, `Drawer`, `Avatar`, `CommentThread`, `AnnotationLayer`, `CompareSlider`, `StatusPill`.
v0.3: `TagChip` (suggested/accepted), `SearchBar` (câu tự nhiên → chip bộ lọc), `RuleViolation`.

Mỗi component: story cho mọi trạng thái, test theo role, không chuỗi viết cứng (nhận qua props).

## Ngân sách

- Accessibility: WCAG 2.2 AA; target ≥ 24 px (2.5.8), focus không bị che (2.4.11), có thay thế cho kéo thả (2.5.7: nút chọn file cạnh dropzone, nút chỉnh cho CompareSlider).
- Hiệu năng: LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1; thumbnail có kích thước cố định để không nhảy layout; viewer 3D tải lười.
