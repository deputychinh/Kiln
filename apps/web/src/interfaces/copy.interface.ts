export interface Copy {
  app: { name: string; tagline: string; skipToContent: string };
  health: { checking: string; ok: (version: string) => string; down: string; retry: string };
}
