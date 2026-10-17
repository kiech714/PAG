import osmnx as ox
import geopandas as gpd
from sqlalchemy import create_engine
import warnings

warnings.filterwarnings('ignore')

db_url = 'postgresql+psycopg2://host:<TWOJE_HASLO>@localhost:5433/gis_routing'
engine = create_engine(db_url)

G = ox.graph_from_place('Toruń, Poland', network_type='drive')
nodes, edges = ox.graph_to_gdfs(G)
edges = edges.reset_index()

for column in edges.columns:
    if column == 'geometry':
        continue
    if edges[column].apply(type).eq(list).any():
        edges[column] = edges[column].astype(str)

tagi_turystyczne = {
    'historic': ['monument', 'memorial'],
    'tourism': ['attraction', 'museum']
}
pomniki = ox.features_from_place('Toruń, Poland', tags=tagi_turystyczne)

pomniki_do_bazy = pomniki[['name', 'geometry']].copy()
pomniki_do_bazy = pomniki_do_bazy.dropna(subset=['name'])
pomniki_do_bazy['geometry'] = pomniki_do_bazy.centroid
pomniki_do_bazy = pomniki_do_bazy.reset_index(drop=True)
pomniki_do_bazy.to_postgis(name='pomniki_torun', con=engine, if_exists='replace', index=False)

edges_metry = ox.projection.project_gdf(edges)
pomniki_metry = ox.projection.project_gdf(pomniki)

strefy_gdf = pomniki_metry.dropna(subset=['name'])[['name', 'geometry']].copy()
strefy_gdf = strefy_gdf.rename(columns={'name': 'nazwa_atrakcji'})
strefy_gdf['geometry'] = strefy_gdf.buffer(100)

drogi_w_strefie = gpd.sjoin(edges_metry, strefy_gdf, predicate='intersects')

edges['mnoznik_turystyczny'] = 1.0
edges['atrakcje'] = None

unikalne_id_drog = drogi_w_strefie.index.unique()
edges.loc[unikalne_id_drog, 'mnoznik_turystyczny'] = 0.3

if 'nazwa_atrakcji' in drogi_w_strefie.columns:
    drogi_z_nazwami = drogi_w_strefie.dropna(subset=['nazwa_atrakcji']).copy()
    drogi_z_nazwami['nazwa_atrakcji'] = drogi_z_nazwami['nazwa_atrakcji'].astype(str)

    atrakcje_na_ulicy = drogi_z_nazwami.groupby(drogi_z_nazwami.index)['nazwa_atrakcji'].apply(
        lambda x: ', '.join(x.unique())
    )

    edges.loc[atrakcje_na_ulicy.index, 'atrakcje'] = atrakcje_na_ulicy

edges.to_postgis(name='drogi_torun', con=engine, if_exists='replace', index=False)

nodes = nodes.reset_index()
nodes.to_postgis(name='wezly_torun', con=engine, if_exists='replace', index=False)