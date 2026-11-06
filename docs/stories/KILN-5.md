# KILN-5: Thumbnails for `.glb` models

- Release: v0.1 · Status: doing · Owner: Claude (deliver-loop)

## Story

As a **lead scanning the studio's assets**, I want every uploaded glTF model (`.glb`) to get a preview like images do, so that I can recognise props and characters in the gallery without opening each file in a 3D tool.

INVEST: Independent ☑ (KILN-4 queue and worker) · Negotiable ☑ (a still preview; the interactive viewer is KILN-9) · Valuable ☑ · Estimable ☑ · Small ☑ (one parser, one renderer, one migration) · Testable ☑

## Acceptance criteria

| Id             | Given                                                                                                                                                                       | When                   | Then                                                                                                                                                                                                        |
| -------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1            | a completed `.glb` upload (glTF 2.0 binary, embedded buffer)                                                                                                                | the thumbnail job runs | the worker renders a 512 × 512 WebP preview (transparent background, neutral shaded surface, three-quarter view, model fitted to the frame) to the same key as image previews and marks the version `ready` |
| AC2            | a scene with several meshes and nodes (translation, rotation, scale or a matrix, nested)                                                                                    | it is rendered         | node transforms are applied, so the preview shows the scene as authored                                                                                                                                     |
| AC3            | a ready model version or a model asset with a cover                                                                                                                         | the API returns it     | `thumbnail_url` is set like for images (the API used to return null for models)                                                                                                                             |
| AC4 (negative) | not a GLB, a broken header or chunk, out-of-range accessors or buffer views, no triangles, an external buffer, or a required extension we do not read (e.g. Draco, meshopt) | the job runs           | the version becomes `failed` with reason `UNREADABLE_MODEL`; nothing is rendered                                                                                                                            |
| AC5 (limits)   | more than 2,000,000 triangles or a JSON chunk above 16 MB                                                                                                                   | the job runs           | the version becomes `failed` with reason `MODEL_TOO_LARGE` before any geometry is decoded                                                                                                                   |
| AC6 (backfill) | model versions that became `ready` before this change (without a preview)                                                                                                   | the migration runs     | they go back to `processing` with their job re-queued, so they get a preview                                                                                                                                |
| AC7            | a model failed with either reason                                                                                                                                           | the gallery shows it   | a readable reason in English and Vietnamese                                                                                                                                                                 |

## Non-functional

- Security (A03/A04/A08): the GLB is untrusted input — every length, offset, count, stride, component type and index is checked against the buffers before use; no external URIs are ever fetched; JSON is parsed with the standard library and size-capped; no code paths run model-provided content.
- Performance (measured on an M-series laptop): a 1,000,000-triangle model renders in about 1 s; the worst case — 2,000,000 large, overlapping random triangles — takes about 15 s and peaks at about 580 MB (file, triangles and view each ~50–70 MB in float32; shading and drawing go 65,536 triangles at a time). Peak memory is bounded by the triangle limit, and KILN-25 recycles a worker whose peak passes 1 GiB. Triangles smaller than a pixel are drawn as points.
- Accessibility: previews are decorative in cards (`alt=""`) and named in the detail, as for images.

## Out of scope

- Textures and materials in previews (shaded neutral grey), Draco/meshopt decompression, `.gltf` with external files, animations and skins (rendered in bind pose), the interactive 3D viewer (KILN-9).

## References

- Khronos glTF 2.0 specification — GLB container, accessors, buffer views, node transforms: https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html
- glTF-Validator (the checks a reader must make on untrusted files): https://github.com/KhronosGroup/glTF-Validator
- Painter's algorithm and flat (Lambert) shading for previews: Foley et al., _Computer Graphics: Principles and Practice_, ch. 15–16.
- `references/security.md` (A03 injection, A04 insecure design: parse untrusted files defensively).

## Design

- `kiln_worker/glb.py`: `read_glb(data) -> Mesh` (float32 positions × 3 per triangle in world space) with explicit limits; errors `UnreadableModelError`, `ModelTooLargeError`.
- `kiln_worker/model_preview.py`: `render_model(mesh) -> bytes` (WebP) — fit, rotate 35° / −25°, orthographic, per-face Lambert shading with a key and fill light, painter's order, 2× supersampling.
- Runner: models download like images (ETag-checked) and render with the above; `FailureReason.UNREADABLE_MODEL`, `MODEL_TOO_LARGE`.
- Migration `0005_model_previews`: failure-reason check gains the two reasons; ready model versions go back to `processing`, their jobs re-queued.
- API: `thumbnail_url` for every kind.

## QA

| AC  | Test(s)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | Result |
| --- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| AC1 | `worker/tests/test_runner.py` "a model gets a rendered preview and becomes the cover"; `worker/tests/test_model_preview.py` "a cube renders as a shaded preview on a transparent background", "a box is seen from above with the top face brightest", "back faces never show through a closed box", "the model is fitted to the frame whatever its size"; `e2e/gallery.spec.ts` "a published glTF model gets a rendered preview in the gallery and the detail" (desktop + mobile, real worker) | pass   |
| AC2 | `worker/tests/test_glb.py` "translation rotation and scale are applied", "a matrix is column major", "nested nodes compose their transforms and meshes can be instanced", "without scenes the root nodes are drawn and without nodes the meshes", "interleaved positions with a stride are read", "every index width is read", "a primitive without indices uses its vertices in order", "points and lines are skipped"                                                                        | pass   |
| AC3 | `api/tests/api/test_processing_api.py` "models expose their previews like images"                                                                                                                                                                                                                                                                                                                                                                                                              | pass   |
| AC4 | `worker/tests/test_glb.py` "broken or unsupported models are refused" (34 variants), "an index past the last vertex is refused", "files that are not well formed glb are refused" (10 variants); `worker/tests/test_model_preview.py` "non finite vertices are dropped and nothing drawable is refused"; `worker/tests/test_runner.py` "unreadable or oversized models fail with a reason", "a model replaced between check and download is not rendered"                                      | pass   |
| AC5 | `worker/tests/test_glb.py` "too many triangles are refused before any geometry is decoded", "instancing counts toward the triangle limit", "a huge json chunk is refused without parsing it", "a very deep node chain is refused"; `worker/tests/test_runner.py` (MODEL_TOO_LARGE)                                                                                                                                                                                                             | pass   |
| AC6 | `api/tests/db/test_migrations.py` "migration 0005 sends ready models back for a preview", "migration 0005 downgrade maps model reasons to one the old check allows"                                                                                                                                                                                                                                                                                                                            | pass   |
| AC7 | `AssetDetail.test.tsx` "explains a model that cannot be previewed"; `locales.test.ts` key parity                                                                                                                                                                                                                                                                                                                                                                                               | pass   |

Gates: `make ci` green (counts in the commit); `make e2e` 14 passed. Measured: 1,000,000 triangles in 1.07 s; 2,000,000 large random triangles in 15.4 s, peak 580 MB (first version peaked at 2 GB — Python lists for every triangle at once; now chunked float32).

Exploratory (looked at the renders): the first camera looked from below (bottom faces visible) and a back face poked through a rotated box (centre-depth sorting); fixed — positive pitch, back faces drawn first — and pinned by an orientation test and a back-face test whose oracle is a render with back faces culled (correct for convex solids).

Mutation checks (timeout-safe runner, each reverted): 13 of 13 killed after two tests were rewritten (the first box test passed with plain depth sorting and with the camera below).

## Review score

| #   | Criterion | Score | Evidence |
| --- | --------- | ----- | -------- |
