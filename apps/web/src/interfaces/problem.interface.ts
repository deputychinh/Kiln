/** The fields of an RFC 9457 problem body the web app reads; unknown until checked. */
export interface ProblemBody {
  title?: unknown;
  code?: unknown;
  /** A review conflict's state now (KILN-11, an RFC 9457 extension member). */
  current_state?: unknown;
}
