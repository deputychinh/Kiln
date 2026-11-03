# Quy ước

Lint ép phần lớn các luật dưới đây; phần còn lại kiểm khi review.

## Chung

- **Một nguồn sự thật**: enum, hằng số, lỗi và interface dùng chung khai báo đúng một chỗ (Python: `enums.py`, `constants.py`, `errors.py` của từng package; TS: `src/enums/*.enum.ts`, `src/constants/*.constant.ts`, `src/interfaces/*.interface.ts`) rồi import ở mọi nơi khác.
- **Phụ thuộc hướng vào trong**: routes → services → domain; domain không import framework, DB hay SDK.
- **Python = class + SOLID; TypeScript = arrow function + design token + BEM.**
- Không nuốt lỗi; lỗi domain mang mã ổn định (`ErrorCode`) và đổi sang HTTP/UI đúng một lần ở biên (API trả RFC 9457 problem details có trường `code`).
- Không log dữ liệu cá nhân, secret, token hay nội dung asset.
- Format: Prettier (100 cột, nháy đơn, trailing comma); Python: ruff format (100 cột).
- Thời gian UTC ISO-8601; id là UUID v7 (có thứ tự) dạng chuỗi; JSON API dùng `snake_case`, web đọc qua type sinh từ OpenAPI.
- Code, tên biến, commit, chuỗi UI gốc bằng tiếng Anh; docs bằng tiếng Việt.

## Python (`services/*`, uv workspace)

| Chủ đề        | Luật                                                                                                                                                  |
| ------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Layout API    | `kiln_api/{config.py, enums.py, constants.py, errors.py, domain/, ports.py, repositories/, services/, routes/, schemas/, db/, container.py, main.py}` |
| Layout worker | `kiln_worker/{config.py, jobs/, processors/, ports.py, adapters/, __main__.py}`; dùng chung model qua `kiln_api` khi cần, không copy                  |
| Kiểu          | mypy `strict`; không `Any`; dataclass `frozen=True, slots=True` cho value; pydantic chỉ ở biên API và output AI                                       |
| Lint          | ruff với bộ luật trong `pyproject.toml` gốc; mỗi `noqa` có lý do                                                                                      |
| Class         | inject qua constructor, thuộc tính `_private`, một lý do để đổi; service nhận port trừu tượng                                                         |
| Test          | `tests/unit` cho domain, `tests/api` qua `TestClient` với fake cho port; tên test là câu; coverage ≥ 90 %                                             |
| Dữ liệu       | Alembic là đường duy nhất đổi schema; migration đảo ngược được; xóa cột/bảng phải có ADR                                                              |
| AI            | gọi Claude chỉ qua port; output qua schema pydantic; không gửi PII lên model                                                                          |

## TypeScript (`apps/web`, `packages/*`)

| Chủ đề     | Luật                                                                                                                                                                                                                |
| ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Layout web | `src/routes` (TanStack Router file routes), `src/features/<tên>/{components,hooks,services,index.ts}`, `src/api` (schema sinh + client), `src/constants`, `src/enums`, `src/interfaces`, `src/utils`, `src/locales` |
| Layout ui  | `src/tokens/*.css`, `src/components/<Tên>/{<Tên>.tsx,<Tên>.css,<Tên>.stories.tsx,<Tên>.test.tsx}`, `src/index.ts`                                                                                                   |
| Hàm        | chỉ arrow function; không class; không `any`; không non-null `!`; alias `@/`                                                                                                                                        |
| CSS        | BEM, block = tên file (`AssetCard.css` ↔ `.asset-card`); màu, khoảng cách, chữ, bo góc, bóng, z-index, thời lượng chỉ dùng token `var(--kiln-…)`; mobile-first                                                      |
| State      | server state qua TanStack Query trong service của feature; state chọn item nằm trên URL; state cục bộ `useState/useReducer`; `useEffect` chỉ để đồng bộ hệ ngoài                                                    |
| UI         | mỗi màn có loading / empty / error / success; màu không là tín hiệu duy nhất; bàn phím dùng được; target ≥ 24 px, hành động chính 44 px                                                                             |
| Copy       | không viết cứng chuỗi hiển thị; `src/locales/en.ts` là nguồn, `vi.ts` cùng khóa (test kiểm)                                                                                                                         |
| Test       | Vitest + Testing Library theo role/label; coverage dòng ≥ 80 %; Playwright cho luồng chính trên bản build                                                                                                           |
| CLI        | `packages/cli`: lệnh thuần, I/O tách khỏi logic; exit code ổn định trong `exit-code.enum.ts`                                                                                                                        |

## Blender add-on (`dcc/blender-addon`)

- Python theo API `bpy` của Blender 4.2+ (extension manifest `blender_manifest.toml`); logic không phụ thuộc `bpy` nằm ở `kiln_blender/core.py` để test bằng pytest ngoài Blender.
- Không chặn UI Blender: upload chạy ở thread nền, báo tiến độ qua `wm.progress`.

## Commit, nhánh, release

- Conventional Commits; scope trong `commitlint.config.mjs`. Một commit cho một đơn vị việc trọn vẹn (code + test + docs). Body ghi `Refs: KILN-<n>`.
- husky chạy Prettier (pre-commit) và commitlint (commit-msg); CI chạy lại cả hai.
- Đổi hành vi hoặc quyết định thì sửa ADR/docs trong cùng commit.
- Trunk-based: nhánh ngắn `feat/KILN-12-…` / `fix/KILN-…` hoặc commit thẳng `main` khi làm một mình; CI xanh trước khi merge.
- Release hàng tuần: `chore(release): v0.x.0` đổi mục `[Unreleased]` thành phiên bản, rồi tag `v0.x.0`.
