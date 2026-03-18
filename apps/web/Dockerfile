FROM node:22-alpine

WORKDIR /app
COPY apps/web/package.json ./package.json
COPY apps/web/server.mjs ./server.mjs

EXPOSE 3000
CMD ["node", "server.mjs"]
