export async function bootstrapDesktopSession() {
  const memory = globalThis.__PP_MEMORY_SESSION__;
  if (memory && memory.token) {
    return { token: memory.token, actorId: memory.actorId || "actor:command-center" };
  }
  if (!("__TAURI_INTERNALS__" in globalThis)) return null;
  const { invoke } = await import("@tauri-apps/api/core");
  const handshake = await invoke("start_or_attach_service");
  const response = await fetch(`${handshake.url}/api/v1/command-center/session/bootstrap`, {
    method: "POST",
    headers: { Accept: "application/json", "Content-Type": "application/json" },
    body: JSON.stringify({ nonce: handshake.nonce, os_identity: handshake.os_identity })
  });
  if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
  const body = await response.json();
  return { token: body.token, actorId: body.actor_id };
}

export async function notifyDesktop({ title, body, actionLink = null }) {
  if (!("__TAURI_INTERNALS__" in globalThis)) return { delivered: false, reason: "NOT_TAURI", actionLinkQualification: "UNAVAILABLE_OUTSIDE_TAURI" };
  const { isPermissionGranted, requestPermission, sendNotification } = await import("@tauri-apps/plugin-notification");
  let allowed = await isPermissionGranted();
  if (!allowed) allowed = (await requestPermission()) === "granted";
  if (!allowed) return { delivered: false, reason: "PERMISSION_DENIED", actionLinkQualification: "NOT_EXERCISED" };
  sendNotification({ title, body });
  return {
    delivered: true,
    reason: "SENT",
    actionLink,
    actionLinkQualification: actionLink ? "UNQUALIFIED_NATIVE_CLICK_HANDLER" : "NOT_REQUESTED"
  };
}
