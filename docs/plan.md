# Plan

Mỗi phase kết thúc khi `make ci` xanh, docs cập nhật, commit trên `main` và (từ phase 1) có tag release. Một release mỗi tuần.

| Phase | Release | Mục tiêu          | Tiêu chí chấp nhận                                                                                                                                                                        |
| ----- | ------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0     | –       | Khởi tạo repo     | `make ci` xanh; commitlint chặn message sai; README, CHANGELOG, ADR 0001–0002, kiến trúc, bảo mật, design system có mặt                                                                   |
| 1     | v0.1    | Upload và gallery | Upload ảnh/`.glb` qua presigned URL; worker tạo thumbnail; gallery có 4 trạng thái; e2e upload → thấy thumbnail trên bản build                                                            |
| 2     | v0.2    | Review            | Phiên bản asset; so sánh side-by-side; viewer 3D (react-three-fiber); ghi chú vùng trên ảnh; comment; trạng thái `in_review → approved/changes_requested`; e2e luồng duyệt                |
| 3     | v0.3    | AI + DCC          | Worker gọi Claude gắn tag + mô tả (người dùng duyệt); lint quy ước đặt tên; tìm kiếm ngôn ngữ tự nhiên → bộ lọc; add-on Blender publish; CLI `kiln publish/validate`; eval tag có số liệu |
| 4     | v0.4    | Đánh bóng + hồ sơ | Audit nhất quán UI theo token; axe 0 lỗi nghiêm trọng; Core Web Vitals đạt; Storybook public; video demo 2 phút; case study 1 trang                                                       |
