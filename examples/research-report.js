// ════════════════════════════════════════════════════════════════
// Example: Domain Research Report Pipeline
//
// Adapts the 6-phase template for generating research reports.
// Phase 3 (EXECUTE) uses parallel agents to analyze multiple
// dimensions simultaneously.
// ════════════════════════════════════════════════════════════════

export const meta = {
  name: 'research-report-pipeline',
  description: 'Multi-dimensional research report: VERIFY → DATA GATE → PARALLEL ANALYSIS → CROSS-VALIDATE → REPORT → ARCHIVE',
  phases: [
    { title: 'VERIFY', detail: 'Check data sources and APIs' },
    { title: 'DATA GATE', detail: 'Validate data completeness and quality' },
    { title: 'EXECUTE', detail: 'Parallel analysis across dimensions' },
    { title: 'BRIDGE', detail: 'Cross-validate and reconcile findings' },
    { title: 'OUTPUT', detail: 'Generate research report' },
    { title: 'RECORD', detail: 'Archive and update handoff' },
  ],
}

const OUT = '/home/ubuntu/claude-workspace/output'
const TOPIC = args?.topic || 'general research'

// ── Schemas ───────────────────────────────────────────────
const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    env_ready: { type: 'boolean' },
    sources_available: { type: 'number' },
    details: { type: 'string' },
  },
  required: ['env_ready'],
}

const GATE_SCHEMA = {
  type: 'object',
  properties: {
    overall_pass: { type: 'boolean' },
    datasets_checked: { type: 'number' },
    critical_count: { type: 'number' },
    warning_count: { type: 'number' },
    summary: { type: 'string' },
  },
  required: ['overall_pass'],
}

const DIM_SCHEMA = {
  type: 'object',
  properties: {
    dimension: { type: 'string' },
    findings: { type: 'array', items: { type: 'object' } },
    data_quality: { type: 'string', enum: ['good', 'partial', 'poor'] },
    summary: { type: 'string' },
  },
  required: ['dimension', 'findings'],
}

const BRIDGE_SCHEMA = {
  type: 'object',
  properties: {
    can_proceed: { type: 'boolean' },
    contradictions_found: { type: 'number' },
    contradictions_resolved: { type: 'number' },
    merged_findings_path: { type: 'string' },
    summary: { type: 'string' },
  },
  required: ['can_proceed'],
}

const REPORT_SCHEMA = {
  type: 'object',
  properties: {
    report_path: { type: 'string' },
    sections: { type: 'number' },
    summary: { type: 'string' },
  },
  required: ['report_path'],
}


// ══════════════════════════════════════════════════════════
// Phase 1: VERIFY
// ══════════════════════════════════════════════════════════
phase('VERIFY')
log(`Phase 1/6: Verifying environment for topic "${TOPIC}"...`)

const verify = await agent(
  `Verify that all data sources needed for researching "${TOPIC}" are available.
Check APIs, local databases, and file access. Return env_ready=true only if all critical sources are reachable.`,
  { label: '环境验证', phase: 'VERIFY', schema: VERIFY_SCHEMA }
)

if (!verify || !verify.env_ready) {
  return { status: 'ABORTED', phase: 'VERIFY', reason: verify?.details }
}
log(`VERIFY OK: ${verify.sources_available} sources available`)


// ══════════════════════════════════════════════════════════
// Phase 2: DATA GATE
// ══════════════════════════════════════════════════════════
phase('DATA GATE')
log('Phase 2/6: Validating data quality...')

const gate = await agent(
  `Validate all input data for the "${TOPIC}" research. Check completeness, date ranges, and data types. Flag CRITICAL issues (missing essential data) vs WARNING (partial data, stale data). Return overall_pass=false if any CRITICAL issues exist.`,
  { label: '数据质量Gate', phase: 'DATA GATE', schema: GATE_SCHEMA }
)

if (!gate || !gate.overall_pass) {
  return { status: 'BLOCKED', phase: 'DATA GATE', reason: `${gate.critical_count} critical issues` }
}
log(`GATE PASSED: ${gate.datasets_checked} datasets, ${gate.warning_count} warnings`)


// ══════════════════════════════════════════════════════════
// Phase 3: EXECUTE — Parallel multi-dimension analysis
// ══════════════════════════════════════════════════════════
phase('EXECUTE')
log('Phase 3/6: Running parallel analysis across dimensions...')

const dimensions = [
  { key: 'macro',    prompt: `Analyze "${TOPIC}" from a MACRO/structural perspective. Identify systemic trends, policy impacts, and long-term forces.` },
  { key: 'micro',    prompt: `Analyze "${TOPIC}" from a MICRO/operational perspective. Examine company-level or entity-level metrics, competitive dynamics.` },
  { key: 'sentiment',prompt: `Analyze "${TOPIC}" from a SENTIMENT/NARRATIVE perspective. Assess market sentiment, media framing, and narrative trends.` },
  { key: 'risk',     prompt: `Analyze "${TOPIC}" from a RISK perspective. Identify key risks, tail events, and vulnerability points.` },
]

const dimResults = await parallel(
  dimensions.map(d => () =>
    agent(
      `You are a research analyst specializing in the ${d.key} dimension.
${d.prompt}
Write intermediate findings to ${OUT}/analysis_${d.key}.json.
Return structured JSON with dimension="${d.key}".`,
      { label: `分析:${d.key}`, phase: 'EXECUTE', schema: DIM_SCHEMA }
    )
  )
)

const validResults = dimResults.filter(Boolean)
log(`EXECUTE OK: ${validResults.length}/${dimensions.length} dimensions analyzed`)


// ══════════════════════════════════════════════════════════
// Phase 4: BRIDGE — Cross-validate and reconcile
// ══════════════════════════════════════════════════════════
phase('BRIDGE')
log('Phase 4/6: Cross-validating findings across dimensions...')

const bridge = await agent(
  `Cross-validate the ${validResults.length} dimension analyses for "${TOPIC}".

Read each dimension's findings from ${OUT}/analysis_*.json.
Look for:
1. Contradictions between dimensions (e.g., macro bullish but risk flags danger)
2. Consensus findings (multiple dimensions agree)
3. Gaps (dimension that found nothing significant)

Reconcile contradictions where possible. Write merged findings to ${OUT}/merged_findings.json.
Return can_proceed=false only if unresolved contradictions would make the report misleading.`,
  { label: '交叉验证', phase: 'BRIDGE', schema: BRIDGE_SCHEMA }
)

if (!bridge || !bridge.can_proceed) {
  return {
    status: 'BLOCKED', phase: 'BRIDGE',
    reason: `${bridge.contradictions_found - bridge.contradictions_resolved} unresolved contradictions`,
  }
}
log(`BRIDGE PASSED: ${bridge.contradictions_resolved}/${bridge.contradictions_found} contradictions resolved`)


// ══════════════════════════════════════════════════════════
// Phase 5: OUTPUT — Generate research report
// ══════════════════════════════════════════════════════════
phase('OUTPUT')
log('Phase 5/6: Generating research report...')

const report = await agent(
  `Generate a research report on "${TOPIC}" using the merged findings.

Read from: ${OUT}/merged_findings.json

Report structure:
1. Executive Summary (3-5 bullet points)
2. Multi-Dimensional Analysis
   - Macro/Structural
   - Micro/Operational
   - Sentiment/Narrative
   - Risk Assessment
3. Cross-Dimensional Synthesis (where dimensions agree/disagree)
4. Key Takeaways
5. Disclaimer

Include data quality notes: ${gate?.warning_count} warnings from the gate phase.

Save to ${OUT}/research_report_${TOPIC.replace(/[^a-zA-Z0-9]/g, '_')}.md`,
  { label: '报告生成', phase: 'OUTPUT', schema: REPORT_SCHEMA }
)
log(`OUTPUT OK: ${report?.report_path}`)


// ══════════════════════════════════════════════════════════
// Phase 6: RECORD
// ══════════════════════════════════════════════════════════
phase('RECORD')
log('Phase 6/6: Archiving...')

const record = await agent(
  `Archive this research run for "${TOPIC}".
Write summary JSON to ${OUT}/research_pipeline_summary.json with status, dimensions analyzed, contradictions resolved, and report path.
Append a line to SESSION_HANDOFF.md for session continuity.`,
  { label: '归档', phase: 'RECORD', schema: { type: 'object', properties: { archived: { type: 'boolean' }, summary: { type: 'string' } } } }
)
log(`RECORD OK`)


return {
  status: 'COMPLETED',
  topic: TOPIC,
  dimensions_analyzed: validResults.length,
  contradictions_resolved: bridge?.contradictions_resolved,
  report_path: report?.report_path,
}
