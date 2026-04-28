FROM node:20-alpine

WORKDIR /app

# Copy package files and install dependencies
COPY package*.json ./
RUN npm install

# Copy the rest of the code
COPY . .

# Expose the Vite default port
EXPOSE 5173

# Run the dev server
# The --host flag is CRITICAL to make it accessible outside the container
CMD ["npm", "run", "dev", "--", "--host"]