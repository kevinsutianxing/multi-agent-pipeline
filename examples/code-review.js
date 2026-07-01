// ════════════════════════════════════════════════════════════════
// Example: Multi-Dimensional Code Review Pipeline
//
// Uses parallel agents to review code from different dimensions,
// then cross-validates and produces a review dashboard.
// ════════════════════════════════════════════════════════════════

export const meta = {
  name: 'code-review-pipeline',
  description: 'Multi-dimensional code review: VERIFY → LINT GATE → PARALLEL REVIEW → DEDUP → DASHBOARD → ARCHIVE',
  phases: [
    { title: 'VERIFY', detail: 'Check repo state and tooling' },
    { title: 'LINT GATE', detail: 'Run linters and static analysis' },
    { title: 'EXECUTE', detail: 'Parallel review across dimensions' },
    { title: 'BRIDGE', detail: 'Deduplicate and verify findings' },
    { title: 'OUTPUT', detail: 'Generate review dashboard' },
    { title: 'RECORD', detail: 'Archive review results' },
  ],
}

const REPO = args?.repo || process.cwd()
const OUT = `${REPO}/.review`

// ── Review Dimensions ─────────────────────────────────────
const DIMENSIONS = [
  {
    key: 'bugs',
    prompt: `Review the code for BUGS and LOGIC ERRORS.
- Off-by-one, null/undefined access, race conditions
- Incorrect error handling, swallowed exceptions
- Type mismatches, wrong API usage
For each finding, provide: file, line, severity (CRITICAL/HIGH/MEDIUM/LOW), description, and suggested fix.`,
  },
  {
    key: 'security',
    prompt: `Review the code for SECURITY issues.
- Injection vectors (SQL, command, path traversal)
- Authentication/authorization gaps
- Secret exposure, insecure defaults
- Unsafe deserialization, prototype pollution
For each finding, provide: file, line, severity, description, CWE reference if applicable.`,
  },
  {
    key: 'performance',
    prompt: `Review the code for PERFORMANCE issues.
- N+1 queries, missing indexes, unbounded collections
- Blocking I/O on hot paths, missing caching
- Memory leaks, excessive allocations
- Inefficient algorithms (O(n²) where O(n) is possible)
For each finding, provide: file, line, severity, description, expected impact.`,
  },
  {
    key: 'maintainability',
    prompt: `Review the code for MAINTAINABILITY issues.
- God functions/classes, deep nesting, high cyclomatic complexity
- Missing or misleading comments, magic numbers
- Duplicated code, inconsistent patterns
- Poor naming, unclear responsibility boundaries
For each finding, provide: file, line, severity, description, refactoring suggestion.`,
  },
]

// ── Schemas ───────────────────────────────────────────────
const FINDINGS_SCHEMA = {
  type: 'object',
  properties: {
    dimension: { type: 'string' },
    findings: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          file: { type: 'string' },
          line: { type: 'number' },
          severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
          title: { type: 'string' },
          description: { type: 'string' },
          suggestion: { type: 'string' },
        },
        required: ['file', 'severity', 'title', 'description'],
      },
    },
    summary: { type: 'string' },
  },
  required: ['dimension', 'findings'],
}

const VERDICT_SCHEMA = {
  type: 'object',
  properties: {
    finding_title: { type: 'string' },
    is_real: { type: 'boolean' },
    severity_agree: { type: 'boolean' },
    adjusted_severity: { type: 'string', enum: ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] },
    reasoning: { type: 'string' },
  },
  required: ['is_real', 'reasoning'],
}


// ══════════════════════════════════════════════════════════
// Phase 1: VERIFY
// ══════════════════════════════════════════════════════════
phase('VERIFY')
log(`Phase 1/6: Verifying repo state for ${REPO}...`)

const verify = await agent(
  `Check that the repository at ${REPO} is in a reviewable state:
1. git status — no merge conflicts, clean or staged changes OK
2. Required tooling available (linters, formatters)
3. Output directory ${OUT} is writable

Return env_ready=true if all checks pass.`,
  { label: '环境检查', phase: 'VERIFY', schema: { type: 'object', properties: { env_ready: { type: 'boolean' }, details: { type: 'string' } }, required: ['env_ready'] } }
)

if (!verify || !verify.env_ready) {
  return { status: 'ABORTED', phase: 'VERIFY', reason: verify?.details }
}
log('VERIFY OK')


// ══════════════════════════════════════════════════════════
// Phase 2: LINT GATE
// ══════════════════════════════════════════════════════════
phase('LINT GATE')
log('Phase 2/6: Running lint gate...')

const lintGate = await agent(
  `Run linters and static analysis on ${REPO}.
Execute the project's lint commands (eslint, pyright, shellcheck, etc. — detect from project config).
CRITICAL = lint errors that would fail CI. WARNING = style nits.
Return overall_pass=false if CRITICAL lint errors exist (code must at least compile/lint-clean before human review).`,
  { label: 'Lint Gate', phase: 'LINT GATE', schema: { type: 'object', properties: { overall_pass: { type: 'boolean' }, critical_count: { type: 'number' }, warning_count: { type: 'number' }, summary: { type: 'string' } }, required: ['overall_pass'] } }
)

if (!lintGate || !lintGate.overall_pass) {
  return { status: 'BLOCKED', phase: 'LINT GATE', reason: `${lintGate.critical_count} lint errors` }
}
log(`LINT GATE PASSED: ${lintGate.warning_count} warnings`)


// ══════════════════════════════════════════════════════════
// Phase 3: EXECUTE — Parallel multi-dimension review
// ══════════════════════════════════════════════════════════
phase('EXECUTE')
log(`Phase 3/6: Reviewing across ${DIMENSIONS.length} dimensions...`)

const reviewResults = await parallel(
  DIMENSIONS.map(d => () =>
    agent(
      `You are a code reviewer specializing in ${d.key}.
${d.prompt}
Review the codebase at ${REPO}. Focus on changed files (git diff).`,
      { label: `review:${d.key}`, phase: 'EXECUTE', schema: FINDINGS_SCHEMA }
    )
  )
)

const allFindings = reviewResults.filter(Boolean).flatMap(r => r.findings)
log(`Found ${allFindings.length} findings across ${reviewResults.filter(Boolean).length} dimensions`)


// ══════════════════════════════════════════════════════════
// Phase 4: BRIDGE — Deduplicate + adversarially verify
// ══════════════════════════════════════════════════════════
phase('BRIDGE')
log('Phase 4/6: Deduplicating and verifying findings...')

// Step 4a: Deduplicate by file+line (same finding flagged by multiple dimensions)
const seen = new Set()
const deduped = allFindings.filter(f => {
  const k = `${f.file}:${f.line}:${f.title?.slice(0, 30)}`
  if (seen.has(k)) return false
  seen.add(k)
  return true
})
log(`Deduped: ${allFindings.length} → ${deduped.length} unique findings`)

// Step 4b: Adversarially verify CRITICAL and HIGH findings
const highSeverity = deduped.filter(f => f.severity === 'CRITICAL' || f.severity === 'HIGH')
const lowSeverity = deduped.filter(f => f.severity === 'MEDIUM' || f.severity === 'LOW')

let verified = lowSeverity // MEDIUM/LOW pass through without adversarial check

if (highSeverity.length > 0) {
  log(`Adversarially verifying ${highSeverity.length} HIGH/CRITICAL findings...`)

  const verifications = await parallel(
    highSeverity.map(f => () =>
      agent(
        `You are a skeptical code reviewer. Try to REFUTE this finding:
File: ${f.file}:${f.line}
Severity: ${f.severity}
Title: ${f.title}
Description: ${f.description}

Is this a real issue? Could it be a false positive? Is the severity appropriate?
Default to is_real=false if uncertain. Be strict.`,
        { label: `verify:${f.file}:${f.line}`, phase: 'BRIDGE', schema: VERDICT_SCHEMA }
      ).then(v => ({ ...f, verdict: v }))
    )
  )

  const confirmed = verifications.filter(Boolean).filter(v => v.verdict?.is_real)
  const falsePositives = verifications.filter(Boolean).filter(v => !v.verdict?.is_real)

  log(`Verified: ${confirmed.length} confirmed, ${falsePositives.length} false positives`)

  if (falsePositives.length > 0) {
    log(`False positives removed: ${falsePositives.map(f => `${f.file}:${f.line}`).join(', ')}`)
  }

  verified = [...verified, ...confirmed]
}


// ══════════════════════════════════════════════════════════
// Phase 5: OUTPUT — Review Dashboard
// ══════════════════════════════════════════════════════════
phase('OUTPUT')
log(`Phase 5/6: Generating review dashboard (${verified.length} confirmed findings)...`)

const report = await agent(
  `Generate a code review dashboard from ${verified.length} verified findings.

Write to ${OUT}/review_dashboard.md:

# Code Review Dashboard
**Repository**: ${REPO}
**Date**: <current date>
**Review Dimensions**: ${DIMENSIONS.map(d => d.key).join(', ')}

## Summary
| Dimension | CRITICAL | HIGH | MEDIUM | LOW |
|-----------|----------|------|--------|-----|
(aggregate counts from verified findings)

## CRITICAL Findings
(list each with file, line, description, suggested fix)

## HIGH Findings
(list each)

## MEDIUM/LOW Findings
(collapsed summary — list top 5, note count of remaining)

## False Positives Removed
(${allFindings.length - verified.length} findings removed after adversarial verification)

Save the dashboard and return the path.`,
  { label: 'Dashboard生成', phase: 'OUTPUT', schema: { type: 'object', properties: { report_path: { type: 'string' }, critical_count: { type: 'number' }, high_count: { type: 'number' }, summary: { type: 'string' } }, required: ['report_path'] } }
)
log(`OUTPUT: ${report?.report_path}`)


// ══════════════════════════════════════════════════════════
// Phase 6: RECORD
// ══════════════════════════════════════════════════════════
phase('RECORD')
log('Phase 6/6: Archiving review...')

await agent(
  `Archive review results to ${OUT}/review_summary.json with finding counts by severity and dimension.
Update SESSION_HANDOFF.md with review completion note.`,
  { label: '归档', phase: 'RECORD' }
)
log('RECORD OK')


return {
  status: 'COMPLETED',
  repo: REPO,
  dimensions: DIMENSIONS.map(d => d.key),
  findings_total: allFindings.length,
  findings_verified: verified.length,
  false_positives: allFindings.length - verified.length,
  report_path: report?.report_path,
}
