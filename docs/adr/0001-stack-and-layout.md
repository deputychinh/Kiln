# ADR 0001: Stack và layout repo

- Trạng thái: chấp nhận · 2026-11-03

## Bối cảnh

Kiln là hub review asset sáng tạo cho studio nhỏ (5–50 người): artist publish ảnh, texture, model 3D; lead so sánh phiên bản và duyệt; AI gắn tag và bắt lỗi đặt tên. Dự án cũng là portfolio cho vị trí full-stack (React/TS, Node tooling, Python pipeline, DCC), nên mỗi phần phải đủ thật để demo, và phát hành mỗi tuần.

## Quyết định

1. **Một repo, hai workspace.** npm workspaces cho `apps/web`, `packages/ui`, `packages/cli`; uv workspace cho `services/api`, `services/worker` và phần lõi của add-on Blender. Tooling repo (Prettier, husky, commitlint) ở gốc. _npm thay vì pnpm_: Node 26 không còn kèm corepack và hai repo tham chiếu đều dùng npm; đổi sau chỉ tốn một commit.
2. **Monolith mô-đun trước** (`references/backend-architecture.md`): một API FastAPI với các bounded context `assets` (core: asset, phiên bản, file), `review` (ghi chú, comment, trạng thái duyệt), `catalog` (tag, tìm kiếm, luật đặt tên). Worker là tiến trình riêng vì việc nặng (render, gọi AI) không được chặn request.
3. **Phân tầng**: routes → services → domain; I/O sau port (`AssetRepository`, `ObjectStorage`, `JobQueue`, `AiTagger`, `Clock`). Domain thuần, test không cần DB.
4. **Dữ liệu**: Postgres 17 (SQLAlchemy 2 + Alembic) cho metadata; file nằm ở object storage S3-compatible (MinIO local). Upload/download qua **presigned URL** nên API không chuyển byte asset.
5. **Hàng đợi việc trên Postgres** (`SELECT … FOR UPDATE SKIP LOCKED`), ghi job trong cùng transaction với thay đổi asset (tương đương outbox, `references/data-and-reliability.md`). Không thêm Redis/Kafka cho đến khi một ADR chỉ ra nhu cầu. Worker idempotent theo `job_id`, retry có backoff, quá 5 lần thì `failed` và hiện trên UI.
6. **API** theo `references/api-design.md`: OpenAPI 3.1 xuất bằng `make openapi`, web sinh type bằng `openapi-typescript`; lỗi RFC 9457 + `code`; phân trang cursor; `Idempotency-Key` cho `POST /assets`; `/health`, `/ready`; `X-Request-Id`.
7. **Web**: React 19 + Vite (SPA, không cần SSR vì là công cụ nội bộ sau đăng nhập), TanStack Router (route có type, state trên URL) + TanStack Query (server state). Viewer 3D: react-three-fiber. Style: CSS thuần + token của `packages/ui`, BEM; không Tailwind để bám house convention.
8. **Design system riêng** (`packages/ui`) với Storybook: đây là bằng chứng cho "visual consistency" và là nơi duy nhất định nghĩa token.
9. **CLI Node** (`packages/cli`, Commander) và **add-on Blender** dùng chung API công khai với web, xác thực bằng personal access token.
10. **Cổng chất lượng**: ruff + mypy strict + pytest ≥ 90 %; ESLint 0 cảnh báo + tsc + Vitest ≥ 80 % + Playwright + axe; Conventional Commits do husky và CI ép.

## Hệ quả

- Một lệnh `make ci` kiểm cả hai hệ sinh thái; CI có hai job (`python`, `node`).
- Postgres làm hàng đợi giới hạn ở vài chục job/giây; đủ cho studio nhỏ, cần ADR mới nếu vượt.
- Presigned URL buộc cấu hình CORS trên bucket và giới hạn kích thước/kiểu file khi ký (A10, `docs/security.md`).
- Xác thực: v0.1 chạy chế độ demo một người dùng; v0.2 thêm đăng nhập email + mật khẩu (Argon2id, cookie phiên HttpOnly) và personal access token cho CLI/Blender (KILN-19).
- Không SSR nên trang công khai (nếu có) phải làm riêng; chấp nhận vì sản phẩm nằm sau đăng nhập.

## Nguồn

`references/backend-architecture.md` (Clean Architecture, monolith-first), `references/api-design.md` (Zalando, RFC 9457), `references/data-and-reliability.md` (DDIA ch. 11, Release It! timeouts/backoff), `references/frontend-and-ux.md`, `references/delivery.md`.
