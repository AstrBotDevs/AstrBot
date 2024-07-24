FROM python:3.10-slim
WORKDIR /AstrBot

COPY . /AstrBot/

RUN python -m pip install -r requirements.txt

CMD [ "python", "main.py" ]
