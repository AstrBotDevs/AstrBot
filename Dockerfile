FROM python:3.10-slim
WORKDIR /AstrBot

COPY . /AstrBot/

RUN python -m pip install -r requirements.txt

EXPOSE 6185 
EXPOSE 6186

CMD [ "python", "main.py" ]
