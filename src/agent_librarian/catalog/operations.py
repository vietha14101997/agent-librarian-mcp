"""Deterministic scan, validate and changes. No document writes or external calls."""
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
import uuid
from .filesystem import SafeRoot
from .model import CatalogError, Document, load_catalog, relationship_issues

def scan(root,manifest=None,**limits):
    managed=load_catalog(manifest) if manifest is not None else []
    root_id=manifest['root_id'] if manifest is not None else 'root-'+str(uuid.uuid5(uuid.NAMESPACE_URL,str(Path(root).absolute())))
    with SafeRoot(root,**limits) as fs:files,issues=fs.inventory()
    if manifest is not None:issues=list(manifest.get('issues',[]))+issues
    by_path={d.relative_path:d for d in managed};docs=[]
    for path,h in sorted(files.items()):
        if path in by_path:
            d=by_path[path]
            if d.content_sha256!=h:issues.append({'document_id':d.document_id,'code':'HASH_MISMATCH'})
            docs.append(replace(d,content_sha256=h,last_indexed_revision=h))
        else:
            doc_id='doc-'+str(uuid.uuid5(uuid.NAMESPACE_URL,root_id+':'+path))
            docs.append(Document(doc_id,Path(path).stem,path,h,
                {'system':'local-discovery','id':root_id+':'+path,'evidence':'Path-based discovery identity; no authority evidence'},
                None,'UNCLASSIFIED','UNKNOWN','UNKNOWN',[],[],h))
    for d in managed:
        if d.relative_path not in files:
            issues.append({'document_id':d.document_id,'code':'MISSING_SOURCE'})
            docs.append(d)
    issues+=relationship_issues(docs)
    groups=defaultdict(list)
    for d in docs:groups[d.content_sha256].append(d.document_id)
    return {'schema_version':2,'root_id':root_id,'documents':[d.to_dict() for d in sorted(docs,key=lambda x:x.document_id)],
            'issues':issues,'duplicates':[{'content_sha256':h,'document_ids':ids} for h,ids in sorted(groups.items()) if len(ids)>1]}

def validate(root,catalog):
    docs=load_catalog(catalog);issues=relationship_issues(docs)
    with SafeRoot(root) as fs:
        for d in docs:
            if d.curation_evidence and d.curation_evidence['content_sha256']!=d.content_sha256:
                issues.append({'document_id':d.document_id,'code':'CURATION_REVISION_MISMATCH'})
            try:
                h,_=fs.hash_file(d.relative_path)
                if h!=d.content_sha256:issues.append({'document_id':d.document_id,'code':'HASH_MISMATCH'})
            except CatalogError as e:issues.append({'document_id':d.document_id,'code':e.code})
    # Retain explicit scan-time uncertainty; validation cannot erase a failed scan's evidence.
    issues+=catalog.get('issues',[])
    return {'valid':not issues,'issues':issues,'documents_checked':len(docs)}

def changes(previous,current):
    old={d.document_id:d for d in load_catalog(previous)};new={d.document_id:d for d in load_catalog(current)}
    if previous['root_id']!=current['root_id']:raise CatalogError('ROOT_IDENTITY_MISMATCH')
    result=[]
    for key in sorted(old.keys()|new.keys()):
        a=old.get(key);b=new.get(key)
        status='ADDED' if a is None else 'REMOVED' if b is None else 'MODIFIED' if a.content_sha256!=b.content_sha256 else 'RENAMED' if a.relative_path!=b.relative_path else 'METADATA_CHANGED' if a!=b else 'UNCHANGED'
        if any(isinstance(i,dict) and i.get('document_id')==key and i.get('code')=='MISSING_SOURCE' for i in current.get('issues',[])):
            status='MISSING'
        result.append({'document_id':key,'status':status})
    return {'changes':result,'current_snapshot_has_issues':bool(current.get('issues'))}
