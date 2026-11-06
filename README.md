# PAG
Projekt zaliczeniowy z przedmiotu Programowanie Aplikacji Geoinformacyjnych.

Silnik nawigacji drogowej dla Torunia wyznaczający trasy na grafie sieci z bazy PostGIS z wykorzystaniem algorytmów Dijkstra oraz A*.

---

## 1. Wymagania i środowisko

Wymagany jest zainstalowany Docker oraz Python 3.

docker-compose up -d
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

---

## 2. Pliki danych i załadowanie do bazy

W głównym katalogu projektu muszą znajdować się 4 pliki źródłowe:
* torun.osm.gz — sieć drogowa Torunia (spakowany XML OSM)
* torun.geojson.gz — obiekty przestrzenne Torunia (granice, atrakcje)
* powiat.osm — sieć drogowa powiatu toruńskiego (XML OSM)
* powiat.geojson.gz — obiekty przestrzenne powiatu toruńskiego

Załadowanie i przetworzenie danych do bazy PostGIS:

python load_data.py

Skrypt rozpakowuje dane, rzutuje je metrycznie, filtruje atrakcje (bufor 100 m) oraz granice miejskie, a następnie tworzy w bazie tabele:
- wezly_torun
- drogi_torun
- pomniki_torun

---

## 3. Silnik routingu (SilnikNawigacji)

Główny moduł silnika znajduje się w pliku silnik.py. 

Klasa SilnikNawigacji przyjmuje przy inicjalizacji URL bazy danych, wczytuje sieć dróg i buduje graf w pamięci.

### Kluczowe metody:
- znajdz_najblizszy_wezel(lon, lat) — rzutuje współrzędne geograficzne GPS na najbliższy węzeł w grafie (osmid).
- astar(start, meta, preferencja_turystyczna=0.0, waga_h=1.0) — wyznacza trasę algorytmem A* (zwraca krotkę: trasa, koszt, atrakcje, odwiedzone_wezly).
- dijkstra(start, meta, preferencja_turystyczna=0.0) — wyznacza trasę referencyjną algorytmem Dijkstry (zwraca krotkę: trasa, koszt, atrakcje, odwiedzone_wezly).
- trasa_na_geojson(trasa) — konwertuje listę węzłów na obiekt GeoJSON (LineString) gotowy do odesłania przez endpoint API i wyświetlenia na mapie.
- trasa_na_wspolrzedne(trasa) — konwertuje listę węzłów na listę współrzędnych [[lat, lon], ...].
