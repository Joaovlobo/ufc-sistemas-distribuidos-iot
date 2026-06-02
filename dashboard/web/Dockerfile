FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

# Expõe a porta do Vite
EXPOSE 5173

# Executa o vite em host 0.0.0.0
CMD ["npm", "run", "dev", "--", "--host"]
