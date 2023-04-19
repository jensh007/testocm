#! /bin/sh
docker run -d -p 4430:4430 -v $PWD/certs:/certs --name registry -e "REGISTRY_AUTH_HTPASSWD_REALM=Registry Realm" -e REGISTRY_AUTH=htpasswd -e REGISTRY_AUTH_HTPASSWD_PATH=/certs/htpasswd -e REGISTRY_HTTP_ADDR=:4430 -e REGISTRY_HTTP_TLS_CERTIFICATE=/certs/ociregistry.crt -e REGISTRY_HTTP_TLS_KEY=/certs/ociregistry.key registry:2.8.1

# docker run -d -p 4430:4430 -v $PWD/certs:/certs --mount type=bind,source="$(pwd)"/dockercerts,target=/etc/docker/certs.d/TDT7W57RPY.dhcp.wdf.sap.corp:4430 --name registry -e "REGISTRY_AUTH_HTPASSWD_REALM=Registry Realm" -e REGISTRY_AUTH=htpasswd -e REGISTRY_AUTH_HTPASSWD_PATH=/certs/passwd -e REGISTRY_HTTP_ADDR=:4430 -e REGISTRY_HTTP_TLS_CERTIFICATE=/certs/ociregistry.crt -e REGISTRY_HTTP_TLS_KEY=/certs/ociregistry.key registry:2.8.1
#  ocm transfer artifacts gcr.io/google-containers/pause:3.2 ${FQDN_HOST}:4430/images/pause:3.2
# https://github.com/abiosoft/colima/issues/131
# sudo security add-trusted-cert -d -r trustRoot -k "/Library/Keychains/System.keychain" $certificate_file
# for personal key-chain
# security add-trusted-cert -d -r trustRoot -k ~/Library/Keychains/login.keychain ca.crt