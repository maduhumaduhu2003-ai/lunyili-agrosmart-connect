"""
USSD Engine - Complete state machine for farmer services
"""
from __future__ import annotations
import logging
from decimal import Decimal
from django.utils import timezone
from django.db.models import Q
from ..models import (
    Farmer, Product, Category, Order, OrderItem, 
    LoanApplication, SMSMessage, Supplier, User,
    MarketPrice, BuyingRequest, Advice, WeatherData,
    WeatherAlert, USSDStatus, Buyer, InterestedFarmer
)

logger = logging.getLogger(__name__)

CON = "CON"
END = "END"

BACK = "0"
HOME = "00"
CANCEL = "#"


def screen_main_menu() -> str:
    """Main menu screen"""
    return (
        "Karibu Lunyili AgroSmart Connect\n"
        "1. Jisajili\n"
        "2. Agiza Pembejeo\n"
        "3. Bei za Soko\n"
        "4. Tafuta Wanunuzi\n"
        "5. Ushauri wa Kilimo\n"
        "6. Hali ya Hewa\n"
        "7. Huduma za Kifedha\n"
        "0. Mwisho"
    )


def _error(msg: str = "Chaguo batili. Jaribu tena.") -> str:
    return msg


def _menu(title: str, options: list) -> str:
    lines = [title] + options
    return "\n".join(lines)


def _get_last_input(text: str) -> str:
    """Get the last part of USSD input (after the last *)"""
    if not text:
        return ""
    parts = text.split('*')
    return parts[-1] if parts else ""


class USSDEngine:
    """Complete USSD state machine"""
    
    def __init__(self, session, phone_number: str):
        self.session = session
        self.phone_number = phone_number
        self.state = session.state_data or {}
        self.data = self.state.setdefault("data", {})
        self.history = self.state.setdefault("_history", [])
        self.path = session.current_screen or "main"
        self.logger = logging.getLogger(__name__)

    def _goto(self, next_path: str, keep_data: bool = True):
        if self.path != next_path:
            self.history.append(self.path)
        self.path = next_path
        if not keep_data:
            self.data.clear()

    def _save(self):
        self.state["data"] = self.data
        self.state["_history"] = self.history
        from .session_service import USSDSessionService
        USSDSessionService.save_state(
            session=self.session,
            current_screen=self.path,
            state_data=self.state,
            last_input=self.state.get("_last_input", "")
        )

    def _end(self):
        from .session_service import USSDSessionService
        USSDSessionService.end_session(session=self.session)

    def _send_sms(self, phone_number: str, message: str):
        """Send SMS"""
        try:
            SMSMessage.objects.create(
                recipient=phone_number,
                message=message,
                status='QUEUED'
            )
            self.logger.info(f"SMS queued for {phone_number}")
        except Exception as e:
            self.logger.error(f"Error sending SMS: {str(e)}")

    def step(self, user_input: str):
        """Process user input and return response"""
        user_input = (user_input or "").strip()
        self.state["_last_input"] = user_input
        
        # Get the last part of the input
        last_input = _get_last_input(user_input)

        try:
            # Handle special commands
            if self.path == "main" and user_input == "":
                self._goto("main", keep_data=False)
                self._save()
                return CON, screen_main_menu()

            if last_input == CANCEL:
                self._end()
                return END, "Umeghairi kikao. Piga *566# wakati wowote."

            if last_input == HOME:
                self._goto("main", keep_data=False)
                self._save()
                return CON, screen_main_menu()

            if last_input == BACK and self.history:
                self.path = self.history.pop()
                self._save()
                return CON, self._render_current_screen()

            handler = getattr(self, f"_handle_{self.path}", None)
            if handler is None:
                self._goto("main", keep_data=False)
                self._save()
                return CON, screen_main_menu()

            # Pass both full text and last input
            status, screen = handler(user_input, last_input)
            if status == END:
                self._end()
            else:
                self._save()
            return status, screen
            
        except Exception as e:
            self.logger.error(f"Error in step: {str(e)}")
            self._end()
            return END, "Samahani, kuna tatizo. Jaribu tena baadaye."

    def _render_current_screen(self) -> str:
        renderer = getattr(self, f"_render_{self.path}", None)
        if renderer:
            return renderer()
        return screen_main_menu()

    # ======================================================================
    # MAIN MENU
    # ======================================================================
    def _handle_main(self, full_text: str, last_input: str):
        routes = {
            "1": self._start_register,
            "2": self._start_order,
            "3": self._start_prices,
            "4": self._start_buyers,
            "5": self._start_advice,
            "6": self._start_weather,
            "7": self._start_financial,
            "0": self._exit,
        }
        starter = routes.get(last_input)
        if starter is None:
            return CON, _error() + "\n\n" + screen_main_menu()
        return starter()

    def _exit(self):
        self._end()
        return END, "Asante kwa kutumia Lunyili AgroSmart. Piga *566# wakati wowote."

    # ======================================================================
    # 1. REGISTER
    # ======================================================================
    def _start_register(self):
        if Farmer.objects.filter(phone_number=self.phone_number).exists():
            farmer = Farmer.objects.get(phone_number=self.phone_number)
            self._end()
            return END, (
                f"Tayari umesajiliwa!\n"
                f"Jina: {farmer.full_name}\n"
                f"Eneo: {farmer.region}, {farmer.district}\n"
                f"Zao: {farmer.primary_crop or 'Halijawekwa'}\n"
                f"Piga *566# tena kutumia huduma."
            )
        self._goto("register_name")
        return CON, "Jisajili\nAndika jina lako kamili:"

    def _handle_register_name(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika jina lako kamili (herufi 2 au zaidi):"
        self.data["full_name"] = last_input.strip()
        self._goto("register_gender")
        return CON, "Jinsia:\n1. Mwanaume\n2. Mwanamke"

    def _handle_register_gender(self, full_text: str, last_input: str):
        if last_input == "1":
            self.data["gender"] = "M"
            self._goto("register_region")
            return CON, "Andika mkoa wako:"
        elif last_input == "2":
            self.data["gender"] = "F"
            self._goto("register_region")
            return CON, "Andika mkoa wako:"
        else:
            return CON, _error() + "\nChagua 1 kwa Mwanaume au 2 kwa Mwanamke:"

    def _handle_register_region(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika mkoa wako:"
        self.data["region"] = last_input.strip()
        self._goto("register_district")
        return CON, "Andika wilaya:"

    def _handle_register_district(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika wilaya:"
        self.data["district"] = last_input.strip()
        self._goto("register_ward")
        return CON, "Andika kata:"

    def _handle_register_ward(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika kata:"
        self.data["ward"] = last_input.strip()
        self._goto("register_village")
        return CON, "Andika kijiji:"

    def _handle_register_village(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika kijiji:"
        self.data["village"] = last_input.strip()
        self._goto("register_crop")
        return CON, "Andika zao lako kuu (mfano: Mahindi):"

    def _handle_register_crop(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika zao lako kuu:"
        
        try:
            farmer = Farmer.objects.create(
                full_name=self.data.get("full_name", ""),
                phone_number=self.phone_number,
                region=self.data.get("region", ""),
                district=self.data.get("district", ""),
                ward=self.data.get("ward", ""),
                village=self.data.get("village", ""),
                gender=self.data.get("gender", ""),
                primary_crop=last_input.strip(),
                registered_via="USSD"
            )
            
            self._send_sms(
                farmer.phone_number,
                f"Karibu {farmer.full_name}! Umesajiliwa Lunyili AgroSmart. "
                f"Piga *566# kupata huduma za kilimo."
            )
            
            self._end()
            return END, (
                f"Umefanikiwa kujisajili {farmer.full_name}!\n"
                f"Piga *566# wakati wowote kupata huduma."
            )
            
        except Exception as e:
            self.logger.error(f"Registration error: {str(e)}")
            self._end()
            return END, "Samahani, imeshindikana kujisajili. Jaribu tena."

    # ======================================================================
    # 2. ORDER
    # ======================================================================
    def _start_order(self):
        if not Farmer.objects.filter(phone_number=self.phone_number).exists():
            return END, "Jisajili kwanza (chagua 1 kwenye menu kuu)."
        
        categories = list(Category.objects.filter(is_active=True))
        if not categories:
            self._end()
            return END, "Samahani, hakuna bidhaa zilizopo kwa sasa."
        
        self.data["category_ids"] = [str(c.id) for c in categories]
        self._goto("order_category")
        lines = [f"{i+1}. {c.name}" for i, c in enumerate(categories[:9])]
        return CON, _menu("Agiza Pembejeo\nChagua kundi:", lines)

    def _handle_order_category(self, full_text: str, last_input: str):
        try:
            idx = int(last_input) - 1
            category_id = self.data["category_ids"][idx]
        except:
            return CON, _error() + "\nChagua namba sahihi:"
        
        products = list(Product.objects.filter(
            category_id=category_id, 
            is_available=True, 
            stock__gt=0
        )[:9])
        
        if not products:
            self._end()
            return END, "Hakuna bidhaa zenye stock katika kundi hili."
        
        self.data["product_ids"] = [str(p.id) for p in products]
        self._goto("order_product")
        lines = [f"{i+1}. {p.name} - TSh {int(p.price):,}/{p.unit}" for i, p in enumerate(products)]
        return CON, _menu("Chagua bidhaa:", lines)

    def _handle_order_product(self, full_text: str, last_input: str):
        try:
            idx = int(last_input) - 1
            product_id = self.data["product_ids"][idx]
            product = Product.objects.get(id=product_id)
        except:
            return CON, _error()
        
        self.data["product_id"] = str(product.id)
        self.data["product_name"] = product.name
        self.data["product_unit"] = product.unit
        self.data["product_stock"] = product.stock
        self._goto("order_quantity")
        return CON, f"{product.name}\nStock: {product.stock} {product.unit}\nWeka kiasi:"

    def _handle_order_quantity(self, full_text: str, last_input: str):
        try:
            qty = int(last_input)
            if qty <= 0:
                raise ValueError
        except:
            return CON, "Weka namba sahihi (mfano: 10):"
        
        if qty > self.data.get("product_stock", 0):
            return CON, f"Stock ni {self.data.get('product_stock', 0)} {self.data.get('product_unit', '')} tu.\nWeka kiasi kingine:"
        
        self.data["quantity"] = qty
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        
        if farmer and farmer.village:
            self.data["_farmer_village"] = farmer.village
            self.data["_farmer_district"] = farmer.district
            self._goto("order_address_choice")
            return CON, (
                f"Tuma kwa anwani yako?\n{farmer.village}, {farmer.district}\n"
                f"1. Ndiyo\n2. Hapana"
            )
        
        self._goto("order_village")
        return CON, "Andika kijiji cha kufikisha:"

    def _handle_order_address_choice(self, full_text: str, last_input: str):
        if last_input == "1":
            self.data["village"] = self.data.get("_farmer_village", "")
            self.data["district"] = self.data.get("_farmer_district", "")
            return self._show_order_confirm()
        if last_input == "2":
            self._goto("order_village")
            return CON, "Andika kijiji cha kufikisha:"
        return CON, _error() + "\nChagua 1 au 2:"

    def _handle_order_village(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika kijiji:"
        self.data["village"] = last_input.strip()
        self._goto("order_district")
        return CON, "Andika wilaya:"

    def _handle_order_district(self, full_text: str, last_input: str):
        if not last_input or len(last_input.strip()) < 2:
            return CON, "Andika wilaya:"
        self.data["district"] = last_input.strip()
        return self._show_order_confirm()

    def _show_order_confirm(self):
        d = self.data
        self._goto("order_confirm")
        return CON, (
            f"Thibitisha Agizo\n"
            f"Bidhaa: {d['product_name']}\n"
            f"Kiasi: {d['quantity']} {d.get('product_unit', '')}\n"
            f"Mahali: {d.get('village', '')}, {d.get('district', '')}\n"
            f"1. Thibitisha\n2. Ghairi"
        )

    def _handle_order_confirm(self, full_text: str, last_input: str):
        if last_input != "1":
            self._end()
            return END, "Agizo limeghairiwa."

        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza."

        d = self.data
        product = Product.objects.get(id=d["product_id"])
        supplier = product.supplier
        
        try:
            total_amount = product.price * d["quantity"]
            
            order = Order.objects.create(
                farmer=farmer,
                supplier=supplier,
                total_amount=total_amount,
                delivery_address=f"{d.get('village', '')}, {d.get('district', '')}",
                status='PENDING'
            )
            
            OrderItem.objects.create(
                order=order,
                product=product,
                quantity=d["quantity"],
                price=product.price
            )
            
            product.stock -= d["quantity"]
            product.save(update_fields=['stock'])
            
            self._send_sms(
                farmer.phone_number,
                f"Agizo lako #{order.reference} limepokelewa. "
                f"{product.name} x {d['quantity']} = TSh {int(total_amount):,}"
            )
            
        except Exception as exc:
            self.logger.error(f"Order error: {str(exc)}")
            self._end()
            return END, f"Agizo halikufanikiwa. Jaribu tena."

        self._end()
        return END, (
            f"Agizo limepokelewa!\n"
            f"{product.name} x {d['quantity']}\n"
            f"Kumbukumbu: #{order.reference}\n"
            f"Jumla: TSh {int(total_amount):,}\n"
            f"Litafikishwa {d.get('village', '')} ndani ya siku 1-2."
        )

    # ======================================================================
    # 3. CROP PRICES - FROM DATABASE
    # ======================================================================
    def _start_prices(self):
        """Show market prices from database"""
        # Get latest market prices
        latest_date = MarketPrice.objects.order_by('-price_date').values_list('price_date', flat=True).first()
        
        if latest_date:
            prices = list(MarketPrice.objects.filter(price_date=latest_date).order_by('crop')[:10])
        else:
            prices = list(MarketPrice.objects.all().order_by('-price_date', 'crop')[:10])
        
        if not prices:
            self._end()
            return END, (
                "Samahani, hakuna taarifa za bei kwa sasa.\n"
                "Piga *566# tena baadaye."
            )
        
        lines = []
        for p in prices:
            market = p.market or "Soko"
            unit = p.unit or "kg"
            lines.append(f"{p.crop}: TSh {int(p.price):,}/{unit} ({market})")
        
        self._end()
        return END, (
            "Bei za Soko:\n" + 
            "\n".join(lines[:10]) + 
            f"\n\nTarehe: {latest_date or timezone.now().date()}\n"
            "Piga *566# tena."
        )

    # ======================================================================
    # 4. FIND BUYERS - WITH REGION AND CROP SELECTION (IMPROVED)
    # ======================================================================
    def _start_buyers(self):
        """Start buyer search - select region first"""
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza (chagua 1 kwenye menu kuu)."
        
        # Get unique regions from BuyingRequest (where buyers have posted requests)
        regions = list(BuyingRequest.objects.filter(
            is_open=True,
            expiry_date__gte=timezone.now().date()
        ).exclude(
            location__isnull=True
        ).exclude(
            location=''
        ).values_list('location', flat=True).distinct()[:9])
        
        # If no regions from BuyingRequest, get from Buyer model
        if not regions:
            regions = list(Buyer.objects.filter(
                is_verified='VERIFIED'
            ).exclude(
                location__isnull=True
            ).exclude(
                location=''
            ).values_list('location', flat=True).distinct()[:9])
        
        # If still no regions, use sample regions for demo
        if not regions:
            regions = [
                "Dar es Salaam",
                "Morogoro", 
                "Arusha",
                "Mwanza",
                "Mbeya",
                "Tanga",
                "Dodoma",
                "Iringa",
                "Kilimanjaro"
            ]
        
        self.data["regions"] = regions
        self._goto("buyer_region")
        
        lines = [f"{i+1}. {r}" for i, r in enumerate(regions[:9])]
        return CON, _menu("Chagua mkoa uliopo:", lines)

    def _handle_buyer_region(self, full_text: str, last_input: str):
        """Handle region selection"""
        try:
            idx = int(last_input) - 1
            region = self.data["regions"][idx]
        except (ValueError, IndexError, KeyError):
            return CON, _error() + "\nChagua namba sahihi ya mkoa:"
        
        self.data["selected_region"] = region
        
        # Get crops available in this region from BuyingRequest
        crops = list(BuyingRequest.objects.filter(
            location__icontains=region,
            is_open=True,
            expiry_date__gte=timezone.now().date()
        ).values_list('crop', flat=True).distinct()[:9])
        
        # If no crops from BuyingRequest, get from farmers in this region
        if not crops:
            farmers = Farmer.objects.filter(
                region__icontains=region,
                primary_crop__isnull=False
            ).exclude(primary_crop='')
            crops = list(farmers.values_list('primary_crop', flat=True).distinct()[:9])
        
        # If still no crops, get from MarketPrice
        if not crops:
            crops = list(MarketPrice.objects.values_list('crop', flat=True).distinct()[:9])
        
        # If still no crops, use sample crops
        if not crops:
            crops = ["Mahindi", "Mpunga", "Maharage", "Viazi", "Nyanya", "Mtama", "Alizeti", "Kunde", "Njugu"]
        
        self.data["crops"] = crops
        self._goto("buyer_crop")
        
        lines = [f"{i+1}. {c}" for i, c in enumerate(crops[:9])]
        return CON, _menu(f"Mkoa: {region}\nChagua zao:", lines)

    def _handle_buyer_crop(self, full_text: str, last_input: str):
        """Handle crop selection and show buyers"""
        try:
            idx = int(last_input) - 1
            crop = self.data["crops"][idx]
        except (ValueError, IndexError, KeyError):
            return CON, _error() + "\nChagua namba sahihi ya zao:"
        
        region = self.data.get("selected_region", "")
        self.data["selected_crop"] = crop
        
        # Find buyers looking for this crop
        buyers = BuyingRequest.objects.filter(
            crop__icontains=crop,
            is_open=True,
            expiry_date__gte=timezone.now().date()
        ).order_by('-created_at')[:5]
        
        # If no real buyers, check if we have a buyer with this crop
        if not buyers:
            # Try to find any buyer who might be interested
            buyer = Buyer.objects.filter(is_verified='VERIFIED').first()
            if buyer:
                # Create a sample buying request display
                self.data["buyer_ids"] = ['sample']
                self.data["selected_crop"] = crop
                self._goto("buyer_select")
                
                lines = [
                    f"1. {buyer.company_name or 'Mnunuzi'}\n"
                    f"   {crop}: 1000kg @ TSh 1,500/kg\n"
                    f"   Mahali: {region}"
                ]
                return CON, _menu(f"Wanunuzi wa {crop} katika {region}:", lines)
            else:
                self._end()
                return END, (
                    f"Samahani, hakuna wanunuzi wa {crop} katika mkoa wa {region} kwa sasa.\n"
                    f"Jaribu tena baadaye."
                )
        
        # Real buyers found
        self.data["buyer_ids"] = [str(b.id) for b in buyers]
        self.data["selected_crop"] = crop
        self._goto("buyer_select")
        
        lines = []
        for i, b in enumerate(buyers, 1):
            buyer_name = b.buyer.company_name if b.buyer and b.buyer.company_name else "Mnunuzi"
            lines.append(
                f"{i}. {buyer_name}\n"
                f"   {b.crop}: {b.quantity_kg}kg @ TSh {int(b.price_offered):,}\n"
                f"   Mahali: {b.location}"
            )
        
        return CON, _menu(f"Wanunuzi wa {crop} katika {region}:", lines)

    def _handle_buyer_select(self, full_text: str, last_input: str):
        """Handle buyer selection and send SMS to both parties"""
        try:
            idx = int(last_input) - 1
            buyer_id = self.data["buyer_ids"][idx]
        except (ValueError, IndexError, KeyError):
            return CON, _error() + "\nChagua namba sahihi ya mnunuzi:"
        
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        
        if not farmer:
            self._end()
            return END, "Tafadhali jisajili kwanza (chagua 1)."
        
        crop = self.data.get("selected_crop", "")
        region = self.data.get("selected_region", "")
        
        # Handle sample buyer (demo mode)
        if buyer_id == 'sample':
            buyer = Buyer.objects.filter(is_verified='VERIFIED').first()
            buyer_name = buyer.company_name if buyer and buyer.company_name else "Mnunuzi"
            buyer_phone = buyer.phone if buyer else "0712345678"
            
            # Send SMS to Farmer
            farmer_message = (
                f"Umefanikiwa kuonyesha nia ya kuuza {crop}!\n"
                f"Mnunuzi: {buyer_name}\n"
                f"Simu: {buyer_phone}\n"
                f"Bei: TSh 1,500/kg\n"
                f"Watawasiliana nawe hivi karibuni."
            )
            self._send_sms(farmer.phone_number, farmer_message)
            
            # Send SMS to Buyer
            if buyer_phone:
                self._send_sms(
                    buyer_phone,
                    f"Mkulima ameonyesha nia ya kuuza {crop}!\n"
                    f"Jina: {farmer.full_name}\n"
                    f"Simu: {farmer.phone_number}\n"
                    f"Eneo: {farmer.region}, {farmer.district}\n"
                    f"Wasiliana naye moja kwa moja."
                )
            
            # Record interest if real buyer exists
            if buyer:
                try:
                    buying_request = BuyingRequest.objects.filter(buyer=buyer).first()
                    if buying_request:
                        InterestedFarmer.objects.get_or_create(
                            buying_request=buying_request,
                            farmer=farmer
                        )
                except:
                    pass
            
            self._end()
            return END, (
                f"Taarifa zimewasilishwa!\n"
                f"✓ SMS imetumwa kwako na kwa mnunuzi.\n"
                f"✓ Mnunuzi: {buyer_name}\n"
                f"✓ Simu: {buyer_phone}\n\n"
                f"Wasiliana naye moja kwa moja kupanga mauzo.\n"
                f"Piga *566# tena."
            )
        
        # Handle real buyer
        try:
            buying_request = BuyingRequest.objects.get(id=buyer_id)
        except BuyingRequest.DoesNotExist:
            return CON, _error() + "\nMnunuzi hapatikani. Jaribu tena."
        
        # Record interest
        InterestedFarmer.objects.get_or_create(
            buying_request=buying_request,
            farmer=farmer
        )
        
        buyer_name = buying_request.buyer.company_name if buying_request.buyer and buying_request.buyer.company_name else "Mnunuzi"
        buyer_phone = buying_request.buyer.phone if buying_request.buyer else "0712345678"
        
        # Send SMS to Farmer
        farmer_message = (
            f"Umefanikiwa kuonyesha nia ya kuuza {crop}!\n"
            f"Mnunuzi: {buyer_name}\n"
            f"Simu: {buyer_phone}\n"
            f"Bei: TSh {int(buying_request.price_offered):,}/kg\n"
            f"Watawasiliana nawe hivi karibuni."
        )
        self._send_sms(farmer.phone_number, farmer_message)
        
        # Send SMS to Buyer
        if buyer_phone:
            buyer_message = (
                f"Mkulima ameonyesha nia ya kuuza {crop}!\n"
                f"Jina: {farmer.full_name}\n"
                f"Simu: {farmer.phone_number}\n"
                f"Eneo: {farmer.region}, {farmer.district}\n"
                f"Wasiliana naye moja kwa moja."
            )
            self._send_sms(buyer_phone, buyer_message)
        
        self._end()
        return END, (
            f"Taarifa zimewasilishwa!\n"
            f"✓ SMS imetumwa kwako na kwa mnunuzi.\n"
            f"✓ Mnunuzi: {buyer_name}\n"
            f"✓ Simu: {buyer_phone}\n\n"
            f"Wasiliana naye moja kwa moja kupanga mauzo.\n"
            f"Piga *566# tena."
        )

    def _render_buyer_region(self) -> str:
        """Re-render region selection screen"""
        lines = [f"{i+1}. {r}" for i, r in enumerate(self.data.get("regions", []))]
        return _menu("Chagua mkoa uliopo:", lines) if lines else screen_main_menu()

    def _render_buyer_crop(self) -> str:
        """Re-render crop selection screen"""
        region = self.data.get("selected_region", "")
        lines = [f"{i+1}. {c}" for i, c in enumerate(self.data.get("crops", []))]
        return _menu(f"Mkoa: {region}\nChagua zao:", lines) if lines else screen_main_menu()

    # ======================================================================
    # 5. FARMING ADVICE
    # ======================================================================
    def _start_advice(self):
        self._goto("advice")
        return CON, _menu("Ushauri wa Kilimo", [
            "1. Ushauri wa Jumla",
            "2. Udhibiti wa Wadudu",
            "3. Udhibiti wa Magonjwa",
            "4. Mbolea na Rutuba",
            "5. Rudi Menu"
        ])

    def _handle_advice(self, full_text: str, last_input: str):
        # Try to get advice from database
        category_map = {
            '1': 'GENERAL',
            '2': 'PEST',
            '3': 'DISEASE',
            '4': 'FERTILIZER',
        }
        
        if last_input == '5':
            self._goto('main')
            return CON, screen_main_menu()
        
        if last_input in category_map:
            advice = Advice.objects.filter(
                category=category_map[last_input],
                is_published=True
            ).order_by('-published_date').first()
            
            if advice:
                self._end()
                return END, f"{advice.title}\n{advice.content[:300]}\n\nPiga *566# tena."
        
        # Default advice if no database records
        default_msgs = {
            '1': "Ushauri wa Jumla:\n- Panda wakati wa mvua\n- Tumia mbegu bora\n- Palilia mara kwa mara\n- Vuna kwa wakati",
            '2': "Udhibiti wa Wadudu:\n- Tumia dawa asilia\n- Panda mazao mchanganyiko\n- Angalia shamba mara kwa mara",
            '3': "Udhibiti wa Magonjwa:\n- Tumia mbegu zilizothibitishwa\n- Weka umbali sahihi wa kupanda\n- Ondoa mimea mgonjwa",
            '4': "Mbolea na Rutuba:\n- Tumia mbolea ya samadi\n- Weka mazao mbadala\n- Jaribu udongo mara kwa mara",
        }
        
        if last_input in default_msgs:
            self._end()
            return END, f"{default_msgs[last_input]}\n\nPiga *566# tena."
        
        return CON, _error()

    # ======================================================================
    # 6. WEATHER
    # ======================================================================
    def _start_weather(self):
        self._end()
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        region = farmer.region if farmer else "Tanzania"
        
        # Try to get weather from database
        weather = WeatherData.objects.filter(region__icontains=region).order_by('-fetched_at').first()
        
        if weather:
            return END, (
                f"Hali ya Hewa - {region}\n"
                f"Joto: {weather.temperature}°C\n"
                f"Unyevu: {weather.humidity}%\n"
                f"Hali: {weather.condition}\n"
                f"Piga *566# tena."
            )
        
        return END, (
            f"Hali ya Hewa - {region}\n"
            f"Joto: 28°C\n"
            f"Unyevu: 65%\n"
            f"Mvua inatarajiwa wiki ijayo.\n"
            f"Piga *566# tena."
        )

    # ======================================================================
    # 7. FINANCIAL SERVICES
    # ======================================================================
    def _start_financial(self):
        self._goto("financial")
        return CON, _menu("Huduma za Kifedha", [
            "1. Taarifa za Mikopo",
            "2. Omba Mkopo",
            "3. Rudi Menu"
        ])

    def _handle_financial(self, full_text: str, last_input: str):
        if last_input == '1':
            self._end()
            # Get loan products from database
            products = LoanProduct.objects.filter(is_active=True)[:5]
            if products:
                lines = []
                for p in products:
                    lines.append(f"{p.name}: Riba {p.interest_rate}%")
                    lines.append(f"  TSh {int(p.min_amount):,} - {int(p.max_amount):,}")
                    lines.append(f"  Muda: {p.duration_months} miezi")
                    lines.append("")
                return END, (
                    "Mikopo Inapatikana:\n" + 
                    "\n".join(lines) + 
                    "\nTembelea ofisi yetu kwa maelezo zaidi."
                )
            return END, "Mikopo: SACCOS 12%, Benki 15%.\nTembelea ofisi yetu kwa maelezo."
        elif last_input == '2':
            return self._start_loan_apply()
        elif last_input == '3':
            self._goto('main')
            return CON, screen_main_menu()
        else:
            return CON, _error()

    def _start_loan_apply(self):
        farmer = Farmer.objects.filter(phone_number=self.phone_number).first()
        if not farmer:
            self._end()
            return END, "Jisajili kwanza (chagua 1)."
        
        self._goto("loan_amount")
        return CON, "Omba Mkopo\nWeka kiasi unachotaka (TSh):"

    def _handle_loan_amount(self, full_text: str, last_input: str):
        try:
            amount = Decimal(last_input)
            if amount <= 0:
                raise ValueError
        except:
            return CON, "Andika kiasi sahihi (mfano: 1000000):"
        
        farmer = Farmer.objects.get(phone_number=self.phone_number)
        
        try:
            LoanApplication.objects.create(
                farmer=farmer,
                amount=amount,
                status='PENDING',
                purpose="USSD Application"
            )
            
            self._send_sms(
                farmer.phone_number,
                f"Ombi lako la mkopo TSh {int(amount):,} limepokelewa."
            )
            
        except Exception as e:
            self.logger.error(f"Loan error: {str(e)}")
            self._end()
            return END, "Samahani, ombi halikufanikiwa. Jaribu tena."

        self._end()
        return END, (
            f"Ombi lako la mkopo TSh {int(amount):,} limepokelewa!\n"
            f"Tutakujulisha baada ya siku 2-3.\n"
            f"Piga *566# tena."
        )