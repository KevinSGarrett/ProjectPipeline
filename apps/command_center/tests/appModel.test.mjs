import test from "node:test";
import assert from "node:assert/strict";
import { NAV_ITEMS, filterGraph, healthTone, makeControlCommand, makeDirectorRequest, normalizeLiveApplication, percent, summarize } from "../src/appModel.mjs";

test("navigation contains all Pass 21 operator surfaces", () => {
  const ids = NAV_ITEMS.map(([id]) => id);
  for (const required of ["overview","graph","work","health","budgets","providers","context","recovery","director","incidents","approvals","sync","evidence"]) assert.ok(ids.includes(required));
});

test("summary keeps readiness dimensions distinct", () => {
  const value = summarize({ project_id:"P1", overall_health:"HEALTHY", completion_percent:50, readiness:[{metric_id:"implementation",value:.4},{metric_id:"verification",value:.8}] }, {});
  assert.equal(value.projectId, "P1"); assert.equal(value.implementation, 40); assert.equal(value.verification, 80); assert.notEqual(value.implementation, value.verification);
});

test("graph filtering only retains valid visible edges", () => {
  const filtered = filterGraph({nodes:[{id:"A",label:"Alpha",kind:"task"},{id:"B",label:"Beta",kind:"task"}],edges:[{source:"A",target:"B"}]}, "Alpha");
  assert.equal(filtered.nodes.length,1); assert.equal(filtered.edges.length,0);
});

test("typed control command carries actor, project, correlation, and idempotency", () => {
  const command = makeControlCommand({commandType:"project.pause",projectId:"PROJECT-PIPELINE",actorId:"operator:1",authorityScope:["command-center"]});
  assert.equal(command.schema_version,"1.0.0"); assert.equal(command.project_id,"PROJECT-PIPELINE"); assert.equal(command.actor_id,"operator:1"); assert.match(command.correlation_id,/^cc:/); assert.ok(command.idempotency_key.length >= 8); assert.equal(command.action_intent.operation,"project.pause"); assert.equal(command.action_intent.actor_id,"operator:1"); assert.equal(command.action_intent.approval_state,"APPROVED");
});

test("format helpers are bounded and health tones are deterministic", () => {
  assert.equal(percent(155),"100%"); assert.equal(percent(-5),"0%"); assert.equal(healthTone("HEALTHY"),"good"); assert.equal(healthTone("CRITICAL"),"bad");
});


test("live application projection normalizes canonical backend contract", () => {
  const app = normalizeLiveApplication(
    { completion_gate_state:"NOT_COMPLETE", health:[{name:"system",state:"HEALTHY",reason:"ok"}] },
    { graph:{nodes:[{node_id:"REQ-1",label:"Requirement",kind:"requirement",state:"PARTIAL"}],edges:[]}, evidence:[{evidence_id:"EVID-1",kind:"TEST",status:"VERIFIED",summary:"proof"}], synchronization:[{system:"Jira",mode:"LOCAL_ONLY",stale:true,pending_outbox_count:1,conflict_count:2,note:"stale"}], live_work:[{work_id:"W1",title:"Work",state:"IN_PROGRESS"}], approvals_detail:[], recovery_detail:[], budget_detail:{}, provider_detail:{}, context_detail:{} }
  );
  assert.equal(app.graph.nodes[0].id,"REQ-1"); assert.equal(app.evidence[0].id,"EVID-1"); assert.equal(app.sync[0].pending,1); assert.equal(app.health[0].label,"system"); assert.ok(app.risks.length >= 2);
});


test("Director request cannot smuggle incident context into project scope", () => {
  const project = makeDirectorRequest({message:"status",scope:"PROJECT"});
  assert.equal(project.scope,"PROJECT"); assert.equal(project.incident_id,undefined);
  const incident = makeDirectorRequest({message:"help",scope:"INCIDENT",incidentId:"INCIDENT-AAAAAAAAAAAAAAAAAAAA",conversationId:"conversation:1"});
  assert.equal(incident.incident_id,"INCIDENT-AAAAAAAAAAAAAAAAAAAA"); assert.equal(incident.conversation_id,"conversation:1");
});
