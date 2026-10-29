"""Revision-bound planning only. This module has no provider execution capability."""
from ..catalog.model import CatalogError, digest, identifier, load_catalog, relationship_issues

ACCEPTED={'OWNER_APPROVED','STATIC_ACCEPTED','RUNTIME_VERIFIED','PRODUCTION_INTEGRATED'}

def sync_plan(catalog,policy):
    docs=load_catalog(catalog)
    keys={'schema_version','account_id','notebooks','mappings','approvals','remote_sources','prior_sync','verified_drive_revisions'}
    if not isinstance(policy,dict) or set(policy)!=keys or type(policy['schema_version']) is not int or policy['schema_version']!=1:
        raise CatalogError('SYNC_POLICY_INVALID')
    account=identifier(policy['account_id'])
    if not isinstance(policy['notebooks'],list) or not policy['notebooks'] or len(policy['notebooks'])>100:
        raise CatalogError('SYNC_POLICY_INVALID')
    allowed=set(identifier(x) for x in policy['notebooks'])
    for field in keys-{'schema_version','account_id','notebooks'}:
        rows=policy[field]
        if not isinstance(rows,list) or len(rows)>1000 or not all(isinstance(r,dict) for r in rows):
            raise CatalogError('SYNC_POLICY_INVALID')
        for row in rows:
            identifier(row.get('document_id'))
            fields={
                'mappings':{'document_id','notebook_id','drive_file_id'},
                'approvals':{'document_id','content_sha256','account_id','notebook_id','approved_for','approval_id','revoked'},
                'remote_sources':{'document_id','account_id','notebook_id','drive_file_id','source_id','revision','status'},
                'prior_sync':{'document_id','account_id','notebook_id','drive_file_id','source_id','content_sha256','status'},
                'verified_drive_revisions':{'document_id','drive_file_id','content_sha256'},
            }[field]
            if set(row)!=fields:raise CatalogError('SYNC_POLICY_ROW_INVALID')
            for key in fields-{'approved_for','revoked'}:
                if not isinstance(row[key],str) or not row[key] or len(row[key])>256:raise CatalogError('SYNC_POLICY_ROW_INVALID')
            if field=='approvals' and (type(row['revoked']) is not bool or not isinstance(row['approved_for'],list)
                    or not all(isinstance(x,str) for x in row['approved_for'])):
                raise CatalogError('SYNC_POLICY_ROW_INVALID')
    def rows(field,doc):return [r for r in policy[field] if r['document_id']==doc]
    result=[]
    catalog_problem=bool(catalog.get('issues') or relationship_issues(docs))
    for doc in docs:
        status='REVIEW_REQUIRED';reason='CATALOG_UNCERTAIN'
        mapping=rows('mappings',doc.document_id);approvals=rows('approvals',doc.document_id)
        remote=rows('remote_sources',doc.document_id);prior=rows('prior_sync',doc.document_id)
        drive=rows('verified_drive_revisions',doc.document_id)
        if catalog_problem:pass
        elif doc.document_kind=='UNCLASSIFIED':reason='UNSUPPORTED_DOCUMENT_TYPE'
        elif doc.authority_status not in ACCEPTED:
            status='BLOCKED_APPROVAL';reason='AUTHORITY_NOT_ELIGIBLE'
        elif doc.disclosure_status!='OWNER_APPROVED_FOR_EXTERNAL':
            status='BLOCKED_APPROVAL';reason='EXTERNAL_DISCLOSURE_NOT_APPROVED'
        elif len(approvals)!=1 or approvals[0].get('revoked') is not False:
            status='BLOCKED_APPROVAL';reason='APPROVAL_ABSENT_AMBIGUOUS_OR_REVOKED'
        elif set(approvals[0].get('approved_for',[]))!={'drive','notebook'} or not isinstance(approvals[0].get('approval_id'),str) or not approvals[0]['approval_id']:
            status='BLOCKED_APPROVAL';reason='DISCLOSURE_SCOPE_MISSING'
        elif approvals[0].get('content_sha256')!=doc.content_sha256:
            status='BLOCKED_REVISION';reason='APPROVAL_REVISION_MISMATCH'
        elif doc.last_indexed_revision!=doc.content_sha256:
            status='BLOCKED_REVISION';reason='INDEX_REVISION_STALE'
        elif len(mapping)!=1:
            status='BLOCKED_IDENTITY';reason='MAPPING_ABSENT_OR_DUPLICATED'
        else:
            m=mapping[0];nb=m.get('notebook_id');fid=m.get('drive_file_id')
            if not isinstance(nb,str) or nb not in allowed or not isinstance(fid,str) or not fid:
                status='BLOCKED_IDENTITY';reason='DESTINATION_NOT_ALLOWED'
            elif approvals[0].get('account_id')!=account or approvals[0].get('notebook_id')!=nb:
                status='BLOCKED_APPROVAL';reason='APPROVAL_DESTINATION_MISMATCH'
            elif sum(r.get('drive_file_id')==fid and r.get('notebook_id')==nb for r in policy['mappings'])!=1:
                status='BLOCKED_IDENTITY';reason='DUPLICATE_DRIVE_MAPPING'
            elif any(r.get('drive_file_id')==fid and r.get('notebook_id')==nb and r.get('account_id')==account and r['document_id']!=doc.document_id for r in policy['remote_sources']):
                status='BLOCKED_IDENTITY';reason='DRIVE_ID_ALREADY_REGISTERED_UNDER_ANOTHER_DOCUMENT'
            elif len(drive)!=1 or drive[0].get('drive_file_id')!=fid or drive[0].get('content_sha256')!=doc.content_sha256:
                status='BLOCKED_REVISION';reason='DRIVE_REVISION_NOT_VERIFIED'
            elif len(remote)>1 or len(prior)>1:
                status='BLOCKED_IDENTITY';reason='DUPLICATE_REMOTE_OR_PRIOR_IDENTITY'
            elif any(r.get('status')!='VERIFIED' for r in remote+prior):
                reason='REMOTE_OUTCOME_UNKNOWN'
            elif any(r.get('account_id')!=account or r.get('notebook_id')!=nb or r.get('drive_file_id')!=fid for r in remote+prior):
                status='BLOCKED_IDENTITY';reason='REMOTE_DESTINATION_MISMATCH'
            elif not remote:
                if prior:reason='STALE_SYNC_REGISTRY'
                else:status='ADD_CANDIDATE';reason='APPROVED_UNREGISTERED_IDENTITY'
            else:
                r=remote[0];sid=r.get('source_id')
                collision=any(x is not r and x.get('source_id')==sid for x in policy['remote_sources'])
                if not isinstance(sid,str) or not sid or collision:
                    status='BLOCKED_IDENTITY';reason='DUPLICATE_OR_MISSING_SOURCE_ID'
                elif not prior or prior[0].get('source_id')!=sid or prior[0].get('content_sha256')!=r.get('revision'):
                    reason='STALE_SYNC_REGISTRY'
                elif r.get('revision')==doc.content_sha256:
                    status='UNCHANGED';reason='MATCHING_VERIFIED_IDENTITIES_AND_REVISION'
                else:
                    try:digest(r.get('revision'))
                    except CatalogError:reason='REMOTE_REVISION_UNKNOWN'
                    else:status='UPDATE_CANDIDATE';reason='EXISTING_SOURCE_NEEDS_APPROVED_REVISION'
        result.append({'document_id':doc.document_id,'action':status,'reason':reason})
    return {'execution_enabled':False,'requires_revalidation_before_future_execution':True,
        'remote_operations':0,'plan':result}
