// ════════════════════════════════════════════════════════════════
// Multi-Agent Pipeline Template
// A generalized framework for orchestrating multiple AI agents
// through gated phases with structured output validation.
//
// Runs on the cc-connect Workflow tool.
// Invoke: /workflow run pipeline-template
//
// Architecture:
//   Phase 1: VERIFY  — environment/sanity checks
//   Phase 2: GATE    — data/input quality hard gate
//   Phase 3: EXECUTE — core work (can fan-out to parallel agents)
//   Phase 4: BRIDGE  — cross-validation of outputs
//   Phase 5: OUTPUT  — final deliverable generation
//   Phase 6: RECORD  — archive and handoff
//
// Each phase is an independent agent with:
//   - A specific role/persona
//   - A JSON Schema for structured output
//   - A hard gate: if critical check fails, pipeline ABORTS
// ════════════════════════════════════════════════════════════════

export const meta = {
  name: 'multi-agent-pipeline',
  description: 'Generalized multi-agent pipeline: VERIFY → GATE → EXECUTE → BRIDGE → OUTPUT → RECORD',
  phases: [
    { title: 'VERIFY', detail: 'Check environment and prerequisites' },
    { title: 'GATE', detail: 'Validate input data quality' },
    { title: 'EXECUTE', detail: 'Core analysis by specialized agents' },
    { title: 'BRIDGE', detail: 'Cross-validate and resolve issues' },
    { title: 'OUTPUT', detail: 'Generate final deliverable' },
    { title: 'RECORD', detail: 'Archive results and update handoff' },
  ],
}

// ──────────────────────────────────────────────────────────────
// CONFIGURATION — customize these for your pipeline
// ──────────────────────────────────────────────────────────────

const CONFIG = {
  // Base directory for the project
  baseDir: '/home/ubuntu/claude-workspace',

  // Output directory for intermediate and final artifacts
  outputDir: '/home/ubuntu/claude-workspace/output',

  // Pipeline name (used in log messages and archive filenames)
  name: 'my-pipeline',

  // Maximum warnings allowed before BRIDGE phase blocks
  maxWarnings: 10,
}

// ──────────────────────────────────────────────────────────────
// SCHEMAS — define structured output contracts for each phase
// Customize these to match your domain's data shapes.
// ──────────────────────────────────────────────────────────────

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    env_ready: { type: 'boolean', description: 'Whether all prerequisites are met' },
    checks_passed: { type: 'number', description: 'Number of checks that passed' },
    checks_total: { type: 'number', description: 'Total number of checks run' },
    details: { type: 'string', description: 'Human-readable summary' },
  },
  required: ['env_ready'],
}

const GATE_SCHEMA = {
  type: 'object',
  properties: {
    overall_pass: { type: 'boolean', description: 'Whether all critical checks passed' },
    items_checked: { type: 'number' },
    checks_passed: { type: 'number' },
    checks_failed: { type: 'number' },
    critical_count: { type: 'number' },
    warning_count: { type: 'number' },
    report_path: { type: 'string' },
    summary: { type: 'string' },
  },
  required: ['overall_pass'],
}

const EXECUTE_SCHEMA = {
  type: 'object',
  properties: {
    items_processed: { type: 'number' },
    status: { type: 'string', enum: ['ready', 'partial', 'failed'] },
    output_path: { type: 'string' },
    summary: { type: 'string' },
  },
  required: ['status'],
}

const BRIDGE_SCHEMA = {
  type: 'object',
  properties: {
    can_proceed: { type: 'boolean' },
    total_findings: { type: 'number' },
    critical_count: { type: 'number' },
    warning_count: { type: 'number' },
    resolved_count: { type: 'number' },
    findings_path: { type: 'string' },
    summary: { type: 'string' },
  },
  required: ['can_proceed'],
}

const OUTPUT_SCHEMA = {
  type: 'object',
  properties: {
    output_path: { type: 'string' },
    format: { type: 'string' },
    summary: { type: 'string' },
  },
  required: ['output_path'],
}

const RECORD_SCHEMA = {
  type: 'object',
  properties: {
    archived: { type: 'boolean' },
    handoff_updated: { type: 'boolean' },
    summary_path: { type: 'string' },
    summary: { type: 'string' },
  },
}


// ════════════════════════════════════════════════════════════════
// Phase 1: VERIFY — Environment & Prerequisites Check
// ════════════════════════════════════════════════════════════════
phase('VERIFY')
log(`Phase 1/6: Verifying environment for ${CONFIG.name}...`)

// --- Customize this agent's prompt for your environment ---
const verify = await agent(
  `You are the Environment Verifier for the "${CONFIG.name}" pipeline.

Your job: verify that all prerequisites are met before the pipeline proceeds.

Steps:
1. Check that required services/APIs are reachable
2. Check that necessary files/credentials exist
3. Check that output directories are writable

Perform the checks relevant to your project and return structured JSON.
Only return JSON, no extra text.`,

  { label: '环境验证', phase: 'VERIFY', schema: VERIFY_SCHEMA }
)

if (!verify || !verify.env_ready) {
  log(`ABORTED: Environment not ready — ${verify?.details || 'unknown reason'}`)
  return {
    status: 'ABORTED',
    phase: 'VERIFY',
    reason: verify?.details || 'Environment verification failed',
  }
}

log(`VERIFY OK: ${verify.checks_passed}/${verify.checks_total} checks passed`)


// ════════════════════════════════════════════════════════════════
// Phase 2: GATE — Input Quality Hard Gate
// ════════════════════════════════════════════════════════════════
phase('GATE')
log('Phase 2/6: Running input quality gate...')

// --- Customize this agent's prompt for your data validation ---
const gate = await agent(
  `You are the Data Quality Gatekeeper for the "${CONFIG.name}" pipeline.

Your job: validate all input data/sources before the pipeline proceeds to execution.

Steps:
1. Run your quality validation script/checks
2. Categorize findings: CRITICAL (block) vs WARNING (allow with note)
3. If any CRITICAL failures exist, overall_pass=false

Only return JSON.`,

  { label: '数据质量Gate', phase: 'GATE', schema: GATE_SCHEMA }
)

if (!gate || !gate.overall_pass) {
  const n = gate?.critical_count ?? '?'
  log(`BLOCKED: Gate failed with ${n} CRITICAL issues`)
  return {
    status: 'BLOCKED',
    phase: 'GATE',
    reason: `${n} critical failures — see ${gate?.report_path || 'gate report'}`,
    report_path: gate?.report_path,
  }
}

log(`GATE PASSED: ${gate.items_checked} items, ${gate.checks_passed} passed, ${gate.warning_count} warnings`)


// ════════════════════════════════════════════════════════════════
// Phase 3: EXECUTE — Core Work (can fan out to parallel agents)
// ════════════════════════════════════════════════════════════════
//
// PATTERN A: Single agent (simple tasks)
//   const result = await agent(prompt, { schema: EXECUTE_SCHEMA })
//
// PATTERN B: Parallel agents (multi-dimensional analysis)
//   const results = await parallel([
//     () => agent(dimension1Prompt, { label: 'dim1', phase: 'EXECUTE', schema: DIM_SCHEMA }),
//     () => agent(dimension2Prompt, { label: 'dim2', phase: 'EXECUTE', schema: DIM_SCHEMA }),
//     () => agent(dimension3Prompt, { label: 'dim3', phase: 'EXECUTE', schema: DIM_SCHEMA }),
//   ])
//
// PATTERN C: Pipeline (sequential stages per item)
//   const results = await pipeline(
//     items,
//     item => agent(stage1Prompt(item), { label: `stage1:${item.id}`, phase: 'EXECUTE' }),
//     prev => agent(stage2Prompt(prev), { label: `stage2:${prev.id}`, phase: 'EXECUTE' }),
//   )
//
// Choose the pattern that fits your task.
// ════════════════════════════════════════════════════════════════

phase('EXECUTE')
log('Phase 3/6: Executing core analysis...')

// --- Customize this section for your domain logic ---
const analysis = await agent(
  `You are the Core Analyst for the "${CONFIG.name}" pipeline.

The gate has passed — all input data is validated. Now perform the main analysis.

Steps:
1. Read input data from validated sources
2. Perform your domain-specific analysis/transformation
3. Write intermediate results to ${CONFIG.outputDir}/analysis_result.json
4. Return structured summary

Only return JSON.`,

  { label: '核心分析', phase: 'EXECUTE', schema: EXECUTE_SCHEMA }
)

if (!analysis || analysis.status === 'failed') {
  log('BLOCKED: Analysis failed')
  return {
    status: 'BLOCKED',
    phase: 'EXECUTE',
    reason: analysis?.summary || 'Core analysis returned failed status',
  }
}

log(`EXECUTE OK: ${analysis?.items_processed || 0} items processed, status=${analysis?.status}`)


// ════════════════════════════════════════════════════════════════
// Phase 4: BRIDGE — Cross-Validation & Issue Resolution
// ════════════════════════════════════════════════════════════════
phase('BRIDGE')
log('Phase 4/6: Running cross-validation bridge...')

// --- Customize: verify analysis outputs, retry on transient failures ---
const bridge = await agent(
  `You are the Cross-Validator for the "${CONFIG.name}" pipeline.

Your job: verify the analysis outputs before final deliverable generation.

Steps:
1. Read the analysis results from ${CONFIG.outputDir}/analysis_result.json
2. Cross-check outputs against input data for consistency
3. Identify issues: CRITICAL (must fix) vs WARNING (note in deliverable)
4. Attempt to auto-resolve warnings where possible
5. If CRITICAL issues remain unresolved, set can_proceed=false

Only return JSON.`,

  { label: '交叉验证桥接', phase: 'BRIDGE', schema: BRIDGE_SCHEMA }
)

if (!bridge || !bridge.can_proceed) {
  const n = bridge?.critical_count ?? '?'
  log(`BLOCKED: Bridge found ${n} unresolved CRITICAL issues`)
  return {
    status: 'BLOCKED',
    phase: 'BRIDGE',
    reason: `${n} critical issues unresolved — see ${bridge?.findings_path || 'findings'}`,
    findings_path: bridge?.findings_path,
  }
}

log(`BRIDGE PASSED: ${bridge.total_findings} findings, ${bridge.warning_count} warnings, ${bridge.resolved_count} resolved`)


// ════════════════════════════════════════════════════════════════
// Phase 5: OUTPUT — Final Deliverable Generation
// ════════════════════════════════════════════════════════════════
phase('OUTPUT')
log('Phase 5/6: Generating final deliverable...')

// --- Customize: generate your report, PDF, dashboard, etc. ---
const output = await agent(
  `You are the Deliverable Generator for the "${CONFIG.name}" pipeline.

All validations have passed. Generate the final output.

Steps:
1. Read analysis results: ${CONFIG.outputDir}/analysis_result.json
2. Read bridge findings: ${bridge?.findings_path || 'N/A'}
3. Generate the final deliverable in your desired format
4. Save to ${CONFIG.outputDir}/final_output.md (or .pdf, .html, etc.)
5. Include any quality notes from the bridge phase

Only return JSON.`,

  { label: '产出物生成', phase: 'OUTPUT', schema: OUTPUT_SCHEMA }
)

log(`OUTPUT OK: ${output?.output_path}`)


// ════════════════════════════════════════════════════════════════
// Phase 6: RECORD — Archive & Handoff
// ════════════════════════════════════════════════════════════════
phase('RECORD')
log('Phase 6/6: Archiving results...')

const record = await agent(
  `You are the Archivist for the "${CONFIG.name}" pipeline.

Archive this pipeline run's results for future sessions.

Steps:
1. Write run summary to ${CONFIG.outputDir}/pipeline_run_summary.json:
   {
     "timestamp": "<current ISO time>",
     "pipeline": "${CONFIG.name}",
     "status": "COMPLETED",
     "phases": {
       "verify": { "passed": true },
       "gate": { "items": ${gate?.items_checked}, "passed": ${gate?.checks_passed}, "warnings": ${gate?.warning_count} },
       "execute": { "items_processed": ${analysis?.items_processed || 0} },
       "bridge": { "findings": ${bridge?.total_findings}, "warnings": ${bridge?.warning_count} },
       "output": { "path": "${output?.output_path}" }
     },
     "artifacts": [
       "${CONFIG.outputDir}/analysis_result.json",
       "${CONFIG.outputDir}/final_output.md"
     ]
   }

2. Append a summary line to SESSION_HANDOFF.md so the next session can pick up context

Return JSON.`,

  { label: '归档', phase: 'RECORD', schema: RECORD_SCHEMA }
)

log(`RECORD OK: ${record?.summary}`)


// ════════════════════════════════════════════════════════════════
// Final Result — consumed by the caller or monitoring dashboard
// ════════════════════════════════════════════════════════════════
return {
  status: 'COMPLETED',
  pipeline: CONFIG.name,
  phases_completed: 6,
  gate: {
    items: gate?.items_checked,
    passed: gate?.checks_passed,
    warnings: gate?.warning_count,
  },
  bridge: {
    findings: bridge?.total_findings,
    warnings: bridge?.warning_count,
    resolved: bridge?.resolved_count,
  },
  output_path: output?.output_path,
}
