FROM node:22.12-alpine AS builder

COPY package.json package-lock.json tsconfig.json /app/
COPY src /app/src
# index.ts is the CLI/MCP entry point emitted to dist/index.js (see ENTRYPOINT below)
# and globals.d.ts supplies the ambient `process` declaration the build depends on.
# Copying only src/ breaks `npm run build` and produces no dist/index.js.
COPY index.ts globals.d.ts /app/

WORKDIR /app

RUN --mount=type=cache,target=/root/.npm npm install
RUN npm run build

FROM node:22-alpine AS release

COPY --from=builder /app/dist /app/dist
COPY --from=builder /app/package.json /app/package.json
COPY --from=builder /app/package-lock.json /app/package-lock.json

ENV NODE_ENV=production

WORKDIR /app

RUN npm ci --ignore-scripts --omit-dev

USER node

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD node -e "process.exit(0)" || exit 1

ENTRYPOINT ["node", "--max-old-space-size=512", "dist/index.js"]
