// CSS rules from docs/conventions.md: BEM blocks, design tokens only, fixed property order.
const WORD = '[a-z0-9]+(?:-[a-z0-9]+)*';

// Block name from the file name: ProductCard.css → product-card, stack.css → stack.
const toBlockName = (fileName) => fileName.replace(/([a-z0-9])([A-Z])/g, '$1-$2').toLowerCase();

const bemSelector = (fileName) =>
  new RegExp(
    `^\\.${toBlockName(fileName)}(?:__${WORD})?(?:--${WORD})?(?:\\.(?:is|has)-${WORD})*(?:\\[.+\\])?$`,
  );

const TOKEN_PROPERTIES = [
  '/color$/',
  'fill',
  'stroke',
  'z-index',
  'font-family',
  'font-size',
  'font-weight',
  'line-height',
  'border-radius',
  'box-shadow',
  '/^(margin|padding)/',
  '/gap$/',
  'transition-duration',
  'animation-duration',
];

const PROPERTY_GROUPS = [
  ['position', 'inset', 'top', 'right', 'bottom', 'left', 'z-index'],
  [
    'display',
    'flex',
    'flex-direction',
    'flex-wrap',
    'flex-grow',
    'flex-shrink',
    'flex-basis',
    'grid',
    'grid-template-columns',
    'grid-template-rows',
    'grid-template-areas',
    'grid-column',
    'grid-row',
    'gap',
    'row-gap',
    'column-gap',
    'align-items',
    'align-self',
    'justify-content',
    'justify-items',
    'place-items',
    'order',
    'box-sizing',
    'overflow',
    'overflow-x',
    'overflow-y',
    'inline-size',
    'min-inline-size',
    'max-inline-size',
    'block-size',
    'min-block-size',
    'max-block-size',
    'aspect-ratio',
    'margin',
    'margin-inline',
    'margin-block',
    'padding',
    'padding-inline',
    'padding-block',
  ],
  [
    'font',
    'font-family',
    'font-size',
    'font-weight',
    'font-variant-numeric',
    'line-height',
    'letter-spacing',
    'text-align',
    'text-decoration',
    'text-underline-offset',
    'text-transform',
    'white-space',
    'overflow-wrap',
    'color',
    'list-style',
  ],
  [
    'background',
    'background-color',
    'border',
    'border-block-end',
    'border-color',
    'border-radius',
    'outline',
    'outline-offset',
    'box-shadow',
    'opacity',
    'clip-path',
    'cursor',
  ],
  ['transition', 'transition-property', 'transition-duration', 'animation'],
];

export default {
  extends: ['stylelint-config-standard'],
  plugins: [
    'stylelint-order',
    'stylelint-selector-bem-pattern',
    'stylelint-declaration-strict-value',
  ],
  rules: {
    'selector-max-id': 0,
    'declaration-no-important': true,
    'max-nesting-depth': 1,
    'media-feature-range-notation': 'prefix',
    'import-notation': 'string',
    'selector-class-pattern': [
      `^${WORD}(?:__${WORD})?(?:--${WORD})?$`,
      { message: 'Use BEM: block, block__element, block--modifier (docs/conventions.md).' },
    ],
    'order/properties-order': [
      PROPERTY_GROUPS.map((properties) => ({ properties })),
      { unspecified: 'bottomAlphabetical' },
    ],
    'scale-unlimited/declaration-strict-value': [
      TOKEN_PROPERTIES,
      {
        ignoreValues: [
          '0',
          'inherit',
          'initial',
          'unset',
          'transparent',
          'currentcolor',
          'none',
          'auto',
        ],
        disableFix: true,
        message: 'Use a design token (var(--…)) for "${property}" (docs/conventions.md).',
      },
    ],
    'plugin/selector-bem-pattern': {
      componentName: /^[a-zA-Z][a-zA-Z0-9]*(?:-[a-z0-9]+)*$/,
      componentSelectors: bemSelector,
      implicitComponents: [
        '**/src/components/**/*.css',
        '**/src/features/**/*.css',
        '**/src/styles/layout/**/*.css',
      ],
    },
  },
  overrides: [
    {
      files: ['**/src/tokens/**/*.css'],
      rules: {
        'scale-unlimited/declaration-strict-value': null,
        // Token groups are separated by a blank line.
        'custom-property-empty-line-before': null,
      },
    },
    {
      files: [
        '**/src/components/**/*.css',
        '**/src/features/**/*.css',
        'src/styles/layout/**/*.css',
      ],
      rules: { 'selector-max-type': 0 },
    },
  ],
};
