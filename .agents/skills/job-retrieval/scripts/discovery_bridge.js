// Codex tool bridge. Python generates every request and persists every response.
// Load this file once; await eval(load('stage1_driver')) to run or resume.
(async () => {
  const options = load('stage1_options');
  if (!options?.runId) throw new Error('Set stage1_options.runId before running');
  if (!options.cwd || !String(options.cwd).startsWith('/')) throw new Error('Set stage1_options.cwd to the absolute workspace path');
  const cwd = options.cwd;
  const maxBatches = options.maxBatches ?? 1;
  if (!Number.isInteger(maxBatches) || maxBatches < 1 || maxBatches > 3) throw new Error('maxBatches must be between 1 and 3; supervise and resume each batch');
  const quote = x => "'" + String(x).replace(/'/g, "'\\''") + "'";
  const base = './.venv/bin/python .agents/skills/job-retrieval/scripts/discovery.py';
  let common = ' --run-id ' + quote(options.runId);
  if (options.stateRoot !== undefined) common += ' --state-root ' + quote(options.stateRoot);
  if (options.cacheRoot !== undefined) common += ' --cache-root ' + quote(options.cacheRoot);
  async function shell(cmd) {
    let r = await tools.exec_command({cmd, workdir:cwd, yield_time_ms:1000, max_output_tokens:20000});
    let output = r.output;
    while (r.session_id) {
      r = await tools.write_stdin({session_id:r.session_id, chars:'', yield_time_ms:1000, max_output_tokens:20000});
      output += r.output;
    }
    if (r.exit_code !== 0) {
      const error = new Error('Stage 1 command failed: ' + output);
      error.commandOutput = output;
      throw error;
    }
    return output;
  }
  async function cli(command, extra = '', response) {
    let cmd = base + ' ' + command + common + extra;
    if (response !== undefined) {
      // Compact JSON cannot contain a standalone heredoc terminator.
      cmd += " <<'STAGE1_RESPONSE_JSON'\n" + JSON.stringify(response) + '\nSTAGE1_RESPONSE_JSON';
    }
    return JSON.parse(await shell(cmd));
  }
  // The launcher reuses verified fingerprinted readiness; a bare skip flag is not evidence.
  notify({stage1:'checking_prerequisites'});
  await shell('./.venv/bin/python scripts/readiness.py --mode discovery');
  let extra = options.smoke ? ' --smoke' : '';
  if (options.acquisition) extra += ' --acquisition';
  if (options.chargeContracts !== undefined) extra += ' --charge-contracts ' + quote(options.chargeContracts);
  if (options.chargeLimitUsd !== undefined) extra += ' --charge-limit-usd ' + quote(options.chargeLimitUsd);
  if (options.lookbackHours !== undefined) extra += ' --lookback-hours ' + quote(options.lookbackHours);
  if (options.maxResults !== undefined) extra += ' --max-results ' + quote(options.maxResults);
  for (const key of ['platform', 'title', 'location']) {
    if (options[key] !== undefined) extra += ' --' + key + ' ' + quote(options[key]);
  }
  const initialized = await cli('init', extra);
  notify({stage1: initialized.status, searches:initialized.search_count});
  for (let batch = 0; batch < maxBatches; batch++) {
    const next = await cli('next', ' --limit 3');
    if (next.terminal) {
      const summary = await cli('finish');
      store('stage1_summary', summary);
      text(summary);
      return summary;
    }
    if (!next.requests.length) break; // Return backoff/blocked progress to Codex without sleeping.
    // At most three calls in flight. Each completion is committed immediately.
    const inspections = [];
    const outcomes = await Promise.allSettled(next.requests.map(async request => {
      if (request.tool === 'inspect_seek_description') { inspections.push(request); return; }
      let response;
      try {
        if (request.tool === 'local_seek_detail') {
          response = JSON.parse(await shell("./.venv/bin/python .agents/skills/job-retrieval/scripts/seek_details.py <<'SEEK_DETAIL_JSON'\n" + JSON.stringify(request.args) + '\nSEEK_DETAIL_JSON'));
        } else if (request.tool === 'local_apify') {
          response = JSON.parse(await shell("./.venv/bin/python .agents/skills/job-retrieval/scripts/apify_transport.py submit <<'APIFY_SUBMISSION_JSON'\n" + JSON.stringify(request.args) + '\nAPIFY_SUBMISSION_JSON'));
        } else {
        if (typeof tools[request.tool] !== 'function') throw new Error('Required connector tool unavailable: ' + request.tool);
        response = await tools[request.tool](request.args);
        }
      } catch (error) {
        response = {isError:true, content:[{type:'text',text:String(error)}]};
        if (request.tool === 'local_apify' && error.commandOutput) {
          try {
            const failure = JSON.parse(error.commandOutput);
            if (['not_submitted', 'submission_unknown', 'confirmed_run'].includes(failure.submission_outcome)) {
              response.transportFailure = failure;
            }
          } catch {}
        }
      }
      const saved = await cli('accept', ' --request-id ' + quote(request.id), response);
      notify(saved);
    }));
    const failed = outcomes.find(x => x.status === 'rejected');
    if (failed) throw failed.reason;
    if (inspections.length) {
      const pending = {...await cli('status'), inspections};
      store('stage1_progress', pending); text(pending); return pending;
    }
  }
  const progress = await cli('status');
  if (progress.terminal) {
    const summary = await cli('finish');
    store('stage1_summary', summary);
    text(summary);
    return summary;
  }
  store('stage1_progress', progress);
  text(progress);
  return progress;
})()
