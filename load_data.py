import osmnx as ox
import geopandas as gpd
from sqlalchemy import create_engine
import gzip
import shutil
import os
import warnings

warnings.filterwarnings('ignore')

path_osm_gz = 'torun.osm.gz'
path_geojson_gz = 'torun.geojson.gz'
path_osm_powiat = 'powiat.osm'
path_geojson_powiat = 'powiat.geojson.gz'

engine = create_engine('postgresql+psycopg2://host:<TWOJE_HASLO>@localhost:5433/gis_routing')

with gzip.open(path_osm_gz, 'rb') as f_in, open('torun_temp.osm', 'wb') as f_out:
    shutil.copyfileobj(f_in, f_out)

G = ox.graph_from_xml('torun_temp.osm', retain_all=True)
if os.path.exists('torun_temp.osm'):
    os.remove('torun_temp.osm')

nodes, edges = ox.graph_to_gdfs(G)
edges = edges.reset_index()

for col in edges.columns:
    if col != 'geometry' and edges[col].apply(type).eq(list).any():
        edges[col] = edges[col].astype(str)

with gzip.open(path_geojson_gz, 'rb') as f_in, open('torun_temp.geojson', 'wb') as f_out:
    shutil.copyfileobj(f_in, f_out)

wszystkie_dane = gpd.read_file('torun_temp.geojson')
if os.path.exists('torun_temp.geojson'):
    os.remove('torun_temp.geojson')

if 'historic' in wszystkie_dane.columns and 'tourism' in wszystkie_dane.columns:
    pomniki = wszystkie_dane[
        wszystkie_dane['historic'].isin(['monument', 'memorial']) |
        wszystkie_dane['tourism'].isin(['attraction', 'museum'])
        ].copy()
else:
    pomniki = gpd.GeoDataFrame(columns=['name', 'geometry'], crs=wszystkie_dane.crs)

if not pomniki.empty and 'name' in pomniki.columns:
    p_baza = pomniki[['name', 'geometry']].copy().dropna(subset=['name'])
    p_baza['geometry'] = p_baza.centroid
    p_baza.reset_index(drop=True).to_postgis(name='pomniki_torun', con=engine, if_exists='replace', index=False)

edges_metry = ox.projection.project_gdf(edges)
nodes_metry = ox.projection.project_gdf(nodes)

edges['obok_atrakcji'] = 0
edges['atrakcje'] = None

if not pomniki.empty and 'name' in pomniki.columns:
    pomniki_metry = ox.projection.project_gdf(pomniki)
    strefy_gdf = pomniki_metry.dropna(subset=['name'])[['name', 'geometry']].copy()
    strefy_gdf = strefy_gdf.rename(columns={'name': 'nazwa_atrakcji'})
    strefy_gdf['geometry'] = strefy_gdf.buffer(100)

    drogi_w_strefie = gpd.sjoin(edges_metry, strefy_gdf, predicate='intersects')
    edges.loc[drogi_w_strefie.index.unique(), 'obok_atrakcji'] = 1

    if 'nazwa_atrakcji' in drogi_w_strefie.columns:
        d_nazwy = drogi_w_strefie.dropna(subset=['nazwa_atrakcji']).copy()
        d_nazwy['nazwa_atrakcji'] = d_nazwy['nazwa_atrakcji'].astype(str)
        atrakcje_ulica = d_nazwy.groupby(d_nazwy.index)['nazwa_atrakcji'].apply(lambda x: ', '.join(x.unique()))
        edges.loc[atrakcje_ulica.index, 'atrakcje'] = atrakcje_ulica

if 'place' in wszystkie_dane.columns:
    granice_miast = wszystkie_dane[
        wszystkie_dane['place'].isin(['city', 'town']) &
        wszystkie_dane.geometry.type.isin(['Polygon', 'MultiPolygon'])
        ].copy()
else:
    granice_miast = gpd.GeoDataFrame(columns=['geometry'], crs=wszystkie_dane.crs)

if not granice_miast.empty:
    g_metry = ox.projection.project_gdf(granice_miast)
    edges['w_miescie'] = 0
    nodes['w_miescie'] = 0
    edges.loc[gpd.sjoin(edges_metry, g_metry[['geometry']], predicate='intersects').index.unique(), 'w_miescie'] = 1
    nodes.loc[gpd.sjoin(nodes_metry, g_metry[['geometry']], predicate='within').index.unique(), 'w_miescie'] = 1
else:
    edges['w_miescie'] = 1
    nodes['w_miescie'] = 1

edges.to_postgis(name='drogi_torun', con=engine, if_exists='replace', index=False)
nodes.reset_index().to_postgis(name='wezly_torun', con=engine, if_exists='replace', index=False)

G_powiat = ox.graph_from_xml(path_osm_powiat, retain_all=True)
nodes_powiat, edges_powiat = ox.graph_to_gdfs(G_powiat)
edges_powiat = edges_powiat.reset_index()

for col in edges_powiat.columns:
    if col != 'geometry' and edges_powiat[col].apply(type).eq(list).any():
        edges_powiat[col] = edges_powiat[col].astype(str)

with gzip.open(path_geojson_powiat, 'rb') as f_in, open('powiat_temp.geojson', 'wb') as f_out:
    shutil.copyfileobj(f_in, f_out)

dane_powiat = gpd.read_file('powiat_temp.geojson')
if os.path.exists('powiat_temp.geojson'):
    os.remove('powiat_temp.geojson')

if 'historic' in dane_powiat.columns and 'tourism' in dane_powiat.columns:
    pomniki_p = dane_powiat[
        dane_powiat['historic'].isin(['monument', 'memorial']) |
        dane_powiat['tourism'].isin(['attraction', 'museum'])
        ].copy()
else:
    pomniki_p = gpd.GeoDataFrame(columns=['name', 'geometry'], crs=dane_powiat.crs)

if not pomniki_p.empty and 'name' in pomniki_p.columns:
    p_baza_p = pomniki_p[['name', 'geometry']].copy().dropna(subset=['name'])
    p_baza_p['geometry'] = p_baza_p.centroid
    p_baza_p_res = p_baza_p.reset_index(drop=True)
    if not p_baza_p_res.empty:
        p_baza_p_res.to_postgis(name='pomniki_torun', con=engine, if_exists='append', index=False)

edges_metry_p = ox.projection.project_gdf(edges_powiat)
pomniki_metry_p = ox.projection.project_gdf(pomniki_p) if not pomniki_p.empty else None

edges_powiat['obok_atrakcji'] = 0
edges_powiat['atrakcje'] = None

if pomniki_metry_p is not None and not pomniki_metry_p.empty and 'name' in pomniki_metry_p.columns:
    strefy_p = pomniki_metry_p.dropna(subset=['name'])[['name', 'geometry']].copy()
    strefy_p = strefy_p.rename(columns={'name': 'nazwa_atrakcji'})
    strefy_p['geometry'] = strefy_p.buffer(100)

    drogi_strefa_p = gpd.sjoin(edges_metry_p, strefy_p, predicate='intersects')
    edges_powiat.loc[drogi_strefa_p.index.unique(), 'obok_atrakcji'] = 1

    if 'nazwa_atrakcji' in drogi_strefa_p.columns:
        d_nazwy_p = drogi_strefa_p.dropna(subset=['nazwa_atrakcji']).copy()
        d_nazwy_p['nazwa_atrakcji'] = d_nazwy_p['nazwa_atrakcji'].astype(str)
        atrakcje_p = d_nazwy_p.groupby(d_nazwy_p.index)['nazwa_atrakcji'].apply(lambda x: ', '.join(x.unique()))
        edges_powiat.loc[atrakcje_p.index, 'atrakcje'] = atrakcje_p

edges_powiat['w_miescie'] = 0
nodes_powiat['w_miescie'] = 0

if 'osmid' in edges_powiat.columns and type(edges_powiat['osmid'].iloc[0]) == list:
    edges_powiat['osmid'] = edges_powiat['osmid'].astype(str)

edges_powiat.to_postgis(name='drogi_torun', con=engine, if_exists='append', index=False)
nodes_powiat.reset_index().to_postgis(name='wezly_torun', con=engine, if_exists='append', index=False)
