# Étape 1 : compilation de l'interface
FROM node:22-alpine AS build
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
ARG VITE_TILE_URL
ARG VITE_TILE_ATTRIBUTION
ARG VITE_REFRESH_SECONDS=60
ARG VITE_BASEMAP=offline
RUN npm run build

# Étape 2 : service des fichiers statiques + relais /api vers le backend
FROM nginx:1.27-alpine
COPY deploy/nginx/gsm.conf /etc/nginx/conf.d/default.conf
COPY deploy/nginx/outils.inc /etc/nginx/conf.d/outils.inc
COPY --from=build /src/dist /usr/share/nginx/html
EXPOSE 8080
