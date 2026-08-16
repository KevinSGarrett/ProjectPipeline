import React, { useEffect, useMemo, useState } from "react";
import { CommandCenterClient, createMemorySession } from "./apiClient.mjs";
import { NAV_ITEMS, filterGraph, healthTone, makeControlCommand, makeDirectorRequest, money, normalizeLiveApplication, percent, summarize } from "./appModel.mjs";
import { notifyDesktop } from "./desktopBridge.mjs";

const session = createMemorySession();

const FALLBACK = {
  snapshot: {
    project_id: "PROJECT-PIPELINE",
    overall_health: "DEGRADED",
    completion_gate_state: "NOT_COMPLETE",
    completion_percent: 62,
    approval_count: 3,
    evidence_count: 139,
    readiness: [
      { metric_id: "implementation", label: "Implementation", value: 0.62 },
      { metric_id: "verification", label: "Verification", value: 0.79 },
      { metric_id: "release", label: "Release", value: 0.48 },
      { metric_id: "operational", label: "Operational", value: 0.55 }
    ],
    live_work: [],
    health: []
  },
  application: {
    project_id: "PROJECT-PIPELINE",
    generated_at_utc: "offline-preview",
    readiness: { implementation: 62, verification: 79, release: 48, operational: 55, unresolved_scope: 38 },
    health: [
      { label: "System", state: "HEALTHY", detail: "Control plane responsive" },
      { label: "Project", state: "DEGRADED", detail: "Accepted scope remains incomplete" },
      { label: "Evidence", state: "HEALTHY", detail: "Current pass evidence attached" },
      { label: "Budget", state: "HEALTHY", detail: "Within configured guardrail" },
      { label: "Providers", state: "DEGRADED", detail: "Some external providers unverified" },
      { label: "Sync", state: "DEGRADED", detail: "Remote Jira/GitHub mutation disabled" }
    ],
    risks: [
      { severity: "HIGH", title: "Completion Gate remains open", detail: "Critical accepted requirements remain without full evidence." },
      { severity: "MEDIUM", title: "Desktop runtime unverified", detail: "Tauri source boundary exists but Windows binary requires external toolchain verification." }
    ],
    budget: { total_cap: 500, committed: 212, forecast: 286, by_provider: [{ label: "OpenAI", value: 132 }, { label: "Local", value: 24 }, { label: "Other", value: 56 }] },
    providers: [{ name: "OpenAI", state: "READY", latency_ms: 780, success_rate: 98.4 }, { name: "Local runtime", state: "READY", latency_ms: 1240, success_rate: 96.8 }],
    context: { freshness_percent: 97, coverage_percent: 93, trusted_sources: 18, restricted_items: 4 },
    recovery: [{ incident_id: "INCIDENT-LOCAL-001", state: "MONITORING", affected: "External GitHub sync", checkpoint: "Local outbox preserved", runbook: "command_center_realtime_recovery.md" }],
    approvals: [{ approval_id: "APPROVAL-DEMO-001", action: "Increase provider budget threshold", risk: "HIGH", requester: "budget-governor", expires: "2h", impact: "+$75 maximum authorized spend", state: "PENDING" }],
    sync: [{ system: "Jira", state: "LOCAL_ONLY", mismatches: 0, pending: 0, stale: true }, { system: "GitHub", state: "LOCAL_ONLY", mismatches: 0, pending: 0, stale: true }],
    evidence: [{ id: "EVID-000136", kind: "TEST", status: "VERIFIED", title: "Command Center backend focused suite" }, { id: "EVID-000138", kind: "RECOVERY", status: "VERIFIED", title: "Realtime reconnect simulation" }],
    graph: {
      nodes: [
        { id: "REQ-UX-0008", label: "Interactive project graph", kind: "requirement", state: "IN_PROGRESS" },
        { id: "PP-STORY-000114", label: "Project Intelligence", kind: "story", state: "IN_PROGRESS" },
        { id: "EVID-000136", label: "Backend evidence", kind: "evidence", state: "VERIFIED" },
        { id: "PP-TASK-000171", label: "React + Tauri client", kind: "task", state: "IN_PROGRESS" }
      ],
      edges: [
        { source: "REQ-UX-0008", target: "PP-STORY-000114", kind: "implemented_by" },
        { source: "PP-STORY-000114", target: "EVID-000136", kind: "supported_by" },
        { source: "PP-STORY-000114", target: "PP-TASK-000171", kind: "delivered_by" }
      ]
    },
    live_work: [
      { id: "PP-TASK-000171", title: "React operator client and Tauri shell", owner: "command-center", stage: "UI implementation", state: "RUNNING", progress: 74, next: "Browser verification" },
      { id: "PP-STORY-000114", title: "Project Intelligence surfaces", owner: "command-center", stage: "Projection wiring", state: "RUNNING", progress: 68, next: "Evidence drill-down" },
      { id: "PP-STORY-000115", title: "Accessible responsive surfaces", owner: "verification", stage: "Visual QA", state: "QUEUED", progress: 51, next: "Mobile viewport audit" }
    ]
  },
  inbox: [
    { inbox_id: "INBOX-001", level: 3, title: "Windows desktop build requires toolchain verification", impact: "Desktop runtime cannot be certified in this environment", exact_action: "Run the documented Tauri Windows qualification workflow", post_action_verification: "Attach a successful native Windows qualification record", deadline_at_utc: "2026-08-16T04:00:00Z", state: "OPEN" },
    { inbox_id: "INBOX-002", level: 2, title: "Remote Jira observation is stale", impact: "Local mirror remains authoritative for this pass", exact_action: "Reconcile after credentials and remote-write approval are available", post_action_verification: "Confirm remote observation timestamp and reconciliation state", deadline_at_utc: "2026-08-16T12:00:00Z", state: "OPEN" }
  ],
  incidents: [
    { incident: { incident_id: "INCIDENT-AAAAAAAAAAAAAAAAAAAA", summary: "External provider credentials require human repair", exact_human_action: "Rotate the provider credential and confirm the health check succeeds.", verification_steps: ["credential validates", "provider health check passes"] }, state: "OPEN", severity: 3, project_id: "PROJECT-PIPELINE", inbox_id: "INBOX-INCIDENT-001" }
  ]
};

function Badge({ children, tone = "neutral" }) { return <span className={`badge badge-${tone}`}>{children}</span>; }
function Progress({ value, label }) { return <div className="progress-wrap"><div className="progress-label"><span>{label}</span><strong>{percent(value)}</strong></div><div className="progress-track"><span style={{ width: `${Math.max(0, Math.min(100, value))}%` }} /></div></div>; }
function Section({ id, title, kicker, actions, children }) { return <section id={id} className="surface-card" aria-labelledby={`${id}-heading`}><header className="section-head"><div><p className="eyebrow">{kicker}</p><h2 id={`${id}-heading`}>{title}</h2></div>{actions}</header>{children}</section>; }

export function App() {
  const [active, setActive] = useState("overview");
  const [data, setData] = useState(FALLBACK);
  const [connection, setConnection] = useState("OFFLINE PREVIEW");
  const [graphSearch, setGraphSearch] = useState("");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [controlStatus, setControlStatus] = useState("Controls are routed through the canonical API.");
  const [directorInput, setDirectorInput] = useState("");
  const [directorScope, setDirectorScope] = useState("PROJECT");
  const [directorMessages, setDirectorMessages] = useState([]);
  const [directorStatus, setDirectorStatus] = useState("Director answers are grounded in the current authorized projection; raw chat never mutates state.");
  const [incidentStatus, setIncidentStatus] = useState("Incident resolution requires verification and reconciliation evidence.");
  const [notificationStatus, setNotificationStatus] = useState("Remote delivery is disabled unless explicitly configured; desktop action-click qualification remains separate.");
  const summary = useMemo(() => summarize(data.snapshot, data.application), [data]);
  const graph = useMemo(() => filterGraph(data.application.graph, graphSearch), [data.application.graph, graphSearch]);

  useEffect(() => {
    const current = session.get();
    if (!current.token) return undefined;
    const client = new CommandCenterClient(current);
    Promise.all([client.status(), client.application(), client.inbox()])
      .then(([snapshot, application, inbox]) => {
        setData((currentData) => ({ ...currentData, snapshot, application: normalizeLiveApplication(snapshot, application), inbox }));
        setConnection("LIVE");
        client.incidents().then((incidents) => setData((currentData) => ({ ...currentData, incidents }))).catch(() => undefined);
      })
      .catch(() => setConnection("DEGRADED"));
    return undefined;
  }, []);

  async function issueControl(commandType, label) {
    const current = session.get();
    if (!current.token || !current.actorId) { setControlStatus(`${label}: authentication required before issuing a command.`); return; }
    try {
      const client = new CommandCenterClient(current);
      const command = makeControlCommand({ commandType, projectId: summary.projectId, actorId: current.actorId, authorityScope: ["command-center"] });
      const result = await client.control(command);
      setControlStatus(`${label}: ${result.status}`);
    } catch (error) { setControlStatus(`${label}: ${error.message}`); }
  }

  async function askDirector(event) {
    event?.preventDefault();
    const message = directorInput.trim();
    if (!message) return;
    const current = session.get();
    if (!current.token || !current.actorId) {
      setDirectorMessages((items) => [...items, { role: "USER", content: message }, { role: "ASSISTANT", content: "Offline evidence preview: Director Chat would answer only from the authorized Project Pipeline projection. No command was executed." }]);
      setDirectorInput("");
      setDirectorStatus("Preview response only; authentication is required for live grounded context and typed action proposals.");
      return;
    }
    try {
      const client = new CommandCenterClient(current);
      const incidentId = directorScope === "INCIDENT" ? data.incidents?.[0]?.incident?.incident_id : null;
      const response = await client.directorChat(makeDirectorRequest({ message, scope: directorScope, incidentId }));
      setDirectorMessages((items) => [...items, { role: "USER", content: message }, { role: "ASSISTANT", content: response.response_message.content, proposals: response.proposals }]);
      setDirectorStatus(response.proposals?.length ? "Typed proposals prepared; explicit operator confirmation is still required." : "Grounded response returned; no mutation requested.");
      setDirectorInput("");
    } catch (error) { setDirectorStatus(`Director request failed: ${error.message}`); }
  }

  async function incidentAction(incidentId, action) {
    const current = session.get();
    if (!current.token) { setIncidentStatus(`${action}: preview only; live authentication and canonical incident state are required.`); return; }
    try {
      const client = new CommandCenterClient(current);
      let result;
      if (action === "acknowledge") result = await client.acknowledgeIncident(incidentId);
      else if (action === "start recovery") result = await client.startIncidentRecovery(incidentId);
      else if (action === "verify repair") result = await client.verifyIncident(incidentId, { verification_results: { operator_check: true }, stale_assumptions_invalidated: true, reconciliation_complete: true });
      else result = await client.resolveIncident(incidentId);
      setIncidentStatus(`${action}: canonical incident state is now ${result.state}.`);
      client.incidents().then((incidents) => setData((currentData) => ({ ...currentData, incidents }))).catch(() => undefined);
    } catch (error) { setIncidentStatus(`${action}: ${error.message}`); }
  }

  async function handleInbox(item, mode) {
    const current = session.get();
    if (!current.token) { setNotificationStatus(`${mode}: preview only; no notification or acknowledgement was sent.`); return; }
    try {
      const client = new CommandCenterClient(current);
      if (mode === "acknowledge") {
        const updated = await client.acknowledge(item.inbox_id);
        setNotificationStatus(`Acknowledged ${updated.inbox_id}; canonical inbox state=${updated.state}.`);
        return;
      }
      const result = await client.dispatchInbox(item.inbox_id);
      const nativeAttempt = result.deliveries?.find((attempt) => attempt.state === "CLIENT_ACTION_REQUIRED");
      if (nativeAttempt) {
        const native = await notifyDesktop({ title: item.title, body: `${item.impact} Action: ${item.exact_action}`, actionLink: nativeAttempt.action_link });
        setNotificationStatus(`Broker dispatch complete; desktop=${native.reason}; action-click=${native.actionLinkQualification}.`);
      } else setNotificationStatus(`Broker dispatch complete across ${result.deliveries?.length || 0} channel attempts.`);
    } catch (error) { setNotificationStatus(`${mode}: ${error.message}`); }
  }

  function navigate(id) {
    setActive(id); setMobileOpen(false);
    requestAnimationFrame(() => document.getElementById(id)?.focus({ preventScroll: true }));
  }

  return <div className="app-shell">
    <a className="skip-link" href="#main-content">Skip to content</a>
    <aside className={`sidebar ${mobileOpen ? "sidebar-open" : ""}`} aria-label="Primary navigation">
      <div className="brand"><div className="brand-mark">PP</div><div><strong>Project Pipeline</strong><span>Command Center</span></div></div>
      <nav>{NAV_ITEMS.map(([id, label]) => <button key={id} type="button" className={active === id ? "nav-item active" : "nav-item"} aria-current={active === id ? "page" : undefined} onClick={() => navigate(id)}><span className="nav-dot" />{label}</button>)}</nav>
      <div className="sidebar-foot"><span className="authority-dot" />Canonical authority: Project Pipeline</div>
    </aside>

    <div className="workspace">
      <header className="topbar">
        <button className="menu-button" type="button" aria-label="Toggle navigation" aria-expanded={mobileOpen} onClick={() => setMobileOpen(!mobileOpen)}>☰</button>
        <div><p className="eyebrow">CONTROL PLANE / {summary.projectId}</p><h1>Command Center</h1></div>
        <div className="top-actions"><Badge tone={connection === "LIVE" ? "good" : "warn"}>{connection}</Badge><Badge tone={healthTone(summary.health)}>{summary.health}</Badge><button type="button" className="icon-button" aria-label="Test desktop notification" onClick={() => notifyDesktop({ title: "Project Pipeline", body: "Command Center notification boundary is available.", actionLink: "/command-center" })}>◉</button></div>
      </header>

      <main id="main-content" tabIndex="-1">
        <section className="hero" aria-labelledby="hero-heading"><div><p className="eyebrow">PROJECT OVERVIEW</p><h2 id="hero-heading">Execution truth, without the guesswork.</h2><p>Live operational state is projected from canonical records. The UI never becomes authoritative.</p></div><div className="hero-gate"><span>Completion Gate</span><strong>{summary.gate}</strong><small>{percent(summary.completion)} deterministic completion</small></div></section>

        <div className="metric-grid" aria-label="Key project metrics">
          <article className="metric-card"><span>Implementation</span><strong>{percent(summary.implementation)}</strong><small>accepted scope delivered</small></article>
          <article className="metric-card"><span>Verification</span><strong>{percent(summary.verification)}</strong><small>behavior linked evidence</small></article>
          <article className="metric-card"><span>Live work</span><strong>{data.application.live_work?.length ?? summary.liveWork}</strong><small>active / queued items</small></article>
          <article className="metric-card"><span>Human attention</span><strong>{data.inbox?.length ?? 0}</strong><small>operator inbox items</small></article>
        </div>

        <div className="content-grid">
          <div className="main-column">
            <Section id="overview" kicker="READINESS" title="Project readiness">
              <div className="readiness-grid"><Progress value={summary.implementation} label="Implementation"/><Progress value={summary.verification} label="Verification"/><Progress value={summary.release} label="Release readiness"/><Progress value={summary.operational} label="Operational readiness"/></div>
            </Section>

            <Section id="graph" kicker="TRACEABILITY" title="Interactive project graph" actions={<label className="search-field"><span className="sr-only">Search graph</span><input aria-label="Search graph" value={graphSearch} onChange={(e) => setGraphSearch(e.target.value)} placeholder="Filter requirements, work, evidence…" /></label>}>
              <div className="graph-canvas" role="group" aria-label="Requirement and work dependency graph">{graph.nodes.map((node, index) => <button type="button" className={`graph-node kind-${node.kind}`} style={{ "--x": `${8 + (index % 3) * 31}%`, "--y": `${16 + Math.floor(index / 3) * 38}%` }} key={node.id} title={node.id}><span>{node.kind}</span><strong>{node.label}</strong><small>{node.state}</small></button>)}<svg className="graph-lines" aria-hidden="true" viewBox="0 0 100 100" preserveAspectRatio="none"><path d="M 21 27 C 34 27, 32 27, 42 27"/><path d="M 53 27 C 66 27, 64 27, 74 27"/><path d="M 53 35 C 53 48, 53 52, 53 62"/></svg></div>
              <div className="graph-legend"><span><i className="legend requirement"/>Requirement</span><span><i className="legend story"/>Story</span><span><i className="legend task"/>Task</span><span><i className="legend evidence"/>Evidence</span></div>
            </Section>

            <Section id="work" kicker="EXECUTION" title="Live work">
              <div className="table-wrap"><table><caption className="sr-only">Current and queued work</caption><thead><tr><th>Work</th><th>Owner</th><th>Stage</th><th>State</th><th>Progress</th><th>Next</th></tr></thead><tbody>{(data.application.live_work || []).map((item) => <tr key={item.id}><td><strong>{item.title}</strong><small>{item.id}</small></td><td>{item.owner}</td><td>{item.stage}</td><td><Badge tone={item.state === "RUNNING" ? "good" : "neutral"}>{item.state}</Badge></td><td>{percent(item.progress)}</td><td>{item.next}</td></tr>)}</tbody></table></div>
            </Section>

            <Section id="health" kicker="OPERATIONS" title="Layered health & risk">
              <div className="health-grid">{(data.application.health || []).map((item) => <article key={item.label} className="health-card"><div><span className={`status-light ${healthTone(item.state)}`} /><strong>{item.label}</strong></div><Badge tone={healthTone(item.state)}>{item.state}</Badge><p>{item.detail}</p></article>)}</div>
              <div className="risk-list">{(data.application.risks || []).map((risk) => <article key={risk.title}><Badge tone={risk.severity === "HIGH" ? "bad" : "warn"}>{risk.severity}</Badge><div><strong>{risk.title}</strong><p>{risk.detail}</p></div></article>)}</div>
            </Section>

            <Section id="budgets" kicker="FINANCE" title="Budget & cost drill-down">
              <div className="budget-layout"><div className="budget-total"><span>Forecast</span><strong>{money(data.application.budget?.forecast)}</strong><small>of {money(data.application.budget?.total_cap)} configured cap</small></div><div className="provider-bars">{(data.application.budget?.by_provider || []).map((item) => <Progress key={item.label} value={(item.value / Math.max(1, data.application.budget.total_cap)) * 100} label={`${item.label} · ${money(item.value)}`} />)}</div></div>
            </Section>

            <Section id="providers" kicker="ROUTING" title="Provider & agent performance">
              <div className="provider-grid">{(data.application.providers || []).map((provider) => <article key={provider.name}><div><strong>{provider.name}</strong><Badge tone={provider.state === "READY" ? "good" : "warn"}>{provider.state}</Badge></div><dl><div><dt>Success</dt><dd>{provider.success_rate}%</dd></div><div><dt>p50 latency</dt><dd>{provider.latency_ms} ms</dd></div></dl></article>)}</div>
            </Section>

            <Section id="context" kicker="KNOWLEDGE" title="Context health">
              <div className="context-metrics"><Progress value={data.application.context?.freshness_percent || 0} label="Freshness"/><Progress value={data.application.context?.coverage_percent || 0} label="Coverage"/><article><span>Trusted sources</span><strong>{data.application.context?.trusted_sources || 0}</strong></article><article><span>Egress-restricted</span><strong>{data.application.context?.restricted_items || 0}</strong></article></div>
            </Section>

            <Section id="recovery" kicker="RESILIENCE" title="Recovery Center">
              <div className="record-list">{(data.application.recovery || []).map((item) => <article key={item.incident_id}><div><strong>{item.incident_id}</strong><Badge tone="warn">{item.state}</Badge></div><p>{item.affected}</p><dl><div><dt>Checkpoint</dt><dd>{item.checkpoint}</dd></div><div><dt>Runbook</dt><dd>{item.runbook}</dd></div></dl></article>)}</div>
            </Section>

            <Section id="director" kicker="INTELLIGENCE" title="Director Chat">
              <div className="director-layout">
                <div className="chat-log" aria-live="polite">{directorMessages.length ? directorMessages.map((item, index) => <article key={`${item.role}-${index}`} className={`chat-message ${item.role === "USER" ? "chat-user" : "chat-assistant"}`}><span>{item.role === "USER" ? "Operator" : "Director"}</span><p>{item.content}</p>{item.proposals?.length ? <small>{item.proposals.length} typed proposal(s) prepared — none executed automatically.</small> : null}</article>) : <article className="chat-message chat-assistant"><span>Director</span><p>Ask about global, project, or incident state. Answers are limited to authorized Project Pipeline projections and never expose private reasoning.</p></article>}</div>
                <form className="director-form" onSubmit={askDirector}><label><span>Scope</span><select aria-label="Director scope" value={directorScope} onChange={(event) => setDirectorScope(event.target.value)}><option value="GLOBAL">Global</option><option value="PROJECT">Project</option><option value="INCIDENT">Incident</option></select></label><label className="director-input"><span>Message</span><input aria-label="Director message" value={directorInput} onChange={(event) => setDirectorInput(event.target.value)} placeholder="What is blocked and what needs my attention?" /></label><button type="submit">Ask Director</button></form>
                <p className="control-status" role="status">{directorStatus}</p>
              </div>
            </Section>

            <Section id="incidents" kicker="RECOVERY" title="Incident Manager">
              <div className="record-list incident-list">{(data.incidents || []).map((item) => <article key={item.incident.incident_id}><div><strong>{item.incident.incident_id}</strong><Badge tone={item.state === "VERIFIED" ? "good" : "warn"}>{item.state}</Badge></div><p>{item.incident.summary}</p><div className="incident-action-detail"><span>Exact action</span><strong>{item.incident.exact_human_action}</strong><span>Verification</span><small>{(item.incident.verification_steps || []).join(" · ")}</small></div><div className="incident-actions"><button type="button" onClick={() => incidentAction(item.incident.incident_id, "acknowledge")}>Acknowledge</button><button type="button" onClick={() => incidentAction(item.incident.incident_id, "start recovery")}>Start recovery</button><button type="button" onClick={() => incidentAction(item.incident.incident_id, "verify repair")}>Verify repair</button><button type="button" onClick={() => incidentAction(item.incident.incident_id, "resolve")}>Resolve</button></div></article>)}</div>
              <p className="control-status" role="status">{incidentStatus}</p>
            </Section>

            <Section id="approvals" kicker="GOVERNANCE" title="Approval Center">
              <div className="record-list">{(data.application.approvals || []).map((item) => <article key={item.approval_id}><div><strong>{item.action}</strong><Badge tone="warn">{item.state}</Badge></div><p>{item.impact}</p><dl><div><dt>Risk</dt><dd>{item.risk}</dd></div><div><dt>Requester</dt><dd>{item.requester}</dd></div><div><dt>Expires</dt><dd>{item.expires}</dd></div></dl></article>)}</div>
            </Section>

            <Section id="sync" kicker="RECONCILIATION" title="Jira / GitHub synchronization">
              <div className="sync-grid">{(data.application.sync || []).map((item) => <article key={item.system}><div><strong>{item.system}</strong><Badge tone={item.stale ? "warn" : "good"}>{item.state}</Badge></div><dl><div><dt>Mismatches</dt><dd>{item.mismatches}</dd></div><div><dt>Pending</dt><dd>{item.pending}</dd></div></dl><small>{item.stale ? "Last remote observation is stale" : "Observation current"}</small></article>)}</div>
            </Section>

            <Section id="evidence" kicker="ASSURANCE" title="Evidence drill-down">
              <div className="evidence-list">{(data.application.evidence || []).map((item) => <button type="button" key={item.id}><span><Badge tone={item.status === "VERIFIED" ? "good" : "warn"}>{item.status}</Badge><strong>{item.title}</strong></span><code>{item.id}</code></button>)}</div>
            </Section>
          </div>

          <aside className="right-rail" aria-label="Operator attention and controls">
            <section className="rail-card"><p className="eyebrow">OPERATOR INBOX</p><h2>Human attention</h2><div className="inbox-list">{(data.inbox || []).map((item) => <article key={item.inbox_id}><Badge tone={Number(item.level) >= 3 ? "bad" : "warn"}>L{item.level}</Badge><div><strong>{item.title}</strong><p>{item.impact}</p><small><b>Action:</b> {item.exact_action}</small>{item.deadline_at_utc ? <small><b>Deadline:</b> {new Date(item.deadline_at_utc).toLocaleString()}</small> : <small><b>Deadline:</b> Not specified by canonical work item</small>}{item.post_action_verification ? <small><b>Verify:</b> {item.post_action_verification}</small> : null}<div className="inbox-actions"><button type="button" onClick={() => handleInbox(item, "acknowledge")}>Acknowledge</button><button type="button" onClick={() => handleInbox(item, "dispatch")}>Notify</button></div></div></article>)}</div><p className="control-status" role="status">{notificationStatus}</p></section>
            <section className="rail-card sticky"><p className="eyebrow">SAFE CONTROLS</p><h2>Project controls</h2><div className="control-stack"><button type="button" onClick={() => issueControl("project.pause_new_work", "Pause new work")}>Pause new work</button><button type="button" onClick={() => issueControl("project.pause", "Pause project")}>Pause project</button><button type="button" className="danger" onClick={() => issueControl("project.emergency_stop", "Emergency stop")}>Emergency stop</button></div><p className="control-status" role="status">{controlStatus}</p><small>Every mutation returns through authentication, policy, idempotency, audit, and canonical state transition handling.</small></section>
          </aside>
        </div>
      </main>
    </div>
  </div>;
}
