"""
Custom Django management command to seed USSD test data.
Run: python manage.py seed_ussd_data
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.db import transaction
from decimal import Decimal
import random
import uuid

User = get_user_model()

from core.models import (
    Farmer, Supplier, Buyer, ExtensionOfficer, FinancialInstitution,
    Category, Product, Order, OrderItem, BuyingRequest,
    Advice, LoanProduct, LoanApplication, MarketPrice,
    SMSMessage, InterestedFarmer, WeatherData,
    User as UserModel
)


class Command(BaseCommand):
    help = 'Seed USSD test data for development'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('🌱 Seeding USSD test data...'))
        
        try:
            with transaction.atomic():
                # 1. Create Farmers (for USSD testing)
                farmers_created = self.create_farmers()
                
                # 2. Create Buyers and Buying Requests
                buyers_created, requests_created = self.create_buyers_and_requests()
                
                # 3. Create Financial Institutions and Loan Products
                institutions_created, loans_created = self.create_financial_institutions()
                
                # 4. Create Market Prices
                prices_created = self.create_market_prices()
                
                # 5. Create Advice
                advice_created = self.create_advice()
                
                # 6. Create Products (for order testing)
                products_created = self.create_products()
                
                # 7. Create Weather Data
                weather_created = self.create_weather_data()
                
                # 8. Create Interested Farmers
                interested_created = self.create_interested_farmers(farmers_created, requests_created)
                
            self.stdout.write(self.style.SUCCESS('✅ USSD test data seeded successfully!'))
            self.stdout.write(f'\n📊 Summary:')
            self.stdout.write(f'   👨‍🌾 Farmers: {len(farmers_created)}')
            self.stdout.write(f'   🛒 Buyers: {len(buyers_created)}')
            self.stdout.write(f'   📋 Buying Requests: {len(requests_created)}')
            self.stdout.write(f'   🏦 Financial Institutions: {len(institutions_created)}')
            self.stdout.write(f'   💰 Loan Products: {len(loans_created)}')
            self.stdout.write(f'   💹 Market Prices: {len(prices_created)}')
            self.stdout.write(f'   📝 Advice: {len(advice_created)}')
            self.stdout.write(f'   📦 Products: {len(products_created)}')
            self.stdout.write(f'   🌤️ Weather Data: {len(weather_created)}')
            self.stdout.write(f'   🤝 Interested Farmers: {len(interested_created)}')
            
            self.stdout.write(self.style.SUCCESS(f'\n✨ USSD Test Phone Numbers:'))
            self.stdout.write(f'   📱 0750941683 - Farmer (Registered)')
            self.stdout.write(f'   📱 0750941684 - Farmer (Registered)')
            self.stdout.write(f'   📱 0750941685 - Farmer (Not Registered)')
            
            self.stdout.write(self.style.SUCCESS(f'\n📌 USSD Short Code: *384*20997#'))
            self.stdout.write(f'   Piga *384*20997# kwenye simu yako')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error seeding data: {str(e)}'))
            raise e

    def create_farmers(self):
        """Create farmers for USSD testing"""
        self.stdout.write('👨‍🌾 Creating farmers...')
        farmers = []
        
        # Registered farmers
        farmer_data = [
            {
                'phone': '0750941683',
                'name': 'Juma Mkulima',
                'region': 'Morogoro',
                'district': 'Mvomero',
                'ward': 'Mvomero',
                'village': 'Kibwaya',
                'crop': 'Mahindi'
            },
            {
                'phone': '0750941684',
                'name': 'Asha Mshamba',
                'region': 'Arusha',
                'district': 'Arusha',
                'ward': 'Sokon',
                'village': 'Ngaramtoni',
                'crop': 'Mpunga'
            },
            {
                'phone': '0712345678',
                'name': 'Hamisi Kilimo',
                'region': 'Mbeya',
                'district': 'Mbeya',
                'ward': 'Mbalizi',
                'village': 'Mbalizi',
                'crop': 'Maharage'
            },
            {
                'phone': '0712345679',
                'name': 'Fatuma Mazao',
                'region': 'Tanga',
                'district': 'Tanga',
                'ward': 'Muheza',
                'village': 'Korogwe',
                'crop': 'Viazi'
            },
            {
                'phone': '0712345680',
                'name': 'Salimu Shamba',
                'region': 'Iringa',
                'district': 'Iringa',
                'ward': 'Mwangosi',
                'village': 'Igawa',
                'crop': 'Nyanya'
            }
        ]
        
        for data in farmer_data:
            farmer, created = Farmer.objects.get_or_create(
                phone_number=data['phone'],
                defaults={
                    'full_name': data['name'],
                    'region': data['region'],
                    'district': data['district'],
                    'ward': data['ward'],
                    'village': data['village'],
                    'primary_crop': data['crop'],
                    'registered_via': 'USSD',
                    'is_active': True
                }
            )
            farmers.append(farmer)
            self.stdout.write(f'   ✅ Created farmer: {farmer.full_name} ({farmer.phone_number})')
        
        # Unregistered farmer
        farmer, created = Farmer.objects.get_or_create(
            phone_number='0750941685',
            defaults={
                'full_name': 'Mgeni Mkulima',
                'region': 'Dodoma',
                'district': 'Dodoma',
                'ward': 'Dodoma',
                'village': 'Dodoma',
                'primary_crop': '',
                'registered_via': 'USSD',
                'is_active': True
            }
        )
        # Remove full_name to simulate unregistered
        if created:
            farmer.full_name = ''
            farmer.save(update_fields=['full_name'])
            self.stdout.write(f'   ✅ Created unregistered farmer: {farmer.phone_number}')
        
        self.stdout.write(f'   ✅ Total farmers: {len(farmers)}')
        return farmers

    def create_buyers_and_requests(self):
        """Create buyers and buying requests"""
        self.stdout.write('🛒 Creating buyers and buying requests...')
        buyers = []
        requests = []
        
        # Create buyers
        buyer_data = [
            {
                'phone': '0712345681',
                'name': 'Bora Grains Ltd',
                'location': 'Dar es Salaam'
            },
            {
                'phone': '0712345682',
                'name': 'AgroMarket Tanzania',
                'location': 'Morogoro'
            },
            {
                'phone': '0712345683',
                'name': 'GreenHarvest Company',
                'location': 'Arusha'
            },
            {
                'phone': '0712345684',
                'name': 'Fresh Farm Buyers',
                'location': 'Mbeya'
            },
            {
                'phone': '0712345685',
                'name': 'Tanzania Grain Traders',
                'location': 'Mwanza'
            }
        ]
        
        for data in buyer_data:
            # Create user for buyer
            user, created = UserModel.objects.get_or_create(
                username=f"buyer_{data['name'].replace(' ', '_').lower()}",
                defaults={
                    'email': f"{data['name'].replace(' ', '_').lower()}@example.com",
                    'first_name': data['name'].split()[0],
                    'last_name': data['name'].split()[-1] if len(data['name'].split()) > 1 else 'Buyer',
                    'role': 'BUYER',
                    'is_verified': True,
                    'phone': data['phone']
                }
            )
            if created:
                user.set_password('Test@12345')
                user.save()
            
            buyer, created = Buyer.objects.get_or_create(
                user=user,
                defaults={
                    'company_name': data['name'],
                    'phone': data['phone'],
                    'location': data['location'],
                    'is_verified': 'VERIFIED'
                }
            )
            buyers.append(buyer)
            self.stdout.write(f'   ✅ Created buyer: {buyer.company_name}')
        
        # Create buying requests
        crops = ['Mahindi', 'Mpunga', 'Maharage', 'Viazi', 'Nyanya']
        for i, buyer in enumerate(buyers[:4]):
            crop = crops[i % len(crops)]
            request, created = BuyingRequest.objects.get_or_create(
                buyer=buyer,
                crop=crop,
                defaults={
                    'quantity_kg': random.randint(500, 5000),
                    'price_offered': Decimal(random.randint(500, 2500)),
                    'location': buyer.location,
                    'expiry_date': timezone.now().date() + timezone.timedelta(days=random.randint(15, 60)),
                    'is_open': True
                }
            )
            requests.append(request)
            self.stdout.write(f'   ✅ Created buying request: {request.crop} - {request.quantity_kg}kg')
        
        self.stdout.write(f'   ✅ Total buyers: {len(buyers)}, Total requests: {len(requests)}')
        return buyers, requests

    def create_financial_institutions(self):
        """Create financial institutions and loan products"""
        self.stdout.write('🏦 Creating financial institutions and loans...')
        institutions = []
        loans = []
        
        # Create financial user
        fin_user, created = UserModel.objects.get_or_create(
            username='demo_financial',
            defaults={
                'email': 'financial@agrosimple.com',
                'first_name': 'Demo',
                'last_name': 'Financial',
                'phone': '0712345686',
                'is_verified': True,
                'role': 'FINANCIAL'
            }
        )
        if created:
            fin_user.set_password('Test@12345')
            fin_user.save()
        
        # Create financial institution
        institution, created = FinancialInstitution.objects.get_or_create(
            user=fin_user,
            defaults={
                'institution_name': 'AgroSimple Bank',
                'institution_type': 'BANK',
                'phone': '0712345686',
                'email': 'info@agrosimplebank.com',
                'address': 'Dar es Salaam, Tanzania',
                'is_verified': True
            }
        )
        institutions.append(institution)
        self.stdout.write(f'   ✅ Created financial institution: {institution.institution_name}')
        
        # Create loan products
        loan_products = [
            ('Mkopo wa Kilimo', 12, 500000, 5000000, 12),
            ('Mkopo wa Pembejeo', 10, 200000, 3000000, 6),
            ('Mkopo wa Vifaa', 15, 1000000, 10000000, 24),
        ]
        
        for name, rate, min_amt, max_amt, duration in loan_products:
            loan, created = LoanProduct.objects.get_or_create(
                institution=institution,
                name=name,
                defaults={
                    'interest_rate': Decimal(rate),
                    'min_amount': Decimal(min_amt),
                    'max_amount': Decimal(max_amt),
                    'duration_months': duration,
                    'description': f'This {name.lower()} helps farmers grow their business.',
                    'is_active': True
                }
            )
            loans.append(loan)
            self.stdout.write(f'   ✅ Created loan product: {loan.name}')
        
        self.stdout.write(f'   ✅ Total institutions: {len(institutions)}, Total loan products: {len(loans)}')
        return institutions, loans

    def create_market_prices(self):
        """Create market prices"""
        self.stdout.write('💹 Creating market prices...')
        prices = []
        
        crops = ['Mahindi', 'Mpunga', 'Maharage', 'Viazi', 'Nyanya', 'Mtama', 'Alizeti']
        markets = ['Dar es Salaam', 'Morogoro', 'Arusha', 'Mwanza', 'Mbeya', 'Tanga']
        
        for crop in crops:
            for market in random.sample(markets, 3):
                price, created = MarketPrice.objects.get_or_create(
                    crop=crop,
                    market=market,
                    price_date=timezone.now().date() - timezone.timedelta(days=random.randint(0, 7)),
                    defaults={
                        'price': Decimal(random.randint(500, 4000)),
                        'unit': 'kg',
                        'region': market,
                        'source': 'MANUAL'
                    }
                )
                if created:
                    prices.append(price)
        
        self.stdout.write(f'   ✅ Created {len(prices)} market prices')
        return prices

    def create_advice(self):
        """Create farming advice"""
        self.stdout.write('📝 Creating farming advice...')
        advice_list = []
        
        # Create extension officer
        ext_user, created = UserModel.objects.get_or_create(
            username='demo_extension',
            defaults={
                'email': 'extension@agrosimple.com',
                'first_name': 'Demo',
                'last_name': 'Extension',
                'phone': '0712345687',
                'is_verified': True,
                'role': 'EXTENSION_OFFICER'
            }
        )
        if created:
            ext_user.set_password('Test@12345')
            ext_user.save()
        
        officer, created = ExtensionOfficer.objects.get_or_create(
            user=ext_user,
            defaults={
                'region': 'Dar es Salaam',
                'district': 'Ilala',
                'employer': 'Ministry of Agriculture',
                'position': 'Senior Extension Officer',
                'qualification': 'BACHELOR'
            }
        )
        
        advice_topics = [
            ('Jinsi ya Kuongeza Mazao', 'CROP'),
            ('Udhibiti wa Wadudu', 'PEST'),
            ('Magonjwa ya Mimea', 'DISEASE'),
            ('Umwagiliaji Bora', 'IRRIGATION'),
            ('Mbolea na Rutuba', 'FERTILIZER'),
            ('Mbinu Bora za Kilimo', 'GENERAL'),
        ]
        
        for title, category in advice_topics:
            advice, created = Advice.objects.get_or_create(
                title=title,
                author=officer,
                defaults={
                    'content': f'Ushauri muhimu kwa mkulima: {title.lower()}. Fuata hatua hizi: 1. Jitayarishe vizuri. 2. Tumia mbinu sahihi. 3. Angalia mara kwa mara. 4. Rekebisha inapohitajika. 5. Vuna kwa wakati.',
                    'category': category,
                    'crop': random.choice(['Mahindi', 'Mpunga', 'Maharage', 'General']),
                    'is_published': True,
                    'published_date': timezone.now()
                }
            )
            if created:
                advice_list.append(advice)
        
        self.stdout.write(f'   ✅ Created {len(advice_list)} advice articles')
        return advice_list

    def create_products(self):
        """Create products for order testing"""
        self.stdout.write('📦 Creating products...')
        products = []
        
        # Create supplier
        supplier_user, created = UserModel.objects.get_or_create(
            username='demo_supplier',
            defaults={
                'email': 'supplier@agrosimple.com',
                'first_name': 'Demo',
                'last_name': 'Supplier',
                'phone': '0712345688',
                'is_verified': True,
                'role': 'SUPPLIER'
            }
        )
        if created:
            supplier_user.set_password('Test@12345')
            supplier_user.save()
        
        supplier, created = Supplier.objects.get_or_create(
            user=supplier_user,
            defaults={
                'company_name': 'AgroSimple Supplies Ltd',
                'phone': '0712345688',
                'email': 'info@agrosimplesupplies.com',
                'address': 'Dar es Salaam, Tanzania',
                'location': 'Dar es Salaam',
                'is_verified': 'VERIFIED'
            }
        )
        
        # Create categories
        categories = ['Seeds', 'Fertilizers', 'Chemicals', 'Farm Tools']
        category_objs = []
        for name in categories:
            cat, _ = Category.objects.get_or_create(name=name)
            category_objs.append(cat)
        
        # Create products
        product_names = [
            ('Hybrid Maize Seed', 5000, 100, 'kg'),
            ('Premium Rice Seed', 8000, 50, 'kg'),
            ('Organic Fertilizer', 15000, 200, 'kg'),
            ('NPK Fertilizer', 25000, 150, 'kg'),
            ('Pesticide Spray', 12000, 30, 'litre'),
            ('Hand Tractor', 500000, 5, 'piece'),
            ('Water Pump', 300000, 10, 'piece'),
            ('Drip Irrigation Kit', 450000, 8, 'piece'),
            ('Animal Feed', 20000, 300, 'bag'),
            ('Vaccine Kit', 15000, 20, 'piece'),
        ]
        
        for name, price, stock, unit in product_names:
            product, created = Product.objects.get_or_create(
                name=name,
                supplier=supplier,
                defaults={
                    'category': random.choice(category_objs),
                    'description': f'High quality {name.lower()} for farmers',
                    'price': Decimal(price),
                    'stock': stock,
                    'unit': unit,
                    'is_available': True
                }
            )
            if created:
                products.append(product)
        
        self.stdout.write(f'   ✅ Created {len(products)} products')
        return products

    def create_weather_data(self):
        """Create weather data"""
        self.stdout.write('🌤️ Creating weather data...')
        weather_data = []
        
        regions = ['Dar es Salaam', 'Morogoro', 'Arusha', 'Mwanza', 'Mbeya', 'Tanga', 'Dodoma', 'Iringa']
        conditions = ['Sunny', 'Partly Cloudy', 'Cloudy', 'Rainy', 'Stormy']
        
        for region in regions:
            weather, created = WeatherData.objects.get_or_create(
                region=region,
                fetched_at=timezone.now() - timezone.timedelta(hours=random.randint(1, 6)),
                defaults={
                    'temperature': Decimal(random.randint(20, 35)),
                    'humidity': random.randint(40, 90),
                    'condition': random.choice(conditions),
                    'rain_probability': random.randint(0, 80),
                }
            )
            if created:
                weather_data.append(weather)
        
        self.stdout.write(f'   ✅ Created {len(weather_data)} weather records')
        return weather_data

    def create_interested_farmers(self, farmers, requests):
        """Create interested farmers for buying requests"""
        self.stdout.write('🤝 Creating interested farmers...')
        interested = []
        
        if farmers and requests:
            for farmer in farmers[:3]:
                for request in requests[:2]:
                    interest, created = InterestedFarmer.objects.get_or_create(
                        buying_request=request,
                        farmer=farmer,
                        defaults={
                            'is_contacted': random.choice([True, False]),
                            'notes': f"Farmer interested in selling {request.crop}"
                        }
                    )
                    if created:
                        interested.append(interest)
        
        self.stdout.write(f'   ✅ Created {len(interested)} interested farmers')
        return interested