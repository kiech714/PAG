import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from engine import SilnikNawigacji

app = FastAPI(title="GIS Routing API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_URL = os.getenv(
    "DB_URL",
    "postgresql+psycopg2://host:<TWOJE_HASLO>@localhost:5433/gis_routing",
)
silnik_nawigacji = None


@app.on_event("startup")
def startup_event():
    global silnik_nawigacji
    silnik_nawigacji = SilnikNawigacji(DB_URL)


class TrasaRequest(BaseModel):
    start_lat: float
    start_lon: float
    meta_lat: float
    meta_lon: float
    algorytm: str = "astar"
    preferencja_turystyczna: float = 0.0


@app.post("/api/wyznacz_trase")
def wyznacz_trase(req: TrasaRequest):
    if silnik_nawigacji is None:
        raise HTTPException(
            status_code=503,
            detail="Silnik nawigacji nie został jeszcze zainicjalizowany.",
        )

    try:
        start_node = silnik_nawigacji.znajdz_najblizszy_wezel(
            req.start_lon, req.start_lat
        )
        meta_node = silnik_nawigacji.znajdz_najblizszy_wezel(
            req.meta_lon, req.meta_lat
        )

        if start_node is None or meta_node is None:
            raise HTTPException(
                status_code=404,
                detail="Błąd przestrzenny: Nie znaleziono węzłów wejściowych.",
            )

        pref = req.preferencja_turystyczna
        if req.algorytm == "astar":
            wynik = silnik_nawigacji.astar(
                start_node,
                meta_node,
                preferencja_turystyczna=pref,
            )
        else:
            wynik = silnik_nawigacji.dijkstra(
                start_node,
                meta_node,
                preferencja_turystyczna=pref,
            )

        if not wynik or not wynik[0]:
            raise HTTPException(
                status_code=404,
                detail="Brak topologicznej spójności. Nie znaleziono ścieżki.",
            )

        trasa, koszt, _, odwiedzone_wezly = wynik

        if len(trasa) < 2:
            raise HTTPException(
                status_code=400,
                detail="Punkt początkowy i docelowy rzutują na ten sam węzeł sieci drogowej.",
            )

        wzbogacone_atrakcje = {}
        czas_calkowity_s = 0.0

        for i in range(len(trasa) - 1):
            u = trasa[i]
            v = trasa[i + 1]
            krawedzie_uv = [
                krawedz
                for krawedz in silnik_nawigacji.graf.get(u, ())
                if krawedz[0] == v
            ]
            if not krawedzie_uv:
                continue

            _, czas_n, _, atr = min(
                krawedzie_uv,
                key=lambda k: k[1] if pref == 0.0 else k[1] * (1.0 - (1.0 - k[2]) * pref),
            )
            czas_calkowity_s += czas_n

            if pref > 0.0 and atr:
                for a in atr.split(","):
                    nazwa = a.strip()
                    if nazwa and nazwa not in wzbogacone_atrakcje:
                        lon, lat = silnik_nawigacji.wspolrzedne[v]
                        wzbogacone_atrakcje[nazwa] = {
                            "nazwa": nazwa,
                            "lat": float(lat),
                            "lon": float(lon),
                            "czas_dojazdu_s": round(czas_calkowity_s, 1),
                        }

        trasa_geojson = silnik_nawigacji.trasa_na_geojson(trasa)
        trasa_geojson["properties"]["koszt"] = koszt

        return {
            "trasa_geojson": trasa_geojson,
            "metryki": {
                "koszt": koszt,
                "odwiedzone_wezly_zlozonosc": odwiedzone_wezly,
                "czas_calkowity_s": round(czas_calkowity_s, 1),
            },
            "atrakcje": list(wzbogacone_atrakcje.values()),
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
