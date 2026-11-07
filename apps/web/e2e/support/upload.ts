import type { FileChooser, Locator, Page } from '@playwright/test';

/** The top bar's Upload button: new assets from any page. */
export const uploadButton = (page: Page): Locator =>
  page.getByRole('banner').getByRole('button', { name: 'Upload', exact: true });

/** Presses a button that opens the system file picker and picks `files`, as a person would. */
export const chooseFiles = async (
  page: Page,
  button: Locator,
  files: Parameters<FileChooser['setFiles']>[0],
): Promise<void> => {
  const chooser = page.waitForEvent('filechooser');
  await button.click();
  await (await chooser).setFiles(files);
};
