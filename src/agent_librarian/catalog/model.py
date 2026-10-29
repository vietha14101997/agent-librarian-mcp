"""Provider-independent records. Authority is explicit evidence, never filename inference."""
from dataclasses import asdict, dataclass, replace
from enum import StrEnum
import copy
import json
from pathlib import PurePosixPath
import re

class CatalogError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)

class Kind(StrEnum):
    ORIGINAL='ORIGINAL'
    DERIVATIVE='DERIVATIVE'
    FORMAT_ADAPTER='FORMAT_ADAPTER'
    UNCLASSIFIED='UNCLASSIFIED'

class Authority(StrEnum):
    UNKNOWN='UNKNOWN'
    DESIGN_PROPOSED='DESIGN_PROPOSED'
    DEV_SELECTED='DEV_SELECTED'
    OWNER_APPROVED='OWNER_APPROVED'
    STATIC_ACCEPTED='STATIC_ACCEPTED'
    RUNTIME_VERIFIED='RUNTIME_VERIFIED'
    PRODUCTION_INTEGRATED='PRODUCTION_INTEGRATED'
    HISTORICAL='HISTORICAL'

class Disclosure(StrEnum):
    UNKNOWN='UNKNOWN'
    LOCAL_ONLY='LOCAL_ONLY'
    REVIEW_REQUIRED='REVIEW_REQUIRED'
    RECONCILIATION_REQUIRED='RECONCILIATION_REQUIRED'
    OWNER_APPROVED_FOR_EXTERNAL='OWNER_APPROVED_FOR_EXTERNAL'

class Curation(StrEnum):
    UNKNOWN='UNKNOWN'
    CANDIDATE='CANDIDATE'
    REVIEW_REQUIRED='REVIEW_REQUIRED'
    ACCEPTED_FOR_RESEARCH='ACCEPTED_FOR_RESEARCH'
    REJECTED='REJECTED'

def relative_path(value):
    if not isinstance(value,str) or not value or '\\' in value or '\x00' in value:
        raise CatalogError('PATH_INVALID')
    parts=value.split('/')
    if PurePosixPath(value).is_absolute() or any(x in ('','.', '..') for x in parts):
        raise CatalogError('PATH_TRAVERSAL')
    return value

def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}',value):
        raise CatalogError('IDENTITY_INVALID')
    return value

def digest(value):
    if not isinstance(value,str) or not re.fullmatch('[a-f0-9]{64}',value):
        raise CatalogError('HASH_INVALID')
    return value

def strict_json(raw):
    def pairs(items):
        out={}
        for k,v in items:
            if k in out:raise CatalogError('DUPLICATE_JSON_KEY')
            out[k]=v
        return out
    def bad(_):raise CatalogError('MALFORMED_MANIFEST')
    try:return json.loads(raw,object_pairs_hook=pairs,parse_constant=bad)
    except (ValueError,UnicodeError,RecursionError) as e:
        if isinstance(e,CatalogError):raise
        raise CatalogError('MALFORMED_MANIFEST') from None

@dataclass(frozen=True)
class Document:
    document_id: str
    title: str
    relative_path: str
    content_sha256: str
    source_identity: dict
    source_version: str | None
    document_kind: str
    authority_status: str
    disclosure_status: str
    related_document_ids: list[str]
    supersedes: list[str]
    last_indexed_revision: str | None
    authority_evidence: str | None = None
    curation_status: str = 'UNKNOWN'
    curation_evidence: dict | None = None

    @classmethod
    def parse(cls,raw):
        if not isinstance(raw,dict):raise CatalogError('DOCUMENT_INVALID')
        try:d=cls(**raw)
        except TypeError:raise CatalogError('DOCUMENT_FIELDS_INVALID') from None
        identifier(d.document_id);relative_path(d.relative_path);digest(d.content_sha256)
        if not isinstance(d.title,str) or not d.title.strip() or len(d.title)>512:raise CatalogError('TITLE_INVALID')
        try:Kind(d.document_kind);Authority(d.authority_status);Disclosure(d.disclosure_status);Curation(d.curation_status)
        except (ValueError,TypeError):raise CatalogError('CLASSIFICATION_INVALID') from None
        if not isinstance(d.source_identity,dict) or set(d.source_identity)-{'system','id','evidence','document_id'}:
            raise CatalogError('PROVENANCE_INVALID')
        if not all(isinstance(d.source_identity.get(k),str) and 0<len(d.source_identity[k])<=4096 for k in ('system','id','evidence')):
            raise CatalogError('PROVENANCE_INVALID')
        if 'document_id' in d.source_identity:identifier(d.source_identity['document_id'])
        if d.source_version is not None and (not isinstance(d.source_version,str) or len(d.source_version)>256):raise CatalogError('VERSION_INVALID')
        if d.last_indexed_revision is not None:digest(d.last_indexed_revision)
        if d.authority_status!='UNKNOWN' and (not isinstance(d.authority_evidence,str) or not d.authority_evidence.strip()):
            raise CatalogError('AUTHORITY_EVIDENCE_REQUIRED')
        if d.authority_evidence is not None and (not isinstance(d.authority_evidence,str) or len(d.authority_evidence)>4096):raise CatalogError('AUTHORITY_EVIDENCE_INVALID')
        evidence=d.curation_evidence
        if evidence is not None:
            if not isinstance(evidence,dict) or set(evidence)!={'decision_id','reviewer','content_sha256','provenance','status'}:
                raise CatalogError('CURATION_EVIDENCE_INVALID')
            if not all(isinstance(v,str) and 0<len(v)<=4096 for v in evidence.values()):raise CatalogError('CURATION_EVIDENCE_INVALID')
            identifier(evidence['decision_id']);digest(evidence['content_sha256'])
            if evidence['status']!=d.curation_status:raise CatalogError('CONFLICTING_CURATION_EVIDENCE')
        if d.curation_status=='ACCEPTED_FOR_RESEARCH' and evidence is None:
            raise CatalogError('CURATION_EVIDENCE_REQUIRED')
        for refs in (d.related_document_ids,d.supersedes):
            if not isinstance(refs,list) or len(refs)>1000 or len(refs)!=len(set(identifier(x) for x in refs)):
                raise CatalogError('RELATIONSHIP_INVALID')
        return d

    def to_dict(self):return asdict(self)

def migrate_catalog(raw):
    """Return a validated v2 copy. V1 gains UNKNOWN curation, never acceptance."""
    if not isinstance(raw,dict) or set(raw)-{'schema_version','root_id','documents','issues','duplicates'}:
        raise CatalogError('CATALOG_FIELDS_INVALID')
    if type(raw.get('schema_version')) is not int or raw['schema_version'] not in (1,2) or not isinstance(raw.get('documents'),list) or len(raw['documents'])>1000:
        raise CatalogError('CATALOG_INVALID')
    converted=copy.deepcopy(raw)
    for row in converted['documents']:
        if not isinstance(row,dict):raise CatalogError('DOCUMENT_INVALID')
        if raw['schema_version']==1:
            if 'curation_status' in row or 'curation_evidence' in row:raise CatalogError('AMBIGUOUS_V1_CURATION')
            row.update(curation_status='UNKNOWN',curation_evidence=None)
        elif 'curation_status' not in row or 'curation_evidence' not in row:raise CatalogError('V2_CURATION_FIELDS_REQUIRED')
    converted['schema_version']=2
    _validated_documents(converted)
    return converted

def _validated_documents(raw):
    identifier(raw.get('root_id'))
    docs=[Document.parse(x) for x in raw['documents']]
    ids=[d.document_id for d in docs];paths=[d.relative_path for d in docs]
    if len(set(ids))!=len(ids):raise CatalogError('DUPLICATE_DOCUMENT_ID')
    if len(set(paths))!=len(paths):raise CatalogError('DUPLICATE_DOCUMENT_PATH')
    if not isinstance(raw.get('issues',[]),list):raise CatalogError('CATALOG_INVALID')
    return docs

def load_catalog(raw):return _validated_documents(migrate_catalog(raw))

def relationship_issues(docs):
    known={d.document_id for d in docs};issues=[]
    graph={d.document_id:d.supersedes for d in docs}
    for d in docs:
        refs=d.related_document_ids+d.supersedes
        parent=d.source_identity.get('document_id')
        if parent:refs=refs+[parent]
        if any(r not in known or r==d.document_id for r in refs):
            issues.append({'document_id':d.document_id,'code':'BROKEN_RELATIONSHIP'})
        if d.document_kind=='FORMAT_ADAPTER' and not parent:
            issues.append({'document_id':d.document_id,'code':'SOURCE_IDENTITY_REQUIRED'})
        stack=list(graph.get(d.document_id,[]));seen=set()
        while stack:
            node=stack.pop()
            if node==d.document_id:
                issues.append({'document_id':d.document_id,'code':'SUPERSESSION_CYCLE'});break
            if node not in seen:seen.add(node);stack.extend(graph.get(node,[]))
    return issues
