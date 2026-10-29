/* CLI-only notebook creation and discovery. Never loaded by the research MCP. Fetch/form pattern adapted from upstream
 * core/cdp_transport.py and core/base.py, reviewed commit 8ac9728ec5b128b05077e9d7c4c8bb11b5830c61.
 * Copyright (c) 2025 Jacob Ben David, MIT; see THIRD_PARTY_NOTICES.md.
 * Tokens/cookies are never returned. Apple Events uses an isolated JS world.
 */
(function (input) {
  const reply = value => JSON.stringify(value);
  const fail = code => { throw {librarianCode: code}; };
  const key = '__agentLibrarianRequests';
  try {
    if (location.origin !== 'https://notebook.google.com' || location.pathname !== '/') fail('BRAVE_NOTEBOOK_HOMEPAGE_REQUIRED');
    const pending = globalThis[key] || (globalThis[key] = new Map());
    if (input.action === 'poll') {
      const entry = pending.get(input.id);
      if (!entry) fail('BROWSER_REQUEST_LOST');
      if (!entry.result) return reply({status: 'PENDING'});
      pending.delete(input.id);
      return reply(entry.result);
    }
    if (input.action === 'cancel') {
      const entry = pending.get(input.id);
      if (entry) { entry.controller.abort(); pending.delete(input.id); }
      return reply({status: 'CANCELLED'});
    }
    if (input.action !== 'start' || pending.has(input.id) || pending.size >= 4) fail('BROWSER_REQUEST_REJECTED');
    const r = input.request;
    const rpc = r.kind === 'rpc' && ['wXbhsf', 'CCqFvf'].includes(r.method);
    const stream = false;
    if (!rpc || r.path !== '/') fail('FORBIDDEN_OPERATION');
    const p = r.params;
    if (r.method === 'wXbhsf' && JSON.stringify(p) !== '[null,1,null,[2]]') fail('FORBIDDEN_OPERATION');
    if (r.method === 'CCqFvf' && (!Array.isArray(p) || typeof p[0] !== 'string' || !p[0].trim() || p[0].length > 200 ||
        JSON.stringify(p.slice(1)) !== '[null,null,[2],[1,null,null,null,null,null,null,null,null,null,[1]]]')) fail('FORBIDDEN_OPERATION');
    // Read only reviewed fields in-page, never export script text or page HTML.
    const config = Array.from(document.scripts).map(s => s.textContent || '').filter(s => s.includes('WIZ_global_data')).join('\n');
    const field = name => {
      const values = new Set(Array.from(config.matchAll(new RegExp('"' + name + '"\\s*:\\s*("(?:[^"\\\\]|\\\\.)*")', 'g')), m => JSON.parse(m[1])));
      if (values.size !== 1) fail('BRAVE_PAGE_CONTEXT_UNAVAILABLE');
      const value = values.values().next().value;
      if (typeof value !== 'string' || !value || value.length > 4096) fail('BRAVE_PAGE_CONTEXT_UNAVAILABLE');
      return value;
    };
    if (field('oPEP7c').toLowerCase() !== input.expected_email.toLowerCase()) fail('ACCOUNT_IDENTITY_MISMATCH');
    const csrf = field('SNlM0e'), sid = field('FdrFJe'), build = field('cfb2h');
    if (!/^-?\d{1,64}$/.test(sid) || !/^[A-Za-z0-9_.-]{1,256}$/.test(build)) fail('BRAVE_PAGE_CONTEXT_UNAVAILABLE');
    const url = new URL(rpc ? '/_/LabsTailwindUi/data/batchexecute' : r.method, location.origin);
    const fields = rpc ? {rpcids: r.method, 'source-path': r.path, bl: build, hl: 'en', rt: 'c', 'f.sid': sid} :
      {bl: build, hl: 'en', _reqid: String(input.reqid), rt: 'c', 'f.sid': sid};
    url.search = new URLSearchParams(fields).toString();
    const envelope = rpc ? [[[r.method, JSON.stringify(r.params), null, 'generic']]] : [null, JSON.stringify(r.params)];
    const body = 'f.req=' + encodeURIComponent(JSON.stringify(envelope)) + '&at=' + encodeURIComponent(csrf) + '&';
    const controller = new AbortController();
    const entry = {controller, result: null};
    const responseLimit = stream ? 2097152 : 131072;
    pending.set(input.id, entry);
    (async () => {
      const timer = setTimeout(() => controller.abort(), input.timeout_ms);
      let status = null, total = 0;
      try {
        const response = await fetch(url.href, {method: 'POST', credentials: 'include', redirect: 'error',
          headers: {'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8', 'X-Same-Domain': '1'}, body, signal: controller.signal});
        status = response.status;
        const contentType = (response.headers.get('content-type') || '').split(';')[0].trim();
        if (![200, 401, 403].includes(response.status)) fail('HTTP_STATUS_REJECTED');
        if ([401, 403].includes(response.status)) { entry.result = {status: 'DONE', http_status: response.status, text: ''}; return; }
        if (![401, 403].includes(response.status) && !['application/json', 'application/json+protobuf'].includes(contentType)) fail('HTTP_CONTENT_TYPE_REJECTED');
        const reader = response.body.getReader(), parts = [];
        for (;;) {
          const {done, value} = await reader.read();
          if (done) break;
          total += value.byteLength;
          if (total > responseLimit) { await reader.cancel(); fail('HTTP_RESPONSE_LIMIT'); }
          parts.push(value);
        }
        const bytes = new Uint8Array(total);
        let offset = 0;
        for (const part of parts) { bytes.set(part, offset); offset += part.byteLength; }
        entry.result = {status: 'DONE', http_status: response.status, text: new TextDecoder('utf-8', {fatal: true}).decode(bytes)};
      } catch (error) {
        entry.result = {status: 'ERROR', code: error?.librarianCode || 'BROWSER_OUTCOME_UNKNOWN', http_status: status, bytes_read: total, response_limit: responseLimit};
      } finally { clearTimeout(timer); }
    })();
    return reply({status: 'DISPATCHED'});
  } catch (error) {
    return reply({status: 'ERROR', code: error?.librarianCode || 'BROWSER_CONTEXT_FAILURE'});
  }
})(__LIBRARIAN_INPUT__)
