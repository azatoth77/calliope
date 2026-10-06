# Immagine della sandbox degli agenti (03/10/2026): il codice scritto dall'agente gira qui
# dentro, un container usa-e-getta per ogni esecuzione (calliope/agenti/sandbox.py, motore
# «docker»). Si costruisce con setup/linux/motore/sandbox.sh costruisci (o «calliope motore
# sandbox costruisci»); il nome è calliope-sandbox:<prime 12 cifre dello SHA-256 di questo
# file>, così una modifica qui vuol dire un'immagine nuova e Calliope non usa quella vecchia.
#
# Solo Python e le librerie che il prompt dell'agente nomina (libreria standard, openpyxl,
# python-docx) più numpy, fpdf2 e PyYAML: le stesse versioni di uv.lock. Niente compilatori,
# niente pip nell'immagine finale (l'agente non installa nulla, e comunque non ha rete).
# Dal 05/10 anche BeautifulSoup per i parser delle estensioni (beautifulsoup4, soupsieve,
# typing-extensions: tre wheel py3-none-any, niente codice nativo) con html.parser della
# libreria standard. lxml no: libxml2 e libxslt in C (~5 MB in più, una storia lunga di
# vulnerabilità nel parser), e per leggere pagine di dati html.parser basta.
# Lo script _avvio.py non è nell'immagine: si monta in sola lettura dalla versione di
# Calliope in uso, così segue gli aggiornamenti senza ricostruire.
FROM python:3.12-slim

RUN pip install --no-cache-dir --no-compile \
        numpy==2.5.3 openpyxl==3.1.5 python-docx==1.2.0 fpdf2==2.8.9 pyyaml==6.0.3 \
    && pip install --no-cache-dir --no-compile --no-deps --only-binary=:all: \
        beautifulsoup4==4.15.0 soupsieve==2.10 typing-extensions==4.16.0 \
    && pip uninstall -y pip setuptools wheel 2>/dev/null; \
    rm -rf /root/.cache /usr/local/lib/python3.12/ensurepip \
    && mkdir -p /lavoro /opt/calliope \
    && python -c "import numpy, openpyxl, docx, fpdf, yaml, bs4; print('librerie ok')"

LABEL calliope.sandbox="1"
# Utente non root: Calliope comunque lancia con --user <uid>:<gid> dell'utente del servizio,
# così i file scritti nella cartella del lavoro restano suoi
USER 65534:65534
WORKDIR /lavoro
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONIOENCODING=utf-8 LANG=C.UTF-8 \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1
