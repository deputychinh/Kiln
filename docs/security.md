# Bảo mật

Mức mục tiêu: OWASP ASVS 5.0 L1, theo `references/security.md`.

## Mô hình mối đe dọa

| Tài sản                      | Lối vào                           | Mối đe dọa                                 | Biện pháp                                                                                                                                                          |
| ---------------------------- | --------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| File asset của studio (IP)   | presigned URL, API download       | rò link, đoán id                           | URL hết hạn ngắn; id UUID v7 không đoán được trong thực tế; kiểm quyền theo object trước khi ký (A01)                                                              |
| Upload                       | presigned PUT                     | file độc, file quá lớn, zip bomb `.glb`    | ký kèm `Content-Type` và `content-length-range`; worker kiểm magic bytes, giới hạn kích thước giải nén và thời gian xử lý; xử lý trong tiến trình riêng (A06, A10) |
| Tài khoản, token CLI/Blender | đăng nhập, header `Authorization` | đoán mật khẩu, lộ token                    | Argon2id; throttling; token ngẫu nhiên 256 bit, lưu hash, có thể thu hồi (A04, A07)                                                                                |
| Tìm kiếm AI                  | câu người dùng → model            | prompt injection để đọc dữ liệu người khác | model chỉ trả bộ lọc whitelist; quyền áp sau, ở API (A01, A05)                                                                                                     |
| Chi phí Claude               | job AI                            | lạm dụng làm tốn tiền                      | ngân sách tháng, cache theo hash, rate limit theo người dùng                                                                                                       |
| Chuỗi cung ứng               | npm, PyPI, add-on                 | gói độc                                    | lockfile commit, pin chính xác, `npm audit` trong CI, `pip-audit` trước release (A03)                                                                              |

## Bắt buộc

- Header: CSP (không `unsafe-inline` cho script), HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: same-origin`.
- CORS allow-list từ `KILN_CORS_ORIGINS`.
- Giới hạn: body JSON 1 MB; asset 500 MB; `limit` phân trang tối đa 100.
- Log sự kiện bảo mật (đăng nhập, từ chối quyền, thu hồi token) có id, không có secret.
- Secret chỉ ở env; `.env` không vào git.
