"""Read-only adapter for OSAgent Library metadata; no OSAgent runtime dependency."""
from .model import Authority, CatalogError, Document, load_catalog

def adapt_library(raw,root_id='osagent-library'):
    if not isinstance(raw,dict) or not isinstance(raw.get('documents'),list):raise CatalogError('LIBRARY_MANIFEST_INVALID')
    docs=[]
    for row in raw['documents']:
        if not isinstance(row,dict):raise CatalogError('LIBRARY_MANIFEST_INVALID')
        authority=row.get('authority','UNKNOWN')
        if authority=='HISTORICAL_REFERENCE':authority='HISTORICAL'
        if authority not in {x.value for x in Authority}:authority='UNKNOWN'
        d=dict(document_id=row.get('id'),title=row.get('title'),relative_path=row.get('path'),
            content_sha256=row.get('sha256'),source_identity={'system':'osagent-library-manifest',
                'id':str(row.get('id','')),'evidence':row.get('provenance','')},
            source_version=row.get('source_milestone'),document_kind=row.get('kind','UNCLASSIFIED'),
            authority_status=authority,disclosure_status='UNKNOWN',related_document_ids=row.get('related',[]),
            supersedes=[],last_indexed_revision=None,
            authority_evidence='Explicit manifest authority field: '+str(row.get('authority')) if authority!='UNKNOWN' else None)
        docs.append(Document.parse(d).to_dict())
    result={'schema_version':2,'root_id':root_id,'documents':docs,
        'issues':[{'code':'DISCLOSURE_RECONCILIATION_REQUIRED','reason':'Legacy manifest has no revision-bound external disclosure approvals.'}]}
    load_catalog(result)
    return result
