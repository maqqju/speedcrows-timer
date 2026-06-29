export async function onRequest(context) {
  // 1. Fetch the actual static index.html file
  const response = await context.next();
  
  // 2. Only run this logic if it's the main HTML document
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("text/html")) {
    
    // Get your live Render URL from Cloudflare Env
    const apiEnv = context.env.SPRINT_TIMER_API || 'http://localhost:5000';
    
    // Inject a global window variable right before the closing head tag
    const scriptInjection = `<script>window.ENV = { SPRINT_TIMER_API: "${apiEnv}" };</script></head>`;
    const scriptInjection = `<script>window.SPRINT_TIMER_API = "${apiEnv}";</script></head>`;
    
    const originalHtml = await response.text();
    const modifiedHtml = originalHtml.replace("</head>", scriptInjection);
    
    return new Response(modifiedHtml, response);
  }
  
  return response;
}