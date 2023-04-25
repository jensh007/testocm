env GOOS=linux GOARCH=arm64 GO111MODULE=on go build -o local/hello.arm64 -ldflags '-extldflags "-static"' main.go
env GOOS=linux GOARCH=amd64 GO111MODULE=on go build -o local/hello.amd64 -ldflags '-extldflags "-static"' main.go
docker build -f Dockerfile.arm64 --tag hello-arm64:0.1.0 --tag eu.gcr.io/sap-cp-k8s-ocm-gcp-eu30-dev/dev/d058463/images/hello-arm64:0.1.0 .
docker build -f Dockerfile.amd64 --tag hello-amd64:0.1.0 --tag eu.gcr.io/sap-cp-k8s-ocm-gcp-eu30-dev/dev/d058463/images/hello-amd64:0.1.0 .
