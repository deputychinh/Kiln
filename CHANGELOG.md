# Changelog

Follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and [SemVer](https://semver.org/). One version for every part of the repo; one `v0.x` release per week.

## [Unreleased]

### Added

- Local S3 storage on SeaweedFS (ADR 0003) because MinIO images are no longer published.
- Repository bootstrap: Prettier, EditorConfig, husky + commitlint, Makefile, CI, docs (conventions, testing, ADR 0001–0002, architecture, security, design system, plan, backlog).
- API skeleton: `/health` and `/ready`, RFC 9457 problem details with stable codes, request ids, OpenAPI export.
- Worker skeleton with typed settings.
- Design system package with tokens (dark default, light theme, reduced motion) and `Button`.
- `kiln` CLI skeleton (`--version`, `--help`).
- Web app skeleton: app shell with skip link, API status through generated OpenAPI types, English and Vietnamese copy, Playwright smoke with axe checks.
