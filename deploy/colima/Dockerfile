# Colima's virtiofs mount type is unreliable for bind-mounting individual
# files (as opposed to whole directories) -- attempting to bind-mount
# nginx.conf directly produced a persistent "not a directory" mount error
# even though the host file was verified to be a normal file. Baking the
# config into the image at build time sidesteps the issue entirely; only
# frontend/dist (a directory) is still bind-mounted at runtime.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/nginx.conf
