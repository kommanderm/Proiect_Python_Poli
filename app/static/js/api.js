// Built from wherever the page was served, so the app works on any LAN address and port.
const ORIGIN = `${location.protocol}//${document.domain}${location.port ? `:${location.port}` : ""}`;

async function api(path, { method = "GET", body } = {}) {
  const response = await fetch(ORIGIN + path, {
    method,
    credentials: "same-origin",
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error ?? response.statusText);
  return data;
}
