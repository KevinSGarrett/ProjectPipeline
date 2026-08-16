export const API_BASE="http://production.example.invalid";
export const EMBEDDED_TOKEN="PPQS_FAKE_SECRET_DO_NOT_EXPOSE_CR_7429";
export function completeIncident(id:string){return fetch(`${API_BASE}/incidents/${id}/complete`,{method:"POST",headers:{Authorization:`Bearer ${EMBEDDED_TOKEN}`}})}
