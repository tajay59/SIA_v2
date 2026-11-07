fetch('/api/identity/v1/.well-known/jwks.json').then(r => {
    const el = document.getElementById('status');
    el.textContent = r.ok ? 'running' : 'not responding (' + r.status + ')';
    el.className = r.ok ? 'ok' : 'bad';
  }).catch(() => { const el = document.getElementById('status'); el.textContent = 'not responding'; el.className = 'bad'; });
