/** Stable process exit codes; scripts and CI depend on them. */
export enum ExitCode {
  Ok = 0,
  Failure = 1,
  Usage = 2,
}
