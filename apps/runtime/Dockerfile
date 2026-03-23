FROM node:22-alpine

WORKDIR /app
COPY apps/runtime/package.json ./package.json
COPY apps/runtime/server.mjs ./server.mjs
COPY apps/runtime/selection-overlay.js ./selection-overlay.js

EXPOSE 3001
CMD ["node", "server.mjs"]
