import requests
import pandas as pd
import numpy as np
import datetime

from bokeh.plotting import figure, output_file, curdoc
from bokeh.tile_providers import get_provider, OSM
from bokeh.models import ColumnDataSource, CDSView, BooleanFilter, CustomJS
from bokeh.layouts import layout
from bokeh.models import DateRangeSlider, Div, Dropdown
from pyproj import Transformer


def read_api_key(file_name):
    f = open(file_name, 'r')
    key = f.read()
    f.close()
    return key


def getgenre_artist(string):
    ## lower case
    ## replace " " with "_"
    artist = string.replace(' ', '_').lower()
    return artist


def bands_artist(string):
    ## url-ify artist names
    ## replaces " " with "%20"
    artist = string.replace(' ', r'%20')
    return artist


def parse_events(event_json):
    ### defined to help parse the JSON of individual events returned by Bandintown API ###
    ### this will pull out the keys and values for the event object ###
    ### the end result is a list that can be entered as a row to a Pandas dataframe ###

    events_data = []
    num_of_events = len(
        event_json)  # event json has an entry for each event ## each event has lots of other nested data

    keys_of_interest = [
        'datetime'  # date-time of the event
        , 'title'  # name of the event  ## may need to create a condition to check if exists and set to null if missing
        , 'lineup'
        # list of strings containing names of artists  ## may leave as a nested list in data frame to avoid sparseness  ### list may be ordered in terms of headliners (??)
        , 'festival_start_date'
        # date festival starts  ### may be a useful indicator that the artist is performing at a festival-event, need to test this for reliability
        , 'festival_end_date'
        # date festival ends, will differ from start date on multi-day events (may not exist on single day events)
        , 'venue'  # this is a nested dictionary, will need to tease this one out to flatten the data
    ]

    venue_keys_of_interest = [
        'city'  # city name, string
        , 'region'  # state-level, string
        , 'country'  # country name, string
        , 'latitude'  # coordinate data, float
        , 'longitude'  # coordinate data, float
        , 'location'  # arbitrary string describing geolocation  ## consider not including
        , 'name'
        # arbitrary string describing venue name, could be misleading since some venues are at locations, but given festival name  ## consider not including
    ]

    for i in range(num_of_events):
        event = event_json[i]
        event_list = []

        for key in keys_of_interest:
            value = event.get(key)
            if key == 'venue':
                for venue_key in venue_keys_of_interest:
                    venue_value = value.get(venue_key)
                    event_list.append(venue_value)
            else:
                event_list.append(value)

        events_data.append(event_list)

    cols = keys_of_interest[:-1] + venue_keys_of_interest
    events_df = pd.DataFrame(events_data, columns=cols)
    events_df['artist'] = artist
    return events_df


def get_locations(df, latitude_column='latitude', longitude_column='longitude'):
    new_df = df.copy()
    geolocator = Nominatim(user_agent="rg_agent")
    reverse_geocode = RateLimiter(geolocator.reverse, min_delay_seconds=1)
    for index, row in new_df.iterrows():
        lookup = reverse_geocode((row[latitude_column], row[longitude_column]), language='en')
        try:
            new_df.loc[index, 'city'] = lookup.raw['address']['city']
        except:
            continue
        try:
            new_df.loc[index, 'region'] = lookup.raw['address']['state']
        except:
            continue
        try:
            new_df.loc[index, 'country'] = lookup.raw['address']['country']
        except:
            continue

    return new_df

artist = 'Tame Impala'

bands_key = read_api_key('bands_api_key.txt') ## shhhh... its a secret

analysis_level = 1
gg_artist = getgenre_artist(artist)
bands_artist = bands_artist(artist)
getgenre_api_url = r'https://api.getgenre.com/search?artist_name={}&analysis={}'.format(gg_artist, analysis_level)
bands_api_url = r'https://rest.bandsintown.com/artists/{}/events/?app_id={}'.format(bands_artist, bands_key)
bands_api_url_past = r'https://rest.bandsintown.com/artists/{}/events/?app_id={}&date=past'.format(bands_artist, bands_key)

# data extract
r = requests.get(bands_api_url_past)
event_json = r.json()

test_df = parse_events(event_json)
r_gg = requests.get(getgenre_api_url)

genre_json = r_gg.json()
top_gg = genre_json['analysis']['top_genres']

# feature extraction
test_df['artist'] = artist
test_df['artist_topgenres'] = [top_gg for _ in range(len(test_df))]

test_df['lineup_size'] = test_df['lineup'].str.len()
test_df['festival_flag'] = np.where(test_df['lineup'].str.len() > 5, 'Festival', 'Concert')
test_df['festival_flag'] = test_df['festival_flag'].astype(str)

test_df['show_date'] = True
test_df['show_art'] = True

# data cleanup
test_df = test_df[(test_df['latitude'].notna()) & (test_df['longitude'].notna())]
test_df['latitude'] = pd.to_numeric(test_df['latitude'])
test_df['longitude'] = pd.to_numeric((test_df['longitude']))

test_df['datetime'] = test_df['datetime'].str[:10]

# data transformation
in_crs = 4326   # coordinates provided in EPSG:4326 format
out_crs = 3857   # coordinates output in EPSG 3857 (Web Mercator) format

transformer = Transformer.from_crs(in_crs, out_crs, always_xy=True)

lons, lats = [], []
for lon, lat in list(zip(test_df['longitude'], test_df['latitude'])):
    x, y = transformer.transform(lon,lat)
    lons.append(x)
    lats.append(y)

test_df['MercatorX'] = lons
test_df['MercatorY'] = lats



# visualization
#output_file("tile.html")
#output_notebook()

tile_provider = get_provider(OSM)
tools = ['pan', 'zoom_in', 'zoom_out', 'wheel_zoom', 'box_zoom', 'lasso_select', 'tap', 'hover', 'reset', 'save']

tooltips = [
    ("Date", '@datetime'),
    ('Location: ', '@city, @region'),
    ('Country: ', '@country'),
    ('Event Type: ', '@festival_flag'),
    ('Lineup: ', '@lineup'),
]

source = ColumnDataSource(test_df)
source2 = ColumnDataSource(test_df)

#full_table = DataTable(source=source)


view = CDSView(source=source)

#filtered_table = DataTable(source=source, view=data_view)

text_header = Div(text='<H1>Live Music Across Time<H1>', width=300, height=60)

def ts_extract(xl_timestamp):
    d = datetime.datetime.fromtimestamp(int(xl_timestamp/ 1000)).strftime('%Y-%m-%d')
    return d

# https://stackoverflow.com/questions/64458556/how-to-define-python-bokeh-rangeslider-on-change-callback-function-to-alter-inde
# https://medium.com/y-data-stories/python-and-bokeh-part-ii-d81024c9578f

def update(attr, old, new):

    start = ts_extract(new[0])
    end = ts_extract(new[1])
    data=source.data
    mask = np.logical_and(data['datetime'] > start, data['datetime'] < end)
    #source.data['show_date'] = mask
    #print(data['index'].shape)
    #source.trigger('change')

    view.filters=[BooleanFilter(mask)]
    #p.view = view

date_slider = DateRangeSlider(
    title=" Adjust Date range",
    start=min(test_df['datetime']),
    end=max(test_df['datetime']),
    step=1,
    value=(
        min(test_df['datetime']), max(test_df['datetime'])
    )
)

date_slider.on_change('value_throttled', update)
# range bounds supplied in web mercator coordinates

def update_artist(event):

    data=source.data
    mask = data['artist'] == str(event.item)
    view.filters=[BooleanFilter(mask)]

artist_menu = [artist]
artist_dropdown = Dropdown(label="Artist", button_type="warning", menu=artist_menu)
artist_dropdown.on_click(update_artist)

def update_country(event):

    data=source.data
    mask = data['country'] == str(event.item)
    view.filters=[BooleanFilter(mask)]

country_menu = list(set(test_df['country']))
country_dropdown = Dropdown(label="Country", button_type="warning", menu=country_menu)
country_dropdown.on_click(update_country)

def update_city(event):

    data=source.data
    mask = data['city'] == str(event.item)
    view.filters=[BooleanFilter(mask)]

city_menu = list(set(test_df['city']))
city_dropdown = Dropdown(label="City", button_type="warning", menu=city_menu)
city_dropdown.on_click(update_city)

def update_genre(event):

    data=source.data
    z = pd.DataFrame(data['artist_topgenres'])
    mask = z[0].apply(lambda x: str(event.item) in x)
    view.filters=[BooleanFilter(mask)]

genres = []

for i in test_df['artist_topgenres']:
    for z in i:
        genres.append(z)
        
genres = list(set(genres))

genre_menu = genres
genre_dropdown = Dropdown(label="Genre", button_type="warning", menu=genre_menu)
genre_dropdown.on_click(update_genre)

p = figure(x_range=(-18000000, 20000000), y_range=(-7500000, 11500000),
           x_axis_type='mercator', y_axis_type='mercator',
           height=700, width=1500,
           tools=tools, tooltips=tooltips, active_scroll='wheel_zoom')
p.add_tile(tile_provider)
p.circle(x='MercatorX', y='MercatorY', size=6, fill_color='dodgerblue', line_color='dodgerblue', fill_alpha=.3, source=source, view=view)
p.axis.visible = False

layout = layout([text_header], [[genre_dropdown], [artist_dropdown], [country_dropdown], [city_dropdown]], [date_slider], [p])#, [full_table], [filtered_table])

curdoc().add_root(layout)