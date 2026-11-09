import math

import requests
from django.conf import settings


GEOCODER_URL = 'https://geocode-maps.yandex.ru/1.x'
EARTH_RADIUS_KM = 6371


def fetch_coordinates(address):
    response = requests.get(
        GEOCODER_URL,
        params={
            'geocode': address,
            'apikey': settings.YANDEX_GEOCODER_API_KEY,
            'format': 'json',
        },
        timeout=10,
    )
    response.raise_for_status()

    found_places = response.json()['response']['GeoObjectCollection']['featureMember']
    if not found_places:
        return None

    most_relevant = found_places[0]
    lon, lat = most_relevant['GeoObject']['Point']['pos'].split(' ')
    return float(lon), float(lat)


def get_addresses_coordinates(addresses):
    from .models import Geocache

    addresses = set(addresses)
    coordinates = {}
    for place in Geocache.objects.filter(address__in=addresses):
        if place.lat is None or place.lon is None:
            coordinates[place.address] = None
        else:
            coordinates[place.address] = (place.lon, place.lat)

    for address in addresses - coordinates.keys():
        try:
            fetched_coordinates = fetch_coordinates(address)
        except requests.RequestException:
            coordinates[address] = None
            continue

        lon, lat = fetched_coordinates or (None, None)
        Geocache.objects.get_or_create(
            address=address,
            defaults={'lat': lat, 'lon': lon},
        )
        coordinates[address] = fetched_coordinates

    return coordinates


def get_coordinates(address):
    return get_addresses_coordinates([address])[address]


def calculate_distance(point1, point2):
    lon1, lat1 = map(math.radians, point1)
    lon2, lat2 = map(math.radians, point2)
    a = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    distance = 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
    return round(distance, 2)
