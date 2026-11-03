// Shared lint rules for every TypeScript workspace (docs/conventions.md).
import js from '@eslint/js';
import eslintReact from '@eslint-react/eslint-plugin';
import { defineConfig, globalIgnores } from 'eslint/config';
import { createTypeScriptImportResolver } from 'eslint-import-resolver-typescript';
import importX from 'eslint-plugin-import-x';
import jsxA11y from 'eslint-plugin-jsx-a11y-x';
import reactHooks from 'eslint-plugin-react-hooks';
import globals from 'globals';
import tseslint from 'typescript-eslint';

const UPPER_SNAKE = '/^[A-Z][A-Z0-9_]*$/';

// Single-source declarations and "arrow functions only, no classes".
const RESTRICTIONS = {
  class: {
    selector: 'ClassDeclaration, ClassExpression',
    message: 'TypeScript code has no classes (docs/conventions.md).',
  },
  functionExpression: {
    selector: 'VariableDeclarator > FunctionExpression',
    message: 'Use an arrow function.',
  },
  enum: {
    selector: 'TSEnumDeclaration',
    message: 'Enums live only in enums/<name>.enum.ts (one enum per file).',
  },
  interface: {
    selector: 'TSInterfaceDeclaration[id.name!=/Props$/]',
    message: 'Shared interfaces live only in interfaces/<name>.interface.ts.',
  },
  typeAlias: {
    selector: 'ExportNamedDeclaration > TSTypeAliasDeclaration',
    message: 'Exported types live only in *.interface.ts files.',
  },
  constant: {
    selector: `ExportNamedDeclaration > VariableDeclaration > VariableDeclarator[id.name=${UPPER_SNAKE}]`,
    message: 'Constants live only in constants/<topic>.constant.ts.',
  },
  tooManyParams: {
    selector: ':function[params.length>3]',
    message: 'Use at most 3 parameters; pass one options object instead.',
  },
};

const restrictAllExcept = (...allowed) => [
  'error',
  ...Object.entries(RESTRICTIONS)
    .filter(([name]) => !allowed.includes(name))
    .map(([, restriction]) => restriction),
];

export default defineConfig(
  globalIgnores([
    '**/node_modules/**',
    '**/dist/**',
    '**/coverage/**',
    '**/storybook-static/**',
    '**/playwright-report/**',
    '**/test-results/**',
    '**/*.gen.ts',
    '**/src/api/*.schema.ts',
    '**/*.mjs',
    '.venv/**',
    'services/**',
    'dcc/**',
  ]),
  js.configs.recommended,
  tseslint.configs.recommendedTypeChecked,
  importX.flatConfigs.recommended,
  importX.flatConfigs.typescript,
  {
    files: ['**/*.tsx'],
    extends: [
      eslintReact.configs['recommended-type-checked'],
      reactHooks.configs.flat.recommended,
      jsxA11y.configs.recommended,
    ],
  },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    settings: {
      'import-x/resolver-next': [
        createTypeScriptImportResolver({
          project: ['apps/*/tsconfig.json', 'packages/*/tsconfig.json'],
        }),
      ],
    },
    rules: {
      'func-style': ['error', 'expression'],
      'prefer-arrow-callback': 'error',
      'no-console': 'error',
      'no-restricted-syntax': restrictAllExcept(),
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            { group: ['../../*'], message: 'Use the @/ alias instead of deep relatives.' },
          ],
        },
      ],
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-non-null-assertion': 'error',
      '@typescript-eslint/no-floating-promises': 'error',
      '@typescript-eslint/explicit-module-boundary-types': 'error',
      '@typescript-eslint/consistent-type-definitions': ['error', 'interface'],
      '@typescript-eslint/consistent-type-imports': 'error',
      'import-x/no-cycle': 'error',
      'import-x/no-unresolved': 'off',
      'import-x/order': [
        'error',
        {
          groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
          pathGroups: [{ pattern: '@/**', group: 'internal' }],
          'newlines-between': 'always',
          alphabetize: { order: 'asc', caseInsensitive: true },
        },
      ],
      'max-lines': ['error', { max: 300, skipBlankLines: true, skipComments: true }],
    },
  },
  { files: ['**/*.enum.ts'], rules: { 'no-restricted-syntax': restrictAllExcept('enum') } },
  {
    files: ['**/*.interface.ts'],
    rules: { 'no-restricted-syntax': restrictAllExcept('interface', 'typeAlias') },
  },
  { files: ['**/*.constant.ts'], rules: { 'no-restricted-syntax': restrictAllExcept('constant') } },
  {
    // TanStack Router file routes export `Route`; the CLI entry writes to the terminal.
    files: ['apps/web/src/routes/**/*.tsx'],
    rules: { 'no-restricted-syntax': restrictAllExcept('constant') },
  },
  { files: ['packages/cli/src/**/*.ts'], rules: { 'no-console': 'off' } },
  {
    // Router type registration is a module augmentation next to the router it registers.
    files: ['apps/web/src/main.tsx'],
    rules: { 'no-restricted-syntax': restrictAllExcept('interface') },
  },
  {
    files: ['**/*.test.{ts,tsx}', '**/vitest.*.ts', '**/e2e/**/*.ts', '**/*.config.ts'],
    rules: { 'max-lines': 'off', '@typescript-eslint/no-non-null-assertion': 'off' },
  },
);
