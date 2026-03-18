FROM node:22-alpine

WORKDIR /app
COPY apps/runtime/package.json ./package.json
COPY apps/runtime/server.mjs ./server.mjs

EXPOSE 3001
CMD ["node", "server.mjs"]
