import pandas as pd
import numpy as np
import datetime

from bokeh.plotting import figure, output_file, curdoc
from bokeh.tile_providers import get_provider, OSM
from bokeh.models import ColumnDataSource, CDSView, BooleanFilter, TableColumn, DataTable
from bokeh.layouts import layout
from bokeh.models import DateRangeSlider, Div, Dropdown
from bokeh.transform import factor_cmap
from pyproj import Transformer

test_df = pd.read_pickle('./data/data.pkl')

# data transformation
in_crs = 4326  # coordinates provided in EPSG:4326 format
out_crs = 3857  # coordinates output in EPSG 3857 (Web Mercator) format

transformer = Transformer.from_crs(in_crs, out_crs, always_xy=True)

lons, lats = [], []
for lon, lat in list(zip(test_df['longitude'], test_df['latitude'])):
    x, y = transformer.transform(lon, lat)
    lons.append(x)
    lats.append(y)

test_df['MercatorX'] = lons
test_df['MercatorY'] = lats

# visualization

tile_provider = get_provider(OSM)
tools = ['pan', 'zoom_in', 'zoom_out', 'wheel_zoom', 'box_zoom', 'lasso_select', 'tap', 'hover', 'reset', 'save']

tooltips = [
    ("Date", '@datetime'),
    ('Location: ', '@city, @region'),
    ('Country: ', '@country'),
    ('Event Type: ', '@festival_flag'),
    ('Lineup: ', '@lineup'),
    ('', '__________________')
]

source = ColumnDataSource(test_df)
view = CDSView(source=source)

text_header = Div(text='<H1>Live Music Across Time<H1>', width=300, height=60)

show_dat = source.data['show_date']

# columns = [
#     TableColumn(field='artist', title='Artist'),
#     TableColumn(field='lineup', title='Co-Performing Artists')
# ]
#
# table_data = test_df[['artist','lineup']].explode('lineup').drop_duplicates(ignore_index=True)
# table_data = table_data[table_data['lineup'] != table_data['artist']]
# table_source = ColumnDataSource(table_data)
# table = DataTable(source=table_source, columns=columns)

def ts_extract(xl_timestamp):
    d = datetime.datetime.fromtimestamp(int(xl_timestamp / 1000)).strftime('%Y-%m-%d')
    return d


# https://stackoverflow.com/questions/64458556/how-to-define-python-bokeh-rangeslider-on-change-callback-function-to-alter-inde
# https://medium.com/y-data-stories/python-and-bokeh-part-ii-d81024c9578f

def update(attr, old, new):
    start = ts_extract(new[0])
    end = ts_extract(new[1])
    data = source.data
    mask = np.logical_and(data['datetime'] > start, data['datetime'] < end)
    view.filters = [BooleanFilter(mask)]


date_slider = DateRangeSlider(
    title=" Adjust Event Date Range",
    start=min(test_df['datetime']),
    end=max(test_df['datetime']),
    width=1235,
    step=1,
    value=(
        min(test_df['datetime']), max(test_df['datetime'])
    )
)

date_slider.on_change('value', update)

# color map for circles object
color_map = factor_cmap('festival_flag', palette=['dodgerblue', 'darkorange'],
                        factors=sorted(test_df['festival_flag'].unique()))


def update_artist(event):
    data = source.data
    mask = data['artist'] == str(event.item)
    view.filters = [BooleanFilter(mask)]


artist_menu = list(set(test_df['artist']))
artist_dropdown = Dropdown(label="Artist", button_type="warning", menu=artist_menu)
artist_dropdown.on_click(update_artist)


def update_country(event):
    data = source.data
    mask = data['country'] == str(event.item)
    view.filters = [BooleanFilter(mask)]


country_menu = list(set(test_df['country']))
country_dropdown = Dropdown(label="Country", button_type="warning", menu=country_menu)
country_dropdown.on_click(update_country)


def update_city(event):
    print(event.item)
    data = source.data
    mask = data['city'] == str(event.item)
    print(mask)
    view.filters = [BooleanFilter(mask)]


city_menu = list(set(test_df['city']))
city_dropdown = Dropdown(label="City", button_type="warning", menu=city_menu)
city_dropdown.on_click(update_city)


def update_genre(event):
    data = source.data
    z = pd.DataFrame(data['artist_top_genres'])
    mask = z[0].apply(lambda x: str(event.item) in x)
    view.filters = [BooleanFilter(mask)]


genres = []

for i in test_df['artist_top_genres']:
    for z in i:
        genres.append(z)

genres = list(set(genres))

genre_menu = genres
genre_dropdown = Dropdown(label="Genre", button_type="warning", menu=genre_menu)
genre_dropdown.on_click(update_genre)

p = figure(x_range=(-18000000, 20000000), y_range=(-7500000, 11500000), # range bounds supplied in web mercator coordinates
           x_axis_type='mercator', y_axis_type='mercator',
           height=700, width=1500,
           tools=tools, active_scroll='wheel_zoom',
           tooltips=tooltips)
p.add_tile(tile_provider)
p.circle(x='MercatorX', y='MercatorY',
         size=8, fill_color=color_map, line_color=color_map, fill_alpha=.3,
         legend_group='festival_flag',
         source=source, view=view)
p.axis.visible = False
p.legend.location = 'top_right'

layout = layout([text_header], [[genre_dropdown], [artist_dropdown], [country_dropdown], [city_dropdown]],
                [date_slider], [p])#, [table])

curdoc().add_root(layout)