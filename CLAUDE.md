# Kiln

Hub review và phát hành asset sáng tạo (ảnh, texture, model 3D) cho studio, có AI hỗ trợ: tự gắn tag, kiểm tra quy ước đặt tên, tìm kiếm bằng ngôn ngữ tự nhiên; publish thẳng từ Blender hoặc CLI.

Stack: npm workspaces (React 19 + Vite + TS, design system, CLI Node) + uv workspace (FastAPI API, Python worker) + Blender add-on; Postgres + MinIO. Docs language: tiếng Việt (code, commit, UI copy gốc tiếng Anh). Everything below is binding for every session in this repo.

## Nguồn sự thật (đọc trước khi sửa code)

| Việc                                                     | Đọc                                                          |
| -------------------------------------------------------- | ------------------------------------------------------------ |
| Quy ước code, đặt tên, cấu trúc thư mục                  | `docs/conventions.md`                                        |
| Kiểm thử: tầng nào, chạy ở đâu, ngưỡng bao nhiêu         | `docs/testing.md`                                            |
| Vì sao chọn stack / layout này; mọi quyết định có hệ quả | `docs/adr/` (ADR mới = file mới, không sửa ADR đã chấp nhận) |
| Kiến trúc hiện tại                                       | `docs/architecture/README.md`                                |
| Việc đang làm, việc tiếp theo                            | `docs/plan.md`, `docs/backlog.md`                            |
| Lệnh chạy, build, test                                   | `make help`                                                  |

## Bản đồ repo

| Thư mục             | Là gì                                       | Scope commit |
| ------------------- | ------------------------------------------- | ------------ |
| `apps/web`          | React 19 + Vite + TanStack Router/Query     | `web`        |
| `packages/ui`       | design system: tokens, component, Storybook | `ui`         |
| `packages/cli`      | CLI Node `kiln` (publish, validate)         | `cli`        |
| `services/api`      | FastAPI, Postgres, MinIO                    | `api`, `db`  |
| `services/worker`   | Python: thumbnail, validate, AI tag         | `worker`     |
| `dcc/blender-addon` | add-on Blender "Publish to Kiln"            | `blender`    |

## Lệnh

```sh
make install   # mọi dependency
make lint      # format check + lint + typecheck cho mọi phần
make test      # unit + API/component test với coverage
make ci        # = lint + test, đúng những gì GitHub Actions chạy
```

Không chạy lệnh thay thế (npm/uv trực tiếp) khi đã có target trong Makefile, trừ khi đang gỡ lỗi target đó.

## Định nghĩa "xong"

Một việc chỉ được báo xong khi tất cả đúng:

1. Code theo `docs/conventions.md` (lint 0 cảnh báo, typecheck sạch).
2. Có test cho hành vi mới hoặc bug vừa sửa; coverage không giảm dưới ngưỡng trong `docs/testing.md`.
3. `make ci` xanh, kết quả được dán vào báo cáo (số test, số pass).
4. Docs cập nhật trong cùng thay đổi: `CHANGELOG.md` mục `[Unreleased]`, README nếu đổi cách dùng, ADR nếu đổi quyết định.
5. Đã commit (xem routine bên dưới).

## Routine mỗi turn (bắt buộc)

Mỗi turn có thay đổi file phải kết thúc bằng commit:

1. Chạy gate của mọi phần đã chạm (`make lint && make test`, hoặc target tương đương của phần đó).
2. Cập nhật CHANGELOG / docs trong cùng thay đổi.
3. `git add` đúng file của việc đó (không `git add -A` khi tree có file lạ), rồi `git commit` theo Conventional Commits, scope lấy từ `commitlint.config.mjs`:
   - `feat(web): …`, `fix(api): …`, `test(e2e): …`, `docs(plan): …`, `chore(repo): …`
   - Một commit cho một đơn vị việc hoàn chỉnh (code + test + docs). Nhiều commit trong một turn là bình thường.
4. Chỉ commit khi xanh. Nếu gate đỏ khi hết turn: **không commit**, báo rõ cái gì đỏ và vì sao để tree bẩn.
5. Không `git push`, không rebase/force trên `main` trừ khi người dùng yêu cầu.
6. Cuối báo cáo ghi hash + message của các commit vừa tạo.

## Jira và phát hành

- Mỗi việc có id `KILN-<n>` trong `docs/backlog.md` (và Jira khi đã liên kết); nhắc id trong body commit: `Refs: KILN-12`.
- Mỗi tuần một release `v0.x`: cập nhật `CHANGELOG.md` (đổi `[Unreleased]` thành phiên bản + ngày), tag `v0.x.0` cục bộ; chỉ push khi người dùng yêu cầu.

## AI trong sản phẩm

- Gọi Claude chỉ qua port `AiTagger`/`AiSearch` trong `services/api|worker`; test dùng fake, không gọi mạng.
- Output của model luôn qua schema (pydantic) và được người dùng duyệt trước khi thành dữ liệu chính thức.
- Model id, giới hạn token, chi phí nằm trong `constants.py`/env, không rải trong code. Xem ADR về AI.

## Phong cách làm việc

- Làm trọn phase (xem `docs/plan.md`) không dừng hỏi giữa chừng; chỉ hỏi khi cần thông tin chỉ người dùng có (business rule, secret, chọn giữa hai pattern đang cùng tồn tại trong repo).
- Thay đổi nhỏ nhất đủ cho yêu cầu; không refactor ngoài phạm vi, không thêm thư viện khi stack đã có cách làm.
- Không nuốt lỗi; lỗi domain có mã ổn định và đổi sang HTTP/UI đúng một lần ở biên.
- Không log dữ liệu cá nhân, secret, token. `.env` không bao giờ vào git; `.env.example` luôn đủ khóa.
- Chuỗi hiển thị nằm trong file locale, không viết cứng trong component.
- Khi thấy UI: chụp màn hình hoặc chạy e2e, không mô tả suông.

## Ngôn ngữ

Người dùng viết tiếng Việt thì trả lời tiếng Việt; tên kỹ thuật, lệnh, message commit giữ tiếng Anh. Docs trong repo viết bằng tiếng Việt; README có câu tóm tắt tiếng Anh vì đây là portfolio.
