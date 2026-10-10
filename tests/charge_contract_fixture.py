"""Mock connector inspection; this schema is not a claim about installed tools."""
from datetime import UTC,datetime,timedelta
import json

def mock_charge_contracts(root):
    path=root/'mock-charge-contracts.json'
    description='Mock connector enforces maximum total USD billed for this run.'
    schema={'properties':{'maxTotalChargeUsd':{'type':'number','description':description}}}
    values={}
    for source,actor,tool,rate,start in [('seek','websift/seek-job-scraper','mcp__apify__websift__seek_job_scraper','0.0025','0'),('linkedin','valig/linkedin-jobs-scraper','mcp__apify__valig__linkedin_jobs_scraper','0.002','0.00005')]:
        values[source]={'actor':actor,'tool':tool,'currency':'USD','enforcement':'provider_total_charge_usd','optional_events':[],
            'pricing_evidence':'mock: pricing fixture','enforcement_evidence':'mock: enforced transport ceiling','schema_evidence':'mock: transport schema inspection',
            'inspected_at':datetime.now(UTC).isoformat(),'expires_at':(datetime.now(UTC)+timedelta(days=1)).isoformat(),
            'result_usd':rate,'start_usd':start,'connector_input_schema':schema,'cap_description':description,'charge_cap_argument':'maxTotalChargeUsd'}
    path.write_text(json.dumps(values));return path
