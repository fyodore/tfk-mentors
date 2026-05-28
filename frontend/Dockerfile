FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
# `npm ci` fails when the lockfile omits optional transitive entries (e.g. Linux-only
# `@emnapi/*` required by Rolldown WASM bindings). `npm install` resolves the full tree.
RUN npm install --no-audit --no-fund

COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

COPY . .

ENV VITE_API_PROXY=http://web:8000

EXPOSE 5173

ENTRYPOINT ["docker-entrypoint.sh"]
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]
