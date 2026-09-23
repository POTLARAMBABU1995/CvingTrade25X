export async function copyText(text: string): Promise<void> {
  const payload = String(text ?? '');
  if (!payload) return;
  if (navigator?.clipboard?.writeText) {
    await navigator.clipboard.writeText(payload);
    return;
  }
  const node = document.createElement('textarea');
  node.value = payload;
  node.setAttribute('readonly', 'true');
  node.style.position = 'fixed';
  node.style.top = '-9999px';
  node.style.left = '-9999px';
  document.body.appendChild(node);
  node.focus();
  node.select();
  const copied = document.execCommand('copy');
  document.body.removeChild(node);
  if (!copied) {
    throw new Error('Clipboard copy is not available in this browser.');
  }
}
