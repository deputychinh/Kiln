import '@testing-library/jest-dom/vitest';
import { setProjectAnnotations } from '@storybook/react';

import * as preview from './.storybook/preview';

// Stories rendered in tests get the same decorators and parameters as in Storybook.
setProjectAnnotations([preview]);
