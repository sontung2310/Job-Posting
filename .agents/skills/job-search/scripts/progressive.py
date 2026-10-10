#!/usr/bin/env python3
"""Durable, sequential acquisition/assessment coordinator; never calls providers."""
from pathlib import Path
import argparse
import fcntl
import time
import json
import sys
from decimal import Decimal, DecimalException
ROOT=Path(__file__).resolve().parents[4]
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'.agents/skills/job-scoring/scripts'),str(ROOT/'.agents/skills/job-retrieval/scripts')]
from private_io import write_private_json
import assessment_validation as validation

SOURCES=('seek','linkedin','indeed')
RATES={'seek':Decimal('0.0025'),'linkedin':Decimal('0.002'),'indeed':Decimal('0')}

def scoring_code_fingerprint():
    return validation.fingerprint([p.read_text() for p in (ROOT/'.agents/skills/job-scoring/scripts/scoring.py',ROOT/'scripts/assessment_validation.py')])

def save(run,state):
    write_private_json(run/'session.json',state)

def initialize(run,queries,config,outcome_cache,lookback=None,capabilities=None,charge_contracts=None,acquisition_cache=None):
    if (run/'session.json').exists():
        existing=json.loads((run/'session.json').read_text())
        if lookback is not None and lookback!=existing['lookback_hours']:
            raise ValueError('continued session cannot change lookback')
        return existing
    from job_sources import load_yaml
    settings=load_yaml(config)
    queries=queries or [{'title':q['title'],'location':city} for q in settings['searches'] for city in q['location']]
    if not queries or any(not q.get('title') or not q.get('location') for q in queries):
        raise ValueError('queries need title and location')
    policy={'batch_size':10,'eligible_target':5,'assessment_limit':None,'budget_usd':'0.50','low_relevance_fraction':0.2,'low_relevance_batches':2,**settings.get('progressive_search',{})}
    if any(type(policy[k]) is not int or policy[k]<1 for k in ('batch_size','eligible_target','low_relevance_batches')) or not Decimal(str(policy['budget_usd'])).is_finite() or Decimal(str(policy['budget_usd']))<=0 or not 0<float(policy['low_relevance_fraction'])<=1:
        raise ValueError('invalid progressive limits')
    if policy['assessment_limit'] is not None and (type(policy['assessment_limit']) is not int or policy['assessment_limit']<1):
        raise ValueError('invalid assessment limit')
    hours=lookback if lookback is not None else settings.get('lookback_hours',24)
    if type(hours) is not int or hours<1:
        raise ValueError('invalid progressive limits')
    maximum=settings.get('max_results_per_search_per_source',100)
    if type(maximum) is not int or maximum<1:raise ValueError('invalid per-search result cap')
    contracts=json.loads(capabilities.read_text()) if capabilities else {}
    if any(s not in SOURCES or not isinstance(c,dict) or c.get('continuation') is not True or not c.get('evidence') for s,c in contracts.items()):
        raise ValueError('continuation contracts need source and inspected evidence')
    scoring_policy={'threshold':settings.get('ats_threshold_exclusive',75),'hybrid_search':settings.get('hybrid_search',True)}
    scoring_policy['code_fingerprint']=scoring_code_fingerprint()
    charge_data=json.loads(charge_contracts.read_text()) if charge_contracts else {}
    state={'search_config':settings,'charge_contracts':charge_data,'charge_contracts_path':str(charge_contracts.resolve()) if charge_contracts else None,'acquisition_cache':str(acquisition_cache.resolve()),'maximum_results':settings.get('max_results_per_search_per_source',100),'scoring_policy':scoring_policy,'capabilities':contracts,'outcome_cache':str(outcome_cache.resolve()),'policy':policy,'enabled_sources':[s for s in SOURCES if settings['sources'].get(s,{}).get('enabled')], 'lookback_hours':hours,'started':time.time(),'duplicates':[], 'cached_buffers':{}, 'query_streaks':{},'version':1,'queries':queries,'source_index':0,'query_positions':dict.fromkeys(SOURCES,0),
           'pending':None,'queue':[],'deferred':[],'recovery_history':[],'admissions':[],'seen':[],'coverage':[],
           'reserved_usd':'0','assessed':0,'eligible':0,'stop_reason':None}
    save(run,state)
    return state

def next_action(run,state):
    if state['scoring_policy']['code_fingerprint']!=scoring_code_fingerprint():raise ValueError('scoring policy changed; new session required')
    if state['stop_reason'] and not state.get('recovery_job_id') and not state.get('recovery_acquisition'):
        return {'action':'report','reason':state['stop_reason']}
    if state['pending']:
        if state['pending']['action']=='reconcile':
            if state.get('recovery_acquisition'):state['source_index']=SOURCES.index(state['pending']['source'])
            state['pending']=None
        else:return state['pending']
    if state['queue']:
        if state['admissions']:
            import assessment
            assessment.load_state(Path(state['admissions'][0]['run']))
        job=state['queue'][0]
        identifier=validation.job_id(job)
        import assessment
        for pointer in Path(state['outcome_cache']).glob(f'{identifier}-*.json'):
            try:
                cached=json.loads(pointer.read_text());origin=Path(cached['run'])
                manifest=assessment.load_state(origin);assessment.require_unchanged_finalized(origin,manifest)
                outcome=json.loads((origin/f'{identifier}-scored.json').read_text())
                if cached.get('scoring_policy')==state['scoring_policy'] and all(manifest[k]==state['scoring_policy'][k] for k in ('threshold','hybrid_search')) and manifest['jobs']==[{'job_id':identifier,'job':job,'units':assessment.job_units(job)}] and validation.fingerprint(outcome)==cached['outcome_fingerprint']:
                    return {'action':'assess','job_id':identifier,'assessment_run':str(origin),'reused':True,'instruction':'Import with assessed; do not rescore.'}
            except (OSError,ValueError,KeyError,TypeError):
                continue
        path=run/'inputs'/f'{identifier}.json'
        write_private_json(path,{'jobs':[job],'coverage':{'status':'partial','progressive':True}})
        return {'action':'assess','job_id':identifier,'input':str(path.resolve()),
                'assessment_run':str((run/'assessments'/identifier).resolve())}
    for _ in range(len(SOURCES)*len(state['queries'])):
        source=SOURCES[state['source_index']]
        state['source_index']=(state['source_index']+1)%3
        if state.get('recovery_acquisition') and source!=state['recovery_acquisition']['source']:continue
        position=state.get('resumed_queries',{}).get(source,state['query_positions'][source])
        if source not in state['enabled_sources'] or position>=len(state['queries']):
            continue
        query=state['queries'][position]
        buffer=state['cached_buffers'].get(f'{source}-{position}')
        if buffer and buffer['raw']:
            count=min(state['policy']['batch_size'],len(buffer['raw']))
            state['pending']={'action':'acquire','source':source,**query,'lookback_hours':state['lookback_hours'],'max_results':count,'acquisition_id':f'{source}-{position}','reservation_usd':'0'}
            base=run/'cached-batches'/f'{source}-{position}'
            cov=dict(buffer['coverage']);cov.update(reused=True,raw_row_count=len(buffer['raw']),acquisition={k:state['pending'][k] for k in ('source','title','location','lookback_hours','max_results')},cached_raw=buffer['raw'])
            write_private_json(base/'jobs.json',buffer['jobs']);write_private_json(base/'coverage.json',cov);write_private_json(base/'relevance.json',buffer['relevance'])
            ingest(run,state,base/'jobs.json',base/'coverage.json',base/'relevance.json')
            return next_action(run,state)
        import discovery
        cap=min(state['policy']['batch_size'],state['maximum_results'],1000 if state['search_config']['sources'][source].get('actor') == 'valig/linkedin-jobs-scraper' else state['maximum_results'])
        cached=discovery.probe_cache(state['search_config'],source,query['title'],query['location'],state['lookback_hours'],Path(state['acquisition_cache']))
        if any(d['target']=='acquisition' and d['source']==source for d in state.get('deferred',[])) and not cached.get('reusable'):
            continue
        if cached.get('requires_reconciliation'):
            state['source_index']=(state['source_index']-1)%3
            state['pending']={'action':'reconcile','source':source,**cached}
            save(run,state);return state['pending']
        if state.get('recovery_acquisition') and not cached.get('reusable'):
            state['pending']={**state['recovery_acquisition']['request'],'query_position':position}
            save(run,state)
            return {'action':'blocked','reason':'terminal_recovery_requires_confirmed_cache',**progress_report(run,state)}
        contract=None
        if source!='indeed' and not cached['reusable']:
            if any(d['target']=='acquisition' and d['failure_kind']=='unknown_submission' and 'reservation_usd' not in d['request'] for d in state.get('deferred',[])):
                continue
            from charge_contract import checked_contract
            try:
                contract=checked_contract(state['charge_contracts'],source,state['search_config']['sources'][source].get('actor'),discovery.ACTOR_TOOLS[state['search_config']['sources'][source]['actor']])
                if contract.get('actor_version')!=state['search_config']['sources'][source].get('actor_version'):raise ValueError('charge contract actor version mismatch')
            except (ValueError,KeyError,TypeError,DecimalException) as error:
                state['coverage'].append({'source':source,**query,'stop_reason':'unverified_charge_ceiling','reason':str(error)})
                state['query_positions'][source]=position+1
                continue
        rate=Decimal(str(contract['result_usd'])) if contract else Decimal(0)
        start=Decimal(str(contract['start_usd'])) if contract else Decimal(0)
        available=Decimal(str(state['policy']['budget_usd']))-Decimal(state['reserved_usd'])-start
        count=min(cap,int(available/rate)) if rate else cap
        if count<1:
            state['coverage'].append({'source':source,**query,'stop_reason':'budget_exhausted'})
            state['query_positions'][source]=position+1
            continue
        reserved=rate*count+start
        state['reserved_usd']=str(Decimal(state['reserved_usd'])+reserved)
        state['pending']={'action':'acquire','source':source,**query,'max_results':count,
                          'query_position':position,'lookback_hours':state['lookback_hours'],'acquisition_id':f'{source}-{position}','reservation_usd':str(reserved),
                          'cache_root':state['acquisition_cache'],'reused':cached['reusable']}
        if contract:
            state['pending'].update(charge_contracts=state['charge_contracts_path'],charge_limit_usd=str(reserved))
        cursor=state.get('cursors',{}).get(f'{source}-{position}')
        if cursor:state['pending']['cursor']=cursor
        save(run,state)
        return state['pending']
    if state.get('deferred'):
        save(run,state)
        return {'action':'blocked','reason':'deferred_work_remaining',**progress_report(run,state)}
    reasons={c.get('stop_reason') for c in state['coverage']}
    state['stop_reason']=('budget_cap' if 'budget_exhausted' in reasons else
                          'coverage_limited' if reasons-{'exhausted'} else 'sources_exhausted')
    save(run,state)
    return next_action(run,state)

def ingest(run,state,handoff,coverage,relevance):
    pending=state['pending']
    if not pending or pending['action']!='acquire':
        raise ValueError('no pending acquisition')
    jobs=json.loads(handoff.read_text())
    if isinstance(jobs,dict): jobs=jobs['jobs']
    cov=json.loads(coverage.read_text()); judgments=json.loads(relevance.read_text())
    acquisition=cov.get('acquisition')
    if not isinstance(acquisition,dict):
        searches=cov.get('searches',[])
        if len(searches)!=1:raise ValueError('coverage needs one matching acquisition')
        acquisition={**searches[0],'max_results':searches[0].get('cap'),'lookback_hours':cov.get('lookback_hours')}
    for field in ('source','title','location','lookback_hours','max_results'):
        if acquisition.get(field)!=pending[field]:raise ValueError('acquisition identity changed: '+field)
    if cov.get('blocked',0)>0 or cov.get('status') in {'unknown','pending','in_progress','blocked_unknown_submission'}:
        raise ValueError('reconcile pending/unknown acquisition before ingestion')
    if not cov.get('reused') and (len(jobs)>pending['max_results'] or cov.get('raw_row_count',0)>pending['max_results']):
        raise ValueError('acquisition exceeds reserved event/result cap')
    if not isinstance(judgments,list) or any(row.get('status') not in {'relevant','irrelevant','uncertain'} or not row.get('reason') for row in judgments):
        raise ValueError('relevance rows need job_id, status and reason')
    if cov.get('reused'):
        raw=cov.get('cached_raw')
        if raw is None:
            raw=json.loads(Path(cov['raw_jobs_path']).read_text()) if cov.get('raw_jobs_path') else jobs
        if len(raw)>pending['max_results']:
            take=raw[:pending['max_results']];rest=raw[pending['max_results']:]
            take_ids={validation.job_id(j) for j in take};rest_ids={validation.job_id(j) for j in rest}
            state['cached_buffers'][pending['acquisition_id']]={'raw':rest,'jobs':[j for j in jobs if validation.job_id(j) in rest_ids],'relevance':[j for j in judgments if j['job_id'] in rest_ids],'coverage':cov}
            jobs=[j for j in jobs if validation.job_id(j) in take_ids];judgments=[j for j in judgments if j['job_id'] in take_ids]
            cov=dict(cov);cov['raw_row_count']=len(take)
        else:
            state['cached_buffers'].pop(pending['acquisition_id'],None)
    mapping={row['job_id']:row for row in judgments}
    if any(validation.job_id(job) not in mapping for job in jobs):
        raise ValueError('every normalized job needs role-family relevance judgment')
    novel=0
    for job in jobs:
        key=validation.job_id(job)
        # Existing conservative source identity; do not merge unrelated employers by title.
        exact=validation.fingerprint({k:job.get(k) for k in ('company','position','location','description_text')})
        previous=[*state['queue'],*[json.loads((Path(a['run'])/'manifest.json').read_text())['jobs'][0]['job'] for a in state['admissions']]]
        duplicate=next((j for j in previous if validation.fingerprint({k:j.get(k) for k in ('company','position','location','description_text')})==exact),None)
        if key in state['seen'] or duplicate:
            state['duplicates'].append({'job':job,'original_job_id':validation.job_id(duplicate) if duplicate else key})
            continue
        state['seen'].append(key)
        if mapping[key]['status']!='irrelevant':
            state['queue'].append(job);novel+=1
    capped=(cov.get('raw_row_count',cov.get('raw_count',len(jobs)))>=pending['max_results'] or bool(cov.get('capped_searches')))
    full=capped and pending['max_results']==state['policy']['batch_size']
    known=[r for r in judgments if r['status']!='uncertain']
    low=full and len(known)==pending['max_results'] and sum(r['status']=='relevant' for r in known)/len(known)<state['policy']['low_relevance_fraction']
    source=pending['source'];position=pending.get('query_position',state['query_positions'][source])
    query_key=f'{source}-{position}'
    streak=state['query_streaks'].get(query_key,0)+1 if low else 0
    state['query_streaks'][query_key]=streak
    incomplete=cov.get('status') not in {None,'complete','completed'} or bool(cov.get('failed_search_ids')) or bool(cov.get('source_failures')) or any(r.get('error_type') for r in cov.get('searches',[]))
    stop=('coverage_incomplete' if incomplete else 'low_relevance' if streak>=state['policy']['low_relevance_batches'] else 'capped_noncontinuable' if capped else 'exhausted')
    if cov.get('reused') is True:
        state['reserved_usd']=str(Decimal(state['reserved_usd'])-Decimal(pending['reservation_usd']))
    state['coverage'].append({'request':pending,'coverage':cov,'relevance':judgments,
                              'novel_assessable':novel,'low_relevance_batch':low,
                              'stop_reason':stop})
    # Published actors have no verified continuation: never rerun a prefix.
    if state['cached_buffers'].get(query_key) and stop!='low_relevance':
        state['coverage'][-1]['stop_reason']='cached_batch_remaining'
    elif state['capabilities'].get(source,{}).get('continuation') is True and cov.get('continuation')=='verified' and cov.get('cursor') and capped and not incomplete and stop!='low_relevance':
        state.setdefault('cursors',{})[query_key]=cov['cursor']
    else:
        state['query_positions'][source]=max(state['query_positions'][source],position+1)
    if cov.get('source_unavailable') is True or any(r.get('error_type') in {'ProviderUsageLimit','ActorDisabled','SourceUnavailable'} for r in cov.get('searches',[])):
        state['query_positions'][source]=len(state['queries'])
        state['coverage'][-1]['stop_reason']='source_unavailable'
    state['pending']=None
    state.pop('recovery_acquisition',None)
    state.get('resumed_queries',{}).pop(source,None)
    save(run,state)
    return {'queued':len(state['queue']),'reserved_usd':state['reserved_usd']}

def accept_assessment(run,state,path):
    import assessment
    if state['stop_reason'] and not state.get('recovery_job_id'):raise ValueError('session stopped; unused jobs cannot be admitted')
    if state['scoring_policy']['code_fingerprint']!=scoring_code_fingerprint():raise ValueError('scoring policy changed; new session required')
    if not state['queue']: raise ValueError('no queued job')
    expected=validation.job_id(state['queue'][0])
    if state.get('recovery_job_id') and state['recovery_job_id']!=expected:raise ValueError('only resumed deferred job may be admitted after session stop')
    manifest=assessment.load_state(path)
    assessment.require_unchanged_finalized(path,manifest)
    if any(manifest[k]!=state['scoring_policy'][k] for k in ('threshold','hybrid_search')):
        raise ValueError('assessment scoring policy differs from session')
    if len(manifest['jobs'])!=1 or manifest['jobs'][0]['job_id']!=expected or manifest['jobs'][0]['job']!=state['queue'][0]:
        raise ValueError('assessment must match queued job exactly')
    outcome=json.loads((path/f'{expected}-scored.json').read_text())
    if outcome['status'] not in {'qualified','below_threshold','condition_failed','evidence_review'}:
        raise ValueError('assessment unfinished')
    if outcome.get('assessment_fingerprint')!=assessment.assessment_fingerprint(path,expected,manifest):
        raise ValueError('assessment provenance changed')
    if outcome['status'] == 'evidence_review':
        result = outcome['result']
        return defer_work(run, state, 'assessment', 'evidence_review',
                          f"Evidence clarification required: score {result['score_range']['lower']}–{result['score_range']['upper']}; unknown requirements {', '.join(result['unknown_requirements'])}", path)
    if state['admissions']:
        prior=json.loads((Path(state['admissions'][0]['run'])/'manifest.json').read_text())
        if any(manifest[k]!=prior[k] for k in ('input_fingerprint','threshold','hybrid_search','resume_lines')):
            raise ValueError('assessment policy/evidence/resumes changed; new session required')
    pointer={'scoring_policy':state['scoring_policy'],'run':str(path.resolve()),'outcome_fingerprint':validation.fingerprint(outcome)}
    write_private_json(Path(state['outcome_cache'])/f'{expected}-{manifest["input_fingerprint"]}.json',pointer)
    state['admissions'].append({'job_id':expected,'run':str(path.resolve()),'outcome_fingerprint':validation.fingerprint(outcome)})
    state['queue'].pop(0);state['assessed']+=1
    state['eligible']+=outcome['status']=='qualified'
    state.pop('recovery_job_id',None)
    if state['eligible']>=state['policy']['eligible_target']: state['stop_reason']='eligible_target'
    elif state['policy'].get('assessment_limit') is not None and state['assessed']==state['policy']['assessment_limit']: state['stop_reason']='assessment_limit'
    save(run,state)
    return {'assessed':state['assessed'],'eligible':state['eligible'],'stop_reason':state['stop_reason']}

def progress_report(run,state):
    deferred=state.get('deferred',[])
    runnable=bool(state['queue'] or state['pending']) or any(state['query_positions'][source]<len(state['queries']) for source in state['enabled_sources'])
    summary={'status':'in_progress' if runnable and not state['stop_reason'] else 'blocked' if deferred else 'stopped','assessed':state['assessed'],
             'eligible':state['eligible'],'stop_reason':state['stop_reason'],
             'reserved_usd':state['reserved_usd'],'actual_billing_usd':None,
             'pending_job_count':len(state['queue'])+sum(d['target']=='assessment' for d in deferred),
             'deferred_job_count':sum(d['target']=='assessment' for d in deferred),
             'deferred_acquisition_count':sum(d['target']=='acquisition' for d in deferred),
             'failed_job_count':sum(d['target']=='assessment' and d['failure_kind']!='evidence_review' for d in deferred),
             'evidence_review_job_count':sum(d['failure_kind']=='evidence_review' for d in deferred),
             'pending_acquisition_count':int(bool(state['pending']))+sum(d['target']=='acquisition' for d in deferred),
             'unused_jobs':len(state['queue'])+sum(len(b['jobs']) for b in state['cached_buffers'].values()),
             'coverage':state['coverage'],'query_positions':state['query_positions']}
    result={'selectable':False,'report_id':None,'summary':summary,'unresolved':deferred,
            'checkpoint':str((run/'session.json').resolve())}
    write_private_json(run/'progress.json',result)
    return result


def defer_work(run,state,target,kind,reason,checkpoint):
    if not reason or not kind or checkpoint is None or not checkpoint.exists():
        raise ValueError('defer requires failure-kind, reason and existing checkpoint')
    if state['stop_reason']:raise ValueError('session stopped; cannot defer work')
    duplicate=next((d for d in state.get('deferred',[]) if d['target']==target and d['checkpoint']==str(checkpoint.resolve()) and d['failure_kind']==kind and d['reason']==reason),None)
    if duplicate:return {'deferred_id':duplicate['deferred_id'],'reserved_usd':state['reserved_usd'],'eligible':state['eligible']}
    if state['scoring_policy']['code_fingerprint']!=scoring_code_fingerprint():
        raise ValueError('scoring policy changed; new session required')
    if target=='assessment':
        if state['pending'] or not state['queue']:raise ValueError('no current assessment to defer')
        if kind not in {'validation_input','dependency_unavailable','evidence_review'}:
            raise ValueError('assessment deferral requires a job-specific failure')
        job=state['queue'][0];identifier=validation.job_id(job)
        entry={'target':target,'job':job,'job_id':identifier}
    else:
        pending=state['pending']
        if not pending or pending['action'] not in {'acquire','reconcile'}:
            raise ValueError('no pending acquisition to defer')
        if kind not in {'dependency_unavailable','source_unavailable','unknown_submission'}:
            raise ValueError('acquisition deferral requires a source-specific failure')
        source=pending['source'];position=state['query_positions'][source]
        entry={'target':target,'source':source,'request':dict(pending),'query_position':position}
        identifier=pending.get('acquisition_id',f'{source}-{position}')
    identifier=f"{target}-{identifier}-{len(state.get('recovery_history',[]))}"
    entry.update(deferred_id=identifier,failure_kind=kind,reason=reason,checkpoint=str(checkpoint.resolve()),deferred_at=time.time())
    if target=='assessment':state['queue'].pop(0)
    else:
        state['pending']=None
        state['query_positions'][source]=position+1
    state.setdefault('deferred',[]).append(entry)
    state.setdefault('recovery_history',[]).append({'event':'deferred',**entry})
    save(run,state)
    return {'deferred_id':identifier,'reserved_usd':state['reserved_usd'],'eligible':state['eligible']}


def resume_work(run,state,identifier):
    if not identifier:raise ValueError('resume requires deferred-id')
    entry=next((d for d in state.get('deferred',[]) if d['deferred_id']==identifier),None)
    if entry is None:raise ValueError('unknown deferred-id')
    if state['scoring_policy']['code_fingerprint']!=scoring_code_fingerprint():
        raise ValueError('scoring policy changed; new session required')
    if (run/'report-assessment'/'report.json').exists():raise ValueError('published report is immutable')
    if state.get('recovery_job_id') or state.get('recovery_acquisition'):raise ValueError('finish current recovery before resuming another')
    if state['pending']:raise ValueError('finish or defer current acquisition before resuming')
    if entry['target']=='assessment':
        state['queue'].insert(0,entry['job'])
        if state['stop_reason']:state['recovery_job_id']=entry['job_id']
    else:
        state['pending']={**entry['request'],'query_position':entry['query_position']}
        if state['stop_reason']:state['recovery_acquisition']=entry
        if state['pending']['action']=='reconcile':
            state.setdefault('resumed_queries',{})[entry['source']]=entry['query_position']
    state['deferred'].remove(entry)
    state.setdefault('recovery_history',[]).append({'event':'resumed','deferred_id':identifier,'resumed_at':time.time()})
    save(run,state)
    return {'resumed':identifier,'reserved_usd':state['reserved_usd']}


def migrate_code(run,state,expected,reason):
    """Explicit repair migration verifies unchanged saved outcomes under current code."""
    import assessment
    import scoring
    if not reason or not expected or expected!=state['scoring_policy']['code_fingerprint']:
        raise ValueError('migrate-code requires reason and matching expected-code-fingerprint')
    if (run/'report-assessment'/'report.json').exists():raise ValueError('published report is immutable')
    for admission in state['admissions']:
        origin=Path(admission['run']);manifest=assessment.load_state(origin)
        assessment.require_unchanged_finalized(origin,manifest)
        if any(manifest[k]!=state['scoring_policy'][k] for k in ('threshold','hybrid_search')):
            raise ValueError('assessment scoring policy differs from session')
        identifier=admission['job_id'];outcome=json.loads((origin/f'{identifier}-scored.json').read_text())
        if validation.fingerprint(outcome)!=admission['outcome_fingerprint']:
            raise ValueError('original outcome changed')
        condition=validation.validate_condition(manifest['jobs'][0]['job'],assessment.current_profile(Path(manifest['vault'])),outcome['condition_review'])
        if outcome['status']=='condition_failed':
            if condition!='failed':raise ValueError('condition semantics changed')
        else:
            reviewed=json.loads((origin/f'{identifier}-reviewed.json').read_text())
            result=scoring.calculate(reviewed,state=origin,vault=Path(manifest['vault']),resumes_dir=Path(manifest['resumes_dir']),pdftotext=manifest['pdftotext'])
            if result!=outcome['result']:raise ValueError('score semantics changed; new session required')
    current=scoring_code_fingerprint()
    state.setdefault('recovery_history',[]).append({'event':'code_migration','previous':expected,'current':current,'reason':reason,'validated_admissions':len(state['admissions']),'migrated_at':time.time()})
    state['scoring_policy']['code_fingerprint']=current
    save(run,state)
    return {'migrated':True,'validated_admissions':len(state['admissions']),'reserved_usd':state['reserved_usd'],'assessed':state['assessed'],'eligible':state['eligible']}


def report(run,state):
    import assessment
    if not state['stop_reason'] or state.get('deferred') or state.get('recovery_job_id') or state.get('recovery_acquisition'):return progress_report(run,state)
    target=run/'report-assessment'
    if not state['admissions']:
        empty=run/'empty.json'
        write_private_json(empty,{'jobs':[],'coverage':{'status':'partial','progressive':True,'session':state}})
        assessment.prepare_run(empty,target,ROOT/'career-vault',ROOT/'resumes',log_root=run/'logs')
        published=json.loads((target/'report.json').read_text())
        published['summary'].update(assessed=0,eligible=0,stop_reason=state['stop_reason'],reserved_usd=state['reserved_usd'],actual_billing_usd=None,coverage=state['coverage'],unused_jobs=0,first_qualifiers_not_exhaustive=True)
        write_private_json(target/'report.json',published)
        annotation=f"\nStop reason: {state['stop_reason']} | Reserved retrieval USD: {state['reserved_usd']} | Actual billing unavailable.\n"
        report_md=target/'report.md'
        if annotation not in report_md.read_text():report_md.write_text(report_md.read_text()+annotation);report_md.chmod(0o600)
        return {'run_handle':str(target.resolve()),**published}
    manifests=[];outcomes=[]
    for admission in state['admissions']:
        origin=Path(admission['run']);manifest=assessment.load_state(origin)
        assessment.require_unchanged_finalized(origin,manifest)
        identifier=admission['job_id'];outcome=json.loads((origin/f'{identifier}-scored.json').read_text())
        if validation.fingerprint(outcome)!=admission['outcome_fingerprint']:
            raise ValueError('original outcome changed')
        manifests.append(manifest);outcomes.append(outcome)
    aggregate=dict(manifests[0]);aggregate['jobs']=[m['jobs'][0] for m in manifests]
    aggregate['prepared']=dict(aggregate['prepared']);aggregate['prepared']['jobs']=[m['prepared']['jobs'][0] for m in manifests]
    aggregate['run_id']=run.name;aggregate['handoff']={'jobs':[m['jobs'][0]['job'] for m in manifests],'coverage':{'status':'partial','progressive':True}}
    aggregate['fingerprint']=validation.fingerprint({'origins':state['admissions'],'stop_reason':state['stop_reason']})
    if (target/'report.json').exists():
        existing=assessment.load_state(target);assessment.require_unchanged_finalized(target,existing)
        if existing['fingerprint']!=aggregate['fingerprint']:raise ValueError('frozen report cannot change')
        published=json.loads((target/'report.json').read_text())
        expected=validation.fingerprint({'manifest':existing['fingerprint'],'candidates':published['candidates'],'unresolved':published['unresolved']})
        if published['report_id']!=expected:raise ValueError('frozen report mapping changed')
        return {'run_handle':str(target.resolve()),**published}
    write_private_json(target/'manifest.json',aggregate)
    for admission,outcome in zip(state['admissions'],outcomes):
        origin=Path(admission['run']);identifier=admission['job_id']
        for artifact in origin.glob(f'{identifier}-*.json'):
            write_private_json(target/artifact.name,json.loads(artifact.read_text()))
        outcome['assessment_fingerprint']=assessment.assessment_fingerprint(target,identifier,aggregate)
        outcome['integrity']=assessment.outcome_integrity(outcome)
        write_private_json(target/f'{identifier}-scored.json',outcome)
    coverage=list(state['coverage'])
    for source in SOURCES:
        for index,query in enumerate(state['queries']):
            if index>=state['query_positions'][source]:
                coverage.append({'source':source,**query,'stop_reason':'disabled' if source not in state['enabled_sources'] else 'unvisited_at_session_stop'})
    precision={}
    for manifest in manifests:
        name=manifest['jobs'][0]['job'].get('freshness_class','legacy_unknown')
        precision[name]=precision.get(name,0)+1
    summary={'freshness_counts':precision,'first_qualifiers_not_exhaustive':True,'status':'partial','assessed':state['assessed'],'eligible':state['eligible'],'stop_reason':state['stop_reason'],
             'reserved_usd':state['reserved_usd'],'actual_billing_usd':None,'unused_jobs':len(state['queue'])+sum(len(b['jobs']) for b in state['cached_buffers'].values()),'coverage':coverage, 'elapsed_seconds':round(time.time()-state['started'],3), 'retained_job_count':len(outcomes),
             'qualified_job_count':state['eligible'], 'below_threshold_job_count':sum(o['status']=='below_threshold' for o in outcomes),
             'condition_failed_count':sum(o['status']=='condition_failed' for o in outcomes),'pending_job_count':0,'failed_job_count':0}
    write_private_json(target/'summary.json',summary)
    write_private_json(target/'results.json',{'jobs':outcomes,'coverage':summary})
    published=assessment.publish_report(target,aggregate,outcomes,summary)
    report_md=target/'report.md'
    annotation='\nFreshness precision: '+json.dumps(precision)+'\nThese are the first qualifying jobs found, not an exhaustive ranking.\n'
    annotation+='\n'.join(f"Candidate {entry['number']}: freshness {entry['job'].get('freshness_class','legacy_unknown')} — {json.dumps(entry['job'].get('freshness_provenance',{}))}" for entry in published['candidates'])+'\n'
    if annotation not in report_md.read_text():
        report_md.write_text(report_md.read_text()+annotation)
        report_md.chmod(0o600)
    return {'candidates':published['candidates'],'report_id':published['report_id'],'run_handle':str(target.resolve()),'selectable':published['selectable'],'summary':summary}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['init','next','ingest','assessed','report','status','progress','defer','resume','migrate-code'])
    parser.add_argument('--run',type=Path,required=True)
    parser.add_argument('--config',type=Path,default=ROOT/'config/search_targets.yaml')
    parser.add_argument('--charge-contracts',type=Path,help='inspected prices and connector-enforced total USD charge ceiling')
    parser.add_argument('--acquisition-cache',type=Path,default=ROOT/'.state/acquisitions')
    parser.add_argument('--capabilities',type=Path,help='inspected provider continuation contracts; default unsupported')
    parser.add_argument('--lookback-hours',type=int)
    parser.add_argument('--outcome-cache',type=Path,default=ROOT/'.state/assessment-cache')
    parser.add_argument('--queries');parser.add_argument('--handoff',type=Path);parser.add_argument('--coverage',type=Path)
    parser.add_argument('--relevance',type=Path);parser.add_argument('--assessment-run',type=Path)
    parser.add_argument('--target',choices=['assessment','acquisition'],default='assessment')
    parser.add_argument('--failure-kind',choices=['validation_input','dependency_unavailable','source_unavailable','unknown_submission','evidence_review'])
    parser.add_argument('--expected-code-fingerprint')
    parser.add_argument('--reason');parser.add_argument('--checkpoint',type=Path);parser.add_argument('--deferred-id')
    args=parser.parse_args()
    if args.command=='ingest' and any(getattr(args,k) is None for k in ('handoff','coverage','relevance')):
        parser.error('ingest requires --handoff, --coverage and --relevance')
    if args.command=='assessed' and args.assessment_run is None:
        parser.error('assessed requires --assessment-run')
    args.run.mkdir(parents=True,exist_ok=True)
    lock=(args.run/'.lock').open('a')
    try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:parser.error('session busy; retry after current command completes')
    try:
        if args.command=='init':result=initialize(args.run,json.loads(args.queries) if args.queries else None,args.config,args.outcome_cache,args.lookback_hours,args.capabilities,args.charge_contracts,args.acquisition_cache)
        else:
            state=json.loads((args.run/'session.json').read_text())
            if args.command=='next':result=next_action(args.run,state)
            elif args.command=='status':result=state
            elif args.command=='progress':result=progress_report(args.run,state)
            elif args.command=='defer':result=defer_work(args.run,state,args.target,args.failure_kind,args.reason,args.checkpoint)
            elif args.command=='resume':result=resume_work(args.run,state,args.deferred_id)
            elif args.command=='migrate-code':result=migrate_code(args.run,state,args.expected_code_fingerprint,args.reason)
            elif args.command=='ingest':result=ingest(args.run,state,args.handoff,args.coverage,args.relevance)
            elif args.command=='assessed':result=accept_assessment(args.run,state,args.assessment_run)
            else:result=report(args.run,state)
        print(json.dumps(result))
    except (OSError,ValueError,KeyError,TypeError,DecimalException) as error:parser.error(str(error))
if __name__=='__main__':main()
