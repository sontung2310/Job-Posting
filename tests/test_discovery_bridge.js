// Saved connector boundary: this test never invokes a shell or paid tool.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const driver = fs.readFileSync(require('node:path').join(__dirname, '../.agents/skills/job-retrieval/scripts/discovery_bridge.js'), 'utf8');

async function fixture(next, transportFailure) {
  const commands = [], calls = [], output = [];
  const context = {
    load: () => ({runId:'fixture', cwd:'/portable/job-search', preflightDone:true, smoke:true, platform:'linkedin', title:'AI Engineer', location:'Melbourne', lookbackHours:48, chargeContracts:'/private/inspected.json', chargeLimitUsd:'0.006'}),
    store: () => {}, notify: () => {}, text: x => output.push(x),
    tools: {
      exec_command: async options => {
        commands.push(options);
        if (options.cmd.includes('apify_transport.py submit') && transportFailure) return {exit_code:1,output:JSON.stringify(transportFailure)};
        if (options.cmd.includes('apify_transport.py submit')) return {exit_code:0,output:JSON.stringify({structuredContent:{runId:'capped'}})};
        if (options.cmd.includes('seek_details.py')) return {exit_code:0,output:JSON.stringify({structuredContent:{url:'https://www.seek.com.au/job/1',error:'blocked'}})};
        const command = options.cmd.match(/discovery.py (\w+)/)?.[1];
        const responses = {init:{status:'initialized', search_count:1}, next, accept:{phase:'poll'}, status:{status:'in_progress',remaining:1,terminal:false,blocked:0},finish:{status:'completed'}};
        return {exit_code:0,output:JSON.stringify(responses[command])};
      },
      actor: async args => { calls.push(args); return {structuredContent:{runId:'saved-actor'}}; },
    },
  };
  const result = await vm.runInNewContext(driver, context);
  assert.equal(commands.every(x => x.workdir === '/portable/job-search'), true);
  assert.equal(commands[0].cmd,'./.venv/bin/python scripts/readiness.py --mode discovery');
  assert.match(commands[1].cmd, /--platform 'linkedin'/);
  assert.match(commands[1].cmd, /--lookback-hours '48'/);
  assert.match(commands[1].cmd, /--charge-contracts '\/private\/inspected.json'/);
  assert.match(commands[1].cmd, /--charge-limit-usd '0.006'/);
  assert.equal(commands.filter(x => /discovery.py next /.test(x.cmd)).length,1);
  assert.equal(output.length,1);
  return {result, calls, commands};
}
(async () => {
  const batch = await fixture({requests:[{id:'request1',tool:'actor',args:{maxResults:3,maxTotalChargeUsd:0.006}}],blocked:0,terminal:false});
  assert.equal(batch.calls.length,1);
  assert.equal(batch.calls[0].maxTotalChargeUsd,0.006);
  assert.equal(batch.result.status,'in_progress');
  const backoff = await fixture({requests:[],blocked:0,terminal:false,retry_after_seconds:120});
  assert.equal(backoff.calls.length,0);
  assert.equal(backoff.result.status,'in_progress');
  const capped = await fixture({requests:[{id:'capped',tool:'local_apify',args:{actor:'bovi/seek-jobs-scraper',input:{maxItems:1},maxTotalChargeUsd:0.0027}}],terminal:false});
  assert.equal(capped.calls.length,0);
  assert.equal(capped.commands.filter(x => x.cmd.includes('apify_transport.py submit')).length,1);
  for (const submission_outcome of ['not_submitted', 'submission_unknown', 'confirmed_run']) {
    const failed = await fixture({requests:[{id:'failed', tool:'local_apify', args:{}}], terminal:false},
      {error:'fixture failure', submission_outcome, run_id:submission_outcome === 'confirmed_run' ? 'known' : null});
    const accepted = failed.commands.find(x => /discovery.py accept /.test(x.cmd));
    assert.match(accepted.cmd, new RegExp('\"submission_outcome\":\"' + submission_outcome + '\"'));
    assert.equal(failed.commands.filter(x => x.cmd.includes('apify_transport.py submit')).length, 1);
  }
  const detail = await fixture({requests:[{id:'detail',tool:'local_seek_detail',args:{url:'https://www.seek.com.au/job/1'}}],terminal:false});
  assert.equal(detail.commands.filter(x => x.cmd.includes('seek_details.py')).length,1);
  const inspection = await fixture({requests:[{id:'inspect',tool:'inspect_seek_description',args:{url:'https://www.seek.com.au/job/1'}}],terminal:false});
  assert.equal(inspection.calls.length,0);
  assert.equal(inspection.result.inspections[0].id,'inspect');
  assert.equal(inspection.commands.filter(x => /discovery.py accept /.test(x.cmd)).length,0);
  console.log('Discovery bridge fixture checks passed');
})().catch(error => { console.error(error); process.exitCode=1; });
