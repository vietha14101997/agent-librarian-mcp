/* Incremental framing/projection, mirrored by providers/wire.py. No network API. */
(function () {
  const FRAME=2097152, WIRE=67108864, FRAMES=256;
  const fail=code=>{throw {librarianCode:code};};
  function structure(value) {
    const stack=[[value,0]];let count=0;
    while(stack.length){const [x,d]=stack.pop();if(d>24||++count>100000)fail('PROVIDER_RESPONSE_LIMIT');
      if(Array.isArray(x))for(const y of x)stack.push([y,d+1]);
      else if(x&&typeof x==='object')for(const y of Object.values(x))stack.push([y,d+1]);}
  }
  function compact(data,method) {
    const row=r=>{
      if(!Array.isArray(r)||r.length<3)return r;
      let sources=r[1];
      if(Array.isArray(sources)){
        if(sources.length>1000)fail('PROVIDER_RESPONSE_LIMIT');
        sources=sources.map(s=>{
          if(!Array.isArray(s))return s;
          const out=s.slice(0,4);
          if(Array.isArray(out[2]))out[2]=[null,null,null,null,out[2][4]??null];
          return out;
        });
      }
      return [r[0],sources,r[2]];
    };
    if(method==='rLM1Ne'&&Array.isArray(data)&&data.length===1)return [row(data[0])];
    if(method==='wXbhsf'&&Array.isArray(data)&&data.length===1&&Array.isArray(data[0]))return [data[0].map(row)];
    return data;
  }
  async function project(reader,method) {
    const decoder=new TextDecoder('utf-8',{fatal:true}),encoder=new TextEncoder();
    let pending='',total=0,count=0,first=true,marker=false,seen=0,selected=null,best=-1,bestCitations=-1;
    function line(value){
      if(encoder.encode(value).length>FRAME)fail('HTTP_FRAME_LIMIT');
      value=value.trim();
      if(first){first=false;if(!value.startsWith(")]}'"))fail('PROVIDER_PROTOCOL_ERROR');value=value.slice(4).trim();}
      if(!value)return;
      if(/^\d+$/.test(value)){if(marker||value.length>8)fail('PROVIDER_PROTOCOL_ERROR');marker=true;return;}
      marker=false;if(++count>FRAMES)fail('HTTP_FRAME_COUNT_LIMIT');
      let frame;try{frame=JSON.parse(value);}catch(_){fail('PROVIDER_PROTOCOL_ERROR');}
      structure(frame);if(!Array.isArray(frame))fail('UNIMPLEMENTED_SOURCE_GAP');
      for(const item of frame){
        if(!Array.isArray(item)||item.length<3||item[0]!=='wrb.fr')continue;
        if(item[1]!==method)fail('PROVIDER_RPC_MISMATCH');
        if(item[2]===null||(Array.isArray(item[5])&&item[5].length)){
          const code=item[5]?.[0];
          throw {librarianCode:code===16?'AUTHENTICATION_EXPIRED':Number.isInteger(code)?'GOOGLE_RPC_REJECTED':'PROVIDER_PROTOCOL_ERROR',rpc_error_code:code};
        }
        if(typeof item[2]!=='string')fail('UNIMPLEMENTED_SOURCE_GAP');
        let inner;try{inner=JSON.parse(item[2]);}catch(_){fail('PROVIDER_PROTOCOL_ERROR');}
        structure(inner);
        if(method!==null){if(++seen!==1)fail('UNIMPLEMENTED_SOURCE_GAP');selected=['wrb.fr',method,JSON.stringify(compact(inner,method))];}
        else{
          const row=inner?.[0],info=row?.[4];
          if(!Array.isArray(inner)||!Array.isArray(row)||row.length<5||!Array.isArray(info)||info.length<5)fail('UNIMPLEMENTED_SOURCE_GAP');
          if(info[info.length-1]===1){if(typeof row[0]!=='string')fail('PROVIDER_STRUCTURE_INVALID');const citations=Array.isArray(info[3])?info[3].length:0;
            if(row[0].length>best||(row[0].length===best&&citations>=bestCitations)){selected=item;best=row[0].length;bestCitations=citations;}}
        }
      }
    }
    try{
      for(;;){const {done,value}=await reader.read();if(done)break;
        total+=value.byteLength;if(total>WIRE)fail('HTTP_WIRE_BUDGET_LIMIT');
        pending+=decoder.decode(value,{stream:true});let pos;
        while((pos=pending.indexOf('\n'))>=0){line(pending.slice(0,pos));pending=pending.slice(pos+1);}
        if(encoder.encode(pending).length>FRAME)fail('HTTP_FRAME_LIMIT');
      }
      pending+=decoder.decode();if(pending.trim())line(pending);
      if(marker)fail('HTTP_FRAME_TRUNCATED');if(first)fail('PROVIDER_PROTOCOL_ERROR');if(selected===null)fail('UNIMPLEMENTED_SOURCE_GAP');
      const result=")]}'\n"+JSON.stringify([selected])+'\n';
      if(encoder.encode(result).length>(method==='hizoJc'?FRAME:131072))fail('PROVIDER_PROJECTION_LIMIT');
      return {text:result,bytes_read:total,frames:count};
    }catch(error){await reader.cancel();error.bytes_read=total;error.frames=count;error.frame_limit=FRAME;error.wire_limit=WIRE;throw error;}
  }
  return {project};
})()
