"""Named constants for the worker."""

THUMBNAIL_MAX_SIDE = 512
THUMBNAIL_QUALITY = 82
# Header-declared pixels above these are refused before decoding (decompression bombs).
# Budget: about 256 MB peak per job. Measured peak per pixel: PNG ~4.4 B (full decode), JPEG
# ~0.3 B (decoded at reduced size), WebP up to ~29 B for lossless or animated RGBA (no reduced
# decode), hence 8 MP (worst case measured 234 MB).
MAX_SOURCE_PIXELS_BY_DECODER: dict[str, int] = {
    "PNG": 50_000_000,
    "JPEG": 50_000_000,
    "WEBP": 8_000_000,
}
# Only these decoders ever run on uploaded bytes (GD, PCF and others are never reached).
DECODERS_BY_MEDIA_TYPE: dict[str, tuple[str, ...]] = {
    "image/png": ("PNG",),
    "image/jpeg": ("JPEG",),
    "image/webp": ("WEBP",),
}
# Downloads stay in memory up to this size, then spill to a temporary file.
SPOOL_MAX_BYTES = 16 * 1024 * 1024
IDLE_POLL_SECONDS = 1.0
# Pillow reads a whole WebP into memory (animated files can hold many frames), so WebP sources
# are also capped by file size; a 450 MB animated WebP on a 1 MP canvas peaked at 950 MB.
MAX_SOURCE_BYTES_BY_MEDIA_TYPE: dict[str, int] = {"image/webp": 64 * 1024 * 1024}
# How often a worker asks the database whether a maintenance run is due (KILN-22).
MAINTENANCE_CHECK_SECONDS = 60.0
# Recycling (KILN-25): a fresh process after this many jobs or once peak memory passes this.
WORKER_MAX_JOBS = 200
WORKER_MAX_RSS_MB = 1024  # on Linux the child starts from the supervisor's peak (~65 MB)
# Exit code of a worker process that asks to be replaced (EX_TEMPFAIL).
WORKER_RECYCLE_EXIT_CODE = 75
# Exit code of a worker process ended by its watchdog because a job overran (KILN-28).
WORKER_OVERRAN_EXIT_CODE = 76
# After a stop is asked, a running job gets this long to finish before the process exits.
JOB_STOP_GRACE_SECONDS = 60.0
# At most this long, so a shutdown is bounded (grace + kill margin); a child frozen while it stops
# is killed on lost liveness anyway, whatever the grace (ADR 0010).
JOB_STOP_GRACE_MAX_SECONDS = 120.0
# How often the watchdog looks at the running job.
WATCHDOG_POLL_SECONDS = 0.5
# The supervisor's backstops for a child its own watchdog cannot end (native code holding the
# GIL, a frozen process — the heartbeat stops too, so the lease lapses at least
# lease - heartbeat - slowest extension = 165 s after the freeze, ADR 0010): no sign of life for
# this long while in a job …
SUPERVISOR_LIVENESS_SECONDS = 60.0
# … or still in one job this long past its maximum runtime.
SUPERVISOR_DEADLINE_MARGIN_SECONDS = 5.0
# How long the supervisor waits for a killed child to be reaped before it moves on (a process in
# uninterruptible sleep cannot die until the kernel lets it).
SUPERVISOR_REAP_SECONDS = 10.0
# Internal: the code `Supervisor` uses for a child it killed as stuck (never a real exit code).
WORKER_STUCK_CODE = -1000
# The supervisor kills a child that has not exited this long after its stop grace.
SUPERVISOR_KILL_MARGIN_SECONDS = 10.0
# Restarting a crashed worker waits 1, 2, 4 … s, at most this long.
WORKER_RESTART_BACKOFF_MAX_SECONDS = 30.0
# How often the supervisor checks whether its child exited or a stop was asked.
SUPERVISOR_POLL_SECONDS = 0.2
# A child that ran this long without crashing resets the restart backoff.
WORKER_HEALTHY_UPTIME_SECONDS = 60.0
# Restart delays are spread by up to this fraction so several supervisors do not restart together.
WORKER_RESTART_JITTER = 0.25
# How often a child checks that its supervisor is still alive.
PARENT_CHECK_SECONDS = 1.0
# Model previews (KILN-5): limits checked before any geometry is decoded.
MODEL_MAX_TRIANGLES = 2_000_000
MODEL_MAX_VERTICES = 6_000_000  # summed over the distinct position accessors of every mesh
# Every accessor of the file together (KILN-9: the browser viewer reads them all): up to eight
# attributes per vertex (position, normal, tangent, two UVs, colour, joints, weights) plus indices.
MODEL_MAX_ATTRIBUTES_PER_VERTEX = 8
MODEL_MAX_ACCESSOR_ELEMENTS = (
    MODEL_MAX_ATTRIBUTES_PER_VERTEX * MODEL_MAX_VERTICES + 3 * MODEL_MAX_TRIANGLES
)
MODEL_MAX_BYTES = 256 * 1024 * 1024  # larger .glb files are refused before download
MODEL_MAX_JSON_BYTES = 16 * 1024 * 1024
MODEL_MAX_NODE_DEPTH = 64
MODEL_MAX_INSTANCES = 10_000
# Longest node, mesh, accessor, buffer-view or scene list read from the JSON.
MODEL_MAX_OBJECTS = 100_000
# Drawing stops and the model is refused as too large past this (heavy overdraw).
MODEL_RENDER_SECONDS = 20.0
# Rendering: drawn at twice the size, then downsampled (anti-aliasing).
MODEL_SUPERSAMPLE = 2
MODEL_FILL_RATIO = 0.86
MODEL_YAW_DEGREES = 35.0
MODEL_PITCH_DEGREES = 25.0  # positive tips the top towards the viewer
# Model previews run in a child process (KILN-5): killed past these, the model is too large.
MODEL_SANDBOX_SECONDS = 60.0
MODEL_SANDBOX_MEMORY_BYTES = 2 * 1024 * 1024 * 1024  # address space; enforced on Linux
# The child also limits itself (it may outlive a parent killed mid-render): CPU seconds; it
# checks that the worker is alive every PARENT_CHECK_SECONDS.
MODEL_SANDBOX_CPU_SECONDS = 65
# Temporary model folders older than this are leftovers of a killed worker.
MODEL_SANDBOX_STALE_SECONDS = 15 * 60
