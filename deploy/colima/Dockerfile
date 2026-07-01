# Colima's virtiofs + Docker bind-mounts proved unreliable in this
# environment for BOTH a single file (nginx.conf: "not a directory" mount
# error) and a whole directory (frontend/dist: silently mounted as an
# empty, root-owned directory instead of the real host contents -- verified
# even with a raw `docker run` and an absolute path, ruling out relative-
# path resolution or docker-compose specifically). Baking everything into
# the image at build time sidesteps runtime bind-mounts entirely.
FROM nginx:alpine
COPY deploy/colima/nginx.conf /etc/nginx/nginx.conf
COPY frontend/dist/ /usr/share/nginx/html/
