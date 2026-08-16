const API_ROOT = "/api/v1";

export class CommandCenterClient {
  constructor({ token, actorId, fetchImpl = globalThis.fetch } = {}) {
    this.token = token || "";
    this.actorId = actorId || "";
    this.fetchImpl = fetchImpl;
  }

  headers(extra = {}) {
    return {
      Accept: "application/json",
      ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
      ...extra
    };
  }

  async request(path, options = {}) {
    const response = await this.fetchImpl(`${API_ROOT}${path}`, {
      ...options,
      credentials: "same-origin",
      headers: this.headers(options.headers || {})
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return response.json();
  }

  status() { return this.request("/command-center/status"); }
  application() { return this.request("/command-center/application"); }
  inbox() { return this.request("/command-center/inbox"); }
  timeline(afterSequence = 0) { return this.request(`/command-center/timeline?after_sequence=${Number(afterSequence)}`); }
  acknowledge(inboxId) { return this.request(`/command-center/inbox/${encodeURIComponent(inboxId)}/ack`, { method: "POST" }); }
  dispatchInbox(inboxId, localHour = new Date().getHours()) { return this.request(`/command-center/inbox/${encodeURIComponent(inboxId)}/dispatch?local_hour=${Number(localHour)}`, { method: "POST" }); }
  directorChat(request) { return this.request("/director/chat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(request) }); }
  directorHistory(conversationId) { return this.request(`/director/conversations/${encodeURIComponent(conversationId)}`); }
  incidents() { return this.request("/command-center/incidents"); }
  acknowledgeIncident(incidentId) { return this.request(`/command-center/incidents/${encodeURIComponent(incidentId)}/ack`, { method: "POST" }); }
  startIncidentRecovery(incidentId) { return this.request(`/command-center/incidents/${encodeURIComponent(incidentId)}/recovery/start`, { method: "POST" }); }
  verifyIncident(incidentId, verification) { return this.request(`/command-center/incidents/${encodeURIComponent(incidentId)}/verify`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(verification) }); }
  resolveIncident(incidentId) { return this.request(`/command-center/incidents/${encodeURIComponent(incidentId)}/resolve`, { method: "POST" }); }
  control(command) {
    return this.request("/command-center/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(command)
    });
  }

  eventSource(afterSequence = 0) {
    const url = `${API_ROOT}/command-center/events?after_sequence=${Number(afterSequence)}&follow=true`;
    return new EventSource(url, { withCredentials: true });
  }
}

export function createMemorySession() {
  let token = "";
  let actorId = "";
  return {
    get: () => ({ token, actorId }),
    set: (next) => { token = next.token || ""; actorId = next.actorId || ""; },
    clear: () => { token = ""; actorId = ""; }
  };
}
