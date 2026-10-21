import {callEngine} from "./engine-client.js";
export async function apiRequest(route, options = {}) {
  const headers = new Headers(options.headers);
  const metadata = {
    name: decodeURIComponent(headers.get("X-File-Name") || "selected-file"),
    expected: headers.get("X-Expected-SHA256"),
    policy: headers.get("X-Lab-Policy") || "baseline",
    replay: headers.has("X-Replay-Count") ? Number(headers.get("X-Replay-Count")) : null,
  };
  const result = await callEngine(route, options.body, metadata, options.signal);
  return new Response(JSON.stringify(result.data), {status: result.status, headers: {"Content-Type": "application/json"}});
}
