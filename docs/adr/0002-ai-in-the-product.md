# ADR 0002: AI trong sản phẩm

- Trạng thái: chấp nhận · 2026-11-03

## Bối cảnh

Ba tính năng dùng mô hình ngôn ngữ: (1) gắn tag và viết mô tả từ thumbnail, (2) giải thích lỗi đặt tên và gợi ý tên đúng, (3) chuyển câu tìm kiếm tự nhiên ("rock textures approved last week") thành bộ lọc có cấu trúc. Rủi ro: model trả sai, chi phí tăng, rò dữ liệu khách, test phụ thuộc mạng.

## Quyết định

1. **Claude qua Anthropic API**, model id và giá nằm trong `constants.py`/env. Mặc định model Sonnet cho vision (tag), Haiku cho chuyển câu tìm kiếm (rẻ, nhanh). Đổi model là đổi cấu hình, không đổi code.
2. **Chỉ qua port** `AiTagger` và `AiSearchPlanner`; có adapter Claude và adapter offline tất định (dùng tên file + màu chủ đạo) để chạy khi không có key và trong test.
3. **Output có cấu trúc**: tool use với JSON schema; parse bằng pydantic; sai schema thì job thất bại có lý do, không đoán.
4. **Người duyệt cuối cùng**: tag AI lưu ở trạng thái `suggested`; chỉ thành `accepted` khi người dùng bấm nhận. Luật đặt tên là code tất định; AI chỉ giải thích và gợi ý.
5. **Tìm kiếm**: model chỉ được trả bộ lọc trong whitelist (tag, loại, trạng thái, khoảng ngày, người tạo); API tự dựng query có tham số, không bao giờ chạy SQL do model sinh (A05).
6. **Chi phí và giới hạn**: chỉ gọi khi có phiên bản mới; cache theo hash file; ngân sách tháng `KILN_AI_MONTHLY_BUDGET_USD`, vượt thì chuyển sang adapter offline và hiện thông báo.
7. **Dữ liệu**: chỉ gửi thumbnail 512 px và tên file, không gửi metadata người dùng; ghi log số token và độ trễ, không log nội dung.
8. **Đo chất lượng**: `services/worker/evals/` có ~50 asset gắn nhãn tay; báo precision/recall tag mỗi release trong CHANGELOG.

## Hệ quả

- Không có key thì sản phẩm vẫn chạy đầy đủ (chất lượng tag thấp hơn); CI không cần secret.
- Thêm một bảng `ai_usage` để theo dõi ngân sách.
- Mỗi lần đổi prompt hay model phải chạy lại eval và ghi kết quả.

## Nguồn

`references/security.md` (A05, A10), `references/data-and-reliability.md` (timeouts, cache), tài liệu Anthropic về tool use và vision.
