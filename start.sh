#!/bin/sh
echo "starting server"

python3 manage.py makemigrations
echo "migrating database"
python3 manage.py migrate
echo "starting server"

python3 manage.py runserver 0.0.0.0:80
