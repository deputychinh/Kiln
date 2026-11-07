/** The hidden file input a picker button opens (`FilePickerButton`), to hand it files in tests. */
export const fileInputOf = (button: HTMLElement): HTMLInputElement => {
  const input = button.parentElement?.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) throw new Error('The button opens no file input');
  return input;
};
