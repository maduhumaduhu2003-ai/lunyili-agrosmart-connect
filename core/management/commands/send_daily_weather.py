"""
Daily Weather SMS Command - Sends weather updates to all farmers every morning
Run: python manage.py send_daily_weather
For automation: Add to cron job to run daily at 6:00 AM
"""
import logging
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.conf import settings
from ...models import Farmer, SMSMessage
from ...services.weather_service import WeatherService
from ...services.location_service import LocationService
from ...services.africastalking_service import AfricaTalkingService

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Send daily weather updates to all farmers via SMS'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print messages without sending SMS',
        )
        parser.add_argument(
            '--test',
            type=str,
            help='Send test SMS to a specific phone number',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        test_phone = options.get('test')
        
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write(self.style.SUCCESS('DAILY WEATHER SMS - STARTING'))
        self.stdout.write(self.style.SUCCESS('=' * 50))
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No SMS will be sent'))
        
        # Initialize services
        weather_service = WeatherService()
        location_service = LocationService()
        africa_talking = AfricaTalkingService()
        
        # Get all active farmers
        farmers = Farmer.objects.filter(is_active=True)
        
        if test_phone:
            farmers = Farmer.objects.filter(phone_number=test_phone)
            if not farmers.exists():
                self.stdout.write(self.style.ERROR(f'Farmer with phone {test_phone} not found'))
                return
        
        total_farmers = farmers.count()
        self.stdout.write(f'📊 Total farmers: {total_farmers}')
        
        if total_farmers == 0:
            self.stdout.write(self.style.WARNING('No farmers found!'))
            return
        
        sent_count = 0
        failed_count = 0
        
        for farmer in farmers:
            try:
                # Get weather for farmer's location
                weather_data = self._get_weather_for_farmer(farmer, weather_service, location_service)
                
                if weather_data:
                    # Format weather message
                    message = self._format_weather_message(weather_data, farmer)
                    
                    if not dry_run:
                        # Send SMS
                        result = africa_talking.send_sms(
                            phone_number=farmer.phone_number,
                            message=message,
                            sender_id="agrosmart"
                        )
                        
                        if result.get('status') == 'sent':
                            sent_count += 1
                            self.stdout.write(f'✅ Sent to {farmer.phone_number} - {farmer.full_name}')
                        else:
                            failed_count += 1
                            self.stdout.write(f'❌ Failed to send to {farmer.phone_number}: {result.get("message")}')
                    else:
                        # Dry run - just print
                        sent_count += 1
                        self.stdout.write(f'📱 [DRY RUN] Would send to {farmer.phone_number}: {message[:50]}...')
                else:
                    # No weather data available
                    failed_count += 1
                    self.stdout.write(f'⚠️ No weather data for {farmer.phone_number} - {farmer.full_name}')
                    
                    # Send fallback message
                    fallback_message = (
                        "Lunyili AgroSmart\n"
                        "Habari za asubuhi! Hali ya hewa kwa sasa haipatikani.\n"
                        "Tafadhali piga *566# kuangalia mwenyewe."
                    )
                    
                    if not dry_run:
                        africa_talking.send_sms(
                            phone_number=farmer.phone_number,
                            message=fallback_message,
                            sender_id="agrosmart"
                        )
                    sent_count += 1
                    
            except Exception as e:
                failed_count += 1
                self.stdout.write(self.style.ERROR(f'Error for {farmer.phone_number}: {str(e)}'))
                logger.error(f'Weather SMS error: {str(e)}')
        
        # Summary
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write(self.style.SUCCESS('SUMMARY'))
        self.stdout.write(self.style.SUCCESS('=' * 50))
        self.stdout.write(f'✅ Successfully sent: {sent_count}')
        self.stdout.write(f'❌ Failed: {failed_count}')
        self.stdout.write(f'📊 Total farmers processed: {total_farmers}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No SMS were actually sent'))

    def _get_weather_for_farmer(self, farmer, weather_service, location_service):
        """Get weather data for a farmer based on their location"""
        
        # Try using saved coordinates first
        if farmer.latitude and farmer.longitude:
            return weather_service.get_weather_by_coordinates(
                float(farmer.latitude),
                float(farmer.longitude)
            )
        
        # Try by village name
        if farmer.village:
            lat, lon = location_service.get_coordinates_by_place(farmer.village)
            if lat and lon:
                # Save coordinates for future use
                farmer.latitude = lat
                farmer.longitude = lon
                farmer.save()
                return weather_service.get_weather_by_coordinates(lat, lon)
        
        # Try by district
        if farmer.district:
            lat, lon = location_service.get_coordinates_by_place(farmer.district)
            if lat and lon:
                return weather_service.get_weather_by_coordinates(lat, lon)
        
        # Try by region
        if farmer.region:
            lat, lon = location_service.get_coordinates_by_place(farmer.region)
            if lat and lon:
                return weather_service.get_weather_by_coordinates(lat, lon)
        
        return None

    def _format_weather_message(self, weather_data, farmer):
        """Format weather message for SMS"""
        
        temp = weather_data.get('temperature', 0)
        humidity = weather_data.get('humidity', 0)
        wind = weather_data.get('wind_speed', 0)
        description = weather_data.get('weather_description', 'Anga safi')
        city = weather_data.get('city', farmer.village or farmer.district or farmer.region or 'Eneo lako')
        
        # Translate description to Swahili
        desc_sw = self._translate_weather_description(description)
        
        # Current date
        current_date = timezone.now().strftime('%d/%m/%Y')
        
        message = (
            "Lunyili AgroSmart\n"
            "HABARI ZA ASUBUHI!\n"
            f"{current_date}\n"
            "━" * 20 + "\n"
            f"📍 {city}\n"
            f"🌡️ Joto: {temp:.1f}°C\n"
            f"💧 Unyevu: {int(humidity) if humidity else 0}%\n"
            f"💨 Upepo: {wind:.1f} m/s\n"
            f"☁️ Hali: {desc_sw}\n"
            "━" * 20 + "\n"
            "Piga *566# kwa huduma zaidi."
        )
        
        return message

    def _translate_weather_description(self, description):
        """Translate weather description to Swahili"""
        if not description:
            return "Anga safi"
        
        desc_lower = description.lower()
        
        translations = {
            'clear sky': 'Anga safi',
            'few clouds': 'Mawingu machache',
            'scattered clouds': 'Mawingu yaliyotawanyika',
            'broken clouds': 'Mawingu yaliyovunjika',
            'overcast clouds': 'Mawingu mengi',
            'partly cloudy': 'Mawingu kiasi',
            'cloudy': 'Mawingu',
            'rain': 'Mvua',
            'light rain': 'Mvua kidogo',
            'moderate rain': 'Mvua ya wastani',
            'heavy rain': 'Mvua kubwa',
            'shower rain': 'Mvua ya mawe',
            'thunderstorm': 'Dhoruba ya radi',
            'snow': 'Theluji',
            'mist': 'Ukungu',
            'fog': 'Ukungu mzito',
            'haze': 'Vumbi hewani',
            'smoke': 'Moshi',
            'dust': 'Vumbi',
            'sand': 'Mchanga',
            'ash': 'Mavumbi',
            'squall': 'Dhoruba',
            'tornado': 'Kimbunga',
            'sunny': 'Jua kali',
            'fair': 'Anga safi',
            'hot': 'Joto kali',
            'cold': 'Baridi',
            'windy': 'Upepo mkali',
            'humid': 'Unyevu mkali',
            'drizzle': 'Mvua nyepesi',
            'showers': 'Mvua ya mawe',
            'storm': 'Dhoruba',
            'blizzard': 'Dhoruba ya theluji',
            'freezing': 'Baridi kali',
            'icy': 'Barafu',
            'frost': 'Baridi',
        }
        
        for key, value in translations.items():
            if key in desc_lower:
                return value
        
        return description.capitalize()