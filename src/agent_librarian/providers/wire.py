"""Bounded incremental consumer framing; discard repeated progress, not final evidence.

The framing/layout is source-derived, not a promise of upstream compatibility.
Budgets bound a frame (2 MiB), traversal, frame count and total wire work separately.
The existing 128-KiB projected research envelope remains independently bounded.
"""
import codecs
import json
from ..gateway.common import Rejected, strict_json

FRAME_BYTES = 2 * 1024 * 1024
WIRE_BYTES = 64 * 1024 * 1024
MAX_FRAMES = 256
SOURCE_CHARS = 1024 * 1024


def frames(chunks):
    decoder = codecs.getincrementaldecoder('utf-8')('strict')
    pending = ''; total = count = 0; first = True; marker = False
    def decode_line(line):
        nonlocal first, count, marker
        line = line.strip()
        if first:
            first = False
            if not line.startswith(")]}'"):raise Rejected('PROVIDER_PROTOCOL_ERROR')
            line = line[4:].strip()
        if not line:return None
        if line.isdigit():
            if marker or len(line)>8:raise Rejected('PROVIDER_PROTOCOL_ERROR')
            marker=True;return None
        marker=False;count+=1
        if count>MAX_FRAMES:raise Rejected('HTTP_FRAME_COUNT_LIMIT')
        try:value=strict_json(line)
        except (ValueError,RecursionError):raise Rejected('PROVIDER_PROTOCOL_ERROR') from None
        structure(value)
        if not isinstance(value,list):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
        return value
    try:
        for chunk in chunks:
            if not isinstance(chunk,bytes):raise Rejected('PROVIDER_PROTOCOL_ERROR')
            total+=len(chunk)
            if total>WIRE_BYTES:raise Rejected('HTTP_WIRE_BUDGET_LIMIT')
            pending+=decoder.decode(chunk)
            while '\n' in pending:
                line,pending=pending.split('\n',1)
                if len(line.encode())>FRAME_BYTES:raise Rejected('HTTP_FRAME_LIMIT')
                value=decode_line(line)
                if value is not None:yield value
            if len(pending.encode())>FRAME_BYTES:raise Rejected('HTTP_FRAME_LIMIT')
        pending+=decoder.decode(b'',final=True)
        if pending.strip():
            value=decode_line(pending)
            if value is not None:yield value
        if marker:raise Rejected('HTTP_FRAME_TRUNCATED')
        if first:raise Rejected('PROVIDER_PROTOCOL_ERROR')
    except UnicodeError:
        error=Rejected('PROVIDER_PROTOCOL_ERROR');error.diagnostics={'bytes_read':total,'frames':count,'frame_limit':FRAME_BYTES,'wire_limit':WIRE_BYTES};raise error from None
    except Rejected as error:
        error.diagnostics={'bytes_read':total,'frames':count,'frame_limit':FRAME_BYTES,'wire_limit':WIRE_BYTES};raise


def structure(value):
    stack=[(value,0)];count=0
    while stack:
        item,depth=stack.pop();count+=1
        if depth>24 or count>100000:raise Rejected('PROVIDER_RESPONSE_LIMIT')
        if isinstance(item,list):stack.extend((x,depth+1) for x in item)
        elif isinstance(item,dict):stack.extend((x,depth+1) for x in item.values())


def compact_rpc(data,method):
    """Retain identity/type/status, dropping unused notebook guides/artifacts."""
    def row(r):
        if not isinstance(r,list) or len(r)<3:return r
        sources=r[1]
        if isinstance(sources,list):
            if len(sources)>1000:raise Rejected('PROVIDER_RESPONSE_LIMIT')
            sources=[s[:4] if isinstance(s,list) else s for s in sources]
            # Only source type is used from the large optional metadata tuple.
            for s in sources:
                if isinstance(s,list) and len(s)>2 and isinstance(s[2],list):
                    s[2]=[None,None,None,None,s[2][4] if len(s[2])>4 else None]
        return [r[0],sources,r[2]]
    if method=='rLM1Ne' and isinstance(data,list) and len(data)==1:return [row(data[0])]
    if method=='wXbhsf' and isinstance(data,list) and len(data)==1 and isinstance(data[0],list):return [[row(r) for r in data[0]]]
    return data


def project_response(chunks,method):
    """Process bounded frames and return only one useful frame across the bridge."""
    selected=None;seen=0;best=-1;best_citations=-1
    for frame in frames(chunks):
        for item in frame:
            if not isinstance(item,list) or len(item)<3 or item[0]!='wrb.fr':continue
            if item[1]!=method:raise Rejected('PROVIDER_RPC_MISMATCH')
            if item[2] is None or len(item)>5 and isinstance(item[5],list) and item[5]:
                code=item[5][0] if len(item)>5 and isinstance(item[5],list) and item[5] else None
                error=Rejected('AUTHENTICATION_EXPIRED' if code==16 else 'GOOGLE_RPC_REJECTED' if type(code) is int else 'PROVIDER_PROTOCOL_ERROR')
                error.diagnostics={'stage':'RPC_ENVELOPE',**({'rpc_error_code':code} if type(code) is int else {})}
                raise error
            if not isinstance(item[2],str):raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
            try:inner=strict_json(item[2])
            except (ValueError,RecursionError):raise Rejected('PROVIDER_PROTOCOL_ERROR') from None
            structure(inner)
            if method is not None:
                seen+=1
                if seen!=1:raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
                selected=['wrb.fr',method,json.dumps(compact_rpc(inner,method),ensure_ascii=False)]
            else:
                if not isinstance(inner,list) or not inner or not isinstance(inner[0],list) or len(inner[0])<5:raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
                row=inner[0];info=row[4]
                if not isinstance(info,list) or len(info)<5:raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
                if type(info[-1]) is int and info[-1]==1:
                    if not isinstance(row[0],str):raise Rejected('PROVIDER_STRUCTURE_INVALID')
                    citations=len(info[3]) if isinstance(info[3],list) else 0
                    if len(row[0])>best or len(row[0])==best and citations>=best_citations:
                        selected=item;best=len(row[0]);best_citations=citations
    if selected is None:raise Rejected('UNIMPLEMENTED_SOURCE_GAP')
    try:result=(")]}'\n"+json.dumps([selected],ensure_ascii=False)+'\n').encode()
    except UnicodeError:raise Rejected('PROVIDER_PROTOCOL_ERROR') from None
    limit=FRAME_BYTES if method=='hizoJc' else 131072
    if len(result)>limit:raise Rejected('PROVIDER_PROJECTION_LIMIT')
    return result
