FROM node:22-alpine

WORKDIR /app

RUN npm config set strict-ssl false
RUN npm install -g pnpm@10.6.2

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml turbo.json tsconfig.base.json ./
COPY apps ./apps
COPY packages ./packages

RUN pnpm install --frozen-lockfile
RUN pnpm --filter @local-figma/web build

EXPOSE 3000
CMD ["pnpm", "--filter", "@local-figma/web", "start"]
