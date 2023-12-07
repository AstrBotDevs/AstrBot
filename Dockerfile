FROM python:3.10.13-bullseye
WORKDIR /AstrBot

COPY . /AstrBot/

RUN python -m pip install -r requirements.txt
RUN python -m pip install

CMD [ "python", "main.py" ]