FROM python:2.7-alpine
WORKDIR /usr/src/app
EXPOSE 5000
RUN pip install --upgrade \
	sqlalchemy \
	oauth2client \
	requests \
	werkzeug==0.8.3 \
	flask==0.9 \
	Flask-Login==0.1.3

# Create database
COPY database_setup.py database_setup.py
RUN python database_setup.py

# Seed database
COPY lotsofmenus.py lotsofmenus.py
RUN python lotsofmenus.py

COPY . .
ENTRYPOINT [ "python", "project.py" ]

# ENTRYPOINT [ "./startup.sh" ]

