FROM node:18.12.1-bullseye-slim

RUN npm install -g npm@9.1.3

WORKDIR /usr/src/app

COPY package*.json ./
RUN npm install --omit=dev

COPY app.js ./
COPY review.js ./
COPY dealership.js ./
COPY data ./data

EXPOSE 3030

CMD [ "node", "app.js" ]
