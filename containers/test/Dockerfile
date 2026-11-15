ARG BASE_IMAGE=alpine:3.23.6
FROM ${BASE_IMAGE}
# Refresh security fixes even when the pinned base image still has older APKs.
# Every built digest is scanned and gets its own SBOM before it can be published.
RUN apk upgrade --no-cache musl musl-utils zlib && apk add --no-cache busybox-extras
WORKDIR /srv
COPY index.html /srv/index.html
COPY --chmod=0555 serve.sh /usr/local/bin/team4-serve
USER 10001:10001
EXPOSE 8080
CMD ["/usr/local/bin/team4-serve"]
