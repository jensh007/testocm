#! /bin/sh
id=`docker ps -q -f name="registry"`
docker stop registry && docker rm registry