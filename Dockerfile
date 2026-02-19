FROM python:3.12-alpine

# openconnect + runtime deps (vpnc-script, ip command)
RUN sed -i 's|^#\(.*community\)|\1|' /etc/apk/repositories && \
    apk add --no-cache openconnect vpnc iproute2 && \
    rm -rf /var/cache/apk/*

# Python deps
COPY app/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt

# Application
COPY app/ /app/
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
