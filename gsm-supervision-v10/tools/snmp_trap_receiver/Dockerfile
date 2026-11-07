# Récepteur de traps SNMP (alarmes d'OMC) : snmptrapd (Net-SNMP) + scripts Python (bibliothèque standard)
FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends snmptrapd snmp python3 tzdata \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --uid 10002 --home /data trap \
 && mkdir -p /data/spool /run/snmp && chown -R trap /data /run/snmp
COPY entrypoint.sh trap_handler.py alarm_exporter.py /app/
RUN chmod 755 /app/*.sh /app/*.py
USER trap
ENV SNMP_PERSISTENT_DIR=/run/snmp PYTHONUNBUFFERED=1
EXPOSE 1162/udp
ENTRYPOINT ["/app/entrypoint.sh"]
