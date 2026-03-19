export function setComposerState(input, btn, enabled, placeholder) {
  if (!input || !btn) return;
  input.disabled = !enabled;
  btn.disabled = !enabled;
  if (placeholder) input.placeholder = placeholder;
}
