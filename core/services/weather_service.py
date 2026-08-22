import logging
import requests
from django.conf import settings
from django.utils import timezone
from datetime import datetime
from .location_service import LocationService
import time  # Ongeza hii

logger = logging.getLogger(__name__)

class WeatherService:
    """
    Service for weather data with multiple API support
    """
    
    # API Providers
    PROVIDER_OPENWEATHER = 'openweather'
    PROVIDER_WEATHERAPI = 'weatherapi'
    PROVIDER_TOMORROW = 'tomorrow'
    PROVIDER_ACCUWEATHER = 'accuweather'
    
    def __init__(self, provider=None):
        self.provider = provider or getattr(settings, 'WEATHER_PROVIDER', self.PROVIDER_OPENWEATHER)
        self.api_key = self._get_api_key()
        self.units = getattr(settings, 'WEATHER_UNITS', 'metric')
        self.language = getattr(settings, 'WEATHER_LANGUAGE', 'sw')
        self.location_service = LocationService()
    
    def _get_api_key(self):
        """Get API key based on provider"""
        if self.provider == self.PROVIDER_OPENWEATHER:
            return getattr(settings, 'OPENWEATHER_API_KEY', '')
        elif self.provider == self.PROVIDER_WEATHERAPI:
            return getattr(settings, 'WEATHERAPI_API_KEY', '')
        elif self.provider == self.PROVIDER_TOMORROW:
            return getattr(settings, 'TOMORROW_API_KEY', '')
        elif self.provider == self.PROVIDER_ACCUWEATHER:
            return getattr(settings, 'ACCUWEATHER_API_KEY', '')
        return ''
    
    def get_weather_by_phone(self, phone_number):
        """Get weather using phone number (GPS)"""
        lat, lon = self.location_service.get_location_by_phone(phone_number)
        if lat and lon:
            return self.get_weather_by_coordinates(lat, lon)
        return None
    
    def get_weather_by_coordinates(self, lat, lon):
        """Get weather by coordinates using selected provider with retry"""
        # Try primary provider first
        if self.provider == self.PROVIDER_OPENWEATHER:
            data = self._get_openweather_with_retry(lat, lon)
            if data:
                return data
            # If OpenWeather fails, try WeatherAPI as fallback
            logger.warning("OpenWeather failed, trying WeatherAPI as fallback...")
            return self._get_weatherapi(lat, lon)
        
        elif self.provider == self.PROVIDER_WEATHERAPI:
            return self._get_weatherapi_with_retry(lat, lon)
        
        elif self.provider == self.PROVIDER_TOMORROW:
            return self._get_tomorrow(lat, lon)
        
        elif self.provider == self.PROVIDER_ACCUWEATHER:
            return self._get_accuweather(lat, lon)
        
        return None
    
    def _get_openweather_with_retry(self, lat, lon):
        """Get weather from OpenWeather API with retry and timeout"""
        if not self.api_key:
            logger.error('OpenWeather API key not configured')
            return None
        
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {
            'lat': lat,
            'lon': lon,
            'appid': self.api_key,
            'units': self.units,
            'lang': self.language,
        }
        
        # Retry up to 3 times
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.info(f"OpenWeather attempt {attempt + 1}/{max_retries} for lat={lat}, lon={lon}")
                
                # Increase timeout for each retry
                timeout = 10 + (attempt * 5)  # 10s, 15s, 20s
                response = requests.get(url, params=params, timeout=timeout)
                response.raise_for_status()
                data = response.json()
                
                logger.info(f"OpenWeather success on attempt {attempt + 1}")
                return self._format_weather_response(data, 'OpenWeather')
                
            except requests.exceptions.Timeout:
                logger.warning(f"OpenWeather timeout on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(2)  # Wait 2 seconds before retry
                    continue
                else:
                    logger.error(f"OpenWeather timeout after {max_retries} attempts")
                    return None
                    
            except requests.exceptions.ConnectionError:
                logger.warning(f"OpenWeather connection error on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(3)
                    continue
                else:
                    return None
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"OpenWeather request error: {str(e)}")
                return None
            except Exception as e:
                logger.error(f"OpenWeather unexpected error: {str(e)}")
                return None
        
        return None
    
    def _get_weatherapi_with_retry(self, lat, lon):
        """Get weather from WeatherAPI.com with retry"""
        if not self.api_key:
            logger.error('WeatherAPI key not configured')
            return None
        
        url = "https://api.weatherapi.com/v1/current.json"
        params = {
            'key': self.api_key,
            'q': f"{lat},{lon}",
            'lang': 'sw' if self.language == 'sw' else 'en',
            'aqi': 'no',
        }
        
        max_retries = 2
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                current = data.get('current', {})
                location = data.get('location', {})
                
                return {
                    'temperature': current.get('temp_c'),
                    'feels_like': current.get('feelslike_c'),
                    'humidity': current.get('humidity'),
                    'wind_speed': current.get('wind_kph', 0) / 3.6,
                    'wind_direction': current.get('wind_degree'),
                    'clouds': current.get('cloud'),
                    'visibility': current.get('vis_km', 0) * 1000,
                    'precipitation': current.get('precip_mm'),
                    'weather_description': current.get('condition', {}).get('text'),
                    'weather_icon': current.get('condition', {}).get('icon'),
                    'city': location.get('name'),
                    'country': location.get('country'),
                    'provider': 'WeatherAPI',
                    'updated_at': timezone.now().isoformat(),
                }
                
            except requests.exceptions.Timeout:
                logger.warning(f"WeatherAPI timeout on attempt {attempt + 1}/{max_retries}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    return None
            except Exception as e:
                logger.error(f"WeatherAPI error: {str(e)}")
                return None
        
        return None
    
    def _get_openweather(self, lat, lon):
        """Get weather from OpenWeather API (legacy)"""
        return self._get_openweather_with_retry(lat, lon)
    
    def _get_weatherapi(self, lat, lon):
        """Get weather from WeatherAPI.com (legacy)"""
        return self._get_weatherapi_with_retry(lat, lon)
    
    def _get_tomorrow(self, lat, lon):
        """Get weather from Tomorrow.io API"""
        if not self.api_key:
            logger.error('Tomorrow.io API key not configured')
            return None
        
        url = f"https://api.tomorrow.io/v4/timelines"
        params = {
            'apikey': self.api_key,
            'location': f"{lat},{lon}",
            'fields': ['temperature', 'humidity', 'windSpeed', 'cloudCover', 'visibility'],
            'units': 'metric',
            'timesteps': 'current',
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            current = data.get('data', {}).get('timelines', [{}])[0].get('intervals', [{}])[0].get('values', {})
            
            return {
                'temperature': current.get('temperature'),
                'humidity': current.get('humidity'),
                'wind_speed': current.get('windSpeed'),
                'clouds': current.get('cloudCover'),
                'visibility': current.get('visibility'),
                'weather_description': self._get_condition_from_clouds(current.get('cloudCover', 0)),
                'provider': 'Tomorrow.io',
                'updated_at': timezone.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"Tomorrow.io error: {str(e)}")
            return None
    
    def _get_accuweather(self, lat, lon):
        """Get weather from AccuWeather API"""
        if not self.api_key:
            logger.error('AccuWeather API key not configured')
            return None
        
        location_url = "http://dataservice.accuweather.com/locations/v1/cities/geoposition/search"
        location_params = {
            'apikey': self.api_key,
            'q': f"{lat},{lon}",
        }
        
        try:
            location_response = requests.get(location_url, params=location_params, timeout=10)
            location_response.raise_for_status()
            location_data = location_response.json()
            location_key = location_data.get('Key')
            
            if not location_key:
                return None
            
            conditions_url = f"http://dataservice.accuweather.com/currentconditions/v1/{location_key}"
            conditions_params = {
                'apikey': self.api_key,
                'details': 'true',
            }
            
            conditions_response = requests.get(conditions_url, params=conditions_params, timeout=10)
            conditions_response.raise_for_status()
            conditions_data = conditions_response.json()
            
            if not conditions_data:
                return None
            
            current = conditions_data[0]
            
            return {
                'temperature': current.get('Temperature', {}).get('Metric', {}).get('Value'),
                'humidity': current.get('RelativeHumidity'),
                'wind_speed': current.get('Wind', {}).get('Speed', {}).get('Metric', {}).get('Value', 0) / 3.6,
                'weather_description': current.get('WeatherText'),
                'weather_icon': current.get('WeatherIcon'),
                'provider': 'AccuWeather',
                'updated_at': timezone.now().isoformat(),
            }
            
        except Exception as e:
            logger.error(f"AccuWeather error: {str(e)}")
            return None
    
    def _format_weather_response(self, data, provider):
        """Format weather data consistently"""
        return {
            'temperature': data.get('main', {}).get('temp'),
            'feels_like': data.get('main', {}).get('feels_like'),
            'temp_min': data.get('main', {}).get('temp_min'),
            'temp_max': data.get('main', {}).get('temp_max'),
            'humidity': data.get('main', {}).get('humidity'),
            'pressure': data.get('main', {}).get('pressure'),
            'wind_speed': data.get('wind', {}).get('speed'),
            'wind_direction': data.get('wind', {}).get('deg'),
            'clouds': data.get('clouds', {}).get('all'),
            'visibility': data.get('visibility'),
            'precipitation': data.get('rain', {}).get('1h', 0),
            'weather_description': data.get('weather', [{}])[0].get('description'),
            'weather_icon': data.get('weather', [{}])[0].get('icon'),
            'city': data.get('name'),
            'country': data.get('sys', {}).get('country'),
            'provider': provider,
            'updated_at': timezone.now().isoformat(),
        }
    
    def _get_condition_from_clouds(self, cloud_cover):
        """Get weather description from cloud cover"""
        if cloud_cover is None:
            return "Unknown"
        elif cloud_cover <= 20:
            return "Clear sky"
        elif cloud_cover <= 50:
            return "Partly cloudy"
        elif cloud_cover <= 80:
            return "Cloudy"
        else:
            return "Overcast"