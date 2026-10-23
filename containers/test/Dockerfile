ARG BASE_IMAGE=alpine:3.23.6
FROM ${BASE_IMAGE}
RUN if command -v apk >/dev/null 2>&1; then apk add --no-cache busybox-extras; fi
WORKDIR /srv
COPY index.html /srv/index.html
COPY --chmod=0555 serve.sh /usr/local/bin/team4-serve
USER 10001:10001
EXPOSE 8080
CMD ["/usr/local/bin/team4-serve"]
