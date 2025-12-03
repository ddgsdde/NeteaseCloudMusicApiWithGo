FROM golang:1.20-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o singo main.go

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/singo .
COPY --from=builder /app/conf ./conf

EXPOSE 3333
CMD ["./singo"]
