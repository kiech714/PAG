# PAG
Projekt zaliczeniowy z przedmiotu programowanie aplikacji geoinformacyjnych 
Projekt wykorzystuje konteneryzację do obsługi bazy danych. Wymagany jest zainstalowany Docker.
W terminalu, w głównym folderze projektu wpisz:
```bash
docker-compose up -d
python -m venv venv
source venv/bin/activate  # na systemie Windows: venv\Scripts\activate
pip install -r requirements.txt
python load_data.py
