FROM lordgaav/jython:2.7.0

RUN mkdir -p /usr/src/app
RUN mkdir -p /usr/src/app/log

WORKDIR /usr/src/app

#ONBUILD COPY requirements.txt /usr/src/app/
#ONBUILD RUN pip install --no-cache-dir -r requirements.txt

ADD ./SizedTimedRotatingFileHandler.py /usr/src/app/
ADD ./*.properties /usr/src/app/
ADD ./*.jar /usr/src/app/
ADD ./XMLRPC-bitcoinj.py /usr/src/app/

#ONBUILD COPY ./XMLRPC-bitcoinj.py /usr/src/app
#ONBUILD COPY ./SizedTimedRotatingFileHandler.py /usr/src/app
#ONBUILD COPY ./*.jar /usr/src/app
#ONBUILD COPY ./*.properties /usr/src/app

#RUN ls /usr/src/app/log
ENTRYPOINT jython XMLRPC-bitcoinj.py
