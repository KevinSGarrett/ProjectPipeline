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
