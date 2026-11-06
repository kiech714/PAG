import heapq
import pandas as pd
from sqlalchemy import create_engine
import re
import math


class SilnikNawigacji:
    def __init__(self, db_url):
        self.engine = create_engine(db_url)
        self.graf = {}
        self.wspolrzedne = {}
        self.w_miescie = {}
        self.max_v_miasto_ms = 13.89
        self.max_v_poza_ms = 25.0
        self.zbuduj_graf()

    def zbuduj_graf(self):
        df_wezly = pd.read_sql("SELECT osmid, x, y, w_miescie FROM wezly_torun", self.engine)

        for _, wiersz in df_wezly.iterrows():
            osmid = int(wiersz['osmid'])
            self.wspolrzedne[osmid] = (float(wiersz['x']), float(wiersz['y']))
            self.w_miescie[osmid] = int(wiersz['w_miescie']) if 'w_miescie' in df_wezly.columns and pd.notna(wiersz['w_miescie']) else 0

        df_drogi = pd.read_sql("SELECT u, v, length, maxspeed, atrakcje, w_miescie FROM drogi_torun", self.engine)

        def wyciagnij_predkosc(wartosc):
            if pd.isna(wartosc):
                return 50.0
            liczby = re.findall(r'\d+', str(wartosc))
            return float(liczby[0]) if liczby else 50.0

        df_drogi['num_speed'] = df_drogi['maxspeed'].apply(wyciagnij_predkosc)
        
        if 'w_miescie' in df_drogi.columns:
            m_s = df_drogi[df_drogi['w_miescie'] == 1]['num_speed']
            p_s = df_drogi[df_drogi['w_miescie'] == 0]['num_speed']
            self.max_v_miasto_ms = (m_s.max() if not m_s.empty and m_s.max() > 0 else 50.0) / 3.6
            self.max_v_poza_ms = (p_s.max() if not p_s.empty and p_s.max() > 0 else 90.0) / 3.6

        for _, wiersz in df_drogi.iterrows():
            u = int(wiersz['u'])
            v = int(wiersz['v'])
            dlugosc = float(wiersz['length'])
            v_ms = wiersz['num_speed'] / 3.6 if wiersz['num_speed'] > 0 else 13.89
            
            czas_normalny = dlugosc / v_ms
            atrakcja = str(wiersz['atrakcje']) if pd.notna(wiersz['atrakcje']) and str(wiersz['atrakcje']).strip() != "" else ""
            mnoznik = 0.5 if atrakcja else 1.0

            if u not in self.graf:
                self.graf[u] = []
            self.graf[u].append((v, czas_normalny, mnoznik, atrakcja))

    def znajdz_najblizszy_wezel(self, lon, lat):
        if not self.wspolrzedne:
            return None
        return min(
            self.wspolrzedne.keys(),
            key=lambda w: (self.wspolrzedne[w][0] - lon) ** 2 + (self.wspolrzedne[w][1] - lat) ** 2
        )

    def trasa_na_wspolrzedne(self, trasa):
        return [[self.wspolrzedne[w][1], self.wspolrzedne[w][0]] for w in trasa if w in self.wspolrzedne]

    def trasa_na_geojson(self, trasa):
        wspolrzedne_geojson = [[self.wspolrzedne[w][0], self.wspolrzedne[w][1]] for w in trasa if w in self.wspolrzedne]
        return {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": wspolrzedne_geojson
            },
            "properties": {}
        }

    def _heurystyka(self, wezel_a, meta):
        x1, y1 = self.wspolrzedne[wezel_a]
        x2, y2 = self.wspolrzedne[meta]
        dystans = math.sqrt(((x2 - x1) * math.cos(math.radians((y1 + y2) / 2)) * 111320) ** 2 + ((y2 - y1) * 111320) ** 2)
        v_max = self.max_v_miasto_ms if (self.w_miescie.get(wezel_a, 0) == 1 or self.w_miescie.get(meta, 0) == 1) else self.max_v_poza_ms
        return dystans / v_max if v_max > 0 else dystans / 13.89

    def _odtworz_trase(self, meta, poprzednicy, atrakcje_krawedzi, preferencja_turystyczna):
        trasa = []
        mijetne = set()
        krok = meta
        while krok is not None:
            trasa.append(krok)
            if preferencja_turystyczna > 0.0 and atrakcje_krawedzi.get(krok):
                for a in atrakcje_krawedzi[krok].split(','):
                    if a.strip():
                        mijetne.add(a.strip())
            krok = poprzednicy.get(krok)
        trasa.reverse()
        return trasa, list(mijetne)

    def dijkstra(self, start, meta, preferencja_turystyczna=0.0):
        if start not in self.wspolrzedne or meta not in self.wspolrzedne:
            return None, float('inf'), [], 0

        koszt_g = {start: 0.0}
        poprzednicy = {start: None}
        atrakcje_krawedzi = {start: None}
        kolejka = [(0.0, start)]
        odwiedzone = set()
        liczba_odwiedzonych = 0

        while kolejka:
            _, aktualny = heapq.heappop(kolejka)

            if aktualny == meta:
                trasa, atrakcje = self._odtworz_trase(meta, poprzednicy, atrakcje_krawedzi, preferencja_turystyczna)
                return trasa, koszt_g[meta], atrakcje, liczba_odwiedzonych

            if aktualny in odwiedzone:
                continue
            odwiedzone.add(aktualny)
            liczba_odwiedzonych += 1

            if aktualny not in self.graf:
                continue

            for v, czas_n, mnoznik, atr in self.graf[aktualny]:
                koszt_k = czas_n * (1.0 - (1.0 - mnoznik) * preferencja_turystyczna)
                nowy_g = koszt_g[aktualny] + koszt_k

                if v not in koszt_g or nowy_g < koszt_g[v]:
                    koszt_g[v] = nowy_g
                    poprzednicy[v] = aktualny
                    atrakcje_krawedzi[v] = atr if preferencja_turystyczna > 0.0 else None
                    heapq.heappush(kolejka, (nowy_g, v))

        return None, float('inf'), [], liczba_odwiedzonych

    def astar(self, start, meta, preferencja_turystyczna=0.0, waga_h=1.0):
        if start not in self.wspolrzedne or meta not in self.wspolrzedne:
            return None, float('inf'), [], 0

        koszt_g = {start: 0.0}
        poprzednicy = {start: None}
        atrakcje_krawedzi = {start: None}
        h_start = waga_h * self._heurystyka(start, meta)
        kolejka = [(h_start, start)]
        odwiedzone = set()
        liczba_odwiedzonych = 0

        while kolejka:
            _, aktualny = heapq.heappop(kolejka)

            if aktualny == meta:
                trasa, atrakcje = self._odtworz_trase(meta, poprzednicy, atrakcje_krawedzi, preferencja_turystyczna)
                return trasa, koszt_g[meta], atrakcje, liczba_odwiedzonych

            if aktualny in odwiedzone:
                continue
            odwiedzone.add(aktualny)
            liczba_odwiedzonych += 1

            if aktualny not in self.graf:
                continue

            for v, czas_n, mnoznik, atr in self.graf[aktualny]:
                koszt_k = czas_n * (1.0 - (1.0 - mnoznik) * preferencja_turystyczna)
                nowy_g = koszt_g[aktualny] + koszt_k

                if v not in koszt_g or nowy_g < koszt_g[v]:
                    koszt_g[v] = nowy_g
                    poprzednicy[v] = aktualny
                    atrakcje_krawedzi[v] = atr if preferencja_turystyczna > 0.0 else None
                    f = nowy_g + (waga_h * self._heurystyka(v, meta))
                    heapq.heappush(kolejka, (f, v))

        return None, float('inf'), [], liczba_odwiedzonych
