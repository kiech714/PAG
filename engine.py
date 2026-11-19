import heapq
import json
import pandas as pd
from sqlalchemy import create_engine
import re
import math


class SilnikNawigacji:
    # Stałe przeliczeniowe stopni WGS84 na metry dla szerokości geograficznej Torunia (~53.01° N)
    M_PER_DEG_LAT = 111320.0
    M_PER_DEG_LON = 111320.0 * math.cos(math.radians(53.01))

    def __init__(self, db_url):
        self.engine = create_engine(db_url)
        self.graf = {}
        self.wspolrzedne = {}
        self.geometrie_krawedzi = {}
        self.w_miescie = {}
        # Realistyczne prędkości bazowe dla heurystyki (50 km/h w mieście, 90 km/h poza miastem)
        self.max_v_miasto_ms = 50.0 / 3.6
        self.max_v_poza_ms = 90.0 / 3.6
        self.zbuduj_graf()

    def zbuduj_graf(self):
        df_wezly = pd.read_sql("SELECT osmid, x, y, w_miescie FROM wezly_torun", self.engine)

        for row in df_wezly.itertuples(index=False):
            osmid = int(row.osmid)
            self.wspolrzedne[osmid] = (float(row.x), float(row.y))
            self.w_miescie[osmid] = int(row.w_miescie) if pd.notna(row.w_miescie) else 0

        query = """
            SELECT 
                u, v, length, maxspeed, atrakcje,
                ST_AsGeoJSON(geometry) AS geojson
            FROM drogi_torun
        """
        df_drogi = pd.read_sql(query, self.engine)

        def wyciagnij_predkosc(wartosc):
            if pd.isna(wartosc):
                return 50.0
            liczby = re.findall(r'\d+', str(wartosc))
            return float(liczby[0]) if liczby else 50.0

        df_drogi['num_speed'] = df_drogi['maxspeed'].apply(wyciagnij_predkosc)

        loads = json.loads
        wsp = self.wspolrzedne
        geom_kraw = self.geometrie_krawedzi
        graf = self.graf

        for row in df_drogi.itertuples(index=False):
            u = int(row.u)
            v = int(row.v)
            dlugosc = float(row.length)
            v_ms = row.num_speed / 3.6 if row.num_speed > 0 else 13.89

            czas_normalny = dlugosc / v_ms
            atrakcja = str(row.atrakcje).strip() if pd.notna(row.atrakcje) and str(row.atrakcje).strip() != "" else ""
            mnoznik = 0.1 if atrakcja else 1.0

            if u not in graf:
                graf[u] = []
            graf[u].append((v, czas_normalny, mnoznik, atrakcja))

            if row.geojson:
                coords = loads(row.geojson)['coordinates']
                if len(coords) >= 2:
                    if u in wsp:
                        ux, uy = wsp[u]
                        if (coords[-1][0] - ux) ** 2 + (coords[-1][1] - uy) ** 2 < (coords[0][0] - ux) ** 2 + (coords[0][1] - uy) ** 2:
                            coords.reverse()
                    if (u, v) not in geom_kraw or dlugosc < geom_kraw[(u, v)][0]:
                        geom_kraw[(u, v)] = (dlugosc, coords)
            elif u in wsp and v in wsp:
                geom_kraw[(u, v)] = (dlugosc, [list(wsp[u]), list(wsp[v])])

    def znajdz_najblizszy_wezel(self, lon, lat):
        if not self.wspolrzedne:
            return None
        return min(
            self.wspolrzedne.keys(),
            key=lambda w: (self.wspolrzedne[w][0] - lon) ** 2 + (self.wspolrzedne[w][1] - lat) ** 2
        )

    def trasa_na_geojson(self, trasa):
        if not trasa or len(trasa) < 2:
            return {"type": "Feature", "geometry": {"type": "LineString", "coordinates": []}, "properties": {}}

        pelne_coords = []
        for i in range(len(trasa) - 1):
            u = trasa[i]
            v = trasa[i + 1]
            dane_segmentu = self.geometrie_krawedzi.get((u, v))

            if dane_segmentu:
                segment = dane_segmentu[1]
            elif u in self.wspolrzedne and v in self.wspolrzedne:
                segment = [list(self.wspolrzedne[u]), list(self.wspolrzedne[v])]
            else:
                continue

            if not pelne_coords:
                pelne_coords.extend(segment)
            else:
                pelne_coords.extend(segment[1:])

        return {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": pelne_coords
            },
            "properties": {}
        }

    def trasa_na_wspolrzedne(self, trasa):
        geojson = self.trasa_na_geojson(trasa)
        return [[pt[1], pt[0]] for pt in geojson["geometry"]["coordinates"]]

    def _odtworz_trase(self, meta, poprzednicy, atrakcje_krawedzi, preferencja_turystyczna):
        trasa = []
        miniete = set()
        krok = meta
        while krok is not None:
            trasa.append(krok)
            if preferencja_turystyczna > 0.0 and atrakcje_krawedzi.get(krok):
                for a in atrakcje_krawedzi[krok].split(','):
                    if a.strip():
                        miniete.add(a.strip())
            krok = poprzednicy.get(krok)
        trasa.reverse()
        return trasa, list(miniete)

    def dijkstra(self, start, meta, preferencja_turystyczna=0.0):
        wsp = self.wspolrzedne
        if start not in wsp or meta not in wsp:
            return None, float('inf'), [], 0

        koszt_g = {start: 0.0}
        poprzednicy = {start: None}
        atrakcje_krawedzi = {start: None}
        kolejka = [(0.0, start)]
        odwiedzone = set()
        liczba_odwiedzonych = 0
        graf = self.graf
        heappop = heapq.heappop
        heappush = heapq.heappush
        pref = preferencja_turystyczna

        while kolejka:
            _, aktualny = heappop(kolejka)

            if aktualny == meta:
                trasa, atrakcje = self._odtworz_trase(meta, poprzednicy, atrakcje_krawedzi, pref)
                return trasa, koszt_g[meta], atrakcje, liczba_odwiedzonych

            if aktualny in odwiedzone:
                continue
            odwiedzone.add(aktualny)
            liczba_odwiedzonych += 1

            g_akt = koszt_g[aktualny]
            for v, czas_n, mnoznik, atr in graf.get(aktualny, ()):
                koszt_k = czas_n if pref == 0.0 else czas_n * (1.0 - (1.0 - mnoznik) * pref)
                nowy_g = g_akt + koszt_k

                if v not in koszt_g or nowy_g < koszt_g[v]:
                    koszt_g[v] = nowy_g
                    poprzednicy[v] = aktualny
                    if pref > 0.0:
                        atrakcje_krawedzi[v] = atr
                    heappush(kolejka, (nowy_g, v))

        return None, float('inf'), [], liczba_odwiedzonych

    def astar(self, start, meta, preferencja_turystyczna=0.0):
        wsp = self.wspolrzedne
        if start not in wsp or meta not in wsp:
            return None, float('inf'), [], 0

        x_meta, y_meta = wsp[meta]
        w_miescie = self.w_miescie
        meta_w_miescie = w_miescie.get(meta, 0) == 1
        pref = preferencja_turystyczna

        # Skalowanie heurystyki przy trybie turystycznym, by nie pomijać objazdów widokowych
        skala_tur = 1.0 - 0.9 * pref
        inv_v_miasto = skala_tur / self.max_v_miasto_ms
        inv_v_poza = skala_tur / self.max_v_poza_ms
        kx = self.M_PER_DEG_LON
        ky = self.M_PER_DEG_LAT
        sqrt = math.sqrt

        x_s, y_s = wsp[start]
        dx_s = (x_meta - x_s) * kx
        dy_s = (y_meta - y_s) * ky
        h_start = sqrt(dx_s * dx_s + dy_s * dy_s) * (inv_v_miasto if (meta_w_miescie and w_miescie.get(start, 0) == 1) else inv_v_poza)

        koszt_g = {start: 0.0}
        poprzednicy = {start: None}
        atrakcje_krawedzi = {start: None}
        kolejka = [(h_start, start)]
        odwiedzone = set()
        liczba_odwiedzonych = 0
        graf = self.graf
        heappop = heapq.heappop
        heappush = heapq.heappush

        while kolejka:
            _, aktualny = heappop(kolejka)

            if aktualny == meta:
                trasa, atrakcje = self._odtworz_trase(meta, poprzednicy, atrakcje_krawedzi, pref)
                return trasa, koszt_g[meta], atrakcje, liczba_odwiedzonych

            if aktualny in odwiedzone:
                continue
            odwiedzone.add(aktualny)
            liczba_odwiedzonych += 1

            g_akt = koszt_g[aktualny]
            for v, czas_n, mnoznik, atr in graf.get(aktualny, ()):
                koszt_k = czas_n if pref == 0.0 else czas_n * (1.0 - (1.0 - mnoznik) * pref)
                nowy_g = g_akt + koszt_k

                if v not in koszt_g or nowy_g < koszt_g[v]:
                    koszt_g[v] = nowy_g
                    poprzednicy[v] = aktualny
                    if pref > 0.0:
                        atrakcje_krawedzi[v] = atr

                    xv, yv = wsp[v]
                    dx = (x_meta - xv) * kx
                    dy = (y_meta - yv) * ky
                    h = sqrt(dx * dx + dy * dy) * (inv_v_miasto if (meta_w_miescie and w_miescie.get(v, 0) == 1) else inv_v_poza)
                    heappush(kolejka, (nowy_g + h, v))

        return None, float('inf'), [], liczba_odwiedzonych
