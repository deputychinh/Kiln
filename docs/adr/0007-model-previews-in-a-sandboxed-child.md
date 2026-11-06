# ADR 0007: Model previews with an own glTF reader, a CPU renderer and a sandboxed child process

- Status: accepted · 2026-11-06

## Context

KILN-5 previews `.glb` uploads. The files come from anyone with upload rights, so they are untrusted. Common options: a full glTF library (trimesh, pygltflib) plus an OpenGL renderer (pyrender, headless EGL/OSMesa), Blender in background mode, or a small purpose-built reader and a CPU renderer. Four review rounds showed that every bound we added (offsets, counts, budgets, node graphs, chunks, lists, primitives) was followed by a new hostile input class the bounds did not cover.

## Decision

1. **Own reader** (`kiln_worker/glb.py`) for the subset a preview needs: GLB container, embedded buffer, accessors, buffer views, meshes, nodes and scenes. Every length, offset, stride, count and index is checked; budgets come from accessor counts before decoding; the node graph must be a strict tree; any malformed structure is unreadable. No URI is ever fetched; required extensions that change geometry are refused.
2. **CPU renderer** (`kiln_worker/model_preview.py`) with numpy and Pillow: orthographic three-quarter view, flat key-and-fill shading, back faces first then far to near, drawing budget of 20 s. No GPU, no OpenGL stack in the worker image.
3. **Sandbox** (`kiln_worker/sandbox.py`): reading and rendering run in a `spawn`ed child process. The worker kills it after 60 s; the child holds its own 65 s CPU limit, exits when the worker dies, and on Linux has a 2 GiB address space. Exceeding any limit ends as `MODEL_TOO_LARGE`; other crashes are retried as transient. The worker never parses a model itself.

## Consequences

- Hostile inputs nobody has thought of yet are contained by the sandbox, not only by the reader's checks; the reader's checks keep the common hostile cases fast (refused in well under a second).
- macOS does not enforce address-space limits: there only time is bounded. Production runs on Linux.
- Previews ignore textures and materials (neutral grey); Draco and meshopt models are not previewed. Both are follow-ups if studios ask.
- Each model costs a child process start (about 0.1 s); acceptable next to rendering.
- New dependency: numpy (worker only).
- Deployments give the worker a stop grace period of at least 70 s so a render can finish.

## Sources

[glTF 2.0 specification](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html), [glTF-Validator](https://github.com/KhronosGroup/glTF-Validator), `references/security.md` (A03, A04: untrusted file parsing), Python `resource` and `multiprocessing` documentation, docs/stories/KILN-5.md (review rounds).
