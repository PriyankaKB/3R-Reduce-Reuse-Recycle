# Stage 1: Build the React Application
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .

# # Set environment variables for the React application
# ARG REACT_APP_ORCHESTRATOR_URL
# ENV REACT_APP_ORCHESTRATOR_URL=$REACT_APP_ORCHESTRATOR_URL

RUN npm run build

# Stage 2: Serve using an ultra-lightweight Nginx server
FROM nginx:1.25-alpine
COPY --from=builder /app/build /usr/share/nginx/html
# Copy custom nginx configuration if handling client-side routing (React Router)
# COPY nginx.conf /etc/nginx/conf.d/default.conf 

EXPOSE 3000
CMD ["nginx", "-g", "daemon off;"]