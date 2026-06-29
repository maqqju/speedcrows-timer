/**
 * Cloudflare Pages Function: /config.js
 *
 * Serves a tiny JS file that sets window.SPRINT_TIMER_API
 * using the SPRINT_TIMER_API environment variable set in the
 * Cloudflare Pages dashboard.
 *
 * The frontend loads this before its own script block,
 * so the API constant picks it up automatically.
 */
export async function onRequest(context) {
  const apiUrl = context.env.SPRINT_TIMER_API || 'http://localhost:8000';

  return new Response(
    `window.SPRINT_TIMER_API = ${JSON.stringify(apiUrl)};`,
    {
      headers: {
        'Content-Type': 'application/javascript',
        'Cache-Control': 'no-store',
      },
    }
  );
}
