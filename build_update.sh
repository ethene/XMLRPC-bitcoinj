#!/bin/bash

docker build -t telegram_bot . -f Dockerfile-telegram-conda
docker tag telegram_bot:latest 584051155560.dkr.ecr.eu-west-1.amazonaws.com/telegram_bot:$1
docker push 584051155560.dkr.ecr.eu-west-1.amazonaws.com/telegram_bot:$1
kubectl set image deployments/mercurybot-telegram telegram-bot=584051155560.dkr.ecr.eu-west-1.amazonaws.com/telegram_bot:$1
kubectl set image deployments/mercurybot-gt-telegram telegram-bot=584051155560.dkr.ecr.eu-west-1.amazonaws.com/telegram_bot:$1
