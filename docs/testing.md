# Kiểm thử

## Các tầng

| Tầng                            | Ở đâu                                  | Chạy                                | Ngưỡng                               |
| ------------------------------- | -------------------------------------- | ----------------------------------- | ------------------------------------ |
| Domain Python (logic thuần)     | `services/*/tests/unit`                | `uv run pytest`                     | tổng ≥ 90 %                          |
| API (FastAPI + fake cho port)   | `services/api/tests/api`               | `uv run pytest`                     | như trên                             |
| Worker (processor với file mẫu) | `services/worker/tests`                | `uv run pytest`                     | như trên                             |
| Blender core (không `bpy`)      | `dcc/blender-addon/tests`              | `uv run pytest`                     | như trên                             |
| Component UI                    | `packages/ui/src/**/*.test.tsx`        | `npm test --workspace packages/ui`  | dòng ≥ 80 %                          |
| Web unit/component              | `apps/web/src/**/*.test.ts(x)`         | `npm test --workspace apps/web`     | dòng ≥ 80 %                          |
| CLI                             | `packages/cli/src/**/*.test.ts`        | `npm test --workspace packages/cli` | dòng ≥ 80 %                          |
| Luồng trình duyệt               | `apps/web/e2e` (Playwright)            | `make e2e` sau khi build            | smoke + luồng chính mỗi feature      |
| Accessibility                   | `apps/web/e2e/a11y.spec.ts` (axe-core) | `make e2e`                          | serious/critical = 0                 |
| Hiệu năng                       | Lighthouse trên bản build              | thủ công mỗi release                | LCP ≤ 2.5 s, INP ≤ 200 ms, CLS ≤ 0.1 |

`make ci` = lint + typecheck + test + build; giống `.github/workflows/ci.yml`.

## Nguyên tắc

- Test hành vi, mỗi test một hành vi, Arrange–Act–Assert; tên test là câu (`test_upload_is_rejected_when_file_type_is_unknown`).
- Fake cho port (DB, storage, đồng hồ, Claude) trong `tests/fakes.py`; test không gọi mạng; warning là lỗi.
- File mẫu nhỏ trong `samples/` (CC0 hoặc tự làm), không dùng asset thật của studio.
- E2E chạy trên bản build production, không chạy trên dev server.

## Những gì test không chứng minh

- Chất lượng tag của Claude: đo riêng bằng bộ eval nhỏ (`services/worker/evals/`) với nhãn tay, báo cáo precision mỗi release.
- Add-on chạy đúng trong Blender thật: kiểm thủ công trên Blender 4.2 LTS trước mỗi release có đổi add-on.
- Hiệu năng với hàng nghìn asset: chỉ đo khi có seed lớn (v0.4).
