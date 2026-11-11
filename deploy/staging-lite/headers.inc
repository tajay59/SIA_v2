# Security headers for every response (included at server level and again in locations that add headers).
add_header X-Content-Type-Options nosniff always;
add_header Referrer-Policy no-referrer always;
add_header X-Frame-Options DENY always;
add_header Content-Security-Policy $csp always;
add_header Permissions-Policy "camera=(self), microphone=(), geolocation=()" always;
add_header Strict-Transport-Security "max-age=31536000" always;
add_header Cross-Origin-Resource-Policy same-site always;
