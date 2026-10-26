ARG BASE_IMAGE
FROM ${BASE_IMAGE}
WORKDIR /srv
COPY index.html /srv/index.html
USER 10001:10001
EXPOSE 8080
CMD ["busybox", "httpd", "-f", "-p", "8080", "-h", "/srv"]
