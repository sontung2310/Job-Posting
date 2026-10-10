"""Validate inspected connector contracts before authorizing a paid acquisition."""
from datetime import UTC, datetime
from decimal import Decimal, DecimalException

def checked_contract(contracts, source, actor, tool):
    contract=contracts.get(source)
    if not isinstance(contract,dict):raise ValueError('no verified charge ceiling for '+source)
    expected_tool = 'local_apify' if contract.get('transport') == 'apify-api' else tool
    if contract.get('actor')!=actor or contract.get('tool')!=expected_tool:
        raise ValueError('charge contract actor/connector mismatch')
    if contract.get('currency')!='USD' or contract.get('enforcement')!='provider_total_charge_usd' or contract.get('optional_events')!=[]:
        raise ValueError('charge contract must cover total USD charges with optional events disabled')
    if not contract.get('pricing_evidence') or not contract.get('enforcement_evidence') or not contract.get('schema_evidence'):
        raise ValueError('charge contract requires inspected pricing, enforcement and connector schema evidence')
    expiry=datetime.fromisoformat(contract['expires_at'])
    if expiry.tzinfo is None or expiry<=datetime.now(UTC):raise ValueError('charge contract expired')
    inspected=datetime.fromisoformat(contract['inspected_at'])
    if inspected.tzinfo is None or inspected>datetime.now(UTC) or inspected>=expiry:raise ValueError('invalid inspection date')
    try:rate,start=(Decimal(str(contract[k])) for k in ('result_usd','start_usd'))
    except DecimalException as error:raise ValueError('invalid verified prices') from error
    if any(not n.is_finite() or n<0 for n in (rate,start)) or rate<=0:raise ValueError('invalid verified prices')
    if not isinstance(contract.get('charge_cap_argument'),str) or not contract['charge_cap_argument']:raise ValueError('missing inspected charge-cap argument')
    schema=contract['connector_input_schema']
    for field in contract['charge_cap_argument'].split('.'):
        schema=schema.get('properties',{}).get(field,{})
    if schema.get('type') not in ('number','integer') or schema.get('description')!=contract.get('cap_description') or not contract.get('cap_description'):
        raise ValueError('connector schema does not expose inspected charge-cap argument')
    return contract

def cap_arguments(args,contract,ceiling):
    try:value=Decimal(str(ceiling))
    except DecimalException as error:raise ValueError('invalid paid charge ceiling') from error
    if not value.is_finite() or value<=0:raise ValueError('paid acquisition needs a positive charge ceiling')
    cursor=args
    parts=contract['charge_cap_argument'].split('.')
    for field in parts[:-1]:cursor=cursor.setdefault(field,{})
    cursor[parts[-1]]=float(value)
    return args
