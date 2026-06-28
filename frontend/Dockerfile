# Frontend image: Next.js dev server for local Docker Compose.
# Production deploys to Vercel (spec §8), so this image targets local dev.
FROM node:22-alpine

WORKDIR /app

# Install dependencies first to leverage Docker layer caching.
COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
