#!/usr/bin/env node
import { CommanderError } from 'commander';

import { ExitCode } from './enums/exit-code.enum.js';
import { createProgram } from './program.js';

try {
  await createProgram().parseAsync(process.argv);
} catch (error) {
  process.exitCode = error instanceof CommanderError ? error.exitCode : ExitCode.Failure;
}
