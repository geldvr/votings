## Run local

#### Install postgresql

```bash
apt-get update
apt-get install postgresql postgresql-contrib
```

#### Install pipenv
```bash
pip install pipenv
```

#### Install project environment
```bash
# change current directory to project directory
cd /to/this/project
pipenv sync
```

#### Create DB super user 
```bash
pipenv run python manage.py migrate auth
pipenv run python manage.py migrate
pipenv run python manage.py createsuperuser
```

#### Make DB migrations
```bash
pipenv run python manage.py makemigrations
pipenv run python manage.py migrate
```

### Start application
```bash
pipenv run python manage.py runserver --noreload
```