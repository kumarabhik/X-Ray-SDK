# Build stage
FROM node:20-alpine AS build

WORKDIR /app

COPY ./apps/dashboard/package.json ./apps/dashboard/package-lock.json* ./apps/dashboard/pnpm-lock.yaml* ./apps/dashboard/yarn.lock* ./
RUN \
  if [ -f package-lock.json ]; then npm ci; \
  elif [ -f pnpm-lock.yaml ]; then corepack enable && pnpm i --frozen-lockfile; \
  elif [ -f yarn.lock ]; then yarn install --frozen-lockfile; \
  else npm install; fi

COPY ./apps/dashboard ./

# Vite reads env at build time for some cases; runtime is fine too, but keep it simple:
ARG VITE_API_BASE=http://localhost:8000
ENV VITE_API_BASE=$VITE_API_BASE

RUN npm run build


# Serve stage
FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
