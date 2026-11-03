# Plan

A phase ends when `make ci` and `make e2e` are green, docs are updated, commits are on `main` and pushed, and (from phase 1) the release is tagged. One release per week.

| Phase | Release | Goal                      | Acceptance                                                                                                                                                                                                          |
| ----- | ------- | ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0     | –       | Bootstrap                 | `make ci` green; commitlint rejects a bad message; README, CHANGELOG, ADR 0001–0002, architecture, security and design-system docs exist; web shows the API status end to end                                       |
| 1     | v0.1    | Upload and gallery        | Upload images/`.glb` through presigned URLs; the worker makes thumbnails; gallery with all four states and cursor pagination; Storybook for every component; e2e upload → thumbnail visible on the production build |
| 2     | v0.2    | Review                    | Sign-in and access tokens; asset versions; side-by-side compare; 3D viewer (react-three-fiber); region annotations; comments; `in_review → approved / changes_requested`; e2e approval journey                      |
| 3     | v0.3    | AI + DCC                  | Worker asks Claude for tags + descriptions (accepted by a person); naming-convention lint; natural-language search → filters; Blender add-on publish; `kiln publish/validate`; tag eval with numbers                |
| 4     | v0.4    | Polish + application pack | UI consistency audit against tokens; axe 0 serious issues; Core Web Vitals met; public Storybook; 2-minute demo video; one-page case study                                                                          |
