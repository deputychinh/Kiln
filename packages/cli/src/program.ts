import { Command } from 'commander';

import { CLI_DESCRIPTION, CLI_NAME, CLI_VERSION } from './constants/cli.constant.js';

/** Builds the command tree; `publish` and `validate` arrive in v0.3 (KILN-15). */
export const createProgram = (): Command =>
  new Command(CLI_NAME).description(CLI_DESCRIPTION).version(CLI_VERSION).exitOverride();
