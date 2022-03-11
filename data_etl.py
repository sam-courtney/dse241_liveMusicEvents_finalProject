import requests
import pandas as pd
import numpy as np
import datetime

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter


def read_artist_list(file_name='artist_list.txt'):
    f = open(file_name, 'r')
    string = f.read()
    f.close()
    l = list(string.split('\n'))
    return l


def read_api_key(file_name='bands_api_key.txt'):
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


def bands_api_past_pull(artist, api_key=read_api_key()):
    b_artist = bands_artist(artist)
    url = r'https://rest.bandsintown.com/artists/{}/events/?app_id={}&date=past'.format(b_artist, api_key)
    r = requests.get(url)
    event_json = r.json()
    event_df = parse_events(event_json)
    return event_df


def get_genre_api_pull(artist, analysis_level=1):
    gg_artist = getgenre_artist(artist)
    getgenre_api_url = r'https://api.getgenre.com/search?artist_name={}&analysis={}'.format(gg_artist, analysis_level)
    r = requests.get(getgenre_api_url)
    genre_json = r.json()
    top_genres = genre_json['analysis']['top_genres']
    return top_genres


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
    return events_df


def locations_data_prep(df):
    clean_df = df.copy()
    clean_df.dropna(subset=['latitude', 'longitude'], inplace=True) # remove missing data
    clean_df.reset_index(drop=True, inplace=True)
    clean_df['latitude'] = pd.to_numeric(clean_df['latitude'])
    clean_df['longitude'] = pd.to_numeric(clean_df['longitude'])
    return clean_df


def get_locations(df, latitude_column='latitude', longitude_column='longitude'):
    new_df = df.copy()
    geolocator = Nominatim(timeout=None, user_agent="rg_agent")
    reverse_geocode = RateLimiter(geolocator.reverse, min_delay_seconds=2)
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
        if index % 100 == 0: print("Rows Completed: ", index)
    return new_df


def is_festival_column(df, input_col='lineup', output_col='festival_flag', festival_size_cutoff=5):
    new_df = df.copy()
    df['lineup_size'] = df[input_col].str.len()
    df[output_col] = np.where(df['lineup_size'] > festival_size_cutoff, 'Festival', 'Concert')
    df[output_col] = df[output_col].astype(str)
    return new_df


def data_prep_complete():
    df = pd.DataFrame()
    artist_list = read_artist_list()
    bands_api_key = read_api_key()
    print("Reading in Artists")
    for artist in artist_list:
        print(artist)
        artist_df = bands_api_past_pull(artist, api_key=bands_api_key)
        artist_df['artist'] = artist
        top_genres = get_genre_api_pull(artist)
        artist_df['artist_top_genres'] = [top_genres for _ in range(len(artist_df))]  # create nested list of genres in column 'artist_top_genres'
        df = pd.concat([df, artist_df], ignore_index=True).copy()
    print("Reading in Artists Complete")
    df = is_festival_column(df).copy()
    print("Festival Events Identified")
    df['show_date'] = True  # prepare for filtering in visualization
    df['show_art'] = True # prepare for filtering in visualization
    df['datetime'] = df['datetime'].str[:10]  # trim off hours:minutes
    print("Date Cleaned Up")
    df = locations_data_prep(df).copy()
    print("Coordinates Cleaned Up")
    df = get_locations(df).copy()
    print("Locations Cleaned Up")
    return df

cleaned_dat = data_prep_complete()

cleaned_dat.to_pickle('./data/data.pkl')