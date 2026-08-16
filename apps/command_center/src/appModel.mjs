export const NAV_ITEMS = Object.freeze([
  ["overview", "Overview"],
  ["graph", "Project Graph"],
  ["work", "Live Work"],
  ["health", "Health & Risk"],
  ["budgets", "Budgets"],
  ["providers", "Providers"],
  ["context", "Context"],
  ["recovery", "Recovery"],
  ["director", "Director Chat"],
  ["incidents", "Incidents"],
  ["approvals", "Approvals"],
  ["sync", "Jira / GitHub"],
  ["evidence", "Evidence"]
]);

export function percent(value) {
  const n = Number(value ?? 0);
  return `${Math.max(0, Math.min(100, Math.round(n)))}%`;
}

export function money(value) {
  const n = Number(value ?? 0);
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

export function healthTone(state) {
  const normalized = String(state || "UNKNOWN").toUpperCase();
  if (["HEALTHY", "PASS", "OK"].includes(normalized)) return "good";
  if (["DEGRADED", "WARNING", "ATTENTION"].includes(normalized)) return "warn";
  if (["UNHEALTHY", "CRITICAL", "FAILED", "ERROR"].includes(normalized)) return "bad";
  return "neutral";
}

export function summarize(snapshot, application) {
  const readiness = Object.fromEntries((snapshot?.readiness || []).map((item) => [item.metric_id, item.value * 100]));
  return {
    projectId: snapshot?.project_id || application?.project_id || "UNKNOWN",
    health: snapshot?.overall_health || "UNKNOWN",
    completion: snapshot?.completion_percent ?? 0,
    gate: snapshot?.completion_gate_state || "UNKNOWN",
    liveWork: snapshot?.live_work?.length ?? 0,
    approvals: snapshot?.approval_count ?? 0,
    evidence: snapshot?.evidence_count ?? application?.evidence?.length ?? 0,
    implementation: readiness.implementation ?? application?.readiness?.implementation ?? 0,
    verification: readiness.verification ?? application?.readiness?.verification ?? 0,
    release: readiness.release ?? application?.readiness?.release ?? 0,
    operational: readiness.operational ?? application?.readiness?.operational ?? 0,
    unresolvedScope: readiness.unresolved_scope ?? application?.readiness?.unresolved_scope ?? 0
  };
}

export function filterGraph(graph, term) {
  const text = String(term || "").trim().toLowerCase();
  if (!text) return graph;
  const nodes = (graph?.nodes || []).filter((node) => `${node.id} ${node.label} ${node.kind}`.toLowerCase().includes(text));
  const ids = new Set(nodes.map((node) => node.id));
  const edges = (graph?.edges || []).filter((edge) => ids.has(edge.source) && ids.has(edge.target));
  return { nodes, edges };
}

export function makeControlCommand({ commandType, projectId, actorId, payload = {}, authorityScope = [] }) {
  const nonce = `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  const correlationId = `cc:${projectId}:${nonce}`;
  return {
    schema_version: "1.0.0",
    command_id: `command:${nonce}`,
    command_type: commandType,
    project_id: projectId,
    actor_id: actorId,
    correlation_id: correlationId,
    idempotency_key: `cc-${projectId}-${commandType}-${nonce}`,
    issued_at_utc: new Date().toISOString(),
    authority_scope: authorityScope,
    dry_run: false,
    payload,
    action_intent: {
      schema_version: "1.0.0",
      actor_id: actorId,
      authority: "operator",
      target: projectId,
      operation: commandType,
      idempotency_key: `cc-${projectId}-${commandType}-${nonce}`,
      approval_state: "APPROVED",
      correlation_id: correlationId
    }
  };
}

export function makeDirectorRequest({ message, scope = "PROJECT", incidentId = null, conversationId = null }) {
  const request = { schema_version: "1.0.0", message: String(message || "").trim(), scope };
  if (incidentId) request.incident_id = incidentId;
  if (conversationId) request.conversation_id = conversationId;
  return request;
}

export function normalizeLiveApplication(snapshot, application) {
  const health = (snapshot?.health || []).map((item) => ({ label: item.name, state: item.state, detail: item.reason }));
  const risks = [];
  if (snapshot?.completion_gate_state === "NOT_COMPLETE") risks.push({ severity: "HIGH", title: "Completion Gate remains open", detail: "Canonical completion criteria are not yet fully satisfied." });
  const synchronization = application?.synchronization || [];
  if (synchronization.some((item) => item.stale)) risks.push({ severity: "MEDIUM", title: "External synchronization observation is stale", detail: "One or more remote-system views are explicitly marked stale." });
  const rawBudget = application?.budget_detail || {};
  const budget = {
    total_cap: Number(rawBudget.total_cap ?? rawBudget.cap ?? 0),
    committed: Number(rawBudget.committed ?? 0),
    forecast: Number(rawBudget.forecast ?? rawBudget.forecast_total ?? 0),
    by_provider: Array.isArray(rawBudget.by_provider) ? rawBudget.by_provider : []
  };
  const providerRaw = application?.provider_detail || {};
  const providers = Array.isArray(providerRaw) ? providerRaw : Array.isArray(providerRaw.providers) ? providerRaw.providers : [];
  const contextRaw = application?.context_detail || {};
  const evidence = (application?.evidence || []).map((item) => ({ id: item.evidence_id, kind: item.kind, status: item.status, title: item.summary, path: item.path }));
  const graph = {
    nodes: (application?.graph?.nodes || []).map((item) => ({ id: item.node_id, label: item.label, kind: item.kind === "jira" ? "task" : item.kind, state: item.state, path: item.authoritative_path })),
    edges: application?.graph?.edges || [],
    truncated: Boolean(application?.graph?.truncated)
  };
  const live_work = (application?.live_work || []).map((item) => ({ id: item.work_id, title: item.title, owner: item.owner || "unassigned", stage: item.stage || "unknown", state: item.state, progress: 0, next: item.next_transition || "Await canonical transition" }));
  const sync = synchronization.map((item) => ({ system: item.system, state: item.mode, mismatches: item.conflict_count, pending: item.pending_outbox_count, stale: item.stale, note: item.note }));
  const recovery = (application?.recovery_detail || []).map((item) => ({ incident_id: item.incident_id || "INCIDENT", state: item.state || item.detail_state || "UNKNOWN", affected: item.affected || "Canonical incident detail requires live provider", checkpoint: item.checkpoint || "See canonical incident record", runbook: item.runbook || "See recovery runbooks" }));
  const approvals = (application?.approvals_detail || []).map((item) => ({ approval_id: item.approval_id || item.id || "APPROVAL", action: item.action || item.action_id || "Approval", risk: item.risk || "UNKNOWN", requester: item.requester || item.proposer_identity_id || "unknown", expires: item.expires || "n/a", impact: item.impact || item.reason || "See canonical approval record", state: item.state || item.decision || "PENDING" }));
  return { ...application, health, risks, budget, providers, context: contextRaw, recovery, approvals, sync, evidence, graph, live_work };
}
