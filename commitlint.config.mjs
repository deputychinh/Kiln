export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    // One scope per deployable or cross-cutting area. Add a scope when a new deployable appears.
    'scope-enum': [
      2,
      'always',
      [
        'repo',
        'plan',
        'backlog',
        'docs',
        'infra',
        'ci',
        'deps',
        'release',
        'web',
        'ui',
        'cli',
        'api',
        'db',
        'worker',
        'blender',
        'ai',
        'e2e',
      ],
    ],
    'scope-empty': [2, 'never'],
    'subject-case': [2, 'always', 'lower-case'],
    'body-max-line-length': [1, 'always', 100],
  },
};
