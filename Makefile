IMAGE ?= ghcr.io/epoplavskis/mcp-cookidoo
TAG ?= latest

.PHONY: build push login run

login:
	echo $$GITHUB_TOKEN | docker login ghcr.io -u $$GITHUB_USERNAME --password-stdin

build:
	docker build --platform linux/amd64 -t $(IMAGE):$(TAG) .

push: build
	docker push $(IMAGE):$(TAG)

run:
	docker network inspect traefik >/dev/null 2>&1 || docker network create traefik
	docker compose up
