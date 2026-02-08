FROM node:20-slim

WORKDIR /app

# Copy dependency files first for Docker layer caching
COPY package.json package-lock.json* ./

# Install dependencies
RUN npm install

# Copy application code
COPY . .

EXPOSE 5173

# Run Vite dev server, accessible from outside the container
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
