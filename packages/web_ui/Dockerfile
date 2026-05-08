# Solamon web-ui container.
#
# Build from the repo root:
#   docker buildx build --platform linux/arm64 \
#     -t <registry>/solamon-web-ui:vX.Y.Z \
#     -f packages/web_ui/Dockerfile \
#     --push \
#     .

FROM node:22-bookworm-slim AS base

ENV NEXT_TELEMETRY_DISABLED=1 \
    PNPM_HOME=/pnpm
ENV PATH="${PNPM_HOME}:${PATH}"

WORKDIR /app
RUN corepack enable

FROM base AS deps
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY packages/web_ui/package.json packages/web_ui/package.json
RUN pnpm install --filter web_ui --frozen-lockfile

FROM deps AS builder
COPY packages/web_ui packages/web_ui
RUN pnpm install --filter web_ui --frozen-lockfile --offline \
 && pnpm --filter web_ui build

FROM node:22-bookworm-slim AS runner

ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    HOSTNAME=0.0.0.0 \
    PORT=3000

WORKDIR /app
USER node

COPY --from=builder --chown=node:node /app/packages/web_ui/.next/standalone ./
COPY --from=builder --chown=node:node /app/packages/web_ui/.next/static ./packages/web_ui/.next/static

EXPOSE 3000
CMD ["node", "packages/web_ui/server.js"]
