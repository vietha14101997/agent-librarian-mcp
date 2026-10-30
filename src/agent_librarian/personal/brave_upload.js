/* CLI-only file ingestion. Source-derived protocol; see source_admin.py/notices.
 * Does not expose arbitrary URLs, RPCs, cookies, page context or deletion.
 */
(function(input){
  const reply=x=>JSON.stringify(x),fail=code=>{throw {librarianCode:code};};
  const id=x=>typeof x==='string'&&/^[A-Za-z0-9_-]{1,128}$/.test(x);
  const name=x=>typeof x==='string'&&x.length>0&&x.length<=240&&!/[\x00-\x1f/\\]/.test(x)&&!['.','..'].includes(x);
  const session=value=>{
    const u=new URL(value,location.origin);
    if(u.origin!==location.origin||u.pathname!=='/upload/_/'||u.username||u.password||u.hash||u.href.length>8192)fail('IMPORT_UPLOAD_URL_REJECTED');
    return u.href;
  };
  try{
    if(!['https://notebook.google.com','https://notebooklm.google.com'].includes(location.origin)||location.pathname!=='/')fail('BRAVE_NOTEBOOK_HOMEPAGE_REQUIRED');
    const config=Array.from(document.scripts).map(s=>s.textContent||'').filter(s=>s.includes('WIZ_global_data')).join('\n');
    const field=name=>{
      const values=new Set(Array.from(config.matchAll(new RegExp('"'+name+'"\\s*:\\s*("(?:[^"\\\\]|\\\\.)*")','g')),m=>JSON.parse(m[1])));
      if(values.size!==1)fail('BRAVE_PAGE_CONTEXT_UNAVAILABLE');const value=values.values().next().value;
      if(typeof value!=='string'||!value||value.length>4096)fail('BRAVE_PAGE_CONTEXT_UNAVAILABLE');return value;
    };
    if(typeof input.expected_email!=='string'||field('oPEP7c').toLowerCase()!==input.expected_email.toLowerCase())fail('ACCOUNT_IDENTITY_MISMATCH');
    const pool=globalThis.__agentLibrarianUploads||(globalThis.__agentLibrarianUploads={requests:new Map(),stages:new Map()});
    const pending=pool.requests;
    if(input.action==='poll'){
      const e=pending.get(input.id);if(!e)fail('BROWSER_REQUEST_LOST');
      if(!e.result)return reply({status:'PENDING'});pending.delete(input.id);return reply(e.result);
    }
    if(input.action==='cancel'){
      const e=pending.get(input.id);if(e){e.controller.abort();pending.delete(input.id);}return reply({status:'CANCELLED'});
    }
    if(input.action==='stage'){
      if(!/^[a-f0-9]{32}$/.test(input.id)||!Number.isInteger(input.size)||input.size<=0||input.size>8388608||!Number.isInteger(input.offset)||typeof input.data!=='string'||input.data.length>65536)fail('IMPORT_ARGUMENTS_INVALID');
      if(input.offset===0){pool.stages.clear();pool.stages.set(input.id,{parts:[],size:input.size,received:0});}
      const e=pool.stages.get(input.id);if(!e||e.size!==input.size||e.received!==input.offset)fail('IMPORT_STAGE_INVALID');
      const decoded=atob(input.data),bytes=Uint8Array.from(decoded,c=>c.charCodeAt(0));
      if(!bytes.length||e.received+bytes.length>e.size)fail('IMPORT_STAGE_INVALID');e.parts.push(bytes);e.received+=bytes.length;
      return reply({status:'STAGED',bytes:e.received});
    }
    if(input.action!=='start'||!id(input.notebook_id)||pending.has(input.id)||pending.size>=1)fail('BROWSER_REQUEST_REJECTED');
    let url,body,headers={'x-goog-authuser':'0','Content-Type':'application/x-www-form-urlencoded;charset=UTF-8'};
    if(input.operation==='register'){
      const p=input.params,options=[1,null,null,null,null,null,null,null,null,null,[1]];
      if(!Array.isArray(p)||p.length!==4||!Array.isArray(p[0])||p[0].length!==1||!Array.isArray(p[0][0])||p[0][0].length!==1||!name(p[0][0][0])||p[1]!==input.notebook_id||JSON.stringify(p[2])!=='[2]'||JSON.stringify(p[3])!==JSON.stringify(options))fail('FORBIDDEN_OPERATION');
      url=new URL('/_/LabsTailwindUi/data/batchexecute',location.origin);
      url.search=new URLSearchParams({rpcids:'o4cbdc','source-path':'/notebook/'+input.notebook_id,bl:field('cfb2h'),hl:'en',rt:'c','f.sid':field('FdrFJe')}).toString();
      body='f.req='+encodeURIComponent(JSON.stringify([[['o4cbdc',JSON.stringify(p),null,'generic']]]))+'&at='+encodeURIComponent(field('SNlM0e'))+'&';
      headers['X-Same-Domain']='1';
    }else if(input.operation==='upload_start'){
      if(!name(input.filename)||!id(input.source_id)||!Number.isInteger(input.size)||input.size<=0||input.size>8388608)fail('IMPORT_ARGUMENTS_INVALID');
      url=new URL('/upload/_/?authuser=0',location.origin);
      headers={...headers,'x-goog-upload-command':'start','x-goog-upload-header-content-length':String(input.size),'x-goog-upload-protocol':'resumable'};
      body=JSON.stringify({PROJECT_ID:input.notebook_id,SOURCE_NAME:input.filename,SOURCE_ID:input.source_id});
    }else if(input.operation==='finalize'){
      url=new URL(session(input.upload_url));const staged=pool.stages.get(input.token);
      if(!staged||staged.size!==input.size||staged.received!==input.size)fail('IMPORT_STAGE_INVALID');
      body=new Blob(staged.parts);pool.stages.delete(input.token);
      headers={...headers,'x-goog-upload-command':'upload, finalize','x-goog-upload-offset':'0'};
    }else fail('FORBIDDEN_OPERATION');
    const entry={controller:new AbortController(),result:null};pending.set(input.id,entry);
    (async()=>{
      const timer=setTimeout(()=>entry.controller.abort(),Math.min(30000,input.timeout_ms||30000));
      try{
        const response=await fetch(url.href,{method:'POST',credentials:'include',redirect:'error',headers,body,signal:entry.controller.signal});
        if(response.status===401||response.status===403)fail('AUTHENTICATION_EXPIRED');
        if(response.status<200||response.status>=300)fail('IMPORT_HTTP_REJECTED');
        let text='';const decoder=new TextDecoder('utf-8',{fatal:true}),reader=response.body.getReader();let size=0;
        for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>131072){await reader.cancel();fail('HTTP_RESPONSE_LIMIT');}text+=decoder.decode(value,{stream:true});}text+=decoder.decode();
        if(input.operation==='upload_start'){
          const next=response.headers.get('x-goog-upload-url');if(!next)fail('IMPORT_UPLOAD_URL_MISSING');
          entry.result={status:'DONE',upload_url:session(next)};
        }else entry.result={status:'DONE',text:input.operation==='register'?text:''};
      }catch(error){entry.result={status:'ERROR',code:error?.librarianCode||'IMPORT_OUTCOME_UNKNOWN'};}
      finally{clearTimeout(timer);}
    })();
    return reply({status:'DISPATCHED'});
  }catch(error){return reply({status:'ERROR',code:error?.librarianCode||'IMPORT_OUTCOME_UNKNOWN'});}
})(__LIBRARIAN_INPUT__)
