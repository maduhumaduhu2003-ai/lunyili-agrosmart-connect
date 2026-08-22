import logging
import time

import requests
from django.conf import settings
from django.utils import timezone

from ..models import Farmer

logger = logging.getLogger(__name__)


class LocationService:
    """
    Finds a farmer's location using the following priority:

    1. Saved latitude/longitude
    2. Village
    3. District
    4. Region
    5. OpenStreetMap/Nominatim search

    Coordinates found from a place are saved on the farmer.
    """

    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

    def get_location_by_phone(self, phone_number):
        """
        Return:
            (latitude, longitude)

        or:
            (None, None)
        """

        farmer = (
            Farmer.objects
            .filter(phone_number=phone_number)
            .first()
        )

        if not farmer:
            logger.warning(
                "Farmer not found for phone: %s",
                phone_number
            )
            return None, None

        # -------------------------------------------------
        # 1. Already have coordinates
        # -------------------------------------------------
        if farmer.latitude is not None and farmer.longitude is not None:
            return (
                float(farmer.latitude),
                float(farmer.longitude)
            )

        # -------------------------------------------------
        # 2. Try village
        # -------------------------------------------------
        if farmer.village:
            coordinates = self.get_coordinates_by_place(
                farmer.village,
                district=farmer.district,
                region=farmer.region,
            )

            if coordinates:
                self.update_farmer_location(
                    phone_number,
                    *coordinates
                )
                return coordinates

        # -------------------------------------------------
        # 3. Try district
        # -------------------------------------------------
        if farmer.district:
            coordinates = self.get_coordinates_by_place(
                farmer.district,
                region=farmer.region,
            )

            if coordinates:
                self.update_farmer_location(
                    phone_number,
                    *coordinates
                )
                return coordinates

        # -------------------------------------------------
        # 4. Try region
        # -------------------------------------------------
        if farmer.region:
            coordinates = self.get_coordinates_by_place(
                farmer.region
            )

            if coordinates:
                self.update_farmer_location(
                    phone_number,
                    *coordinates
                )
                return coordinates

        logger.warning(
            "Could not determine location for %s",
            phone_number
        )

        return None, None

    def get_coordinates_by_place(
        self,
        place_name,
        district=None,
        region=None
    ):
        """
        Search for a Tanzanian place using OpenStreetMap.

        Examples:
            Dakawa
            Morogoro
            Kilombero
            Dakawa, Morogoro
        """

        if not place_name:
            return None

        place_name = str(place_name).strip()

        queries = []

        # Most specific
        if district and region:
            queries.append(
                f"{place_name}, {district}, {region}, Tanzania"
            )

        if district:
            queries.append(
                f"{place_name}, {district}, Tanzania"
            )

        if region:
            queries.append(
                f"{place_name}, {region}, Tanzania"
            )

        # General Tanzania search
        queries.append(
            f"{place_name}, Tanzania"
        )

        for query in queries:

            coordinates = self._nominatim_search(query)

            if coordinates:
                logger.info(
                    "Location found: %s -> %s",
                    query,
                    coordinates
                )
                return coordinates

        return None

    def _nominatim_search(self, query):
        """
        Search OpenStreetMap Nominatim.
        """

        try:
            response = requests.get(
                self.NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                    "countrycodes": "tz",
                },
                headers={
                    "User-Agent": "LunyiliAgroSmartConnect/1.0"
                },
                timeout=5,
            )

            response.raise_for_status()

            results = response.json()

            if not results:
                return None

            result = results[0]

            latitude = float(result["lat"])
            longitude = float(result["lon"])

            return latitude, longitude

        except requests.RequestException as exc:
            logger.warning(
                "Location API request failed for '%s': %s",
                query,
                exc
            )

        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "Invalid location response for '%s': %s",
                query,
                exc
            )

        except Exception:
            logger.exception(
                "Unexpected location error for '%s'",
                query
            )

        return None

    def get_place_by_coordinates(self, lat, lon):
        """
        Reverse geocoding:
        coordinates -> human readable place.
        """

        try:
            response = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={
                    "lat": lat,
                    "lon": lon,
                    "format": "json",
                    "zoom": 10,
                },
                headers={
                    "User-Agent": "LunyiliAgroSmartConnect/1.0"
                },
                timeout=5,
            )

            response.raise_for_status()

            data = response.json()

            address = data.get("address", {})

            return (
                address.get("village")
                or address.get("town")
                or address.get("city")
                or address.get("municipality")
                or address.get("county")
                or address.get("state")
            )

        except Exception as exc:
            logger.warning(
                "Reverse geocoding failed: %s",
                exc
            )
            return None

    def update_farmer_location(
        self,
        phone_number,
        lat,
        lon
    ):
        """
        Save discovered coordinates on farmer.
        """

        try:
            farmer = (
                Farmer.objects
                .filter(phone_number=phone_number)
                .first()
            )

            if not farmer:
                return False

            farmer.latitude = lat
            farmer.longitude = lon
            farmer.last_location_update = timezone.now()

            farmer.save(
                update_fields=[
                    "latitude",
                    "longitude",
                    "last_location_update",
                ]
            )

            logger.info(
                "Updated location for %s: %s, %s",
                phone_number,
                lat,
                lon
            )

            return True

        except Exception:
            logger.exception(
                "Failed to update location for %s",
                phone_number
            )
            return False