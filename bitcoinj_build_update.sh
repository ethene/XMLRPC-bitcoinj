#!/bin/bash
docker build -t bitcoinj .
docker tag bitcoinj:latest 584051155560.dkr.ecr.eu-west-1.amazonaws.com/bitcoinj:$1
docker push 584051155560.dkr.ecr.eu-west-1.amazonaws.com/bitcoinj:$1
kubectl set image deployments/mercurybot-bitcoinj bitcoinj=584051155560.dkr.ecr.eu-west-1.amazonaws.com/bitcoinj:$1