import { en } from '@/locales/en';
import { vi as viCopy } from '@/locales/vi';

const keys = (value: object, prefix = ''): string[] =>
  Object.entries(value).flatMap(([key, child]) =>
    typeof child === 'object' && child !== null
      ? keys(child as object, `${prefix}${key}.`)
      : [`${prefix}${key}`],
  );

describe('locales', () => {
  it('have the same keys in English and Vietnamese', () => {
    expect(keys(viCopy).sort()).toEqual(keys(en).sort());
  });
});
