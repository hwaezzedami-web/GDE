# Inclus par les blocs /prometheus/ et /alertmanager/ de gsm.conf.
proxy_http_version 1.1;
proxy_set_header Host $host;
proxy_set_header X-Real-IP $remote_addr;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header Authorization "";       # le mot de passe nginx n'est pas transmis
proxy_read_timeout 120s;
proxy_intercept_errors on;
error_page 502 504 = @outil_absent;
# Les interfaces Prometheus et Alertmanager utilisent des scripts intégrés à la page :
# politique de sécurité dédiée, limitée à ces deux chemins.
add_header X-Content-Type-Options nosniff always;
add_header X-Frame-Options DENY always;
add_header Referrer-Policy same-origin always;
add_header Cache-Control "no-store" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-ancestors 'none'" always;
