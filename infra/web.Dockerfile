FROM node:24-alpine
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web/ ./
RUN npm run build
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
