FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci --ignore-scripts

COPY tsconfig.json ./
COPY src/ src/
RUN npx tsc

# --- Production ---
FROM node:20-alpine

WORKDIR /app
ENV NODE_ENV=production

COPY package.json package-lock.json* ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force

COPY --from=builder /app/dist/ dist/

# Health check
HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
  CMD wget --spider -q http://127.0.0.1:3100/auth/health || exit 1

EXPOSE 3100
USER node

CMD ["node", "dist/server.js"]
