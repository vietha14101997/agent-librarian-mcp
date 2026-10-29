// Execute distributed browser code in a synthetic VM. No real fetch/browser enters it.
const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert');
const root=process.argv[2],source=fs.readFileSync(path.join(root,'src/agent_librarian/personal/brave_upload.js'),'utf8');
const calls=[];
function response(body='',headers={}){const bytes=new TextEncoder().encode(body);let sent=false;return {status:200,headers:{get:key=>headers[key]||null},body:{getReader:()=>({read:async()=>sent?{done:true}:(sent=true,{done:false,value:bytes}),cancel:async()=>{}})}};}
const context={location:{origin:'https://notebook.google.com',pathname:'/'},document:{scripts:[{textContent:'WIZ_global_data = {"oPEP7c":"owner@example.invalid","SNlM0e":"synthetic-token","FdrFJe":"123","cfb2h":"synthetic-build"}'}]},
 URL,URLSearchParams,AbortController,TextDecoder,TextEncoder,Uint8Array,Blob,atob,setTimeout,clearTimeout,
 fetch:async(url,options)=>{calls.push({url,headers:options.headers,body:options.body instanceof Blob?Buffer.from(await options.body.arrayBuffer()).toString():options.body});
 if(options.headers['x-goog-upload-command']==='start')return response('',{'x-goog-upload-url':'https://notebook.google.com/upload/_/?upload_id=SYNTHETIC'});
 return response(")]}'\n"+JSON.stringify([['wrb.fr','o4cbdc',JSON.stringify([[[['source-test']]]])]])+'\n');}};
vm.createContext(context);let sequence=0;
const run=input=>JSON.parse(vm.runInContext(source.replace('__LIBRARIAN_INPUT__',JSON.stringify({expected_email:'owner@example.invalid',notebook_id:'notebook-test',timeout_ms:1000,...input})),context));
async function op(operation,values={}){const id=String(++sequence);assert.equal(run({action:'start',id,operation,...values}).status,'DISPATCHED');for(let i=0;i<20;i++){await new Promise(resolve=>setImmediate(resolve));const r=run({action:'poll',id});if(r.status!=='PENDING')return r;}throw Error('Synthetic request not completed');}
(async()=>{
 const params=[[['notes.md']],'notebook-test',[2],[1,null,null,null,null,null,null,null,null,null,[1]]];
 assert.equal(run({action:'start',id:'bad',operation:'delete'}).code,'FORBIDDEN_OPERATION');
 assert.equal(run({action:'start',id:'bad',operation:'register',params,expected_email:'other@example.invalid'}).code,'ACCOUNT_IDENTITY_MISMATCH');assert.equal(calls.length,0);
 assert.equal((await op('register',{params})).status,'DONE');
 const session=await op('upload_start',{filename:'notes.md',size:4,source_id:'source-test'});assert.equal(session.status,'DONE');
 const token='a'.repeat(32);assert.equal(run({action:'stage',id:token,offset:0,size:4,data:Buffer.from('data').toString('base64')}).status,'STAGED');
 assert.equal(run({action:'start',id:'evil',operation:'finalize',upload_url:'https://attacker.invalid/upload/_/',token,size:4}).code,'IMPORT_UPLOAD_URL_REJECTED');
 assert.equal((await op('finalize',{upload_url:session.upload_url,token,size:4})).status,'DONE');
 assert.equal(calls.length,3);assert.equal(calls[2].body,'data');assert.equal(calls[2].headers['x-goog-upload-offset'],'0');assert.equal(calls[2].headers['x-goog-upload-command'],'upload, finalize');
 assert.equal(calls[1].headers['x-goog-upload-header-content-length'],'4');assert.deepEqual(JSON.parse(calls[1].body),{PROJECT_ID:'notebook-test',SOURCE_NAME:'notes.md',SOURCE_ID:'source-test'});
 assert.deepEqual(JSON.parse(JSON.parse(new URLSearchParams(calls[0].body).get('f.req'))[0][0][1]),params);
 process.stdout.write(JSON.stringify({passed:true,network_calls:calls.length,bytes:calls[2].body.length,arbitrary_url_blocked:true,account_mismatch_blocked:true}));
})().catch(e=>{process.stderr.write(String(e.stack));process.exitCode=1;});
