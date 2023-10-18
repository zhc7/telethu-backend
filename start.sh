#!/bin/sh
echo "starting redis"
service redis-server start
echo "preparing server"
python3 manage.py makemigrations
echo "migrating database"
python3 manage.py migrate
echo "starting rabbitmq"
systemctl start rabbitmq-server
echo "starting server"
python3 manage.py runserver 0.0.0.0:80
