/* Public assets only. No request body, filesystem path or upstream URL is accepted. */
export const SECURITY_HEADERS = {
  "Content-Security-Policy": "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'",
  "X-Frame-Options": "DENY",
  "X-Content-Type-Options": "nosniff",
  "Referrer-Policy": "no-referrer",
  "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
  "Strict-Transport-Security": "max-age=31536000",
};
export function createAssetWorker(assets) {
  function response(body, status, headers = {}) {
    return new Response(body, {status, encodeBody: "manual", headers: {...SECURITY_HEADERS, "Cache-Control": "no-cache", ...headers}});
  }
  return {
    async fetch(request) {
      if (!["GET", "HEAD"].includes(request.method)) {
        return response(request.method === "HEAD" ? null : "Method not allowed", 405, {"Allow": "GET, HEAD", "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"});
      }
      const pathname = new URL(request.url).pathname;
      const key = pathname === "/" ? "/index.html" : pathname;
      if (!Object.hasOwn(assets, key)) return response(request.method === "HEAD" ? null : "Not found", 404, {"Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store"});
      const [mime, encoded] = assets[key];
      const headers = {"Content-Type": mime, "Content-Encoding": "gzip"};
      if (key === "/sw.js") headers["Service-Worker-Allowed"] = "/";
      if (request.method === "HEAD") return response(null, 200, headers);
      const bytes = Uint8Array.from(atob(encoded), char => char.charCodeAt(0));
      return response(bytes, 200, headers);
    },
  };
}
