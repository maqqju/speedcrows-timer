export async function onRequest(context) {
  // 1. Let the request proceed to get the static index.html file
  const response = await context.next();
  
  // 2. Only intercept and modify if it's the actual HTML page
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("text/html")) {
    
    // Grabs your environment variable configured in the Cloudflare Dashboard
    const apiEnv = context.env.SPRINT_TIMER_API || 'http://localhost:8000';
    
    // Prepares the script string to inject right before the closing </head> tag
    const scriptInjection = `<script>window.ENV = { SPRINT_TIMER_API: "${apiEnv}" };</script></head>`;
    
    const originalHtml = await response.text();
    const modifiedHtml = originalHtml.replace("</head>", scriptInjection);
    
    return new Response(modifiedHtml, response);
  }
  
  return response;
}