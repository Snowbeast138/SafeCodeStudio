export function withWebviewCsp(html: string, nonce: string): string {
  const csp = `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data:; style-src 'nonce-${nonce}'; script-src 'nonce-${nonce}';">`;
  return html.replace('<meta charset=', csp + '<meta charset=')
    .replace('<style>', `<style nonce="${nonce}">`)
    .replaceAll('<script', `<script nonce="${nonce}"`)
    .replace('</html>', `<script nonce="${nonce}">window.addEventListener('message', event => { if (event.data?.type === 'focus' && typeof event.data.id === 'string' && typeof selectFile === 'function') selectFile(event.data.id); });</script></html>`);
}
