# Stage 1: Build super veloce con Vite
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
# Vite inietta le variabili VITE_* nel bundle in fase di build, non a runtime:
# vanno quindi passate come build arg (vedi docker-compose.yml), non come "environment:".
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# Stage 2: Nginx
FROM nginx:alpine
# Vite genera la cartella "dist", non "build"
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]