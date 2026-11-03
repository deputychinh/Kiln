import { CommanderError } from 'commander';

import { createProgram } from './program.js';

describe('createProgram', () => {
  it('reports the version with --version', () => {
    const program = createProgram();
    let output = '';
    program.configureOutput({ writeOut: (text) => (output += text) });

    expect(() => program.parse(['--version'], { from: 'user' })).toThrow(CommanderError);
    expect(output.trim()).toBe('0.0.0');
  });

  it('describes itself in the help text', () => {
    expect(createProgram().helpInformation()).toContain('Publish and validate assets');
  });
});
